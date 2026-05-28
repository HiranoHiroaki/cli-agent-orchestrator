"""Tests for deterministic debug anchor behavior."""

import logging

from cli_agent_orchestrator.deterministic_runner.debug import emit_anchor


def test_emit_anchor_disabled_by_default(caplog, monkeypatch) -> None:
    monkeypatch.delenv("RUNNER_DEBUG", raising=False)
    monkeypatch.delenv("RUNNER_DEBUG_ANCHORS", raising=False)
    with caplog.at_level(logging.INFO, logger="deterministic_runner"):
        emit_anchor("dispatch.start", "task-1", "RUNNING_AGENT", "START", {})
    assert "RUNNER_ANCHOR" not in caplog.text


def test_emit_anchor_respects_allowlist(caplog, monkeypatch) -> None:
    monkeypatch.setenv("RUNNER_DEBUG", "1")
    monkeypatch.setenv("RUNNER_DEBUG_ANCHORS", "dispatch.end")
    with caplog.at_level(logging.INFO, logger="deterministic_runner"):
        emit_anchor("dispatch.start", "task-1", "RUNNING_AGENT", "START", {})
        emit_anchor("dispatch.end", "task-1", "RUNNING_AGENT", "END", {})
    assert "dispatch.start" not in caplog.text
    assert "dispatch.end" in caplog.text

