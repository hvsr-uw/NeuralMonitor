from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RecorderStatus(str, Enum):
    REGISTERED = "registered"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    SILENT = "silent"
    OFFLINE = "offline"
    ERROR = "error"


class SessionStatus(str, Enum):
    RUNNING = "running"
    ENDED = "ended"
    FAILED = "failed"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class AlertType(str, Enum):
    DROPPED_EVENT = "dropped_event"
    DUPLICATE_EVENT = "duplicate_event"
    OUT_OF_ORDER_EVENT = "out_of_order_event"
    LATENCY_SPIKE = "latency_spike"
    RECORDER_SILENCE = "recorder_silence"
    MALFORMED_PACKET = "malformed_packet"
    CHECKSUM_FAILURE = "checksum_failure"
    CLOCK_DRIFT = "clock_drift"
    BUFFER_PRESSURE = "buffer_pressure"
    HEARTBEAT_MISSED = "heartbeat_missed"
    DEVICE_OVERHEAT = "device_overheat"
    LOW_BATTERY = "low_battery"


class Recorder(BaseModel):
    id: str
    name: str
    hardware_revision: str = "unknown"
    firmware_version: str = "unknown"
    expected_event_rate_hz: float = Field(default=250.0, gt=0)
    status: RecorderStatus = RecorderStatus.REGISTERED
    created_at: datetime = Field(default_factory=utcnow)


class MonitoringSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    recorder_id: str
    operator: str = "local"
    mode: str = "live"
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    status: SessionStatus = SessionStatus.RUNNING
    notes: str = ""


class TelemetryEvent(BaseModel):
    session_id: str
    recorder_id: str
    sequence_number: int = Field(ge=0)
    device_timestamp_us: int = Field(ge=0)
    ingest_timestamp: datetime = Field(default_factory=utcnow)
    event_type: str = "neural_sample"
    channel_count: int = Field(default=0, ge=0)
    payload_size: int = Field(default=0, ge=0)
    checksum_valid: bool = True
    source: str = "live"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def latency_ms(self) -> float:
        device_seconds = self.device_timestamp_us / 1_000_000
        host_seconds = self.ingest_timestamp.timestamp()
        return max(0.0, (host_seconds - device_seconds) * 1000)


class RecorderHealth(BaseModel):
    session_id: str
    recorder_id: str
    timestamp: datetime = Field(default_factory=utcnow)
    battery_percent: float = Field(default=100.0, ge=0, le=100)
    temperature_c: float = Field(default=36.5, ge=0, le=90)
    buffer_depth: int = Field(default=0, ge=0)
    storage_remaining_mb: int = Field(default=1024, ge=0)
    link_quality: float = Field(default=1.0, ge=0, le=1)
    cpu_percent: float = Field(default=0.0, ge=0, le=100)
    memory_percent: float = Field(default=0.0, ge=0, le=100)


class MetricSnapshot(BaseModel):
    session_id: str
    recorder_id: str
    window_start: datetime
    window_end: datetime
    event_rate_hz: float
    dropped_event_count: int
    malformed_packet_count: int
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    jitter_ms: float
    heartbeat_age_ms: float | None = None


class SessionDiagnostics(BaseModel):
    session_id: str
    recorder_id: str
    session_status: SessionStatus
    recorder_status: RecorderStatus
    event_count: int
    metric_count: int
    alert_count: int
    open_alert_count: int
    latest_metric: MetricSnapshot | None = None
    latest_health: RecorderHealth | None = None
    last_event_at: datetime | None = None
    generated_at: datetime = Field(default_factory=utcnow)


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    recorder_id: str
    severity: AlertSeverity
    type: AlertType
    status: AlertStatus = AlertStatus.OPEN
    message: str
    opened_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
