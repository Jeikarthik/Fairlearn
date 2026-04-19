"""Job status state machine with enforced transitions.

Every status change must go through `transition()` — no raw string assignment.
"""
from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    """Possible states for an audit job."""

    CREATED = "created"
    UPLOADED = "uploaded"
    CONFIGURED = "configured"
    VALIDATED = "validated"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    REPORTED = "reported"
    ARCHIVED = "archived"


# Allowed from → {to} transitions
_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.CREATED: {JobStatus.UPLOADED},
    JobStatus.UPLOADED: {JobStatus.CONFIGURED},
    JobStatus.CONFIGURED: {JobStatus.VALIDATED, JobStatus.QUEUED},  # can skip quality check
    JobStatus.VALIDATED: {JobStatus.QUEUED},
    JobStatus.QUEUED: {JobStatus.RUNNING},
    JobStatus.RUNNING: {JobStatus.COMPLETE, JobStatus.FAILED},
    JobStatus.FAILED: {JobStatus.QUEUED},  # retry
    JobStatus.COMPLETE: {JobStatus.REPORTED, JobStatus.ARCHIVED, JobStatus.QUEUED},  # re-run
    JobStatus.REPORTED: {JobStatus.ARCHIVED, JobStatus.QUEUED},
}


def allowed_transitions(current: JobStatus) -> list[str]:
    """Return the list of states reachable from *current*."""
    return sorted(s.value for s in _TRANSITIONS.get(current, set()))


def transition(current: JobStatus, target: JobStatus) -> JobStatus:
    """Validate a state transition and return the new status.

    Args:
        current: The current job status.
        target: The desired next status.

    Returns:
        The target status if the transition is valid.

    Raises:
        ValueError: If the transition is illegal.
    """
    if target not in _TRANSITIONS.get(current, set()):
        raise ValueError(
            f"Invalid transition from '{current.value}' to '{target.value}'. "
            f"Valid next states: {allowed_transitions(current)}"
        )
    return target
