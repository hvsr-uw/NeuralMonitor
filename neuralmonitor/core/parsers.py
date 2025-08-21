from __future__ import annotations

from neuralmonitor.core.protocol import ParsedFrame, parse_frame


class PythonPacketParser:
    def parse(self, frame: bytes) -> ParsedFrame:
        return parse_frame(frame)

