"""Typed execution events and sinks for review runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Protocol

from .models import JobState, ReviewExecutionResult


@dataclass(frozen=True)
class ExecutionEvent:
    """Base execution event."""

    job_id: str
    kind: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class JobStateChanged(ExecutionEvent):
    """State-transition event for a review job."""

    previous_state: JobState | None = None
    new_state: JobState = "created"
    message: str | None = None


@dataclass(frozen=True)
class JobProgressUpdated(ExecutionEvent):
    """Progress event emitted during issue collection."""

    current: int = 0
    total: int = 0
    message: str = ""


@dataclass(frozen=True)
class JobResultAvailable(ExecutionEvent):
    """Final result event for a finished review job."""

    result: ReviewExecutionResult | None = None


@dataclass(frozen=True)
class JobFailed(ExecutionEvent):
    """Failure event for a review job."""

    error_message: str = ""
    exception_type: str | None = None


class ExecutionEventSink(Protocol):
    """Protocol for receiving execution events."""

    def emit(self, event: ExecutionEvent) -> None:
        """Handle one execution event."""


class NullEventSink:
    """Event sink that ignores all events."""

    def emit(self, event: ExecutionEvent) -> None:
        del event


class CallbackEventSink:
    """Event sink backed by a Python callback."""

    def __init__(self, callback: Callable[[ExecutionEvent], None]) -> None:
        self._callback = callback

    def emit(self, event: ExecutionEvent) -> None:
        self._callback(event)


class CompositeEventSink:
    """Fan out execution events to multiple sinks."""

    def __init__(self, *sinks: ExecutionEventSink) -> None:
        self._sinks = [sink for sink in sinks if sink is not None]

    def emit(self, event: ExecutionEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)