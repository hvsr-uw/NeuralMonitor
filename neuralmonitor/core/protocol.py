from __future__ import annotations

import base64
import json
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime

MAGIC = b"NM"
VERSION = 1
HEADER = struct.Struct("!2sBHIQH")


class PacketParseError(ValueError):
    """Raised when a telemetry frame violates the NeuralMonitor wire format."""


@dataclass(frozen=True)
class ParsedFrame:
    sequence_number: int
    device_timestamp_us: int
    channel_count: int
    payload: bytes
    checksum_valid: bool


def encode_frame(
    sequence_number: int,
    device_timestamp_us: int,
    channel_count: int,
    payload: bytes,
) -> bytes:
    header = HEADER.pack(MAGIC, VERSION, len(payload), sequence_number, device_timestamp_us, channel_count)
    checksum = struct.pack("!I", zlib.crc32(header + payload) & 0xFFFFFFFF)
    return header + payload + checksum


def parse_frame(frame: bytes) -> ParsedFrame:
    if len(frame) < HEADER.size + 4:
        raise PacketParseError("frame_too_short")

    magic, version, payload_size, sequence_number, device_timestamp_us, channel_count = HEADER.unpack(
        frame[: HEADER.size]
    )
    if magic != MAGIC:
        raise PacketParseError("bad_magic")
    if version != VERSION:
        raise PacketParseError(f"unsupported_version:{version}")

    expected_len = HEADER.size + payload_size + 4
    if len(frame) != expected_len:
        raise PacketParseError(f"bad_length:expected={expected_len}:actual={len(frame)}")

    payload = frame[HEADER.size : HEADER.size + payload_size]
    stored_checksum = struct.unpack("!I", frame[-4:])[0]
    computed_checksum = zlib.crc32(frame[:-4]) & 0xFFFFFFFF
    return ParsedFrame(
        sequence_number=sequence_number,
        device_timestamp_us=device_timestamp_us,
        channel_count=channel_count,
        payload=payload,
        checksum_valid=stored_checksum == computed_checksum,
    )


def frame_to_json_line(frame: bytes) -> str:
    return json.dumps({"frame_b64": base64.b64encode(frame).decode("ascii")})


def parse_json_line(line: str) -> ParsedFrame:
    data = json.loads(line)
    if "frame_b64" not in data:
        raise PacketParseError("missing_frame_b64")
    return parse_frame(base64.b64decode(data["frame_b64"]))


def device_timestamp_now_us() -> int:
    return int(datetime.now().timestamp() * 1_000_000)
