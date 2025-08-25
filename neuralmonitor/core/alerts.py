from __future__ import annotations

from datetime import datetime, timezone

from neuralmonitor.core.models import Alert, AlertSeverity, AlertStatus, AlertType


class AlertEngine:
    def __init__(self) -> None:
        self._open: dict[tuple[str, str, AlertType], Alert] = {}

    def open_or_update(
        self,
        session_id: str,
        recorder_id: str,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        evidence: dict,
    ) -> Alert:
        key = (session_id, recorder_id, alert_type)
        now = datetime.now(timezone.utc)
        existing = self._open.get(key)
        if existing and existing.status == AlertStatus.OPEN:
            existing.severity = severity
            existing.message = message
            existing.updated_at = now
            existing.evidence = evidence
            return existing

        alert = Alert(
            session_id=session_id,
            recorder_id=recorder_id,
            severity=severity,
            type=alert_type,
            message=message,
            evidence=evidence,
        )
        self._open[key] = alert
        return alert

    def resolve(self, session_id: str, recorder_id: str, alert_type: AlertType) -> Alert | None:
        key = (session_id, recorder_id, alert_type)
        alert = self._open.get(key)
        if not alert or alert.status == AlertStatus.RESOLVED:
            return None
        now = datetime.now(timezone.utc)
        alert.status = AlertStatus.RESOLVED
        alert.updated_at = now
        alert.resolved_at = now
        return alert

    def open_alerts(self) -> list[Alert]:
        return [alert for alert in self._open.values() if alert.status == AlertStatus.OPEN]

