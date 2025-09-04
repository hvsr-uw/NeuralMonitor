from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel

from neuralmonitor.core.models import (
    Alert,
    AlertStatus,
    MetricSnapshot,
    MonitoringSession,
    Recorder,
    RecorderHealth,
    RecorderStatus,
    SessionDiagnostics,
    TelemetryEvent,
    utcnow,
)


class SQLiteRepository:
    def __init__(self, path: str | Path = "neuralmonitor.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS recorders (
                  id TEXT PRIMARY KEY,
                  body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY,
                  recorder_id TEXT NOT NULL,
                  body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS telemetry_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  recorder_id TEXT NOT NULL,
                  sequence_number INTEGER NOT NULL,
                  body TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_session_seq
                  ON telemetry_events(session_id, recorder_id, sequence_number);
                CREATE TABLE IF NOT EXISTS metrics (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  recorder_id TEXT NOT NULL,
                  window_end TEXT NOT NULL,
                  body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS health (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  recorder_id TEXT NOT NULL,
                  timestamp TEXT NOT NULL,
                  body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alerts (
                  id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  recorder_id TEXT NOT NULL,
                  type TEXT NOT NULL,
                  status TEXT NOT NULL,
                  opened_at TEXT NOT NULL,
                  body TEXT NOT NULL
                );
                """
            )

    def upsert_recorder(self, recorder: Recorder) -> None:
        self._upsert("recorders", recorder.id, recorder)

    def get_recorder(self, recorder_id: str) -> Recorder | None:
        row = self._get("recorders", recorder_id)
        return Recorder.model_validate_json(row["body"]) if row else None

    def list_recorders(self) -> list[Recorder]:
        with self.connect() as conn:
            return [Recorder.model_validate_json(row["body"]) for row in conn.execute("SELECT body FROM recorders")]

    def upsert_session(self, session: MonitoringSession) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, recorder_id, body)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET recorder_id=excluded.recorder_id, body=excluded.body
                """,
                (session.id, session.recorder_id, self._dump(session)),
            )

    def get_session(self, session_id: str) -> MonitoringSession | None:
        row = self._get("sessions", session_id)
        return MonitoringSession.model_validate_json(row["body"]) if row else None

    def list_sessions(self) -> list[MonitoringSession]:
        with self.connect() as conn:
            rows = conn.execute("SELECT body FROM sessions ORDER BY id DESC").fetchall()
            return [MonitoringSession.model_validate_json(row["body"]) for row in rows]

    def append_event(self, event: TelemetryEvent) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO telemetry_events (session_id, recorder_id, sequence_number, body)
                VALUES (?, ?, ?, ?)
                """,
                (event.session_id, event.recorder_id, event.sequence_number, self._dump(event)),
            )

    def append_metric(self, snapshot: MetricSnapshot) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO metrics (session_id, recorder_id, window_end, body) VALUES (?, ?, ?, ?)",
                (snapshot.session_id, snapshot.recorder_id, snapshot.window_end.isoformat(), self._dump(snapshot)),
            )

    def append_health(self, health: RecorderHealth) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO health (session_id, recorder_id, timestamp, body) VALUES (?, ?, ?, ?)",
                (health.session_id, health.recorder_id, health.timestamp.isoformat(), self._dump(health)),
            )

    def upsert_alert(self, alert: Alert) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO alerts (id, session_id, recorder_id, type, status, opened_at, body)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status, body=excluded.body
                """,
                (
                    alert.id,
                    alert.session_id,
                    alert.recorder_id,
                    alert.type.value,
                    alert.status.value,
                    alert.opened_at.isoformat(),
                    self._dump(alert),
                ),
            )

    def latest_metrics(self, session_id: str, limit: int = 200) -> list[MetricSnapshot]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT body FROM metrics WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [MetricSnapshot.model_validate_json(row["body"]) for row in reversed(rows)]

    def latest_metric(self, session_id: str) -> MetricSnapshot | None:
        metrics = self.latest_metrics(session_id, limit=1)
        return metrics[0] if metrics else None

    def metric_count(self, session_id: str) -> int:
        return self._count("metrics", session_id)

    def alerts_for_session(self, session_id: str) -> list[Alert]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT body FROM alerts WHERE session_id=? ORDER BY opened_at DESC",
                (session_id,),
            ).fetchall()
            return [Alert.model_validate_json(row["body"]) for row in rows]

    def open_alerts_for_session(self, session_id: str) -> list[Alert]:
        return [
            alert
            for alert in self.alerts_for_session(session_id)
            if alert.status == AlertStatus.OPEN
        ]

    def events_for_session(self, session_id: str, limit: int = 1000) -> list[TelemetryEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT body FROM telemetry_events WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [TelemetryEvent.model_validate_json(row["body"]) for row in reversed(rows)]

    def event_count(self, session_id: str) -> int:
        return self._count("telemetry_events", session_id)

    def last_event(self, session_id: str) -> TelemetryEvent | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT body FROM telemetry_events WHERE session_id=? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            return TelemetryEvent.model_validate_json(row["body"]) if row else None

    def latest_health(self, session_id: str) -> RecorderHealth | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT body FROM health WHERE session_id=? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            return RecorderHealth.model_validate_json(row["body"]) if row else None

    def diagnostics(self, session_id: str) -> SessionDiagnostics:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"unknown session {session_id}")
        recorder = self.get_recorder(session.recorder_id)
        alerts = self.alerts_for_session(session_id)
        last_event = self.last_event(session_id)
        return SessionDiagnostics(
            session_id=session.id,
            recorder_id=session.recorder_id,
            session_status=session.status,
            recorder_status=recorder.status if recorder else RecorderStatus.OFFLINE,
            event_count=self.event_count(session_id),
            metric_count=self.metric_count(session_id),
            alert_count=len(alerts),
            open_alert_count=sum(1 for alert in alerts if alert.status == AlertStatus.OPEN),
            latest_metric=self.latest_metric(session_id),
            latest_health=self.latest_health(session_id),
            last_event_at=last_event.ingest_timestamp if last_event else None,
            generated_at=utcnow(),
        )

    def _upsert(self, table: str, key: str, model: BaseModel) -> None:
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO {table} (id, body) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                (key, self._dump(model)),
            )

    def _get(self, table: str, key: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(f"SELECT body FROM {table} WHERE id=?", (key,)).fetchone()

    def _count(self, table: str, session_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE session_id=?", (session_id,)).fetchone()
            return int(row["count"])

    @staticmethod
    def _dump(model: BaseModel) -> str:
        return model.model_dump_json()


class SessionReport(BaseModel):
    session: MonitoringSession
    recorder: Recorder | None
    metrics: list[MetricSnapshot]
    alerts: list[Alert]
    event_count: int
    generated_at: datetime


def export_session_report(repo: SQLiteRepository, session_id: str) -> str:
    session = repo.get_session(session_id)
    if session is None:
        raise KeyError(f"unknown session {session_id}")
    report = SessionReport(
        session=session,
        recorder=repo.get_recorder(session.recorder_id),
        metrics=repo.latest_metrics(session_id),
        alerts=repo.alerts_for_session(session_id),
        event_count=len(repo.events_for_session(session_id, limit=1_000_000)),
        generated_at=datetime.now().astimezone(),
    )
    return json.dumps(report.model_dump(mode="json"), indent=2)
