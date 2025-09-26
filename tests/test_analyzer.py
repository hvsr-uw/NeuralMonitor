from datetime import datetime, timedelta, timezone

from neuralmonitor.core.analyzer import StreamAnalyzer, Thresholds
from neuralmonitor.core.models import AlertStatus, AlertType, TelemetryEvent


def event(seq: int, session: str = "s1", recorder: str = "r1") -> TelemetryEvent:
    now = datetime.now(timezone.utc)
    return TelemetryEvent(
        session_id=session,
        recorder_id=recorder,
        sequence_number=seq,
        device_timestamp_us=int((now - timedelta(milliseconds=10)).timestamp() * 1_000_000),
    )


def test_missing_sequence_opens_dropped_event_alert():
    analyzer = StreamAnalyzer("s1", "r1")
    analyzer.observe_event(event(1))

    snapshot, alerts = analyzer.observe_event(event(4))

    assert snapshot.dropped_event_count == 2
    assert any(alert.type == AlertType.DROPPED_EVENT for alert in alerts)


def test_normal_sequence_resolves_dropped_event_alert():
    analyzer = StreamAnalyzer("s1", "r1")
    analyzer.observe_event(event(1))
    analyzer.observe_event(event(4))

    _, alerts = analyzer.observe_event(event(5))

    assert any(
        alert.type == AlertType.DROPPED_EVENT and alert.status == AlertStatus.RESOLVED
        for alert in alerts
    )


def test_duplicate_and_out_of_order_do_not_move_high_water_mark():
    analyzer = StreamAnalyzer("s1", "r1")
    analyzer.observe_event(event(10))
    _, duplicate_alerts = analyzer.observe_event(event(10))
    _, out_of_order_alerts = analyzer.observe_event(event(9))
    snapshot, final_alerts = analyzer.observe_event(event(11))

    assert any(alert.type == AlertType.DUPLICATE_EVENT for alert in duplicate_alerts)
    assert any(alert.type == AlertType.OUT_OF_ORDER_EVENT for alert in out_of_order_alerts)
    assert snapshot.dropped_event_count == 0
    assert not any(alert.type == AlertType.DROPPED_EVENT for alert in final_alerts)


def test_latency_threshold_opens_alert():
    analyzer = StreamAnalyzer("s1", "r1", Thresholds(latency_p95_warning_ms=5))
    old = datetime.now(timezone.utc) - timedelta(milliseconds=50)

    _, alerts = analyzer.observe_event(
        TelemetryEvent(
            session_id="s1",
            recorder_id="r1",
            sequence_number=1,
            device_timestamp_us=int(old.timestamp() * 1_000_000),
        )
    )

    assert any(alert.type == AlertType.LATENCY_SPIKE for alert in alerts)

