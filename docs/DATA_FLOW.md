# Data Flow

This document follows a frame from source to dashboard and then covers health samples, alerts, diagnostics, and session closure.

## Telemetry Ingest Flow

```text
Simulator or recorder
  -> binary frame
  -> POST /sessions/{id}/frames or local simulator call
  -> IngestFrameCommand
  -> IngestService.execute_ingest_frame()
  -> PacketParser.parse()
  -> TelemetryEvent
  -> SQLiteRepository.append_event()
  -> StreamAnalyzer.observe_event()
  -> MetricSnapshot + Alert changes
  -> SQLiteRepository.append_metric()
  -> SQLiteRepository.upsert_alert()
  -> recorder_status_from_signals()
  -> SQLiteRepository.upsert_recorder()
  -> RetryingPublisher
  -> WebSocket dashboard updates
```

## Step-By-Step

1. A frame arrives as bytes.
2. The service confirms the session exists and is still running.
3. The parser validates the binary protocol and CRC.
4. A `TelemetryEvent` is created with sequence number, device timestamp, ingest timestamp, channel count, payload size, checksum status, and source.
5. The event is persisted before live publication.
6. The analyzer compares sequence state and computes rolling metrics.
7. Alerts are opened, updated, or resolved.
8. Recorder status is recalculated from active evidence.
9. Metric, alert, recorder, and event updates are published to connected clients.

## Malformed Frame Flow

Malformed frames do not become telemetry events. They are still operationally meaningful.

```text
bad frame
  -> parser raises PacketParseError
  -> malformed packet metric increments
  -> malformed_packet alert opens or updates
  -> alert is persisted
  -> alert.changed is published
  -> API returns 422
```

## Health Sample Flow

```text
POST /sessions/{id}/health
  -> ObserveHealthCommand
  -> IngestService.execute_observe_health()
  -> RecorderHealth persisted
  -> StreamAnalyzer.observe_health()
  -> health alerts opened/resolved
  -> recorder status recalculated
  -> recorder.health, recorder.status, and alert.changed published
```

Health samples are not sequence-numbered telemetry frames. They are operational evidence about the recorder itself.

## Local Simulator Flow

```text
POST /sessions/{id}/simulate
  -> TelemetrySimulator
  -> batch of binary frames
  -> regular telemetry ingest path
```

The local simulator uses the same ingest path as recorder frames. Injected faults pass through parsing, analysis, persistence, and alerting.

## Dashboard Flow

The dashboard opens a WebSocket to `/ws`.

It reacts to:

- `metric.snapshot`
- `telemetry.event`
- `alert.changed`
- `recorder.status`
- `recorder.health`

The dashboard is a realtime view over persisted backend state. If it disconnects, the backend continues persisting data. A client can reload and query REST endpoints for sessions, metrics, alerts, and diagnostics.

## Diagnostics Flow

```text
GET /sessions/{id}/diagnostics
  -> repository.diagnostics()
  -> SessionDiagnostics
```

Diagnostics summarize:

- Session status
- Recorder status
- Event count
- Metric count
- Alert count
- Open alert count
- Latest metric
- Latest health
- Last event timestamp

This endpoint gives operators a compact state summary without reconstructing it from several endpoints.

## Session End Flow

```text
POST /sessions/{id}/end
  -> EndSessionCommand
  -> session.status = ended
  -> session.ended_at set
  -> recorder.status = offline
  -> session.ended published
```

After this point, frame and health ingestion return conflict-style errors. That behavior is deliberate.
