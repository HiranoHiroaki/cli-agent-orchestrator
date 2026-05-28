"""Allowlisted test-runner execution."""

import subprocess
import sys

ALLOWED_COMMANDS: dict[str, list[str]] = {
    "python-tests": [sys.executable, "-m", "pytest", "test/cli/commands/test_deterministic.py"],
}


def run_allowlisted(key: str) -> subprocess.CompletedProcess[str]:
    command = ALLOWED_COMMANDS.get(key)
    if command is None:
        raise ValueError(f"blocked command key: {key}")
    return subprocess.run(command, capture_output=True, text=True, check=False)

