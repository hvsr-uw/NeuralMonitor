# Testing

NeuralMonitor tests the parts of the system that would be expensive to debug during a real recording session: protocol correctness, stream analysis, lifecycle rules, persistence, retry behavior, deterministic data generation, and API-level workflows.

## Run Tests

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
```

Expected current result:

```text
18 passed
All checks passed
```

You may see an upstream TestClient deprecation warning from FastAPI/Starlette dependencies. The application code uses FastAPI lifespan handling for startup and shutdown.

## Test Areas

### Protocol Tests

File: `tests/test_protocol.py`

Covers:

- Binary frame round trip
- CRC validation
- Corrupted payload checksum detection
- Bad magic rejection

Why it matters: every higher-level metric and alert depends on correct sequence and timestamp extraction.

### Analyzer Tests

File: `tests/test_analyzer.py`

Covers:

- Missing sequence detection
- Dropped-event alert resolution
- Duplicate detection
- Out-of-order detection
- Latency threshold alerting

Why it matters: this is the core reliability logic.

### Repository Tests

File: `tests/test_repository.py`

Covers:

- Recorder persistence
- Session persistence
- Event persistence
- Alert persistence
- Session report export

Why it matters: postmortems and diagnostics depend on persisted state, not transient dashboard state.

### Ingest Service Tests

File: `tests/test_ingest_service.py`

Covers:

- Simulator-driven frame ingestion
- Closed-session rejection
- Health alerts updating recorder state
- Diagnostics summarizing session state

Why it matters: `IngestService` is the boundary where parsing, persistence, analysis, lifecycle, and publishing meet.

### API Lifecycle Tests

File: `tests/test_api_lifecycle.py`

Covers:

- Default session creation
- Health ingestion through API
- Diagnostics through API
- End-session through API
- Rejection of local simulator traffic after session closure

Why it matters: this verifies the system is usable through its real external interface.

### Production Boundary Tests

File: `tests/test_production_boundaries.py`

Covers:

- Environment-driven settings
- Domain validation
- Deterministic data source output
- Retry publisher recovery
- Parser injection
- In-memory repository use

Why it matters: these tests prove the project has real seams for configuration, failure recovery, and integration substitution.

## Test Fakes

`InMemoryTelemetryRepository` is an in-memory repository behind the same contract as SQLite. It keeps service tests fast and avoids coupling core behavior to SQL.

Parser injection is tested with a counting parser fake. This proves the service depends on the parser contract instead of hardcoding one implementation.

`RetryingPublisher` can wrap any async publisher, which makes transient failure behavior testable without a real WebSocket.

## Deterministic Data

`TelemetrySimulator.deterministic_validation_run()` uses fixed fault settings, seed, and base timestamp. This gives stable binary frames and repeatable test expectations.

Use deterministic data source output when adding tests for:

- Drop detection
- Replay behavior
- Parser compatibility
- Report generation

## Useful Future Tests

Good next additions:

- Long-running metric compaction
- WebSocket reconnect and REST state resync
- Native parser parity against Python parser
- Storage outage behavior
- Concurrent multi-recorder ingestion
- Configurable threshold tests
