# Architecture Overview

NeuralMonitor is a layered Python application with a native parsing boundary. Domain logic is testable without the web server, persistence sits behind a repository contract, and integration points are explicit.

## High-Level Shape

```text
Recorder / local simulator / replay file
  -> binary telemetry frame
  -> API or CLI boundary
  -> IngestService command
  -> PacketParser port
  -> StreamAnalyzer
  -> AlertEngine + RollingMetrics
  -> TelemetryRepository port
  -> RetryingPublisher
  -> WebSocket dashboard / CLI / reports
```

## Package Responsibilities

### `neuralmonitor.core`

The domain and application contracts live here.

Important files:

- `models.py`: recorder, session, event, health, metric, alert, diagnostics models
- `protocol.py`: binary frame encoder/parser
- `analyzer.py`: stream analysis and health alert evaluation
- `alerts.py`: alert open/update/resolve behavior
- `metrics.py`: rolling metric calculations
- `lifecycle.py`: recorder state derivation
- `commands.py`: explicit action models
- `config.py`: environment-driven runtime settings
- `ports.py`: parser and repository protocols
- `publishing.py`: retry/backoff publishing boundary

### `neuralmonitor.ingest`

`IngestService` is the application service. It coordinates command validation, session lifecycle checks, parsing, persistence, analyzer state, recorder status updates, and live event publishing.

The service exposes convenience methods such as `start_session()` and command-style methods such as `execute_ingest_frame()`. The command methods make actions easier to test and reason about.

### `neuralmonitor.storage`

Storage implementations live here.

- `SQLiteRepository`: local durable repository
- `InMemoryTelemetryRepository`: in-memory repository for tests and local cache-style workflows

The service depends on the repository protocol rather than SQLite directly.

### `neuralmonitor.api`

The FastAPI app provides:

- REST endpoints
- Dashboard hosting
- WebSocket fanout
- Lifespan-managed recorder silence monitor
- Runtime health/status endpoint

### `neuralmonitor.simulator`

The local simulator generates deterministic or configurable frame sequences for walkthroughs, tests, and replay workflows.

### `neuralmonitor.web`

The dashboard shows the operational surface: session status, recorder state, event rate, dropped count, latency, alerts, and recent events.

### `native/packet_parser`

This C++17 helper mirrors the binary frame parser. The running service uses the Python parser by default, and the native helper defines where a lower-level parser fits for throughput-sensitive deployments.

## Design Tradeoffs

### SQLite Instead Of A Larger Database

SQLite keeps the project runnable on a laptop and inside Docker without external services. The schema stores domain objects as JSON bodies plus indexed query fields. This is flexible and easy to inspect. Large analytical queries are better served by a dedicated time-series or analytical store.

For production scale, metric snapshots could move to a time-series database and session/alert metadata could move to Postgres.

### Python Parser As Default

The Python parser is the default runtime parser because it keeps local setup predictable. The C++ parser uses the same frame format and can be promoted behind the parser port when a deployment requires a native hot path.

### WebSocket Publishing Is Best Effort

Persistence and analysis are the source of truth. WebSocket delivery is retried; if a dashboard client disconnects, the session still records data correctly. Clients can recover by reading metrics, alerts, and diagnostics over REST.

### Explicit Session Closure

Closed sessions reject new data. This protects postmortem integrity and makes lifecycle behavior explicit.
