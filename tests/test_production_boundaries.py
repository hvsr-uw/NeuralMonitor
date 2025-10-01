import pytest
from pydantic import ValidationError

from neuralmonitor.core.config import AppSettings
from neuralmonitor.core.models import Recorder, RecorderHealth
from neuralmonitor.core.protocol import parse_frame
from neuralmonitor.core.publishing import RetryingPublisher
from neuralmonitor.ingest.service import IngestService
from neuralmonitor.simulator.generator import TelemetrySimulator
from neuralmonitor.storage.memory import InMemoryTelemetryRepository


def test_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("NEURALMONITOR_DB_PATH", "data/custom.db")
    monkeypatch.setenv("NEURALMONITOR_PORT", "8123")
    monkeypatch.setenv("NEURALMONITOR_PUBLISH_RETRY_ATTEMPTS", "4")

    settings = AppSettings.from_env()

    assert settings.db_path.parts[-2:] == ("data", "custom.db")
    assert settings.port == 8123
    assert settings.publish_retry_attempts == 4


def test_domain_health_validation_rejects_impossible_values():
    with pytest.raises(ValidationError):
        RecorderHealth(session_id="s1", recorder_id="r1", battery_percent=120)


def test_deterministic_simulator_repeats_exact_frames():
    first = TelemetrySimulator.deterministic_validation_run().batch(5)
    second = TelemetrySimulator.deterministic_validation_run().batch(5)

    assert first == second
    assert parse_frame(first[0]).sequence_number == 0


@pytest.mark.asyncio
async def test_retrying_publisher_recovers_from_transient_failure():
    attempts = 0

    async def flaky(topic, payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary websocket failure")

    publisher = RetryingPublisher(flaky, attempts=3, base_delay_ms=0)

    result = await publisher.publish("metric.snapshot", {"ok": True})

    assert result.delivered is True
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_service_uses_injected_parser_and_memory_repository():
    class CountingParser:
        def __init__(self) -> None:
            self.calls = 0

        def parse(self, frame: bytes):
            self.calls += 1
            return parse_frame(frame)

    repo = InMemoryTelemetryRepository()
    parser = CountingParser()
    service = IngestService(repo, parser=parser)
    session = await service.start_session(Recorder(id="r1", name="Recorder"))
    frame = TelemetrySimulator.deterministic_validation_run().batch(1)[0]

    await service.ingest_frame(session.id, frame)

    assert parser.calls == 1
    assert repo.event_count(session.id) == 1
    assert service.diagnostics(session.id).latest_metric is not None
