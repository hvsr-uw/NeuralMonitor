from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    db_path: Path = Path("data/neuralmonitor.db")
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    silence_check_interval_s: float = Field(default=1.0, gt=0)
    publish_retry_attempts: int = Field(default=3, ge=1, le=10)
    publish_retry_base_delay_ms: int = Field(default=25, ge=0, le=5_000)
    simulator_seed: int = 7
    simulator_event_rate_hz: float = Field(default=250.0, gt=0)

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            db_path=Path(os.getenv("NEURALMONITOR_DB_PATH", "data/neuralmonitor.db")),
            host=os.getenv("NEURALMONITOR_HOST", "127.0.0.1"),
            port=int(os.getenv("NEURALMONITOR_PORT", "8000")),
            silence_check_interval_s=float(os.getenv("NEURALMONITOR_SILENCE_CHECK_INTERVAL_S", "1.0")),
            publish_retry_attempts=int(os.getenv("NEURALMONITOR_PUBLISH_RETRY_ATTEMPTS", "3")),
            publish_retry_base_delay_ms=int(os.getenv("NEURALMONITOR_PUBLISH_RETRY_BASE_DELAY_MS", "25")),
            simulator_seed=int(os.getenv("NEURALMONITOR_SIMULATOR_SEED", "7")),
            simulator_event_rate_hz=float(os.getenv("NEURALMONITOR_SIMULATOR_EVENT_RATE_HZ", "250.0")),
        )

