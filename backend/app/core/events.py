"""Lightweight in-process event bus for decoupled post-action workflows.

Usage:
    from app.core.events import event_bus

    # Register listener
    @event_bus.on("audit.completed")
    def send_slack_notification(job_id: str, **kwargs):
        ...

    # Emit event
    event_bus.emit("audit.completed", job_id="abc-123")
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

Listener = Callable[..., Any]


class EventBus:
    """Simple synchronous event bus for service-to-service decoupling."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = defaultdict(list)

    def on(self, event_type: str) -> Callable[[Listener], Listener]:
        """Decorator to register a listener for *event_type*."""

        def decorator(fn: Listener) -> Listener:
            self._listeners[event_type].append(fn)
            return fn

        return decorator

    def emit(self, event_type: str, **kwargs: Any) -> None:
        """Fire all listeners registered for *event_type*.

        Listeners run synchronously and exceptions are logged but
        never propagated — an observer can't break the emitter.
        """
        for listener in self._listeners.get(event_type, []):
            try:
                listener(**kwargs)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Event listener %s failed for event '%s'",
                    listener.__name__,
                    event_type,
                )


# Singleton
event_bus = EventBus()
