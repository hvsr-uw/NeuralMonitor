from __future__ import annotations

import base64
import json
from pathlib import Path


def write_replay(path: str | Path, frames: list[bytes]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for frame in frames:
            handle.write(json.dumps({"frame_b64": base64.b64encode(frame).decode("ascii")}) + "\n")


def read_replay(path: str | Path) -> list[bytes]:
    frames: list[bytes] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                frames.append(base64.b64decode(json.loads(line)["frame_b64"]))
    return frames

