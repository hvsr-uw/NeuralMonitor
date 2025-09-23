# How It Works

NeuralMonitor is organized around a simple question: is this recorder session producing complete, timely, valid telemetry?

The system answers that question by combining a binary protocol parser, stream analyzer, alert lifecycle, recorder health model, persistence layer, and realtime dashboard updates.

## Telemetry Frame Format

Frames use network byte order:

```text
magic[2] version[1] payload_size[2] sequence[4] device_timestamp_us[8] channel_count[2] payload[n] crc32[4]
```

The parser checks:

- Minimum frame size
- Magic bytes
- Protocol version
- Payload length
- CRC32 over header and payload

The parsed result includes:

- Sequence number
- Device timestamp
- Channel count
- Payload bytes
- Checksum validity

## Session Lifecycle

A session starts in `running` state. Running sessions accept frame and health ingestion.

When the session is ended, it moves to `ended`, receives an `ended_at` timestamp, and the recorder is marked `offline`. Ended sessions reject new frames and health updates. This is intentional because completed session reports should not silently change.

The service also supports `failed` as a terminal state for abnormal shutdown or future operator workflows.

## Recorder State

Recorder state is derived from evidence, not hand-edited UI state.

- `connected`: no active degrading evidence
- `degraded`: warning-level alerts such as dropped packets, low battery, or buffer pressure
- `silent`: stream silence or stale heartbeat evidence
- `error`: critical alerts
- `offline`: ended session

This logic lives in `neuralmonitor.core.lifecycle`.

## Stream Analysis

The analyzer keeps per-session stream state:

- Last sequence number
- Last event timestamp
- Rolling event window
- Dropped event count
- Malformed packet count
- Heartbeat age

When a new telemetry event arrives, the analyzer compares its sequence number with the previous high-water mark.

Cases:

- Same sequence: duplicate alert
- Lower sequence: out-of-order alert
- Higher than expected: dropped event alert
- Expected next sequence: resolves dropped event alert if one was open

The analyzer also computes latency percentiles and jitter from the rolling event window.

## Alert Lifecycle

Alerts are keyed by session, recorder, and alert type. If the same problem continues, the existing open alert is updated instead of creating alert spam.

Alerts can be resolved when recovery evidence appears. For example, a dropped-event alert can resolve when normal sequence progression resumes.

Alert fields include:

- Severity
- Type
- Status
- Message
- Opened/updated/resolved timestamps
- Evidence dictionary

## Health Samples

Health samples are separate from telemetry frames. They represent recorder-side operational state:

- Battery percent
- Temperature
- Buffer depth
- Storage remaining
- Link quality
- CPU percent
- Memory percent

Health samples are persisted and evaluated by the analyzer. They can open alerts such as `buffer_pressure`, `device_overheat`, and `low_battery`.

## Publishing And Recovery

After ingest, the service publishes live updates:

- `session.started`
- `session.ended`
- `telemetry.event`
- `metric.snapshot`
- `recorder.health`
- `recorder.status`
- `alert.changed`

Publishing is wrapped by `RetryingPublisher`, which retries transient failures with exponential backoff. Ingest correctness is independent of WebSocket delivery; data is persisted and diagnostics remain available.

## Local Simulator

The local simulator emits clean or faulty traffic. It supports:

- Drop rate
- Duplicate rate
- Out-of-order rate
- Checksum failure rate
- Latency spikes
- Fixed seed
- Fixed timestamp base for exact repeatability

Use `TelemetrySimulator.deterministic_validation_run()` for stable tests and repeatable walkthroughs.
