from datetime import datetime, timezone

from neuralmonitor.core.models import Alert, AlertSeverity, AlertType, MonitoringSession, Recorder, TelemetryEvent
from neuralmonitor.storage.repository import SQLiteRepository, export_session_report


def test_repository_persists_session_event_and_alert(tmp_path):
    repo = SQLiteRepository(tmp_path / "test.db")
    recorder = Recorder(id="r1", name="Recorder")
    session = MonitoringSession(recorder_id="r1")
    event = TelemetryEvent(
        session_id=session.id,
        recorder_id="r1",
        sequence_number=1,
        device_timestamp_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
    )
    alert = Alert(
        session_id=session.id,
        recorder_id="r1",
        severity=AlertSeverity.WARNING,
        type=AlertType.DROPPED_EVENT,
        message="missing event",
    )

    repo.upsert_recorder(recorder)
    repo.upsert_session(session)
    repo.append_event(event)
    repo.upsert_alert(alert)

    assert repo.get_recorder("r1") == recorder
    assert repo.get_session(session.id) == session
    assert repo.events_for_session(session.id)[0].sequence_number == 1
    assert repo.alerts_for_session(session.id)[0].type == AlertType.DROPPED_EVENT
    assert "missing event" in export_session_report(repo, session.id)

