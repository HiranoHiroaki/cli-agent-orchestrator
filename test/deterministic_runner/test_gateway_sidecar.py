"""Tests for openziti/llm-gateway sidecar probing."""

import json

import pytest
import requests

from cli_agent_orchestrator.deterministic_runner.gateway import (
    LocalModelBusyError,
    LocalModelTimeoutError,
    probe_gateway_sidecar,
)


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_probe_gateway_disabled(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "lane.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {"enabled": False},
                "lanes": {"code": {"model": "gpt-oss:120b", "timeout_ms": 1000, "max_queue": 1}},
            }
        ),
        encoding="utf-8",
    )

    def _boom(*args, **kwargs):
        raise AssertionError("requests should not be called")

    monkeypatch.setattr(requests, "get", _boom)
    monkeypatch.setattr(requests, "post", _boom)
    probe_gateway_sidecar(str(config_path), lane_name="code", timeout_ms=1000)


def test_probe_gateway_busy_maps_to_local_model_busy(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "lane.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {"enabled": True, "base_url": "http://127.0.0.1:8080"},
                "lanes": {"code": {"model": "gpt-oss:120b", "timeout_ms": 1000, "max_queue": 1}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(200, {"status": "ok"}))
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: _Resp(429, {"error": {"message": "queue full"}}),
    )

    with pytest.raises(LocalModelBusyError):
        probe_gateway_sidecar(str(config_path), lane_name="code", timeout_ms=1000)


def test_probe_gateway_timeout_maps_to_local_model_timeout(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "lane.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {"enabled": True, "base_url": "http://127.0.0.1:8080"},
                "lanes": {"code": {"model": "gpt-oss:120b", "timeout_ms": 1000, "max_queue": 1}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(200, {"status": "ok"}))

    def _timeout(*args, **kwargs):
        raise requests.Timeout("timeout")

    monkeypatch.setattr(requests, "post", _timeout)
    with pytest.raises(LocalModelTimeoutError):
        probe_gateway_sidecar(str(config_path), lane_name="code", timeout_ms=1000)


def test_probe_gateway_rejects_non_local_http_host(tmp_path) -> None:
    config_path = tmp_path / "lane.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {
                    "enabled": True,
                    "base_url": "http://example.com:8080",
                    "allowed_hosts": ["example.com"],
                    "allow_http_localhost_only": True,
                },
                "lanes": {"code": {"model": "gpt-oss:120b", "timeout_ms": 1000, "max_queue": 1}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError):
        probe_gateway_sidecar(str(config_path), lane_name="code", timeout_ms=1000)
