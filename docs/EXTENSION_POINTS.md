# Extension Points

NeuralMonitor is designed with a few deliberate seams. These are the best places to extend the project without fighting the existing structure.

## Storage Backend

Current implementations:

- `SQLiteRepository`
- `InMemoryTelemetryRepository`

Contract:

- `TelemetryRepository` in `neuralmonitor/core/ports.py`

Good extensions:

- Postgres repository for recorder/session/alert metadata
- Time-series store for metric snapshots
- Object storage for raw frame archives
- Retention policy for long-running sessions

Keep the service contract stable. `IngestService` should not learn SQL or database-specific concepts.

## Parser Backend

Current implementations:

- `PythonPacketParser`
- C++ helper under `native/packet_parser`
- `NativePacketParser` wrapper

Contract:

- `PacketParser` in `neuralmonitor/core/ports.py`

Good extensions:

- Native parser as a default runtime option
- Parser parity tests between Python and C++
- Protocol version negotiation
- Support for multiple recorder frame formats

Keep parsed output stable: sequence, timestamp, channel count, payload, checksum status.

## Alert Rules

Current location:

- `neuralmonitor/core/analyzer.py`
- `neuralmonitor/core/alerts.py`
- `neuralmonitor/core/models.py`

Good extensions:

- Configurable thresholds per recorder
- Alert suppression windows
- Escalation policies
- Alert annotations
- Operator acknowledgements

Avoid putting alert rules in the dashboard. Alerts should be backend facts, not UI-only calculations.

## Recorder Lifecycle

Current location:

- `neuralmonitor/core/lifecycle.py`

Good extensions:

- Explicit heartbeat messages
- Grace periods per recorder type
- Firmware-specific degraded states
- Reconnect state transitions
- Session failure reason tracking

Keep lifecycle state evidence-based. Recorder status should be derived from alerts, health, and stream activity.

## Local Simulator

Current location:

- `neuralmonitor/simulator/generator.py`
- `neuralmonitor/simulator/replay.py`

Good extensions:

- Named local simulator profiles
- Long-session load profile
- Clock drift profile
- Burst loss profile
- Thermal stress profile
- Replay speed controls

Prefer deterministic profiles for tests and walkthroughs. Randomness is useful during exploration; repeatability is what makes failures debuggable.

## API And Dashboard

Current locations:

- `neuralmonitor/api/app.py`
- `neuralmonitor/web/`

Good extensions:

- Authenticated operator/admin roles
- WebSocket state resync on reconnect
- Session comparison view
- Alert acknowledgement UI
- Exportable CSV reports
- Dashboard filtering by recorder/session

Keep the dashboard as a view over backend state. The backend should remain the source of truth.

## Observability

Current features:

- `/healthz`
- structured-enough logs with session and recorder context
- diagnostics endpoint
- retry publisher delivery results

Good extensions:

- Prometheus metrics
- OpenTelemetry spans
- Request correlation IDs
- Publisher failure counters
- Background task health reporting

Useful metrics to add:

- Ingested frames per second
- Malformed frames per session
- Open alerts by severity
- Publish retry count
- WebSocket client count
- Repository write latency

## Security

Not currently implemented.

Good extensions:

- API key or OAuth authentication
- Role-based permissions
- TLS termination configuration
- Audit log for operator actions
- Redaction rules for sensitive metadata

Security is listed as an extension point because the current project focuses on recorder monitoring, ingest reliability, diagnostics, and local operation.
