"""Agent dispatch adapters for Codex/Claude."""

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

from cli_agent_orchestrator.deterministic_runner.debug import emit_anchor
from cli_agent_orchestrator.deterministic_runner.gateway import (
    LocalModelTimeoutError,
    enforce_queue_reject,
    load_lane_policy,
    probe_gateway_sidecar,
)
from cli_agent_orchestrator.deterministic_runner.readonly import assert_readonly_policy


@dataclass
class AgentConfig:
    command: str
    lane: str
    allowed_tools: list[str]
    mcp_servers: list[str]


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("config root must be object")
    return data


def load_agent(profile_path: str, agent_name: str) -> AgentConfig:
    cfg = _read_json(profile_path)
    agents = cfg.get("agents", {})
    if not isinstance(agents, dict):
        raise ValueError("agents must be object")
    agent = agents.get(agent_name)
    if not isinstance(agent, dict):
        raise ValueError(f"agent not found: {agent_name}")
    command = str(agent.get("command", "")).strip()
    lane = str(agent.get("lane", "")).strip()
    raw_tools = agent.get("allowed_tools", [])
    raw_mcp_servers = agent.get("mcp_servers", [])
    if not isinstance(raw_tools, list):
        raw_tools = []
    if not isinstance(raw_mcp_servers, list):
        raw_mcp_servers = []
    if not command or not lane:
        raise ValueError(f"agent config incomplete: {agent_name}")
    return AgentConfig(
        command=command,
        lane=lane,
        allowed_tools=[str(tool).strip() for tool in raw_tools if str(tool).strip()],
        mcp_servers=[str(name).strip() for name in raw_mcp_servers if str(name).strip()],
    )


def run_agent(
    profile_path: str,
    lane_config_path: str,
    agent_name: str,
    prompt_path: str,
    queue_depth: int,
    task_id: str = "",
    enforce_readonly_mcp: bool = True,
) -> subprocess.CompletedProcess[str]:
    agent = load_agent(profile_path, agent_name)
    if enforce_readonly_mcp:
        assert_readonly_policy(
            agent_name=agent_name,
            allowed_tools=agent.allowed_tools,
            mcp_servers=agent.mcp_servers,
        )
    lane_policy = load_lane_policy(lane_config_path, agent.lane)
    enforce_queue_reject(lane_policy, queue_depth, task_id=task_id)
    probe_gateway_sidecar(
        config_path=lane_config_path,
        lane_name=agent.lane,
        timeout_ms=lane_policy.timeout_ms,
        task_id=task_id,
    )
    command = shlex.split(agent.command, posix=False)
    command.extend(["--prompt-file", os.path.abspath(prompt_path)])
    if task_id:
        emit_anchor(
            "dispatch.start",
            task_id,
            "RUNNING_AGENT",
            "AGENT_DISPATCH_START",
            {"agent": agent_name, "lane": agent.lane},
        )
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=lane_policy.timeout_ms / 1000,
        )
        if task_id:
            emit_anchor(
                "dispatch.end",
                task_id,
                "RUNNING_AGENT",
                "AGENT_DISPATCH_END",
                {"agent": agent_name, "exit_code": result.returncode},
            )
        return result
    except subprocess.TimeoutExpired as exc:
        if task_id:
            emit_anchor(
                "dispatch.timeout",
                task_id,
                "LOCAL_MODEL_TIMEOUT",
                "LOCAL_MODEL_TIMEOUT",
                {"agent": agent_name},
            )
        raise LocalModelTimeoutError("LOCAL_MODEL_TIMEOUT") from exc
