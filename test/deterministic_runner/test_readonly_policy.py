"""Tests for deterministic read-only MCP/tool policy."""

import pytest

from cli_agent_orchestrator.deterministic_runner.readonly import assert_readonly_policy


def test_readonly_policy_accepts_repo_read() -> None:
    assert_readonly_policy(
        agent_name="codex_worker",
        allowed_tools=["fs_read", "fs_list", "@repo-read"],
        mcp_servers=["repo-read"],
    )


def test_readonly_policy_rejects_write_tools() -> None:
    with pytest.raises(ValueError):
        assert_readonly_policy(
            agent_name="codex_worker",
            allowed_tools=["fs_read", "fs_write", "@repo-read"],
            mcp_servers=["repo-read"],
        )


def test_readonly_policy_requires_repo_read_only() -> None:
    with pytest.raises(ValueError):
        assert_readonly_policy(
            agent_name="codex_worker",
            allowed_tools=["fs_read", "fs_list", "@repo-read"],
            mcp_servers=["repo-read", "test-runner"],
        )
