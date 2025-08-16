# NeuralMonitor

NeuralMonitor is a real-time reliability monitor for implant recorder telemetry pipelines. It ingests binary telemetry frames, validates packet integrity, detects stream gaps and malformed events, tracks latency and jitter, monitors recorder health, persists session state, and streams live updates to a browser dashboard over WebSockets.

The project is written as an engineering and research monitoring system for recorder infrastructure. It uses clear domain models, realistic failure handling, reproducible data sources, production-style configuration, and tests around the behavior that matters.

## Why It Exists

Implant recorder pipelines are easy to make look healthy when traffic is clean. The difficult parts are the operational cases: missing sequence numbers, duplicate packets, out-of-order delivery, malformed frames, stale heartbeats, buffer pressure, low battery, high latency, and sessions that should no longer accept data after they are closed.

NeuralMonitor focuses on those reliability questions. It gives an operator a concrete way to start a recording session, inject realistic faults through a local simulator, observe state transitions, inspect alerts, and export session diagnostics.

## What Is Implemented

- FastAPI service with REST endpoints and WebSocket updates
- Browser dashboard for live metrics, alerts, recorder state, and recent events
- CLI for headless operation, replay, health updates, reports, and diagnostics
- Binary telemetry protocol with CRC validation
- Stream analyzer for dropped, duplicate, out-of-order, malformed, delayed, and silent streams
- Recorder health model with battery, temperature, buffer, storage, link, CPU, and memory signals
- Alert lifecycle with open, update, and resolved states
- Explicit session lifecycle with running, ended, and failed states
- SQLite repository plus in-memory repository for tests
- Configuration layer driven by environment variables
- Retry/backoff wrapper for event publishing
- Deterministic data source and replay file support
- C++ packet parser helper that mirrors the binary frame format
- Unit and integration tests for core behavior and production boundaries

## Quick Start

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000
```

Suggested dashboard walkthrough:

1. Click `Start Session`.
2. Click `Inject Demo Faults`.
3. Click `Send Health` to trigger battery and buffer alerts.
4. Watch recorder state move through connected/degraded/error-style states as evidence changes.
5. Click `End Session`.
6. Try to inject faults again and notice the closed session rejects new data.

## Local Development

This repo is easiest to run with `uv`:

```bash
uv run --extra dev uvicorn neuralmonitor.api.app:app --reload
uv run --extra dev pytest
uv run --extra dev ruff check .
```

Traditional Python setup also works:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn neuralmonitor.api.app:app --reload
pytest
```

## CLI

```bash
neuralmonitor start-session
neuralmonitor sessions
neuralmonitor simulate <session-id> --count 1000 --drop-rate 0.03
neuralmonitor health <session-id> --battery-percent 10 --buffer-depth 7000
neuralmonitor diagnostics <session-id>
neuralmonitor alerts <session-id>
neuralmonitor report <session-id> --output data/session-report.json
neuralmonitor end-session <session-id>
neuralmonitor make-replay --output sample_data/replay.jsonl
neuralmonitor replay <session-id> --input sample_data/replay.jsonl
```

## API Highlights

- `GET /healthz` - service status, runtime configuration, session count, WebSocket client count
- `POST /sessions` - start a monitoring session
- `GET /sessions` - list sessions
- `GET /recorders` - list known recorders and current states
- `POST /sessions/{id}/frames` - ingest one base64-encoded binary frame
- `POST /sessions/{id}/simulate` - inject deterministic or configured local simulator traffic
- `POST /sessions/{id}/health` - record recorder health and evaluate health alerts
- `GET /sessions/{id}/metrics` - retrieve recent metric snapshots
- `GET /sessions/{id}/alerts` - retrieve alert history
- `GET /sessions/{id}/diagnostics` - retrieve a compact session summary
- `GET /sessions/{id}/report` - export a JSON session report
- `POST /sessions/{id}/end` - close a session and mark the recorder offline

## Configuration

Runtime configuration lives in `neuralmonitor.core.config.AppSettings` and can be supplied with environment variables. See `.env.example`.

Common settings:

- `NEURALMONITOR_DB_PATH`
- `NEURALMONITOR_SILENCE_CHECK_INTERVAL_S`
- `NEURALMONITOR_PUBLISH_RETRY_ATTEMPTS`
- `NEURALMONITOR_PUBLISH_RETRY_BASE_DELAY_MS`
- `NEURALMONITOR_SIMULATOR_SEED`
- `NEURALMONITOR_SIMULATOR_EVENT_RATE_HZ`

## Project Layout

```text
neuralmonitor/
  api/          FastAPI app and WebSocket gateway
  core/         domain models, commands, config, protocol, metrics, alerting, ports
  ingest/       service layer coordinating parse, analyze, persist, and publish
  native/       Python wrapper for native parser integration
  simulator/    deterministic telemetry source and replay helpers
  storage/      SQLite repository and in-memory test repository
  web/          dashboard HTML, CSS, and JavaScript
native/         C++ packet parser helper
tests/          unit and integration tests
docs/           documentation suite
```

## Documentation

- [Use Cases](docs/USE_CASES.md)
- [How It Works](docs/HOW_IT_WORKS.md)
- [Architecture Overview](docs/ARCHITECTURE_OVERVIEW.md)
- [Data Flow](docs/DATA_FLOW.md)
- [Testing](docs/TESTING.md)
- [Reviewer Guide](docs/REVIEWER_GUIDE.md)
- [Extension Points](docs/EXTENSION_POINTS.md)

## Native Parser

The Python parser is the service default. The C++ helper in `native/packet_parser` mirrors the frame format and can be built independently:

```bash
cmake -S native/packet_parser -B build/packet_parser
cmake --build build/packet_parser
```

The executable accepts one hex-encoded frame and prints parsed JSON with checksum status.

## Tradeoffs

SQLite is used as the local persistence boundary because it keeps the project runnable without external infrastructure. Domain objects are stored as JSON bodies with indexed session fields; this favors flexibility and inspectability over analytical query speed. A production deployment could move hot metrics to a time-series store and session metadata to Postgres without changing the service-level contract.

The Python parser is authoritative for the running service. The C++ parser mirrors the same frame format and defines the native hot-path boundary for higher-throughput recorder environments.
