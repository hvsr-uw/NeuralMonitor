import pytest

from neuralmonitor.core.models import AlertType, Recorder, RecorderHealth, RecorderStatus
from neuralmonitor.ingest.service import IngestService, SessionNotRunningError
from neuralmonitor.simulator.generator import FaultProfile, TelemetrySimulator
from neuralmonitor.storage.repository import SQLiteRepository


@pytest.mark.asyncio
async def test_ingest_service_processes_simulator_faults(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    published = []

    async def publish(topic, payload):
        published.append((topic, payload))

    service = IngestService(repo, publish)
    session = await service.start_session(Recorder(id="r1", name="Recorder"))
    simulator = TelemetrySimulator(fault_profile=FaultProfile(drop_rate=0.0, duplicate_rate=0.2), seed=11)

    for frame in simulator.batch(20):
        await service.ingest_frame(session.id, frame, source="test")

    assert repo.events_for_session(session.id)
    assert repo.latest_metrics(session.id)
    assert any(topic == "telemetry.event" for topic, _ in published)


@pytest.mark.asyncio
async def test_closed_session_rejects_new_frames(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    service = IngestService(repo)
    session = await service.start_session(Recorder(id="r1", name="Recorder"))
    frame = TelemetrySimulator().batch(1)[0]

    await service.end_session(session.id)

    with pytest.raises(SessionNotRunningError):
        await service.ingest_frame(session.id, frame)


@pytest.mark.asyncio
async def test_health_alerts_drive_recorder_degraded_status(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    service = IngestService(repo)
    session = await service.start_session(Recorder(id="r1", name="Recorder"))

    alerts = await service.observe_health(
        RecorderHealth(
            session_id=session.id,
            recorder_id="r1",
            battery_percent=10,
            buffer_depth=7000,
        )
    )

    recorder = repo.get_recorder("r1")
    assert recorder is not None
    assert recorder.status == RecorderStatus.DEGRADED
    assert {alert.type for alert in alerts} >= {AlertType.LOW_BATTERY, AlertType.BUFFER_PRESSURE}


@pytest.mark.asyncio
async def test_diagnostics_summarize_session_state(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    service = IngestService(repo)
    session = await service.start_session(Recorder(id="r1", name="Recorder"))

    await service.ingest_frame(session.id, TelemetrySimulator().batch(1)[0], source="test")
    diagnostics = service.diagnostics(session.id)

    assert diagnostics.event_count == 1
    assert diagnostics.metric_count == 1
    assert diagnostics.latest_metric is not None
    assert diagnostics.recorder_status == RecorderStatus.CONNECTED
