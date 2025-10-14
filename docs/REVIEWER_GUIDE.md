# Reviewer Guide

This guide gives a direct path through the code, runtime behavior, and tests that define NeuralMonitor.

## Start Here

1. Read `README.md` for the product summary and run commands.
2. Run the tests:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
```

3. Start the app:

```bash
uv run --extra dev uvicorn neuralmonitor.api.app:app --reload
```

4. Open `http://127.0.0.1:8000`.

## Manual Review Walkthrough

In the dashboard:

1. Click `Start Session`.
2. Click `Inject Demo Faults`.
3. Confirm event rate, dropped count, latency, alerts, and recent events update.
4. Click `Send Health`.
5. Confirm low battery and buffer pressure alerts appear.
6. Confirm recorder status changes from connected to degraded or error depending on active evidence.
7. Click `End Session`.
8. Try injecting faults again. The backend should reject closed-session mutation.

Then inspect:

```bash
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/sessions
curl http://127.0.0.1:8000/recorders
curl http://127.0.0.1:8000/sessions/<session-id>/diagnostics
curl http://127.0.0.1:8000/sessions/<session-id>/alerts
```

## What To Inspect In Code

### Domain Models

File: `neuralmonitor/core/models.py`

Look for:

- Explicit recorder, session, event, health, metric, alert, and diagnostics models
- Validation constraints on health values, event sequence, payload size, and expected event rate
- Clear status enums rather than arbitrary strings

### Protocol Parser

File: `neuralmonitor/core/protocol.py`

Look for:

- Binary frame format
- CRC calculation
- Typed parse errors
- Round-trip tests

### Stream Analysis

File: `neuralmonitor/core/analyzer.py`

Look for:

- Dropped event detection
- Duplicate detection
- Out-of-order handling
- Latency percentile alerting
- Health alert evaluation
- Silence detection

### Alert Lifecycle

File: `neuralmonitor/core/alerts.py`

Look for:

- Open/update behavior keyed by session, recorder, and alert type
- Resolution support
- Alert evidence preservation

### Lifecycle Policy

File: `neuralmonitor/core/lifecycle.py`

Look for:

- Recorder state derived from alerts and heartbeats
- Clear mapping from operational evidence to user-facing state

### Application Service

File: `neuralmonitor/ingest/service.py`

Look for:

- Command methods
- Session running-state enforcement
- Parser and repository injection
- Retry-backed publisher
- Persistence before publication
- Recorder state refresh after meaningful signals

### Storage Boundary

Files:

- `neuralmonitor/storage/repository.py`
- `neuralmonitor/storage/memory.py`
- `neuralmonitor/core/ports.py`

Look for:

- SQLite as local durable implementation
- In-memory repository as a test/cache implementation
- Repository protocol as the service contract

### API Boundary

File: `neuralmonitor/api/app.py`

Look for:

- Request validation
- Settings-driven app factory
- Lifespan-managed background silence monitor
- Health/status endpoint
- Conflict responses for closed-session writes

### Local Simulator

File: `neuralmonitor/simulator/generator.py`

Look for:

- Fault injection settings
- Seeded random generator
- Fixed timestamp support for exact repeatability

## Engineering Signals

- The local simulator uses the same ingest path as recorder frames.
- Closed sessions reject new writes.
- Alert lifecycle updates existing alerts instead of spamming duplicates.
- Recorder state is derived from evidence.
- WebSocket publishing is retry-backed and not the source of truth.
- Tests exercise failure modes, not only happy paths.
- The storage and parser boundaries are replaceable.
- Diagnostics summarize state for review and postmortem workflows.

## Known Limitations

- SQLite is local and simple; high-volume production telemetry would need a stronger storage plan.
- The dashboard covers the core operational workflow.
- The C++ parser is present as an integration boundary, while Python remains the default runtime parser.
- Authentication and authorization are planned extension points.
- Regulatory controls, clinical validation, and patient-data workflows are outside this implementation.
