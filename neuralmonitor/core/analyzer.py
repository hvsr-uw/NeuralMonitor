from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from logging import getLogger

from neuralmonitor.core.alerts import AlertEngine
from neuralmonitor.core.metrics import RollingMetrics
from neuralmonitor.core.models import (
    Alert,
    AlertSeverity,
    AlertType,
    MetricSnapshot,
    RecorderHealth,
    TelemetryEvent,
)

logger = getLogger(__name__)


@dataclass(frozen=True)
class Thresholds:
    latency_p95_warning_ms: float = 150.0
    latency_p95_critical_ms: float = 500.0
    silence_warning_ms: float = 3000.0
    buffer_pressure_warning: int = 5000
    temperature_critical_c: float = 42.0
    low_battery_percent: float = 15.0


@dataclass
class StreamState:
    last_sequence: int | None = None
    last_event_at: datetime | None = None


class StreamAnalyzer:
    def __init__(
        self,
        session_id: str,
        recorder_id: str,
        thresholds: Thresholds | None = None,
    ) -> None:
        self.session_id = session_id
        self.recorder_id = recorder_id
        self.thresholds = thresholds or Thresholds()
        self.metrics = RollingMetrics(session_id=session_id, recorder_id=recorder_id)
        self.alerts = AlertEngine()
        self.state = StreamState()

    def observe_event(self, event: TelemetryEvent) -> tuple[MetricSnapshot, list[Alert]]:
        emitted: list[Alert] = []
        if not event.checksum_valid:
            self.metrics.observe_malformed()
            emitted.append(
                self.alerts.open_or_update(
                    event.session_id,
                    event.recorder_id,
                    AlertType.CHECKSUM_FAILURE,
                    AlertSeverity.WARNING,
                    f"Invalid checksum at sequence {event.sequence_number}.",
                    {"sequence_number": event.sequence_number},
                )
            )

        previous = self.state.last_sequence
        if previous is not None:
            expected = previous + 1
            if event.sequence_number == previous:
                emitted.append(
                    self.alerts.open_or_update(
                        event.session_id,
                        event.recorder_id,
                        AlertType.DUPLICATE_EVENT,
                        AlertSeverity.WARNING,
                        f"Duplicate sequence {event.sequence_number} observed.",
                        {"sequence_number": event.sequence_number},
                    )
                )
            elif event.sequence_number < previous:
                emitted.append(
                    self.alerts.open_or_update(
                        event.session_id,
                        event.recorder_id,
                        AlertType.OUT_OF_ORDER_EVENT,
                        AlertSeverity.WARNING,
                        f"Out-of-order sequence {event.sequence_number}; last was {previous}.",
                        {"sequence_number": event.sequence_number, "last_sequence": previous},
                    )
                )
            elif event.sequence_number > expected:
                missing = event.sequence_number - expected
                self.metrics.observe_drops(missing)
                severity = AlertSeverity.CRITICAL if missing >= 10 else AlertSeverity.WARNING
                emitted.append(
                    self.alerts.open_or_update(
                        event.session_id,
                        event.recorder_id,
                        AlertType.DROPPED_EVENT,
                        severity,
                        f"Detected {missing} missing telemetry event(s).",
                        {
                            "expected_sequence": expected,
                            "observed_sequence": event.sequence_number,
                            "missing_count": missing,
                        },
                    )
                )
            elif event.sequence_number == expected:
                resolved = self.alerts.resolve(
                    event.session_id, event.recorder_id, AlertType.DROPPED_EVENT
                )
                if resolved:
                    emitted.append(resolved)

        self.metrics.observe_event(event)
        self.state.last_sequence = max(event.sequence_number, previous or event.sequence_number)
        self.state.last_event_at = event.ingest_timestamp
        snapshot = self.metrics.snapshot()
        emitted.extend(self._evaluate_metrics(snapshot))
        return snapshot, emitted

    def observe_health(self, health: RecorderHealth) -> list[Alert]:
        emitted: list[Alert] = []
        self.metrics.heartbeat(health.timestamp)
        if health.buffer_depth >= self.thresholds.buffer_pressure_warning:
            emitted.append(
                self.alerts.open_or_update(
                    health.session_id,
                    health.recorder_id,
                    AlertType.BUFFER_PRESSURE,
                    AlertSeverity.WARNING,
                    "Recorder buffer depth is approaching capacity.",
                    {"buffer_depth": health.buffer_depth},
                )
            )
        else:
            resolved = self.alerts.resolve(health.session_id, health.recorder_id, AlertType.BUFFER_PRESSURE)
            if resolved:
                emitted.append(resolved)

        if health.temperature_c >= self.thresholds.temperature_critical_c:
            emitted.append(
                self.alerts.open_or_update(
                    health.session_id,
                    health.recorder_id,
                    AlertType.DEVICE_OVERHEAT,
                    AlertSeverity.CRITICAL,
                    "Recorder temperature exceeded critical threshold.",
                    {"temperature_c": health.temperature_c},
                )
            )
        if health.battery_percent <= self.thresholds.low_battery_percent:
            emitted.append(
                self.alerts.open_or_update(
                    health.session_id,
                    health.recorder_id,
                    AlertType.LOW_BATTERY,
                    AlertSeverity.WARNING,
                    "Recorder battery is low.",
                    {"battery_percent": health.battery_percent},
                )
            )
        return emitted

    def check_silence(self, now: datetime | None = None) -> Alert | None:
        if self.state.last_event_at is None:
            return None
        now = now or datetime.now(timezone.utc)
        silence_ms = (now - self.state.last_event_at).total_seconds() * 1000
        if silence_ms < self.thresholds.silence_warning_ms:
            return self.alerts.resolve(self.session_id, self.recorder_id, AlertType.RECORDER_SILENCE)
        return self.alerts.open_or_update(
            self.session_id,
            self.recorder_id,
            AlertType.RECORDER_SILENCE,
            AlertSeverity.CRITICAL,
            "Recorder stream has stopped producing telemetry.",
            {"silence_ms": silence_ms},
        )

    def _evaluate_metrics(self, snapshot: MetricSnapshot) -> list[Alert]:
        emitted: list[Alert] = []
        if snapshot.latency_p95_ms >= self.thresholds.latency_p95_critical_ms:
            emitted.append(
                self.alerts.open_or_update(
                    snapshot.session_id,
                    snapshot.recorder_id,
                    AlertType.LATENCY_SPIKE,
                    AlertSeverity.CRITICAL,
                    "p95 telemetry latency is critically high.",
                    {"latency_p95_ms": snapshot.latency_p95_ms},
                )
            )
        elif snapshot.latency_p95_ms >= self.thresholds.latency_p95_warning_ms:
            emitted.append(
                self.alerts.open_or_update(
                    snapshot.session_id,
                    snapshot.recorder_id,
                    AlertType.LATENCY_SPIKE,
                    AlertSeverity.WARNING,
                    "p95 telemetry latency is elevated.",
                    {"latency_p95_ms": snapshot.latency_p95_ms},
                )
            )
        else:
            resolved = self.alerts.resolve(snapshot.session_id, snapshot.recorder_id, AlertType.LATENCY_SPIKE)
            if resolved:
                emitted.append(resolved)
        return emitted

