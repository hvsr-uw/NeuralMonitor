from __future__ import annotations

from neuralmonitor.core.models import (
    Alert,
    AlertStatus,
    MetricSnapshot,
    MonitoringSession,
    Recorder,
    RecorderHealth,
    RecorderStatus,
    SessionDiagnostics,
    TelemetryEvent,
    utcnow,
)


class InMemoryTelemetryRepository:
    def __init__(self) -> None:
        self.recorders: dict[str, Recorder] = {}
        self.sessions: dict[str, MonitoringSession] = {}
        self.events: list[TelemetryEvent] = []
        self.metrics: list[MetricSnapshot] = []
        self.health: list[RecorderHealth] = []
        self.alerts: dict[str, Alert] = {}

    def upsert_recorder(self, recorder: Recorder) -> None:
        self.recorders[recorder.id] = recorder.model_copy(deep=True)

    def get_recorder(self, recorder_id: str) -> Recorder | None:
        recorder = self.recorders.get(recorder_id)
        return recorder.model_copy(deep=True) if recorder else None

    def list_recorders(self) -> list[Recorder]:
        return [recorder.model_copy(deep=True) for recorder in self.recorders.values()]

    def upsert_session(self, session: MonitoringSession) -> None:
        self.sessions[session.id] = session.model_copy(deep=True)

    def get_session(self, session_id: str) -> MonitoringSession | None:
        session = self.sessions.get(session_id)
        return session.model_copy(deep=True) if session else None

    def list_sessions(self) -> list[MonitoringSession]:
        return [session.model_copy(deep=True) for session in self.sessions.values()]

    def append_event(self, event: TelemetryEvent) -> None:
        self.events.append(event.model_copy(deep=True))

    def append_metric(self, snapshot: MetricSnapshot) -> None:
        self.metrics.append(snapshot.model_copy(deep=True))

    def append_health(self, health: RecorderHealth) -> None:
        self.health.append(health.model_copy(deep=True))

    def upsert_alert(self, alert: Alert) -> None:
        self.alerts[alert.id] = alert.model_copy(deep=True)

    def latest_metrics(self, session_id: str, limit: int = 200) -> list[MetricSnapshot]:
        return [
            metric.model_copy(deep=True)
            for metric in self.metrics
            if metric.session_id == session_id
        ][-limit:]

    def latest_metric(self, session_id: str) -> MetricSnapshot | None:
        metrics = self.latest_metrics(session_id, limit=1)
        return metrics[0] if metrics else None

    def metric_count(self, session_id: str) -> int:
        return len([metric for metric in self.metrics if metric.session_id == session_id])

    def alerts_for_session(self, session_id: str) -> list[Alert]:
        return [
            alert.model_copy(deep=True)
            for alert in self.alerts.values()
            if alert.session_id == session_id
        ]

    def open_alerts_for_session(self, session_id: str) -> list[Alert]:
        return [
            alert
            for alert in self.alerts_for_session(session_id)
            if alert.status == AlertStatus.OPEN
        ]

    def events_for_session(self, session_id: str, limit: int = 1000) -> list[TelemetryEvent]:
        return [
            event.model_copy(deep=True)
            for event in self.events
            if event.session_id == session_id
        ][-limit:]

    def event_count(self, session_id: str) -> int:
        return len([event for event in self.events if event.session_id == session_id])

    def last_event(self, session_id: str) -> TelemetryEvent | None:
        events = self.events_for_session(session_id, limit=1)
        return events[0] if events else None

    def latest_health(self, session_id: str) -> RecorderHealth | None:
        matching = [health for health in self.health if health.session_id == session_id]
        return matching[-1].model_copy(deep=True) if matching else None

    def diagnostics(self, session_id: str) -> SessionDiagnostics:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session {session_id}")
        recorder = self.get_recorder(session.recorder_id)
        alerts = self.alerts_for_session(session_id)
        last_event = self.last_event(session_id)
        return SessionDiagnostics(
            session_id=session.id,
            recorder_id=session.recorder_id,
            session_status=session.status,
            recorder_status=recorder.status if recorder else RecorderStatus.OFFLINE,
            event_count=self.event_count(session_id),
            metric_count=self.metric_count(session_id),
            alert_count=len(alerts),
            open_alert_count=sum(1 for alert in alerts if alert.status == AlertStatus.OPEN),
            latest_metric=self.latest_metric(session_id),
            latest_health=self.latest_health(session_id),
            last_event_at=last_event.ingest_timestamp if last_event else None,
            generated_at=utcnow(),
        )

