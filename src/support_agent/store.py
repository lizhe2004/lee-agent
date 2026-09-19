from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from support_agent.models import Case


class SQLiteCaseStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS cases (case_id TEXT PRIMARY KEY, data TEXT NOT NULL)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS case_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL
                )"""
            )

    def create_case(self, workflow_id: str, workflow_version: int, start_node: str) -> Case:
        case = Case(
            case_id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            current_node=start_node,
            status="active",
        )
        self.save_case(case)
        return case

    def get_case(self, case_id: str) -> Case:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM cases WHERE case_id = ?", (case_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown case: {case_id}")
        return Case.from_dict(json.loads(row[0]))

    def save_case(self, case: Case) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO cases(case_id, data) VALUES(?, ?) "
                "ON CONFLICT(case_id) DO UPDATE SET data = excluded.data",
                (case.case_id, json.dumps(case.to_dict(), ensure_ascii=False)),
            )

    def append_event(self, case_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO case_events(case_id, event_type, payload) VALUES(?, ?, ?)",
                (case_id, event_type, json.dumps(payload, ensure_ascii=False)),
            )

    def list_events(self, case_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_type, payload FROM case_events WHERE case_id = ? ORDER BY event_id",
                (case_id,),
            ).fetchall()
        return [
            {"event_type": event_type, "payload": json.loads(payload)}
            for event_type, payload in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)
