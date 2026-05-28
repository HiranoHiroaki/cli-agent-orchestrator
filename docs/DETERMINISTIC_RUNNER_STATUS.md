# Deterministic Runner Status

## Goal
- Build local Codex/Claude/Ollama operation around a deterministic runner.
- Runner owns state transitions.
- Agents are proposal workers.
- Write paths are fail-closed with approval gates.
- Start MCP with read-only scope.

## Current Snapshot (2026-05-28)
- Fork baseline: `awslabs/cli-agent-orchestrator` -> `HiranoHiroaki/cli-agent-orchestrator`.
- Working branch: `codex/deterministic-runner-foundation`.
- Draft PR: `#1`.
- Main branch protection: enabled.

## Completed
1. Dispatch layer for Codex/Claude adapters:
- `src/cli_agent_orchestrator/deterministic_runner/dispatch.py`
- Lane policy integration and timeout handling.

2. Repo/file lock:
- `src/cli_agent_orchestrator/deterministic_runner/lock_manager.py`
- DB lock + lock file behavior.

3. Lane reject/timeout integration:
- `src/cli_agent_orchestrator/deterministic_runner/gateway.py`
- Immediate `LOCAL_MODEL_BUSY` reject, no wait loop.

4. State machine and failure visibility:
- `src/cli_agent_orchestrator/deterministic_runner/state_machine.py`
- `LOCAL_MODEL_BUSY` and `LOCAL_MODEL_TIMEOUT` transitions wired.
- Failure states/events persisted in SQLite.

5. Test-runner MCP allowlist:
- `src/cli_agent_orchestrator/deterministic_runner/test_runner_mcp.py`
- Explicit key allowlist only.

6. Patch queue -> approval -> apply:
- `src/cli_agent_orchestrator/deterministic_runner/db.py`
- `APPROVED` gate required, apply failures transition to `FAILED_CLOSED`.

7. Status checks + debug anchors + evidence validation:
- Workflow: `.github/workflows/deterministic-runner-checks.yml`
- Required check context on `main`: `deterministic-runner-checks`
- Debug anchors: `src/cli_agent_orchestrator/deterministic_runner/debug.py`
- Env flags:
  - `RUNNER_DEBUG=1`
  - `RUNNER_DEBUG_ANCHORS=anchor1,anchor2`
- Evidence guard:
  - Required keys: `prompt_path`, `constraints_path`, `decision_path`, `patch_path`, `log_path`
  - Missing evidence on sensitive transitions forces `FAILED_CLOSED`.

## In Progress / Recent Refactor
- Consolidated duplicate evidence key definitions into one source:
  - `REQUIRED_EVIDENCE_KEYS` in `db.py`.
- Centralized repeated state update/event write into:
  - `_transition_with_conn` in `db.py`.
- Reduced noisy evidence event output to only changed fields.

## Not Started (Next Phase)
1. Real sidecar connectivity:
- Connect runner gateway path to actual `openziti/llm-gateway` API.

2. MCP strict read-only runtime wiring:
- Pin to `repo-read` only in operational profile.

## Acceptance Mapping
- Runner-only transitions: satisfied.
- Immediate overload rejection: satisfied.
- Explicit failed state in DB: satisfied.
- Prompt/constraints/decision/patch/log evidence persistence: enforced and validated.

## Suggested Execution Line
1. Merge PR `#1` after deterministic check is green.
2. Add `openziti/llm-gateway` integration branch (separate PR).
3. Add read-only MCP profile lock-down branch (separate PR).

