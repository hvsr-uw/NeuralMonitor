from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from neuralmonitor.core.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    RecorderHealth,
    RecorderStatus,
)


DEGRADING_ALERTS = {
    AlertType.DROPPED_EVENT,
    AlertType.LATENCY_SPIKE,
    AlertType.CHECKSUM_FAILURE,
    AlertType.BUFFER_PRESSURE,
    AlertType.LOW_BATTERY,
}


def recorder_status_from_signals(
    alerts: Iterable[Alert],
    latest_health: RecorderHealth | None = None,
    heartbeat_timeout_ms: float = 5_000.0,
    now: datetime | None = None,
) -> RecorderStatus:
    """Collapse stream, alert, and health evidence into the operator-facing recorder state."""
    now = now or datetime.now(timezone.utc)
    open_alerts = [alert for alert in alerts if alert.status == AlertStatus.OPEN]

    if any(alert.type == AlertType.RECORDER_SILENCE for alert in open_alerts):
        return RecorderStatus.SILENT
    if any(alert.severity == AlertSeverity.CRITICAL for alert in open_alerts):
        return RecorderStatus.ERROR
    if latest_health is not None:
        heartbeat_age_ms = (now - latest_health.timestamp).total_seconds() * 1000
        if heartbeat_age_ms > heartbeat_timeout_ms:
            return RecorderStatus.SILENT
    if any(alert.type in DEGRADING_ALERTS for alert in open_alerts):
        return RecorderStatus.DEGRADED
    return RecorderStatus.CONNECTED

