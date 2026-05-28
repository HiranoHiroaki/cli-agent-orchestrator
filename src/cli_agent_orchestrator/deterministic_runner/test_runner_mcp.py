"""Allowlisted test-runner execution."""

import subprocess
import sys

ALLOWED_COMMANDS: dict[str, list[str]] = {
    "python-tests": [
        sys.executable,
        "-m",
        "pytest",
        "test/cli/commands/test_deterministic.py",
        "test/deterministic_runner/test_state_machine.py",
        "test/deterministic_runner/test_runner_features.py",
        "test/deterministic_runner/test_gateway_sidecar.py",
        "test/deterministic_runner/test_readonly_policy.py",
        "test/deterministic_runner/test_dispatch_policy.py",
        "test/deterministic_runner/test_debug_logging.py",
        "test/deterministic_runner/test_dispatch_gateway_e2e.py",
    ],
}


def run_allowlisted(key: str) -> subprocess.CompletedProcess[str]:
    command = ALLOWED_COMMANDS.get(key)
    if command is None:
        raise ValueError(f"blocked command key: {key}")
    return subprocess.run(command, capture_output=True, text=True, check=False)
