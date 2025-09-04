from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from neuralmonitor.core.analyzer import StreamAnalyzer
from neuralmonitor.core.commands import (
    EndSessionCommand,
    IngestFrameCommand,
    ObserveHealthCommand,
    StartSessionCommand,
)
from neuralmonitor.core.lifecycle import recorder_status_from_signals
from neuralmonitor.core.models import (
    Alert,
    AlertSeverity,
    AlertType,
    MetricSnapshot,
    MonitoringSession,
    Recorder,
    RecorderHealth,
    RecorderStatus,
    SessionDiagnostics,
    SessionStatus,
    TelemetryEvent,
    utcnow,
)
from neuralmonitor.core.parsers import PythonPacketParser
from neuralmonitor.core.ports import PacketParser, TelemetryRepository
from neuralmonitor.core.protocol import PacketParseError
from neuralmonitor.core.publishing import EventPublisher, RetryingPublisher, noop_publish

logger = logging.getLogger(__name__)


class SessionNotRunningError(RuntimeError):
    """Raised when a caller tries to mutate a closed monitoring session."""


class IngestService:
    """Application service for recorder-session commands.

    The service is the write boundary for telemetry and health data. It keeps
    parsing, stream analysis, persistence, lifecycle state, and live publishing
    coordinated without letting API or CLI code duplicate those rules.
    """

    def __init__(
        self,
        repo: TelemetryRepository,
        publisher: EventPublisher | None = None,
        parser: PacketParser | None = None,
        publish_retry_attempts: int = 3,
        publish_retry_base_delay_ms: int = 25,
    ) -> None:
        self.repo = repo
        self.publisher = RetryingPublisher(
            publisher or noop_publish,
            attempts=publish_retry_attempts,
            base_delay_ms=publish_retry_base_delay_ms,
        )
        self.parser = parser or PythonPacketParser()
        self._analyzers: dict[str, StreamAnalyzer] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def start_session(
        self,
        recorder: Recorder,
        operator: str = "local",
        mode: str = "live",
        notes: str = "",
    ) -> MonitoringSession:
        return await self.execute_start_session(
            StartSessionCommand(recorder=recorder, operator=operator, mode=mode, notes=notes)
        )

    async def execute_start_session(self, command: StartSessionCommand) -> MonitoringSession:
        recorder = command.recorder
        recorder.status = RecorderStatus.CONNECTED
        self.repo.upsert_recorder(recorder)
        session = MonitoringSession(
            recorder_id=recorder.id,
            operator=command.operator,
            mode=command.mode,
            notes=command.notes,
        )
        self.repo.upsert_session(session)
        self._analyzers[session.id] = StreamAnalyzer(session.id, recorder.id)
        self._locks[session.id] = asyncio.Lock()
        await self.publisher("session.started", session.model_dump(mode="json"))
        logger.info("started monitoring session", extra={"session_id": session.id, "recorder_id": recorder.id})
        return session

    async def end_session(self, session_id: str, status: SessionStatus = SessionStatus.ENDED) -> MonitoringSession:
        return await self.execute_end_session(EndSessionCommand(session_id=session_id, status=status))

    async def execute_end_session(self, command: EndSessionCommand) -> MonitoringSession:
        session = self._require_session(command.session_id)
        if session.status != SessionStatus.RUNNING:
            return session
        session.status = command.status
        session.ended_at = utcnow()
        self.repo.upsert_session(session)
        recorder = self.repo.get_recorder(session.recorder_id)
        if recorder:
            recorder.status = RecorderStatus.OFFLINE if command.status == SessionStatus.ENDED else RecorderStatus.ERROR
            self.repo.upsert_recorder(recorder)
        await self.publisher("session.ended", session.model_dump(mode="json"))
        logger.info("ended monitoring session", extra={"session_id": session.id, "status": command.status.value})
        return session

    async def ingest_frame(self, session_id: str, frame: bytes, source: str = "live") -> tuple[MetricSnapshot, list[Alert]]:
        return await self.execute_ingest_frame(
            IngestFrameCommand(session_id=session_id, frame=frame, source=source)
        )

    async def execute_ingest_frame(self, command: IngestFrameCommand) -> tuple[MetricSnapshot, list[Alert]]:
        session = self._require_session(command.session_id)
        self._ensure_running(session)
        analyzer = self._analyzer_for(session)
        async with self._locks.setdefault(session.id, asyncio.Lock()):
            try:
                parsed = self.parser.parse(command.frame)
            except PacketParseError as exc:
                analyzer.metrics.observe_malformed()
                alert = analyzer.alerts.open_or_update(
                    session.id,
                    session.recorder_id,
                    alert_type=AlertType.MALFORMED_PACKET,
                    severity=AlertSeverity.WARNING,
                    message=f"Malformed telemetry frame: {exc}",
                    evidence={"error": str(exc), "frame_size": len(command.frame)},
                )
                self.repo.upsert_alert(alert)
                await self.publisher("alert.changed", alert.model_dump(mode="json"))
                raise

            event = TelemetryEvent(
                session_id=session.id,
                recorder_id=session.recorder_id,
                sequence_number=parsed.sequence_number,
                device_timestamp_us=parsed.device_timestamp_us,
                ingest_timestamp=datetime.now(timezone.utc),
                channel_count=parsed.channel_count,
                payload_size=len(parsed.payload),
                checksum_valid=parsed.checksum_valid,
                source=command.source,
            )
            self.repo.append_event(event)
            snapshot, alerts = analyzer.observe_event(event)
            self.repo.append_metric(snapshot)
            for alert in alerts:
                self.repo.upsert_alert(alert)
            recorder = self._refresh_recorder_status(session)

        await self.publisher("telemetry.event", event.model_dump(mode="json"))
        await self.publisher("metric.snapshot", snapshot.model_dump(mode="json"))
        await self.publisher("recorder.status", recorder.model_dump(mode="json"))
        for alert in alerts:
            await self.publisher("alert.changed", alert.model_dump(mode="json"))
        return snapshot, alerts

    async def observe_health(self, health: RecorderHealth) -> list[Alert]:
        return await self.execute_observe_health(ObserveHealthCommand(health=health))

    async def execute_observe_health(self, command: ObserveHealthCommand) -> list[Alert]:
        health = command.health
        session = self._require_session(health.session_id)
        self._ensure_running(session)
        analyzer = self._analyzer_for(session)
        async with self._locks.setdefault(session.id, asyncio.Lock()):
            alerts = analyzer.observe_health(health)
            self.repo.append_health(health)
            for alert in alerts:
                self.repo.upsert_alert(alert)
            recorder = self._refresh_recorder_status(session)

        await self.publisher("recorder.health", health.model_dump(mode="json"))
        await self.publisher("recorder.status", recorder.model_dump(mode="json"))
        for alert in alerts:
            await self.publisher("alert.changed", alert.model_dump(mode="json"))
        return alerts

    async def check_silence(self, session_id: str) -> Alert | None:
        session = self._require_session(session_id)
        if session.status != SessionStatus.RUNNING:
            return None
        analyzer = self._analyzer_for(session)
        alert = analyzer.check_silence()
        if alert:
            self.repo.upsert_alert(alert)
            recorder = self._refresh_recorder_status(session)
            await self.publisher("recorder.status", recorder.model_dump(mode="json"))
            await self.publisher("alert.changed", alert.model_dump(mode="json"))
        return alert

    def diagnostics(self, session_id: str) -> SessionDiagnostics:
        return self.repo.diagnostics(session_id)

    def _require_session(self, session_id: str) -> MonitoringSession:
        session = self.repo.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session {session_id}")
        return session

    @staticmethod
    def _ensure_running(session: MonitoringSession) -> None:
        if session.status != SessionStatus.RUNNING:
            raise SessionNotRunningError(f"session {session.id} is {session.status.value}")

    def _analyzer_for(self, session: MonitoringSession) -> StreamAnalyzer:
        analyzer = self._analyzers.get(session.id)
        if analyzer is None:
            analyzer = StreamAnalyzer(session.id, session.recorder_id)
            events = self.repo.events_for_session(session.id)
            for event in events:
                analyzer.observe_event(event)
            self._analyzers[session.id] = analyzer
        return analyzer

    def _refresh_recorder_status(self, session: MonitoringSession) -> Recorder:
        recorder = self.repo.get_recorder(session.recorder_id)
        if recorder is None:
            recorder = Recorder(id=session.recorder_id, name=session.recorder_id)
        recorder.status = recorder_status_from_signals(
            self.repo.alerts_for_session(session.id),
            latest_health=self.repo.latest_health(session.id),
        )
        self.repo.upsert_recorder(recorder)
        return recorder
