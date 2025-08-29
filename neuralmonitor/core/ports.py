from __future__ import annotations

from typing import Protocol

from neuralmonitor.core.models import (
    Alert,
    MetricSnapshot,
    MonitoringSession,
    Recorder,
    RecorderHealth,
    SessionDiagnostics,
    TelemetryEvent,
)
from neuralmonitor.core.protocol import ParsedFrame


class PacketParser(Protocol):
    def parse(self, frame: bytes) -> ParsedFrame:
        ...


class TelemetryRepository(Protocol):
    def upsert_recorder(self, recorder: Recorder) -> None:
        ...

    def get_recorder(self, recorder_id: str) -> Recorder | None:
        ...

    def list_recorders(self) -> list[Recorder]:
        ...

    def upsert_session(self, session: MonitoringSession) -> None:
        ...

    def get_session(self, session_id: str) -> MonitoringSession | None:
        ...

    def list_sessions(self) -> list[MonitoringSession]:
        ...

    def append_event(self, event: TelemetryEvent) -> None:
        ...

    def append_metric(self, snapshot: MetricSnapshot) -> None:
        ...

    def append_health(self, health: RecorderHealth) -> None:
        ...

    def upsert_alert(self, alert: Alert) -> None:
        ...

    def alerts_for_session(self, session_id: str) -> list[Alert]:
        ...

    def events_for_session(self, session_id: str, limit: int = 1000) -> list[TelemetryEvent]:
        ...

    def latest_health(self, session_id: str) -> RecorderHealth | None:
        ...

    def diagnostics(self, session_id: str) -> SessionDiagnostics:
        ...
