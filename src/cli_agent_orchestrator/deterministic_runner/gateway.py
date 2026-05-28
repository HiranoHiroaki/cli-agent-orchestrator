"""Lane policies and overload/timeout signals."""

from dataclasses import dataclass
import json
from typing import Any

from cli_agent_orchestrator.deterministic_runner.debug import emit_anchor


@dataclass
class LanePolicy:
    timeout_ms: int
    max_queue: int
    reject_on_queue_full: bool


class LocalModelBusyError(RuntimeError):
    """Raised when queue is saturated and reject policy is enabled."""


class LocalModelTimeoutError(RuntimeError):
    """Raised when local model call exceeded lane timeout."""


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("config root must be object")
    return data


def load_lane_policy(config_path: str, lane_name: str) -> LanePolicy:
    cfg = _read_json(config_path)
    lanes = cfg.get("lanes", {})
    if not isinstance(lanes, dict):
        raise ValueError("lanes must be object")
    lane = lanes.get(lane_name, {})
    if not isinstance(lane, dict):
        raise ValueError(f"invalid lane config: {lane_name}")
    default_timeout_ms = int(cfg.get("default_timeout_ms", 45000))
    return LanePolicy(
        timeout_ms=int(lane.get("timeout_ms", default_timeout_ms)),
        max_queue=int(lane.get("max_queue", 1)),
        reject_on_queue_full=bool(lane.get("reject_on_queue_full", True)),
    )


def enforce_queue_reject(policy: LanePolicy, queue_depth: int, task_id: str = "") -> None:
    if policy.reject_on_queue_full and queue_depth >= policy.max_queue:
        if task_id:
            emit_anchor(
                "gateway.queue.reject",
                task_id,
                "RUNNING_AGENT",
                "LOCAL_MODEL_BUSY",
                {"queue_depth": queue_depth, "max_queue": policy.max_queue},
            )
        raise LocalModelBusyError("LOCAL_MODEL_BUSY")
