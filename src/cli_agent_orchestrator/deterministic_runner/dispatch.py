"""Agent dispatch adapters for Codex/Claude."""

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

from cli_agent_orchestrator.deterministic_runner.gateway import (
    LocalModelTimeoutError,
    enforce_queue_reject,
    load_lane_policy,
)


@dataclass
class AgentConfig:
    command: str
    lane: str


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
    if not command or not lane:
        raise ValueError(f"agent config incomplete: {agent_name}")
    return AgentConfig(command=command, lane=lane)


def run_agent(
    profile_path: str,
    lane_config_path: str,
    agent_name: str,
    prompt_path: str,
    queue_depth: int,
) -> subprocess.CompletedProcess[str]:
    agent = load_agent(profile_path, agent_name)
    lane_policy = load_lane_policy(lane_config_path, agent.lane)
    enforce_queue_reject(lane_policy, queue_depth)
    command = shlex.split(agent.command, posix=False)
    command.extend(["--prompt-file", os.path.abspath(prompt_path)])
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=lane_policy.timeout_ms / 1000,
        )
    except subprocess.TimeoutExpired as exc:
        raise LocalModelTimeoutError("LOCAL_MODEL_TIMEOUT") from exc

