import pytest

from neuralmonitor.core.protocol import PacketParseError, encode_frame, parse_frame


def test_frame_round_trip_validates_checksum():
    frame = encode_frame(42, 1_700_000_000_000_000, 4, b"payload")

    parsed = parse_frame(frame)

    assert parsed.sequence_number == 42
    assert parsed.device_timestamp_us == 1_700_000_000_000_000
    assert parsed.channel_count == 4
    assert parsed.payload == b"payload"
    assert parsed.checksum_valid is True


def test_corrupted_payload_marks_checksum_invalid():
    frame = bytearray(encode_frame(1, 1_700_000_000_000_000, 2, b"abcd"))
    frame[-5] ^= 0xFF

    parsed = parse_frame(bytes(frame))

    assert parsed.checksum_valid is False


def test_bad_magic_rejected():
    frame = bytearray(encode_frame(1, 1_700_000_000_000_000, 2, b"abcd"))
    frame[0] = 0

    with pytest.raises(PacketParseError, match="bad_magic"):
        parse_frame(bytes(frame))

