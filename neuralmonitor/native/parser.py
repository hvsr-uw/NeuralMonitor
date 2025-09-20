from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class NativeParserUnavailable(RuntimeError):
    """Raised when a configured native parser executable cannot be found."""


@dataclass(frozen=True)
class NativeParseResult:
    sequence_number: int
    device_timestamp_us: int
    channel_count: int
    payload_size: int
    checksum_valid: bool


class NativePacketParser:
    def __init__(self, executable: str | Path) -> None:
        self.executable = Path(executable)

    def parse(self, frame: bytes) -> NativeParseResult:
        if not self.executable.exists():
            raise NativeParserUnavailable(f"native parser not found: {self.executable}")
        completed = subprocess.run(
            [str(self.executable), frame.hex()],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise ValueError(completed.stderr.strip() or "native parser failed")
        return NativeParseResult(**json.loads(completed.stdout))
