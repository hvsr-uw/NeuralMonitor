from __future__ import annotations

import asyncio
import math
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass

from neuralmonitor.core.protocol import device_timestamp_now_us, encode_frame


@dataclass(frozen=True)
class FaultProfile:
    drop_rate: float = 0.0
    duplicate_rate: float = 0.0
    out_of_order_rate: float = 0.0
    checksum_failure_rate: float = 0.0
    jitter_ms: float = 3.0
    latency_spike_every: int | None = None
    latency_spike_ms: float = 250.0


class TelemetrySimulator:
    def __init__(
        self,
        event_rate_hz: float = 250.0,
        channel_count: int = 32,
        fault_profile: FaultProfile | None = None,
        seed: int | None = 7,
        start_timestamp_us: int | None = None,
    ) -> None:
        self.event_rate_hz = event_rate_hz
        self.channel_count = channel_count
        self.fault_profile = fault_profile or FaultProfile()
        self.random = random.Random(seed)
        self.start_timestamp_us = start_timestamp_us

    @classmethod
    def deterministic_validation_run(cls) -> "TelemetrySimulator":
        return cls(
            event_rate_hz=250.0,
            channel_count=32,
            fault_profile=FaultProfile(
                drop_rate=0.03,
                duplicate_rate=0.01,
                out_of_order_rate=0.005,
                checksum_failure_rate=0.005,
                latency_spike_every=75,
                latency_spike_ms=300,
            ),
            seed=2026,
            start_timestamp_us=1_800_000_000_000_000,
        )

    async def frames(self, start_sequence: int = 0) -> AsyncIterator[bytes]:
        sequence = start_sequence
        interval = 1 / self.event_rate_hz
        while True:
            await asyncio.sleep(max(0.0, interval + self.random.uniform(-0.001, 0.001)))
            if self.random.random() < self.fault_profile.drop_rate:
                sequence += 1
                continue

            frame = self._frame(sequence, start_sequence)
            if self.random.random() < self.fault_profile.checksum_failure_rate:
                frame = frame[:-1] + bytes([frame[-1] ^ 0xFF])

            if self.random.random() < self.fault_profile.out_of_order_rate and sequence > 2:
                yield self._frame(sequence - 2, start_sequence)

            yield frame

            if self.random.random() < self.fault_profile.duplicate_rate:
                yield frame
            sequence += 1

    def batch(self, count: int, start_sequence: int = 0) -> list[bytes]:
        sequence = start_sequence
        frames: list[bytes] = []
        while len(frames) < count:
            if self.random.random() >= self.fault_profile.drop_rate:
                frame = self._frame(sequence, start_sequence)
                if self.random.random() < self.fault_profile.checksum_failure_rate:
                    frame = frame[:-1] + bytes([frame[-1] ^ 0xFF])
                frames.append(frame)
                if self.random.random() < self.fault_profile.duplicate_rate:
                    frames.append(frame)
            sequence += 1
        return frames[:count]

    def _frame(self, sequence: int, start_sequence: int = 0) -> bytes:
        ts = self._timestamp_for(sequence, start_sequence)
        if self.fault_profile.latency_spike_every and sequence % self.fault_profile.latency_spike_every == 0:
            ts -= int(self.fault_profile.latency_spike_ms * 1000)
        samples = [
            int(1200 * math.sin((sequence + channel) / 15.0) + self.random.randint(-30, 30))
            for channel in range(self.channel_count)
        ]
        payload = b"".join(sample.to_bytes(2, "big", signed=True) for sample in samples)
        return encode_frame(sequence, ts, self.channel_count, payload)

    def _timestamp_for(self, sequence: int, start_sequence: int) -> int:
        if self.start_timestamp_us is None:
            return device_timestamp_now_us()
        offset = max(0, sequence - start_sequence)
        return self.start_timestamp_us + int(offset * (1_000_000 / self.event_rate_hz))
