"""Integration-style tests for dispatch-agent with gateway sidecar behavior."""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from click.testing import CliRunner

from cli_agent_orchestrator.cli.commands.deterministic import deterministic


class _GatewayHandler(BaseHTTPRequestHandler):
    mode = "ok"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        if self.mode == "busy":
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"queue full"}}')
            return
        if self.mode == "timeout":
            time.sleep(1.2)
            self.send_response(408)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            b'{"id":"ok","choices":[{"index":0,"message":{"role":"assistant","content":"ok"}}]}'
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def _start_gateway_server() -> tuple[HTTPServer, threading.Thread, int]:
    server = HTTPServer(("127.0.0.1", 0), _GatewayHandler)
    port = int(server.server_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def _create_fake_codex(tmp_path: Path) -> Path:
    if os.name == "nt":
        script_path = tmp_path / "codex.cmd"
        script_path.write_text("@echo off\r\necho ok\r\nexit /b 0\r\n", encoding="utf-8")
        return script_path
    script_path = tmp_path / "codex"
    script_path.write_text("#!/usr/bin/env sh\necho ok\n", encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def _write_profile(path: Path, command: str) -> None:
    path.write_text(
        json.dumps(
            {
                "agents": {
                    "codex_worker": {
                        "command": command,
                        "lane": "code",
                        "allowed_tools": ["fs_read", "fs_list", "@repo-read"],
                        "mcp_servers": ["repo-read"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _write_lane(path: Path, port: int, timeout_ms: int) -> None:
    path.write_text(
        json.dumps(
            {
                "default_timeout_ms": timeout_ms,
                "gateway": {
                    "enabled": True,
                    "base_url": f"http://127.0.0.1:{port}",
                    "health_path": "/health",
                    "chat_path": "/v1/chat/completions",
                    "probe_chat": True,
                    "busy_status_codes": [429, 503],
                },
                "lanes": {
                    "code": {
                        "timeout_ms": timeout_ms,
                        "max_queue": 2,
                        "reject_on_queue_full": True,
                        "model": "gpt-oss:120b",
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _prepare_task(runner: CliRunner, db_path: str, title: str = "e2e-task") -> str:
    runner.invoke(deterministic, ["--db", db_path, "init-db"])
    created = runner.invoke(deterministic, ["--db", db_path, "create-task", "--title", title])
    task_id = created.output.strip()
    runner.invoke(
        deterministic,
        ["--db", db_path, "set-state", "--task-id", task_id, "--state", "CONTEXT_COLLECTING"],
    )
    runner.invoke(
        deterministic,
        ["--db", db_path, "set-state", "--task-id", task_id, "--state", "READY_FOR_AGENT"],
    )
    return task_id


def _read_state(runner: CliRunner, db_path: str, task_id: str) -> str:
    shown = runner.invoke(deterministic, ["--db", db_path, "show-task", "--task-id", task_id])
    payload = json.loads(shown.output)
    return str(payload["task"]["state"])


def test_dispatch_agent_transitions_on_gateway_busy(tmp_path: Path) -> None:
    server, thread, port = _start_gateway_server()
    try:
        _GatewayHandler.mode = "busy"
        runner = CliRunner()
        db_path = str(tmp_path / "runner.db")
        profile_path = tmp_path / "agents.json"
        lane_path = tmp_path / "lanes.json"
        prompt_path = tmp_path / "prompt.md"
        codex_path = _create_fake_codex(tmp_path)
        prompt_path.write_text("hello", encoding="utf-8")
        _write_profile(profile_path, command=str(codex_path))
        _write_lane(lane_path, port, timeout_ms=1500)
        task_id = _prepare_task(runner, db_path, title="busy")

        result = runner.invoke(
            deterministic,
            [
                "--db",
                db_path,
                "dispatch-agent",
                "--task-id",
                task_id,
                "--agent",
                "codex_worker",
                "--profile",
                str(profile_path),
                "--lane-config",
                str(lane_path),
                "--prompt-path",
                str(prompt_path),
            ],
        )
        assert result.exit_code != 0
        assert _read_state(runner, db_path, task_id) == "LOCAL_MODEL_BUSY"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_dispatch_agent_transitions_on_gateway_timeout(tmp_path: Path) -> None:
    server, thread, port = _start_gateway_server()
    try:
        _GatewayHandler.mode = "timeout"
        runner = CliRunner()
        db_path = str(tmp_path / "runner.db")
        profile_path = tmp_path / "agents.json"
        lane_path = tmp_path / "lanes.json"
        prompt_path = tmp_path / "prompt.md"
        codex_path = _create_fake_codex(tmp_path)
        prompt_path.write_text("hello", encoding="utf-8")
        _write_profile(profile_path, command=str(codex_path))
        _write_lane(lane_path, port, timeout_ms=500)
        task_id = _prepare_task(runner, db_path, title="timeout")

        result = runner.invoke(
            deterministic,
            [
                "--db",
                db_path,
                "dispatch-agent",
                "--task-id",
                task_id,
                "--agent",
                "codex_worker",
                "--profile",
                str(profile_path),
                "--lane-config",
                str(lane_path),
                "--prompt-path",
                str(prompt_path),
            ],
        )
        assert result.exit_code != 0
        assert _read_state(runner, db_path, task_id) == "LOCAL_MODEL_TIMEOUT"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_dispatch_agent_success_with_gateway_probe(tmp_path: Path) -> None:
    server, thread, port = _start_gateway_server()
    try:
        _GatewayHandler.mode = "ok"
        runner = CliRunner()
        db_path = str(tmp_path / "runner.db")
        profile_path = tmp_path / "agents.json"
        lane_path = tmp_path / "lanes.json"
        prompt_path = tmp_path / "prompt.md"
        codex_path = _create_fake_codex(tmp_path)
        prompt_path.write_text("hello", encoding="utf-8")
        _write_profile(profile_path, command=str(codex_path))
        _write_lane(lane_path, port, timeout_ms=1500)
        task_id = _prepare_task(runner, db_path, title="ok")
        runner.invoke(
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

        result = runner.invoke(
            deterministic,
            [
                "--db",
                db_path,
                "dispatch-agent",
                "--task-id",
                task_id,
                "--agent",
                "codex_worker",
                "--profile",
                str(profile_path),
                "--lane-config",
                str(lane_path),
                "--prompt-path",
                str(prompt_path),
            ],
        )
        assert result.exit_code == 0
        assert _read_state(runner, db_path, task_id) == "PATCH_PROPOSED"
    finally:
        server.shutdown()
        thread.join(timeout=2)
