"""Tests for deterministic runner features."""

from pathlib import Path

import pytest

from cli_agent_orchestrator.deterministic_runner.db import RunnerDB
from cli_agent_orchestrator.deterministic_runner.gateway import (
    LanePolicy,
    LocalModelBusyError,
    enforce_queue_reject,
)
from cli_agent_orchestrator.deterministic_runner.lock_manager import LockManager, LockSpec
from cli_agent_orchestrator.deterministic_runner.test_runner_mcp import run_allowlisted


def test_patch_approval_flow(tmp_path: Path) -> None:
    db_path = str(tmp_path / "runner.db")
    db = RunnerDB(db_path)
    db.init_db()
    task_id = db.create_task("patch flow")
    db.enqueue_patch(task_id, "dummy.patch")
    patch = db.list_patches()[0]
    db.set_patch_status(int(patch["id"]), status="APPROVED", approved_by="human")
    approved = db.list_patches()[0]
    assert approved["status"] == "APPROVED"
    assert approved["approved_by"] == "human"


def test_lock_acquire_release(tmp_path: Path) -> None:
    db = RunnerDB(str(tmp_path / "runner.db"))
    db.init_db()
    lock_dir = str(tmp_path / "locks")
    manager = LockManager(lock_dir=lock_dir)
    spec = LockSpec(kind="repo", resource="E:/Document/repo", owner="runner")
    with db.connect() as conn:
        assert manager.acquire(conn, spec) is True
    with db.connect() as conn:
        assert manager.acquire(conn, spec) is False
    with db.connect() as conn:
        manager.release(conn, spec)
    with db.connect() as conn:
        assert manager.acquire(conn, spec) is True


def test_queue_full_reject() -> None:
    policy = LanePolicy(timeout_ms=60000, max_queue=1, reject_on_queue_full=True)
    with pytest.raises(LocalModelBusyError):
        enforce_queue_reject(policy, queue_depth=1)


def test_allowlist_blocks_unknown_command() -> None:
    with pytest.raises(ValueError):
        run_allowlisted("unknown")

