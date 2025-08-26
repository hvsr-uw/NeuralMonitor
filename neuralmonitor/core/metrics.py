from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median

from neuralmonitor.core.models import MetricSnapshot, TelemetryEvent


def percentile(values: list[float], rank: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * rank)))
    return ordered[index]


@dataclass
class RollingMetrics:
    session_id: str
    recorder_id: str
    max_events: int = 5000
    events: deque[TelemetryEvent] = field(default_factory=deque)
    malformed_packets: int = 0
    dropped_events: int = 0
    last_heartbeat_at: datetime | None = None

    def observe_event(self, event: TelemetryEvent) -> None:
        self.events.append(event)
        while len(self.events) > self.max_events:
            self.events.popleft()

    def observe_malformed(self) -> None:
        self.malformed_packets += 1

    def observe_drops(self, count: int) -> None:
        self.dropped_events += max(0, count)

    def heartbeat(self, timestamp: datetime | None = None) -> None:
        self.last_heartbeat_at = timestamp or datetime.now(timezone.utc)

    def snapshot(self) -> MetricSnapshot:
        now = datetime.now(timezone.utc)
        if not self.events:
            return MetricSnapshot(
                session_id=self.session_id,
                recorder_id=self.recorder_id,
                window_start=now,
                window_end=now,
                event_rate_hz=0.0,
                dropped_event_count=self.dropped_events,
                malformed_packet_count=self.malformed_packets,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                latency_p99_ms=0.0,
                jitter_ms=0.0,
                heartbeat_age_ms=self._heartbeat_age_ms(now),
            )

        start = self.events[0].ingest_timestamp
        end = self.events[-1].ingest_timestamp
        duration = max(0.001, (end - start).total_seconds())
        latencies = [event.latency_ms for event in self.events]
        diffs = [
            abs(latencies[index] - latencies[index - 1])
            for index in range(1, len(latencies))
        ]
        return MetricSnapshot(
            session_id=self.session_id,
            recorder_id=self.recorder_id,
            window_start=start,
            window_end=end,
            event_rate_hz=len(self.events) / duration,
            dropped_event_count=self.dropped_events,
            malformed_packet_count=self.malformed_packets,
            latency_p50_ms=median(latencies),
            latency_p95_ms=percentile(latencies, 0.95),
            latency_p99_ms=percentile(latencies, 0.99),
            jitter_ms=median(diffs) if diffs else 0.0,
            heartbeat_age_ms=self._heartbeat_age_ms(now),
        )

    def _heartbeat_age_ms(self, now: datetime) -> float | None:
        if self.last_heartbeat_at is None:
            return None
        return max(0.0, (now - self.last_heartbeat_at).total_seconds() * 1000)

