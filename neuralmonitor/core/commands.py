from __future__ import annotations

from pydantic import BaseModel, Field

from neuralmonitor.core.models import Recorder, RecorderHealth, SessionStatus


class StartSessionCommand(BaseModel):
    recorder: Recorder
    operator: str = Field(default="local", min_length=1)
    mode: str = Field(default="live", min_length=1)
    notes: str = ""


class IngestFrameCommand(BaseModel):
    session_id: str = Field(min_length=1)
    frame: bytes = Field(min_length=1)
    source: str = Field(default="live", min_length=1)


class ObserveHealthCommand(BaseModel):
    health: RecorderHealth


class EndSessionCommand(BaseModel):
    session_id: str = Field(min_length=1)
    status: SessionStatus = SessionStatus.ENDED

