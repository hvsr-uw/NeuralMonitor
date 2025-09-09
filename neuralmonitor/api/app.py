from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from neuralmonitor.core.config import AppSettings
from neuralmonitor.core.models import Recorder, RecorderHealth, SessionStatus
from neuralmonitor.core.protocol import PacketParseError
from neuralmonitor.ingest.service import IngestService, SessionNotRunningError
from neuralmonitor.simulator.generator import FaultProfile, TelemetrySimulator
from neuralmonitor.storage.repository import SQLiteRepository, export_session_report

logger = logging.getLogger(__name__)


class StartSessionRequest(BaseModel):
    recorder_id: str = Field(default="recorder-alpha", min_length=1)
    name: str = Field(default="Cortical Recorder Alpha", min_length=1)
    operator: str = Field(default="demo", min_length=1)
    hardware_revision: str = Field(default="rev-c", min_length=1)
    firmware_version: str = Field(default="2.4.1", min_length=1)
    expected_event_rate_hz: float = Field(default=250.0, gt=0)
    mode: str = Field(default="live", min_length=1)
    notes: str = ""


class FrameRequest(BaseModel):
    frame_b64: str = Field(min_length=1)


class SimulatorRequest(BaseModel):
    count: int = Field(default=250, ge=1, le=100_000)
    drop_rate: float = Field(default=0.02, ge=0, le=1)
    duplicate_rate: float = Field(default=0.01, ge=0, le=1)
    out_of_order_rate: float = Field(default=0.005, ge=0, le=1)
    checksum_failure_rate: float = Field(default=0.005, ge=0, le=1)
    latency_spike_every: int | None = Field(default=80, ge=1)
    latency_spike_ms: float = Field(default=250.0, ge=0)
    seed: int | None = None


class HealthRequest(BaseModel):
    battery_percent: float = Field(default=92.0, ge=0, le=100)
    temperature_c: float = Field(default=37.2, ge=0, le=90)
    buffer_depth: int = Field(default=128, ge=0)
    storage_remaining_mb: int = Field(default=8192, ge=0)
    link_quality: float = Field(default=0.98, ge=0, le=1)
    cpu_percent: float = Field(default=23.0, ge=0, le=100)
    memory_percent: float = Field(default=31.0, ge=0, le=100)


class ConnectionManager:
    """Tracks live dashboard sockets and fans out backend events."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, topic: str, payload: dict) -> None:
        stale: list[WebSocket] = []
        message = {"topic": topic, "payload": payload}
        for websocket in self._connections:
            try:
                await websocket.send_json(message)
            except RuntimeError:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)


def create_app(db_path: str | None = None, settings: AppSettings | None = None) -> FastAPI:
    settings = settings or AppSettings.from_env()
    if db_path is not None:
        settings = settings.model_copy(update={"db_path": Path(db_path)})
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    repo = SQLiteRepository(settings.db_path)
    manager = ConnectionManager()
    ingest = IngestService(
        repo=repo,
        publisher=manager.broadcast,
        publish_retry_attempts=settings.publish_retry_attempts,
        publish_retry_base_delay_ms=settings.publish_retry_base_delay_ms,
    )

    async def silence_loop() -> None:
        while True:
            await asyncio.sleep(settings.silence_check_interval_s)
            for session in repo.list_sessions():
                if session.status.value == "running":
                    await ingest.check_silence(session.id)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(silence_loop())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="NeuralMonitor", version="0.1.0", lifespan=lifespan)
    app.state.repo = repo
    app.state.ingest = ingest
    app.state.manager = manager

    web_dir = Path(__file__).resolve().parents[1] / "web"
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return (web_dir / "index.html").read_text(encoding="utf-8")

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "status": "ok",
            "sessions": len(repo.list_sessions()),
            "websocket_clients": manager.connection_count,
            "db_path": str(settings.db_path),
            "publish_retry_attempts": settings.publish_retry_attempts,
        }

    @app.post("/sessions")
    async def start_session(request: StartSessionRequest = Body(default_factory=StartSessionRequest)) -> dict:
        recorder = Recorder(
            id=request.recorder_id,
            name=request.name,
            hardware_revision=request.hardware_revision,
            firmware_version=request.firmware_version,
            expected_event_rate_hz=request.expected_event_rate_hz,
        )
        session = await ingest.start_session(
            recorder=recorder,
            operator=request.operator,
            mode=request.mode,
            notes=request.notes,
        )
        return session.model_dump(mode="json")

    @app.get("/sessions")
    async def list_sessions() -> list[dict]:
        return [session.model_dump(mode="json") for session in repo.list_sessions()]

    @app.get("/recorders")
    async def list_recorders() -> list[dict]:
        return [recorder.model_dump(mode="json") for recorder in repo.list_recorders()]

    @app.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict:
        session = repo.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session.model_dump(mode="json")

    @app.post("/sessions/{session_id}/end")
    async def end_session(session_id: str) -> dict:
        try:
            session = await ingest.end_session(session_id, SessionStatus.ENDED)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return session.model_dump(mode="json")

    @app.post("/sessions/{session_id}/frames")
    async def ingest_frame(session_id: str, request: FrameRequest) -> dict:
        try:
            frame = base64.b64decode(request.frame_b64, validate=True)
        except binascii.Error as exc:
            raise HTTPException(status_code=422, detail="frame_b64 must be valid base64") from exc

        try:
            snapshot, alerts = await ingest.ingest_frame(session_id, frame)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SessionNotRunningError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PacketParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "metric": snapshot.model_dump(mode="json"),
            "alerts": [alert.model_dump(mode="json") for alert in alerts],
        }

    @app.post("/sessions/{session_id}/simulate")
    async def simulate(
        session_id: str,
        request: SimulatorRequest = Body(default_factory=SimulatorRequest),
    ) -> dict:
        simulator = TelemetrySimulator(
            fault_profile=FaultProfile(
                drop_rate=request.drop_rate,
                duplicate_rate=request.duplicate_rate,
                out_of_order_rate=request.out_of_order_rate,
                checksum_failure_rate=request.checksum_failure_rate,
                latency_spike_every=request.latency_spike_every,
                latency_spike_ms=request.latency_spike_ms,
            ),
            event_rate_hz=settings.simulator_event_rate_hz,
            seed=request.seed if request.seed is not None else settings.simulator_seed,
        )
        processed = 0
        for frame in simulator.batch(request.count):
            try:
                await ingest.ingest_frame(session_id, frame, source="simulator")
                processed += 1
            except SessionNotRunningError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except PacketParseError:
                logger.warning("simulator emitted malformed frame", exc_info=True)
        return {"processed": processed}

    @app.post("/sessions/{session_id}/health")
    async def health(session_id: str, request: HealthRequest) -> dict:
        session = repo.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        try:
            alerts = await ingest.observe_health(
                RecorderHealth(
                    session_id=session_id,
                    recorder_id=session.recorder_id,
                    battery_percent=request.battery_percent,
                    temperature_c=request.temperature_c,
                    buffer_depth=request.buffer_depth,
                    storage_remaining_mb=request.storage_remaining_mb,
                    link_quality=request.link_quality,
                    cpu_percent=request.cpu_percent,
                    memory_percent=request.memory_percent,
                )
            )
        except SessionNotRunningError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"alerts": [alert.model_dump(mode="json") for alert in alerts]}

    @app.get("/sessions/{session_id}/metrics")
    async def metrics(session_id: str) -> list[dict]:
        return [metric.model_dump(mode="json") for metric in repo.latest_metrics(session_id)]

    @app.get("/sessions/{session_id}/alerts")
    async def alerts(session_id: str) -> list[dict]:
        return [alert.model_dump(mode="json") for alert in repo.alerts_for_session(session_id)]

    @app.get("/sessions/{session_id}/diagnostics")
    async def diagnostics(session_id: str) -> dict:
        try:
            return ingest.diagnostics(session_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/sessions/{session_id}/report")
    async def report(session_id: str) -> dict:
        try:
            return {"report": export_session_report(repo, session_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return app


app = create_app()
