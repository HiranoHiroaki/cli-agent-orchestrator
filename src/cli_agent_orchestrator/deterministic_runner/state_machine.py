"""State machine constraints for deterministic runner."""

from typing import Dict

STATES = {
    "CREATED",
    "CONTEXT_COLLECTING",
    "READY_FOR_AGENT",
    "RUNNING_AGENT",
    "WAITING_LOCAL_MODEL",
    "LOCAL_MODEL_BUSY",
    "LOCAL_MODEL_TIMEOUT",
    "NEEDS_HUMAN_DECISION",
    "PATCH_PROPOSED",
    "TESTING",
    "DONE",
    "FAILED_CLOSED",
}

TRANSITIONS: Dict[str, set[str]] = {
    "CREATED": {"CONTEXT_COLLECTING", "FAILED_CLOSED"},
    "CONTEXT_COLLECTING": {"READY_FOR_AGENT", "FAILED_CLOSED"},
    "READY_FOR_AGENT": {"RUNNING_AGENT", "FAILED_CLOSED"},
    "RUNNING_AGENT": {
        "WAITING_LOCAL_MODEL",
        "LOCAL_MODEL_BUSY",
        "LOCAL_MODEL_TIMEOUT",
        "PATCH_PROPOSED",
        "NEEDS_HUMAN_DECISION",
        "FAILED_CLOSED",
    },
    "WAITING_LOCAL_MODEL": {
        "RUNNING_AGENT",
        "LOCAL_MODEL_BUSY",
        "LOCAL_MODEL_TIMEOUT",
        "NEEDS_HUMAN_DECISION",
    },
    "LOCAL_MODEL_BUSY": {"READY_FOR_AGENT", "NEEDS_HUMAN_DECISION", "FAILED_CLOSED"},
    "LOCAL_MODEL_TIMEOUT": {"RUNNING_AGENT", "NEEDS_HUMAN_DECISION", "FAILED_CLOSED"},
    "NEEDS_HUMAN_DECISION": {"READY_FOR_AGENT", "FAILED_CLOSED"},
    "PATCH_PROPOSED": {"TESTING", "NEEDS_HUMAN_DECISION", "FAILED_CLOSED"},
    "TESTING": {"DONE", "PATCH_PROPOSED", "NEEDS_HUMAN_DECISION", "FAILED_CLOSED"},
    "DONE": set(),
    "FAILED_CLOSED": set(),
}


def is_valid_state(state: str) -> bool:
    return state in STATES


def can_transition(from_state: str, to_state: str) -> bool:
    if from_state not in TRANSITIONS:
        return False
    return to_state in TRANSITIONS[from_state]

