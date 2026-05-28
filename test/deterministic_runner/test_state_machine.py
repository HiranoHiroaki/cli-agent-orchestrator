"""Tests for deterministic runner state machine."""

from cli_agent_orchestrator.deterministic_runner.state_machine import can_transition


def test_local_model_busy_transition() -> None:
    assert can_transition("RUNNING_AGENT", "LOCAL_MODEL_BUSY")


def test_invalid_done_transition() -> None:
    assert not can_transition("CREATED", "DONE")
