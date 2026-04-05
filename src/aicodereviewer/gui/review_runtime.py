"""GUI-side runtime helpers for review execution ownership."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from aicodereviewer.execution import JobProgressUpdated


@dataclass
class CancelableRuntimeController:
    """Base runtime owner for cancel-capable background workflows."""

    client: Any | None = None
    cancel_event: threading.Event | None = None
    running: bool = False
    _event_factory: type[threading.Event] = field(default=threading.Event, repr=False)

    def begin(self, cancel_event: threading.Event | None = None) -> threading.Event:
        """Mark the workflow as active and return its cancel event."""
        self.running = True
        self.cancel_event = cancel_event or self._event_factory()
        self.client = None
        return self.cancel_event

    def bind_client(self, client: Any | None) -> None:
        """Attach the backend client used by the active workflow."""
        self.client = client

    def clear_client(self) -> None:
        """Detach any currently bound backend client."""
        self.client = None

    def set_client_stream_callback(self, callback: Any | None) -> None:
        """Attach or clear the backend's streaming callback when supported."""
        if self.client is None or not hasattr(self.client, "set_stream_callback"):
            return
        try:
            self.client.set_stream_callback(callback)
        except Exception as exc:
            logger.warning("Failed to update backend stream callback: %s", exc)

    def request_cancel(self) -> None:
        """Signal cancellation for the active workflow when possible."""
        if self.cancel_event is not None:
            self.cancel_event.set()
        if self.client is not None and hasattr(self.client, "cancel"):
            self.client.cancel()

    def release_client(self) -> None:
        """Detach and close the currently bound backend client when present."""
        client = self.client
        self.clear_client()
        if client is None:
            return
        if hasattr(client, "set_stream_callback"):
            try:
                client.set_stream_callback(None)
            except Exception as exc:
                logger.warning("Failed to clear backend stream callback: %s", exc)
        if hasattr(client, "close"):
            try:
                client.close()
            except Exception as exc:
                logger.warning("Failed to close backend: %s", exc)

    def finish(self) -> None:
        """Mark the active workflow as no longer running."""
        self.running = False
        self.cancel_event = None


@dataclass
class ActiveReviewController(CancelableRuntimeController):
    """Own the GUI's current review execution binding.

    The GUI still presents a single-active-review experience, but this object
    centralizes the execution-owned state that later queueing work can replace
    or extend without making widget mixins coordinate through ambient fields.
    """

    runner: Any | None = None
    progress_message: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    elapsed_started_at: float | None = None
    elapsed_after_id: str | None = None
    stream_preview_text: str = ""

    def begin(self, cancel_event: threading.Event | None = None) -> threading.Event:
        """Start a review execution and reset its progress snapshot."""
        active_cancel_event = super().begin(cancel_event)
        self.reset_progress()
        return active_cancel_event

    def bind_runner(self, runner: Any | None) -> None:
        """Attach the runner that owns finalize-ready state for this review."""
        self.runner = runner

    def clear_runner(self) -> None:
        """Clear the runner binding used by restored or completed sessions."""
        self.runner = None

    @property
    def progress_fraction(self) -> float:
        """Return normalized review progress for widget updates."""
        if self.progress_total <= 0:
            return 0.0
        return min(1.0, max(0.0, self.progress_current / self.progress_total))

    def record_progress(self, *, message: str, current: int, total: int) -> None:
        """Record the latest execution progress update for this review."""
        self.progress_message = message
        self.progress_current = current
        self.progress_total = total

    def record_progress_event(self, event: JobProgressUpdated) -> None:
        """Apply a GUI review progress event to the controller snapshot."""
        self.record_progress(
            message=event.message,
            current=event.current,
            total=event.total,
        )

    def record_stream_token(self, token: str) -> str:
        """Accumulate streamed review output and return its preview text."""
        self.stream_preview_text = (self.stream_preview_text + token)[-120:].replace("\n", " ")
        return self.stream_preview_text

    @property
    def progress_status_text(self) -> str:
        """Return the formatted status-bar text for the latest progress update."""
        if self.progress_message is None:
            return ""
        return f"{self.progress_message} {self.progress_current}/{self.progress_total}"

    def reset_progress(self) -> None:
        """Clear the latest review progress snapshot."""
        self.progress_message = None
        self.progress_current = 0
        self.progress_total = 0
        self.stream_preview_text = ""

    def bind_elapsed_after(self, after_id: str | None) -> None:
        """Store the Tk timer id used by the elapsed-time ticker."""
        self.elapsed_after_id = after_id

    def start_elapsed(self, started_at: float) -> None:
        """Store the monotonic start time for the active review."""
        self.elapsed_started_at = started_at

    def clear_elapsed(self) -> None:
        """Clear elapsed-time bookkeeping for the active review."""
        self.elapsed_started_at = None
        self.elapsed_after_id = None

    def finish(self) -> None:
        """Mark the active review as finished and clear progress state."""
        super().finish()
        self.reset_progress()


@dataclass
class ActiveAIFixController(CancelableRuntimeController):
    """Own the GUI's current AI Fix execution binding.

    AI Fix still presents its dedicated preview/apply flow, but this object
    centralizes the background state that was previously coordinated through
    mixin-local booleans and ambient client/cancel fields.
    """


@dataclass
class ActiveReviewChangesController:
    """Own the GUI's current Review Changes verification binding."""

    running: bool = False

    def begin(self) -> None:
        """Mark Review Changes verification as active."""
        self.running = True

    def finish(self) -> None:
        """Mark Review Changes verification as finished."""
        self.running = False


@dataclass
class ActiveModelRefreshController:
    """Own backend model-refresh deduplication for GUI combobox updates."""

    in_progress: set[str] = field(default_factory=set)

    def begin(self, backend_name: str) -> bool:
        """Return False when the backend is already refreshing, else mark it active."""
        if backend_name in self.in_progress:
            return False
        self.in_progress.add(backend_name)
        return True

    def finish(self, backend_name: str) -> None:
        """Mark backend model refresh as finished."""
        self.in_progress.discard(backend_name)

    def is_refreshing(self, backend_name: str) -> bool:
        """Return True when the given backend model list is already refreshing."""
        return backend_name in self.in_progress


@dataclass
class ActiveHealthCheckController:
    """Own the GUI's current backend health-check binding."""

    backend_name: str | None = None
    timer: threading.Timer | None = None
    countdown_ends_at: float | None = None
    countdown_after_id: str | None = None

    @property
    def running(self) -> bool:
        """Return True when a health check is currently active."""
        return self.backend_name is not None

    def begin(self, backend_name: str) -> None:
        """Mark a health check as active for the given backend."""
        self.backend_name = backend_name

    def bind_timer(self, timer: threading.Timer | None) -> None:
        """Attach the timeout timer used by the active health check."""
        self.timer = timer

    def bind_countdown_after(self, after_id: str | None) -> None:
        """Attach the Tk timer id used by the visible health countdown."""
        self.countdown_after_id = after_id

    def start_countdown(self, *, ends_at: float) -> None:
        """Record the visible health-check countdown deadline."""
        self.countdown_ends_at = ends_at

    def clear_countdown(self) -> None:
        """Clear visible countdown bookkeeping for the active health check."""
        self.countdown_ends_at = None
        self.countdown_after_id = None

    def cancel_timer(self) -> None:
        """Cancel and detach the active timeout timer when present."""
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def matches(self, backend_name: str) -> bool:
        """Return True when the active health check targets the given backend."""
        return self.backend_name == backend_name

    def finish(self) -> None:
        """Mark the active health check as finished and clear its timer."""
        self.cancel_timer()
        self.clear_countdown()
        self.backend_name = None


@dataclass
class ReviewSubmissionSelectionController:
    """Own the currently selected scheduler submission for queue-oriented GUI views."""

    submission_id: str | None = None
    label_to_submission_id: dict[str, str] = field(default_factory=dict)

    def select(self, submission_id: str | None) -> str | None:
        """Select the given submission id, or clear the selection."""
        self.submission_id = submission_id
        return self.submission_id

    def bind_labels(self, label_to_submission_id: Mapping[str, str]) -> dict[str, str]:
        """Store the current queue-label mapping used by the GUI selection surface."""
        self.label_to_submission_id = dict(label_to_submission_id)
        return dict(self.label_to_submission_id)

    def select_label(self, selected_label: str) -> str | None:
        """Select a submission id using the current queue-label mapping."""
        return self.select(self.label_to_submission_id.get(selected_label))

    def sync(self, available_submission_ids: list[str]) -> str | None:
        """Keep the selection aligned with the currently available submissions."""
        if self.submission_id in available_submission_ids:
            return self.submission_id
        self.submission_id = available_submission_ids[0] if available_submission_ids else None
        return self.submission_id

    def sync_snapshots(self, snapshots: Sequence[Any]) -> Any | None:
        """Keep the selection aligned with visible snapshots and return the selected one."""
        selected_id = self.sync([
            getattr(snapshot, "submission_id") for snapshot in snapshots
        ])
        for snapshot in snapshots:
            if getattr(snapshot, "submission_id") == selected_id:
                return snapshot
        return None