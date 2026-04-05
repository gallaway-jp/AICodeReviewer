"""GUI-side review execution coordinator.

Owns the execution-oriented behavior layered on top of the active review
runtime state, leaving :class:`ActiveReviewController` focused on the live
review state itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from aicodereviewer.execution import CallbackEventSink, ExecutionEvent, JobProgressUpdated

from .review_runtime import ActiveReviewController


@dataclass
class ReviewExecutionCoordinator:
    """Coordinate GUI review execution on top of an active review controller."""

    controller: ActiveReviewController

    def build_stream_handler(self, publish_status: Callable[[str], None]) -> Callable[[str], None]:
        """Return a token handler that updates the formatted review preview."""

        def _handler(token: str) -> None:
            preview = self.controller.record_stream_token(token)
            publish_status(f"\u23f3 {preview}")

        return _handler

    def activate_client(
        self,
        backend_name: str,
        create_client: Callable[[str], Any],
        publish_status: Callable[[str], None],
    ) -> Any:
        """Create, bind, and configure the backend client for a review run."""
        client = create_client(backend_name)
        self.controller.bind_client(client)
        self.controller.set_client_stream_callback(self.build_stream_handler(publish_status))
        return client

    def build_event_sink(
        self,
        publish_progress: Callable[[float, str], None],
    ) -> CallbackEventSink:
        """Return an event sink that publishes controller-owned progress state."""

        def _handle(event: ExecutionEvent) -> None:
            if not isinstance(event, JobProgressUpdated):
                return
            self.controller.record_progress_event(event)
            publish_progress(self.controller.progress_fraction, self.controller.progress_status_text)

        return CallbackEventSink(_handle)

    def classify_run_result(
        self,
        *,
        dry_run: bool,
        result: Any,
        runner: Any,
        cancel_requested: bool,
    ) -> "ReviewExecutionOutcome":
        """Classify the completed review run into a UI-facing outcome."""
        if cancel_requested:
            return ReviewExecutionOutcome(kind="cancelled")
        if dry_run:
            return ReviewExecutionOutcome(kind="dry_run_complete")
        if isinstance(result, list):
            return ReviewExecutionOutcome(kind="issues_found", issues=result, runner=runner)
        if result is None:
            return ReviewExecutionOutcome(kind="no_report")
        return ReviewExecutionOutcome(kind="completed")


@dataclass(frozen=True)
class ReviewExecutionOutcome:
    """Coordinator-classified outcome for one review execution."""

    kind: str
    issues: list[Any] | None = None
    runner: Any | None = None