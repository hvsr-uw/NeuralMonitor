from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from neuralmonitor.core.config import AppSettings
from neuralmonitor.core.models import Recorder, RecorderHealth, SessionStatus
from neuralmonitor.ingest.service import IngestService, SessionNotRunningError
from neuralmonitor.simulator.generator import FaultProfile, TelemetrySimulator
from neuralmonitor.simulator.replay import read_replay, write_replay
from neuralmonitor.storage.repository import SQLiteRepository, export_session_report

app = typer.Typer(help="NeuralMonitor recorder telemetry diagnostics.")
console = Console()


def repo(db: Path) -> SQLiteRepository:
    return SQLiteRepository(db)


def default_db_path() -> Path:
    return AppSettings.from_env().db_path


DEFAULT_DB_PATH = default_db_path()


@app.command()
def start_session(
    db: Path = typer.Option(DEFAULT_DB_PATH, help="SQLite database path."),
    recorder_id: str = "recorder-alpha",
    name: str = "Cortical Recorder Alpha",
    operator: str = "local",
) -> None:
    async def run() -> None:
        service = IngestService(repo(db))
        session = await service.start_session(
            Recorder(id=recorder_id, name=name, hardware_revision="rev-c", firmware_version="2.4.1"),
            operator=operator,
        )
        console.print_json(data=session.model_dump(mode="json"))

    asyncio.run(run())


@app.command()
def simulate(
    session_id: str,
    db: Path = typer.Option(DEFAULT_DB_PATH, help="SQLite database path."),
    count: int = 500,
    drop_rate: float = 0.02,
    duplicate_rate: float = 0.01,
    checksum_failure_rate: float = 0.005,
) -> None:
    async def run() -> None:
        service = IngestService(repo(db))
        simulator = TelemetrySimulator(
            fault_profile=FaultProfile(
                drop_rate=drop_rate,
                duplicate_rate=duplicate_rate,
                checksum_failure_rate=checksum_failure_rate,
                latency_spike_every=100,
            )
        )
        processed = 0
        for frame in simulator.batch(count):
            try:
                await service.ingest_frame(session_id, frame, source="cli-simulator")
                processed += 1
            except SessionNotRunningError as exc:
                raise typer.BadParameter(str(exc)) from exc
            except Exception as exc:
                console.print(f"Rejected frame: {exc}")
        console.print(f"Processed {processed} frames")

    asyncio.run(run())


@app.command()
def sessions(db: Path = typer.Option(DEFAULT_DB_PATH, help="SQLite database path.")) -> None:
    table = Table("Session", "Recorder", "Status", "Started")
    for session in repo(db).list_sessions():
        table.add_row(session.id, session.recorder_id, session.status.value, session.started_at.isoformat())
    console.print(table)


@app.command()
def alerts(
    session_id: str,
    db: Path = typer.Option(DEFAULT_DB_PATH, help="SQLite database path."),
) -> None:
    table = Table("Severity", "Type", "Status", "Message")
    for alert in repo(db).alerts_for_session(session_id):
        table.add_row(alert.severity.value, alert.type.value, alert.status.value, alert.message)
    console.print(table)


@app.command()
def diagnostics(
    session_id: str,
    db: Path = typer.Option(DEFAULT_DB_PATH, help="SQLite database path."),
) -> None:
    console.print_json(data=repo(db).diagnostics(session_id).model_dump(mode="json"))


@app.command()
def end_session(
    session_id: str,
    db: Path = typer.Option(DEFAULT_DB_PATH, help="SQLite database path."),
) -> None:
    async def run() -> None:
        session = await IngestService(repo(db)).end_session(session_id, SessionStatus.ENDED)
        console.print_json(data=session.model_dump(mode="json"))

    asyncio.run(run())


@app.command()
def health(
    session_id: str,
    db: Path = typer.Option(DEFAULT_DB_PATH, help="SQLite database path."),
    battery_percent: float = 92.0,
    temperature_c: float = 37.2,
    buffer_depth: int = 128,
) -> None:
    async def run() -> None:
        database = repo(db)
        session = database.get_session(session_id)
        if session is None:
            raise typer.BadParameter(f"unknown session {session_id}")
        service = IngestService(database)
        alerts = await service.observe_health(
            RecorderHealth(
                session_id=session.id,
                recorder_id=session.recorder_id,
                battery_percent=battery_percent,
                temperature_c=temperature_c,
                buffer_depth=buffer_depth,
            )
        )
        console.print_json(data=[alert.model_dump(mode="json") for alert in alerts])

    asyncio.run(run())


@app.command()
def report(
    session_id: str,
    db: Path = typer.Option(DEFAULT_DB_PATH, help="SQLite database path."),
    output: Path | None = None,
) -> None:
    content = export_session_report(repo(db), session_id)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        console.print(f"Wrote {output}")
    else:
        console.print(content)


@app.command()
def make_replay(
    output: Path = Path("sample_data/replay.jsonl"),
    count: int = 250,
    drop_rate: float = 0.03,
) -> None:
    simulator = TelemetrySimulator(fault_profile=FaultProfile(drop_rate=drop_rate, latency_spike_every=70))
    write_replay(output, simulator.batch(count))
    console.print(f"Wrote {count} replay frames to {output}")


@app.command()
def replay(
    session_id: str,
    input: Path = Path("sample_data/replay.jsonl"),
    db: Path = typer.Option(DEFAULT_DB_PATH, help="SQLite database path."),
) -> None:
    async def run() -> None:
        service = IngestService(repo(db))
        for frame in read_replay(input):
            await service.ingest_frame(session_id, frame, source="replay")
        console.print(f"Replayed {input}")

    asyncio.run(run())


@app.command()
def encode_sample() -> None:
    frame = TelemetrySimulator().batch(1)[0]
    console.print(base64.b64encode(frame).decode("ascii"))
