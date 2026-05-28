"""Lane policies and overload/timeout signals."""

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import urlparse

import requests

from cli_agent_orchestrator.deterministic_runner.debug import emit_anchor

LOCAL_GATEWAY_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass
class LanePolicy:
    timeout_ms: int
    max_queue: int
    reject_on_queue_full: bool


class LocalModelBusyError(RuntimeError):
    """Raised when queue is saturated and reject policy is enabled."""


class LocalModelTimeoutError(RuntimeError):
    """Raised when local model call exceeded lane timeout."""


@dataclass
class GatewayConfig:
    enabled: bool
    base_url: str
    health_path: str
    chat_path: str
    api_key: str
    probe_chat: bool
    probe_prompt: str
    probe_max_tokens: int
    busy_status_codes: tuple[int, ...]
    allowed_hosts: tuple[str, ...]
    allow_http_localhost_only: bool


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


def load_gateway_config(config_path: str) -> GatewayConfig:
    cfg = _read_json(config_path)
    raw = cfg.get("gateway", {})
    if not isinstance(raw, dict):
        raw = {}
    busy_codes_raw = raw.get("busy_status_codes", [429, 503])
    if not isinstance(busy_codes_raw, list):
        busy_codes_raw = [429, 503]
    allowed_hosts_raw = raw.get("allowed_hosts", sorted(LOCAL_GATEWAY_HOSTS))
    if not isinstance(allowed_hosts_raw, list):
        allowed_hosts_raw = sorted(LOCAL_GATEWAY_HOSTS)
    allowed_hosts = tuple(str(host).strip().lower() for host in allowed_hosts_raw if str(host).strip())
    if not allowed_hosts:
        allowed_hosts = tuple(sorted(LOCAL_GATEWAY_HOSTS))
    return GatewayConfig(
        enabled=bool(raw.get("enabled", False)),
        base_url=str(raw.get("base_url", "")).strip().rstrip("/"),
        health_path=str(raw.get("health_path", "/health")).strip(),
        chat_path=str(raw.get("chat_path", "/v1/chat/completions")).strip(),
        api_key=str(raw.get("api_key", "")).strip(),
        probe_chat=bool(raw.get("probe_chat", True)),
        probe_prompt=str(raw.get("probe_prompt", "ping")).strip() or "ping",
        probe_max_tokens=int(raw.get("probe_max_tokens", 1)),
        busy_status_codes=tuple(int(code) for code in busy_codes_raw),
        allowed_hosts=allowed_hosts,
        allow_http_localhost_only=bool(raw.get("allow_http_localhost_only", True)),
    )


def probe_gateway_sidecar(
    config_path: str,
    lane_name: str,
    timeout_ms: int,
    task_id: str = "",
) -> None:
    lane_cfg = _read_json(config_path).get("lanes", {})
    lane = lane_cfg.get(lane_name, {}) if isinstance(lane_cfg, dict) else {}
    gateway = load_gateway_config(config_path)
    if not gateway.enabled:
        return
    if not gateway.base_url:
        raise RuntimeError("GATEWAY_CONFIG_ERROR: base_url missing")
    _validate_gateway_destination(gateway)
    model = str(lane.get("model", "")).strip() if isinstance(lane, dict) else ""
    timeout_sec = max(1.0, timeout_ms / 1000)
    headers = {"Content-Type": "application/json"}
    if gateway.api_key:
        headers["Authorization"] = f"Bearer {gateway.api_key}"
    try:
        health = requests.get(
            f"{gateway.base_url}{gateway.health_path}",
            timeout=min(timeout_sec, 5.0),
        )
    except requests.Timeout as exc:
        raise LocalModelTimeoutError("LOCAL_MODEL_TIMEOUT") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"GATEWAY_UNREACHABLE: {exc}") from exc
    if health.status_code != 200:
        raise RuntimeError(f"GATEWAY_UNHEALTHY: {health.status_code}")
    if task_id:
        emit_anchor(
            "gateway.health.ok",
            task_id,
            "RUNNING_AGENT",
            "GATEWAY_HEALTH_OK",
            {"status_code": health.status_code},
        )
    if not gateway.probe_chat or not model:
        return
    body = {
        "model": model,
        "messages": [{"role": "user", "content": gateway.probe_prompt}],
        "max_tokens": gateway.probe_max_tokens,
        "stream": False,
    }
    try:
        resp = requests.post(
            f"{gateway.base_url}{gateway.chat_path}",
            headers=headers,
            json=body,
            timeout=timeout_sec,
        )
    except requests.Timeout as exc:
        raise LocalModelTimeoutError("LOCAL_MODEL_TIMEOUT") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"GATEWAY_REQUEST_FAILED: {exc}") from exc

    if resp.status_code in gateway.busy_status_codes:
        raise LocalModelBusyError("LOCAL_MODEL_BUSY")
    if resp.status_code in {408, 504}:
        raise LocalModelTimeoutError("LOCAL_MODEL_TIMEOUT")

    response_text = ""
    try:
        payload = resp.json()
        response_text = json.dumps(payload, ensure_ascii=True).lower()
    except ValueError:
        response_text = resp.text.lower()

    if "local_model_busy" in response_text or "queue" in response_text and "full" in response_text:
        raise LocalModelBusyError("LOCAL_MODEL_BUSY")
    if "timeout" in response_text and resp.status_code >= 400:
        raise LocalModelTimeoutError("LOCAL_MODEL_TIMEOUT")
    if resp.status_code >= 400:
        raise RuntimeError(f"GATEWAY_ERROR: {resp.status_code}")

    if task_id:
        emit_anchor(
            "gateway.probe.ok",
            task_id,
            "RUNNING_AGENT",
            "GATEWAY_PROBE_OK",
            {"status_code": resp.status_code, "lane": lane_name},
        )


def _validate_gateway_destination(gateway: GatewayConfig) -> None:
    parsed = urlparse(gateway.base_url)
    host = (parsed.hostname or "").strip().lower()
    scheme = (parsed.scheme or "").strip().lower()
    if scheme not in {"http", "https"}:
        raise RuntimeError(f"GATEWAY_CONFIG_ERROR: invalid scheme '{scheme}'")
    if not host:
        raise RuntimeError("GATEWAY_CONFIG_ERROR: host missing")
    if host not in set(gateway.allowed_hosts):
        raise RuntimeError(f"GATEWAY_CONFIG_ERROR: host '{host}' not allowed")
    if scheme == "http" and gateway.allow_http_localhost_only and host not in LOCAL_GATEWAY_HOSTS:
        raise RuntimeError(f"GATEWAY_CONFIG_ERROR: insecure http host '{host}' is not allowed")
