"""Tests for deterministic dispatch policy enforcement."""

import json

import pytest

from cli_agent_orchestrator.deterministic_runner.dispatch import run_agent


def test_run_agent_blocks_when_readonly_policy_missing(tmp_path) -> None:
    profile_path = tmp_path / "agents.json"
    lane_path = tmp_path / "lanes.json"
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("hello", encoding="utf-8")
    profile_path.write_text(
        json.dumps(
            {
                "agents": {
                    "codex_worker": {
                        "command": "echo hello",
                        "lane": "code",
                        "allowed_tools": ["fs_read", "fs_list"],
                        "mcp_servers": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    lane_path.write_text(
        json.dumps({"default_timeout_ms": 1000, "lanes": {"code": {"max_queue": 2}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        run_agent(
            profile_path=str(profile_path),
            lane_config_path=str(lane_path),
            agent_name="codex_worker",
            prompt_path=str(prompt_path),
            queue_depth=0,
            task_id="t1",
            enforce_readonly_mcp=True,
        )

