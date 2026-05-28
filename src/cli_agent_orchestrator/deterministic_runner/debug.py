"""Debug anchor utilities for deterministic runner."""

import json
import logging
import os

LOGGER = logging.getLogger("deterministic_runner")


def _is_debug_enabled() -> bool:
    return os.getenv("RUNNER_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}


def _anchor_allowed(anchor_id: str) -> bool:
    allowlist = os.getenv("RUNNER_DEBUG_ANCHORS", "").strip()
    if not allowlist:
        return True
    allowed = {item.strip() for item in allowlist.split(",") if item.strip()}
    return anchor_id in allowed


def emit_anchor(anchor_id: str, task_id: str, state: str, event_type: str, detail: dict) -> None:
    if not _is_debug_enabled() or not _anchor_allowed(anchor_id):
        return
    payload = {
        "anchor_id": anchor_id,
        "task_id": task_id,
        "state": state,
        "event_type": event_type,
        "detail": detail,
    }
    LOGGER.info("RUNNER_ANCHOR %s", json.dumps(payload, ensure_ascii=True))
