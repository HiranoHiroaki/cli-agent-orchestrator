"""SQLite-backed deterministic runner storage."""

import json
import os
import sqlite3
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

from cli_agent_orchestrator.deterministic_runner.state_machine import can_transition, is_valid_state

DEFAULT_DB_PATH = os.path.join(".cao", "deterministic_runner.db")
DEFAULT_LOCK_DIR = os.path.join(".cao", "locks")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Task:
    id: str
    title: str
    state: str
    owner: str
    priority: str
    created_at: str
    updated_at: str
    payload_json: str


class RunnerDB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    state TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS patch_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    patch_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approved_by TEXT,
                    reject_reason TEXT NOT NULL DEFAULT '',
                    apply_log TEXT NOT NULL DEFAULT '',
                    applied_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS locks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(kind, resource)
                );
                """
            )

    def create_task(
        self,
        title: str,
        owner: str = "human",
        priority: str = "normal",
        payload: dict[str, Any] | None = None,
    ) -> str:
        payload_obj = payload or {}
        evidence = payload_obj.setdefault("evidence", {})
        evidence.setdefault("prompt_path", "")
        evidence.setdefault("constraints_path", "")
        evidence.setdefault("decision_path", "")
        evidence.setdefault("patch_path", "")
        evidence.setdefault("log_path", "")
        task_id = str(uuid4())
        created_at = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, title, state, owner, priority, created_at, updated_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title,
                    "CREATED",
                    owner,
                    priority,
                    created_at,
                    created_at,
                    json.dumps(payload_obj, ensure_ascii=True),
                ),
            )
            self.add_event(conn, task_id, "runner", "TASK_CREATED", {"title": title})
        return task_id

    def set_state(self, task_id: str, next_state: str, actor: str, reason: str = "") -> None:
        if not is_valid_state(next_state):
            raise ValueError(f"invalid state: {next_state}")
        with self.connect() as conn:
            task = self._get_task_row(conn, task_id)
            if task is None:
                raise ValueError(f"task not found: {task_id}")
            current_state = str(task["state"])
            if not can_transition(current_state, next_state):
                raise ValueError(f"invalid transition: {current_state} -> {next_state}")
            conn.execute(
                "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ?",
                (next_state, now_iso(), task_id),
            )
            self.add_event(
                conn,
                task_id,
                actor,
                "STATE_CHANGED",
                {"from": current_state, "to": next_state, "reason": reason},
            )

    def log_event(self, task_id: str, actor: str, event_type: str, detail: dict[str, Any]) -> None:
        with self.connect() as conn:
            if self._get_task_row(conn, task_id) is None:
                raise ValueError(f"task not found: {task_id}")
            self.add_event(conn, task_id, actor, event_type, detail)

    def get_task(self, task_id: str) -> Task | None:
        with self.connect() as conn:
            row = self._get_task_row(conn, task_id)
        return Task(**dict(row)) if row else None

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, task_id, created_at, actor, event_type, detail_json
                FROM task_events WHERE task_id = ? ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def enqueue_patch(self, task_id: str, patch_path: str, status: str = "PROPOSED") -> None:
        with self.connect() as conn:
            if self._get_task_row(conn, task_id) is None:
                raise ValueError(f"task not found: {task_id}")
            ts = now_iso()
            conn.execute(
                """
                INSERT INTO patch_queue (task_id, patch_path, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, patch_path, status, ts, ts),
            )
            self.add_event(
                conn,
                task_id,
                "runner",
                "PATCH_ENQUEUED",
                {"patch_path": patch_path, "status": status},
            )

    def set_patch_status(
        self,
        patch_id: int,
        status: str,
        approved_by: str | None = None,
        reject_reason: str = "",
        apply_log: str = "",
    ) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, task_id, status FROM patch_queue WHERE id = ?",
                (patch_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"patch not found: {patch_id}")
            now = now_iso()
            conn.execute(
                """
                UPDATE patch_queue
                SET status = ?, approved_by = ?, reject_reason = ?, apply_log = ?, updated_at = ?,
                    applied_at = CASE WHEN ? = 'APPLIED' THEN ? ELSE applied_at END
                WHERE id = ?
                """,
                (status, approved_by, reject_reason, apply_log, now, status, now, patch_id),
            )
            self.add_event(
                conn,
                str(row["task_id"]),
                "runner",
                "PATCH_STATUS_CHANGED",
                {
                    "patch_id": patch_id,
                    "from": str(row["status"]),
                    "to": status,
                    "approved_by": approved_by or "",
                    "reject_reason": reject_reason,
                },
            )

    def list_patches(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT id, task_id, patch_path, status, approved_by, reject_reason, apply_log, applied_at,
                           created_at, updated_at
                    FROM patch_queue
                    WHERE status = ?
                    ORDER BY id DESC
                    """,
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, task_id, patch_path, status, approved_by, reject_reason, apply_log, applied_at,
                           created_at, updated_at
                    FROM patch_queue
                    ORDER BY id DESC
                    """
                ).fetchall()
        return [dict(row) for row in rows]

    def apply_patch(self, patch_id: int, actor: str) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, task_id, patch_path, status FROM patch_queue WHERE id = ?",
                (patch_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"patch not found: {patch_id}")
            if str(row["status"]) != "APPROVED":
                raise ValueError(f"patch not approved: {patch_id}")
            patch_path = str(row["patch_path"])
        check = subprocess.run(
            ["git", "apply", "--check", patch_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode != 0:
            log = (check.stdout + "\n" + check.stderr).strip()
            self.set_patch_status(patch_id, "APPLY_FAILED", apply_log=log)
            self.set_state(str(row["task_id"]), "FAILED_CLOSED", actor=actor, reason="PATCH_APPLY_FAILED")
            return
        apply_result = subprocess.run(
            ["git", "apply", patch_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if apply_result.returncode != 0:
            log = (apply_result.stdout + "\n" + apply_result.stderr).strip()
            self.set_patch_status(patch_id, "APPLY_FAILED", apply_log=log)
            self.set_state(str(row["task_id"]), "FAILED_CLOSED", actor=actor, reason="PATCH_APPLY_FAILED")
            return
        self.set_patch_status(
            patch_id,
            "APPLIED",
            apply_log=(apply_result.stdout + "\n" + apply_result.stderr).strip(),
        )

    @staticmethod
    def add_event(
        conn: sqlite3.Connection,
        task_id: str,
        actor: str,
        event_type: str,
        detail: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO task_events (task_id, created_at, actor, event_type, detail_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, now_iso(), actor, event_type, json.dumps(detail, ensure_ascii=True)),
        )

    @staticmethod
    def _get_task_row(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT id, title, state, owner, priority, created_at, updated_at, payload_json
            FROM tasks WHERE id = ?
            """,
            (task_id,),
        ).fetchone()

