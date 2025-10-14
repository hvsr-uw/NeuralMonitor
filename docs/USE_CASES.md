# Use Cases

NeuralMonitor is built for engineers and research operators who need confidence that an implant recorder telemetry stream is complete, timely, and operationally healthy.

It is a reliability and diagnostics layer for recorder infrastructure.

## Primary Users

Biomedical systems engineers use NeuralMonitor to validate recorder hardware and firmware under normal and degraded stream conditions.

Research lab operators use it to monitor a recording session and quickly see whether the recorder is connected, degraded, silent, offline, or in an error state.

Software and firmware engineers use it to reproduce stream failures such as missing packets, corrupt frames, duplicate sequence numbers, and latency spikes.

Reviewers use it to inspect lifecycle behavior, failure handling, integration boundaries, and test coverage.

## Core Use Cases

### Start A Recorder Monitoring Session

An operator starts a session for a recorder. The system records recorder identity, firmware/hardware details, operator, mode, start time, and expected event rate. The recorder moves into `connected` state.

Relevant surfaces:

- Dashboard `Start Session`
- CLI `neuralmonitor start-session`
- API `POST /sessions`

### Monitor Live Telemetry Integrity

Telemetry frames arrive from a recorder, replay source, or local simulator. NeuralMonitor validates the binary frame, checks the CRC, extracts sequence and timestamp data, persists the event, updates rolling metrics, and publishes dashboard updates.

The system watches for:

- Dropped sequence numbers
- Duplicate events
- Out-of-order events
- Malformed frames
- Invalid checksums
- Latency spikes
- Recorder silence

### Inject Realistic Faults

The local simulator generates deterministic traffic with configurable packet loss, duplicates, out-of-order frames, checksum failures, and latency spikes. This keeps walkthroughs and tests repeatable.

Relevant surfaces:

- Dashboard `Inject Demo Faults`
- CLI `neuralmonitor simulate <session-id>`
- API `POST /sessions/{id}/simulate`
- Code `TelemetrySimulator.deterministic_validation_run()`

### Monitor Recorder Health

Recorder health samples include battery, temperature, buffer depth, storage, link quality, CPU, and memory. Health signals can open alerts and update recorder state.

Examples:

- Low battery opens a `low_battery` warning.
- High buffer depth opens a `buffer_pressure` warning.
- Critical temperature opens a `device_overheat` critical alert.

Relevant surfaces:

- Dashboard `Send Health`
- CLI `neuralmonitor health <session-id>`
- API `POST /sessions/{id}/health`

### Close A Session Safely

When a session is ended, the recorder becomes `offline` and the session stops accepting telemetry or health updates. This prevents replays and accidental requests from mutating a completed postmortem.

Relevant surfaces:

- Dashboard `End Session`
- CLI `neuralmonitor end-session <session-id>`
- API `POST /sessions/{id}/end`

### Review A Session Postmortem

Reviewers and engineers can inspect diagnostics and reports after data has been ingested.

Useful outputs:

- Event count
- Metric count
- Alert count
- Open alert count
- Latest metric snapshot
- Latest health sample
- Last event timestamp
- Recorder and session status

Relevant surfaces:

- CLI `neuralmonitor diagnostics <session-id>`
- CLI `neuralmonitor report <session-id>`
- API `GET /sessions/{id}/diagnostics`
- API `GET /sessions/{id}/report`
