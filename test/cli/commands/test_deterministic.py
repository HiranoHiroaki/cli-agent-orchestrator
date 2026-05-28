"""Tests for deterministic CLI command."""

import json

from click.testing import CliRunner

from cli_agent_orchestrator.cli.commands.deterministic import _sanitize_output, deterministic


def test_cli_has_deterministic_command() -> None:
    runner = CliRunner()
    result = runner.invoke(deterministic, ["--help"])
    assert result.exit_code == 0


def test_deterministic_init_and_create_task(tmp_path) -> None:
    runner = CliRunner()
    db_path = str(tmp_path / "runner.db")
    result_init = runner.invoke(deterministic, ["--db", db_path, "init-db"])
    assert result_init.exit_code == 0

    result_create = runner.invoke(
        deterministic,
        [
            "--db",
            db_path,
            "create-task",
            "--title",
            "sample",
        ],
    )
    assert result_create.exit_code == 0
    assert result_create.output.strip() != ""


def test_set_evidence_command(tmp_path) -> None:
    runner = CliRunner()
    db_path = str(tmp_path / "runner.db")
    runner.invoke(deterministic, ["--db", db_path, "init-db"])
    created = runner.invoke(deterministic, ["--db", db_path, "create-task", "--title", "sample"])
    task_id = created.output.strip()
    result = runner.invoke(
        deterministic,
        [
            "--db",
            db_path,
            "set-evidence",
            "--task-id",
            task_id,
            "--prompt-path",
            "tasks/sample/prompt.md",
            "--constraints-path",
            "tasks/sample/constraints.md",
            "--decision-path",
            "tasks/sample/decision.md",
            "--patch-path",
            "tasks/sample/final.patch",
            "--log-path",
            "tasks/sample/run.log",
        ],
    )
    assert result.exit_code == 0


def test_show_task_agent_view_hides_verbose_fields(tmp_path) -> None:
    runner = CliRunner()
    db_path = str(tmp_path / "runner.db")
    runner.invoke(deterministic, ["--db", db_path, "init-db"])
    created = runner.invoke(deterministic, ["--db", db_path, "create-task", "--title", "sample"])
    task_id = created.output.strip()
    show = runner.invoke(
        deterministic,
        ["--db", db_path, "show-task", "--task-id", task_id, "--view", "agent"],
    )
    assert show.exit_code == 0
    payload = json.loads(show.output)
    assert "task" in payload
    assert "events" in payload
    assert "log_path" not in payload["task"]["evidence"]


def test_sanitize_output_redacts_and_truncates() -> None:
    raw = "token=abc123\nAKIAABCDEFGHIJKLMNOP\n" + ("x" * 5000)
    out = _sanitize_output(raw)
    assert "AKIAABCDEFGHIJKLMNOP" not in out
    assert "token=abc123" not in out
    assert "[REDACTED]" in out
    assert "...[TRUNCATED]..." in out
