"""Deterministic runner commands."""

import json

import click

from cli_agent_orchestrator.deterministic_runner.db import DEFAULT_DB_PATH, DEFAULT_LOCK_DIR, RunnerDB
from cli_agent_orchestrator.deterministic_runner.dispatch import run_agent
from cli_agent_orchestrator.deterministic_runner.gateway import (
    LocalModelBusyError,
    LocalModelTimeoutError,
)
from cli_agent_orchestrator.deterministic_runner.lock_manager import LockManager, LockSpec
from cli_agent_orchestrator.deterministic_runner.test_runner_mcp import run_allowlisted


@click.group()
@click.option("--db", "db_path", default=DEFAULT_DB_PATH, show_default=True)
@click.pass_context
def deterministic(ctx: click.Context, db_path: str) -> None:
    """Manage deterministic runner state machine."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = RunnerDB(db_path=db_path)


@deterministic.command("init-db")
@click.pass_context
def init_db(ctx: click.Context) -> None:
    db: RunnerDB = ctx.obj["db"]
    db.init_db()
    click.echo("initialized")


@deterministic.command("create-task")
@click.option("--title", required=True)
@click.option("--owner", default="human")
@click.option("--priority", default="normal")
@click.option("--payload", default="{}")
@click.pass_context
def create_task(ctx: click.Context, title: str, owner: str, priority: str, payload: str) -> None:
    db: RunnerDB = ctx.obj["db"]
    task_id = db.create_task(title=title, owner=owner, priority=priority, payload=json.loads(payload))
    click.echo(task_id)


@deterministic.command("set-state")
@click.option("--task-id", required=True)
@click.option("--state", required=True)
@click.option("--actor", default="runner")
@click.option("--reason", default="")
@click.pass_context
def set_state(ctx: click.Context, task_id: str, state: str, actor: str, reason: str) -> None:
    db: RunnerDB = ctx.obj["db"]
    db.set_state(task_id=task_id, next_state=state, actor=actor, reason=reason)
    click.echo(f"{task_id}: {state}")


@deterministic.command("show-task")
@click.option("--task-id", required=True)
@click.pass_context
def show_task(ctx: click.Context, task_id: str) -> None:
    db: RunnerDB = ctx.obj["db"]
    task = db.get_task(task_id)
    if task is None:
        raise click.ClickException(f"task not found: {task_id}")
    events = db.list_events(task_id)
    click.echo(json.dumps({"task": task.__dict__, "events": events}, ensure_ascii=True, indent=2))


@deterministic.command("enqueue-patch")
@click.option("--task-id", required=True)
@click.option("--patch-path", required=True)
@click.option("--status", default="PROPOSED")
@click.pass_context
def enqueue_patch(ctx: click.Context, task_id: str, patch_path: str, status: str) -> None:
    db: RunnerDB = ctx.obj["db"]
    db.enqueue_patch(task_id=task_id, patch_path=patch_path, status=status)
    click.echo("patch queued")


@deterministic.command("list-patches")
@click.option("--status", default=None)
@click.pass_context
def list_patches(ctx: click.Context, status: str | None) -> None:
    db: RunnerDB = ctx.obj["db"]
    click.echo(json.dumps(db.list_patches(status=status), ensure_ascii=True, indent=2))


@deterministic.command("approve-patch")
@click.option("--patch-id", required=True, type=int)
@click.option("--approved-by", required=True)
@click.pass_context
def approve_patch(ctx: click.Context, patch_id: int, approved_by: str) -> None:
    db: RunnerDB = ctx.obj["db"]
    db.set_patch_status(patch_id, "APPROVED", approved_by=approved_by)
    click.echo(f"approved: {patch_id}")


@deterministic.command("reject-patch")
@click.option("--patch-id", required=True, type=int)
@click.option("--reason", required=True)
@click.pass_context
def reject_patch(ctx: click.Context, patch_id: int, reason: str) -> None:
    db: RunnerDB = ctx.obj["db"]
    db.set_patch_status(patch_id, "REJECTED", reject_reason=reason)
    click.echo(f"rejected: {patch_id}")


@deterministic.command("apply-approved-patch")
@click.option("--patch-id", required=True, type=int)
@click.option("--actor", default="runner")
@click.pass_context
def apply_approved_patch(ctx: click.Context, patch_id: int, actor: str) -> None:
    db: RunnerDB = ctx.obj["db"]
    db.apply_patch(patch_id, actor=actor)
    click.echo(f"apply attempted: {patch_id}")


@deterministic.command("acquire-lock")
@click.option("--kind", required=True, type=click.Choice(["repo", "file"]))
@click.option("--resource", required=True)
@click.option("--owner", default="runner")
@click.option("--lock-dir", default=DEFAULT_LOCK_DIR, show_default=True)
@click.pass_context
def acquire_lock(
    ctx: click.Context, kind: str, resource: str, owner: str, lock_dir: str
) -> None:
    db: RunnerDB = ctx.obj["db"]
    manager = LockManager(lock_dir=lock_dir)
    with db.connect() as conn:
        locked = manager.acquire(conn, LockSpec(kind=kind, resource=resource, owner=owner))
    if not locked:
        raise click.ClickException("lock-busy")
    click.echo("acquired")


@deterministic.command("release-lock")
@click.option("--kind", required=True, type=click.Choice(["repo", "file"]))
@click.option("--resource", required=True)
@click.option("--owner", default="runner")
@click.option("--lock-dir", default=DEFAULT_LOCK_DIR, show_default=True)
@click.pass_context
def release_lock(
    ctx: click.Context, kind: str, resource: str, owner: str, lock_dir: str
) -> None:
    db: RunnerDB = ctx.obj["db"]
    manager = LockManager(lock_dir=lock_dir)
    with db.connect() as conn:
        manager.release(conn, LockSpec(kind=kind, resource=resource, owner=owner))
    click.echo("released")


@deterministic.command("dispatch-agent")
@click.option("--task-id", required=True)
@click.option("--agent", required=True)
@click.option("--profile", required=True)
@click.option("--lane-config", required=True)
@click.option("--prompt-path", required=True)
@click.option("--queue-depth", default=0, type=int)
@click.pass_context
def dispatch_agent(
    ctx: click.Context,
    task_id: str,
    agent: str,
    profile: str,
    lane_config: str,
    prompt_path: str,
    queue_depth: int,
) -> None:
    db: RunnerDB = ctx.obj["db"]
    db.set_state(task_id, "RUNNING_AGENT", actor="runner", reason="dispatch")
    try:
        result = run_agent(profile, lane_config, agent, prompt_path, queue_depth)
    except LocalModelBusyError:
        db.log_event(task_id, "gateway", "LOCAL_MODEL_BUSY", {"queue_depth": queue_depth})
        db.set_state(task_id, "LOCAL_MODEL_BUSY", actor="runner", reason="immediate reject")
        raise click.ClickException("LOCAL_MODEL_BUSY")
    except LocalModelTimeoutError:
        db.log_event(task_id, "gateway", "LOCAL_MODEL_TIMEOUT", {})
        db.set_state(task_id, "LOCAL_MODEL_TIMEOUT", actor="runner", reason="lane timeout")
        raise click.ClickException("LOCAL_MODEL_TIMEOUT")

    db.log_event(
        task_id,
        actor=agent,
        event_type="AGENT_DISPATCH_RESULT",
        detail={"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
    )
    if result.returncode != 0:
        db.set_state(task_id, "FAILED_CLOSED", actor="runner", reason="AGENT_EXIT_NONZERO")
    elif agent.startswith("codex"):
        db.set_state(task_id, "PATCH_PROPOSED", actor="runner", reason="proposal captured")
    else:
        db.set_state(task_id, "NEEDS_HUMAN_DECISION", actor="runner", reason="review completed")
    click.echo("dispatched")


@deterministic.command("run-test-command")
@click.option("--key", required=True)
def run_test_command(key: str) -> None:
    result = run_allowlisted(key)
    click.echo(result.stdout, nl=False)
    if result.returncode != 0:
        raise click.ClickException(f"test command failed: {key}")

