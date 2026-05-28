"""Repo/file lock manager."""

import os
import sqlite3
from dataclasses import dataclass


@dataclass
class LockSpec:
    kind: str
    resource: str
    owner: str


class LockManager:
    def __init__(self, lock_dir: str) -> None:
        self.lock_dir = lock_dir

    def acquire(self, conn: sqlite3.Connection, spec: LockSpec) -> bool:
        try:
            conn.execute(
                """
                INSERT INTO locks (kind, resource, owner, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                (spec.kind, spec.resource, spec.owner),
            )
        except sqlite3.IntegrityError:
            return False
        return self._acquire_lock_file(spec)

    def release(self, conn: sqlite3.Connection, spec: LockSpec) -> None:
        conn.execute(
            "DELETE FROM locks WHERE kind = ? AND resource = ? AND owner = ?",
            (spec.kind, spec.resource, spec.owner),
        )
        self._release_lock_file(spec)

    def _acquire_lock_file(self, spec: LockSpec) -> bool:
        os.makedirs(self.lock_dir, exist_ok=True)
        path = self._lock_path(spec)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(spec.owner)
        except FileExistsError:
            return False
        return True

    def _release_lock_file(self, spec: LockSpec) -> None:
        path = self._lock_path(spec)
        if os.path.exists(path):
            os.remove(path)

    def _lock_path(self, spec: LockSpec) -> str:
        safe_resource = spec.resource.replace(":", "_").replace("\\", "_").replace("/", "_")
        return os.path.join(self.lock_dir, f"{spec.kind}__{safe_resource}.lock")
