"""Scheduler-facing GUI review execution boundary.

Coordinates GUI submission callbacks above the shared execution runtime so the
GUI queue and local HTTP API observe the same live jobs.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Callable

from aicodereviewer.execution import (
    CallbackEventSink,
    JobResultAvailable,
    JobStateChanged,
    PendingReportContext,
    ReviewExecutionResult,
    ReviewExecutionRuntime,
    ReviewJob,
    ReviewRequest,
)

from .review_execution_coordinator import ReviewExecutionOutcome
from .review_execution_facade import ReviewExecutionFacade


logger = logging.getLogger(__name__)


@dataclass
class ReviewExecutionSubmission:
    """Accepted review submission tracked by the scheduler boundary."""

    submission_id: str | int
    submission_kind: str
    cancel_event: threading.Event | None = None
    status: str = "queued"


@dataclass(frozen=True)
class ReviewExecutionSubmissionSnapshot:
    """Immutable UI-facing snapshot of one scheduler-tracked submission."""

    submission_id: str | int
    submission_kind: str
    status: str
    cancel_requested: bool
    is_active: bool
    thread_attached: bool
    completed_at: datetime | None = None


@dataclass
class _TrackedReviewExecution:
    """Internal callback bundle tracked for one runtime-backed GUI submission."""

    submission_kind: str
    request: ReviewRequest | None
    execute_run: Callable[[ReviewJob, threading.Event, CallbackEventSink], ReviewExecutionOutcome]
    on_started: Callable[[ReviewExecutionSubmission], None]
    on_outcome: Callable[[ReviewExecutionOutcome], None]
    on_error: Callable[[Exception], None]
    on_finished: Callable[[], None]
    started: bool = False
    outcome: ReviewExecutionOutcome | None = None


@dataclass
class _LegacyTrackedReviewExecution:
    """Internal callback bundle tracked for compatibility-mode scheduler tests."""

    submission: ReviewExecutionSubmission
    execute_run: Callable[..., ReviewExecutionOutcome]
    on_started: Callable[[ReviewExecutionSubmission], None]
    on_outcome: Callable[[ReviewExecutionOutcome], None]
    on_error: Callable[[Exception], None]
    on_finished: Callable[[], None]
    thread: Any | None = None
    reserved_active: bool = False
    starting: bool = False


@dataclass
class ReviewExecutionScheduler:
    """Adapt GUI queue callbacks onto the shared execution runtime."""

    facade: ReviewExecutionFacade
    runtime: ReviewExecutionRuntime | None = None
    _thread_factory: Callable[..., Any] = threading.Thread
    _tracked: dict[str, _TrackedReviewExecution] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _legacy_tracked: dict[str | int, _LegacyTrackedReviewExecution] = field(default_factory=dict, init=False, repr=False)
    _legacy_queued_submission_ids: list[str | int] = field(default_factory=list, init=False, repr=False)
    _legacy_active_submission_id: str | int | None = field(default=None, init=False, repr=False)
    _legacy_next_submission_id: int = field(default=1, init=False, repr=False)

    @property
    def active_submission_id(self) -> str | None:
        """Return the currently active scheduler submission id, if any."""
        if self._is_legacy_mode:
            return self._legacy_active_submission_id
        active_snapshot = self.get_active_submission_snapshot()
        return None if active_snapshot is None else active_snapshot.submission_id

    @property
    def queued_submission_ids(self) -> tuple[str, ...]:
        """Return the accepted submissions that are still pending dispatch."""
        if self._is_legacy_mode:
            return tuple(self._legacy_queued_submission_ids)
        return tuple(
            snapshot.submission_id
            for snapshot in self.list_submission_snapshots()
            if snapshot.status == "queued"
        )

    def get_active_submission_snapshot(self) -> ReviewExecutionSubmissionSnapshot | None:
        """Return a snapshot of the currently active submission, if any."""
        snapshots = self.list_submission_snapshots()
        return next((snapshot for snapshot in snapshots if snapshot.is_active), None)

    def get_submission_snapshot(self, submission_id: str) -> ReviewExecutionSubmissionSnapshot | None:
        """Return a snapshot for the active or queued submission matching the id."""
        if self._is_legacy_mode:
            with self._lock:
                tracked = self._legacy_tracked.get(submission_id)
                return None if tracked is None else self._build_legacy_submission_snapshot(tracked)
        return next(
            (
                snapshot
                for snapshot in self.list_submission_snapshots()
                if snapshot.submission_id == submission_id
            ),
            None,
        )

    def list_submission_snapshots(self) -> tuple[ReviewExecutionSubmissionSnapshot, ...]:
        """Return active and queued submission snapshots in dispatch order."""
        if self._is_legacy_mode:
            with self._lock:
                snapshots: list[ReviewExecutionSubmissionSnapshot] = []
                if self._legacy_active_submission_id is not None:
                    active = self._legacy_tracked.get(self._legacy_active_submission_id)
                    if active is not None:
                        snapshots.append(self._build_legacy_submission_snapshot(active))
                for submission_id in self._legacy_queued_submission_ids:
                    queued = self._legacy_tracked.get(submission_id)
                    if queued is not None:
                        snapshots.append(self._build_legacy_submission_snapshot(queued))
                return tuple(snapshots)
        jobs = [job for job in self.runtime.list_jobs() if self._should_surface_job(job)]
        jobs.sort(key=self._job_sort_key)
        return tuple(self._build_submission_snapshot(job) for job in jobs)

    def submit_run(
        self,
        *,
        request: ReviewRequest | None = None,
        submission_kind: str = "review",
        execute_run: Callable[..., ReviewExecutionOutcome],
        on_started: Callable[[ReviewExecutionSubmission], None] | None = None,
        on_outcome: Callable[[ReviewExecutionOutcome], None],
        on_error: Callable[[Exception], None],
        on_finished: Callable[[], None],
    ) -> ReviewExecutionSubmission:
        """Accept one GUI submission and register callbacks against a runtime job."""
        if self._is_legacy_mode:
            return self._submit_run_legacy(
                submission_kind=submission_kind,
                execute_run=execute_run,
                on_started=on_started,
                on_outcome=on_outcome,
                on_error=on_error,
                on_finished=on_finished,
            )
        if request is None:
            raise ValueError("Runtime-backed scheduler submissions require a review request")
        tracked = _TrackedReviewExecution(
            submission_kind=submission_kind,
            request=request,
            execute_run=execute_run,
            on_started=on_started or (lambda _submission: None),
            on_outcome=on_outcome,
            on_error=on_error,
            on_finished=on_finished,
        )
        controller = self.facade.coordinator.controller

        def _handle_started(job: ReviewJob, cancel_event: threading.Event) -> None:
            controller.begin(cancel_event)
            submission = ReviewExecutionSubmission(
                submission_id=job.job_id,
                submission_kind=submission_kind,
                cancel_event=cancel_event,
                status=self._job_status(job),
            )
            tracked.started = True
            tracked.on_started(submission)

        def _execute(job: ReviewJob, sink: CallbackEventSink, cancel_event: threading.Event) -> None:
            tracked.outcome = tracked.execute_run(job, cancel_event, sink)
            self._normalize_runtime_job_outcome(job, tracked.outcome, sink, cancel_event)

        def _handle_finished(job: ReviewJob, error: Exception | None) -> None:
            try:
                if error is None:
                    tracked.on_outcome(tracked.outcome or self._fallback_outcome(job))
                elif job.state == "cancelled":
                    tracked.on_outcome(ReviewExecutionOutcome(kind="cancelled"))
                else:
                    tracked.on_error(error)
            finally:
                controller.finish()
                controller.release_client()
                with self._lock:
                    self._tracked.pop(job.job_id, None)
                tracked.on_finished()

        job = self.runtime.submit_job(
            request,
            auto_finalize=False,
            executor=_execute,
            on_started=_handle_started,
            on_finished=_handle_finished,
        )
        with self._lock:
            self._tracked[job.job_id] = tracked
        return ReviewExecutionSubmission(
            submission_id=job.job_id,
            submission_kind=submission_kind,
            status=self._display_job_status(job),
        )

    def cancel_submission(self, submission_id: str) -> bool:
        """Cancel a queued or active runtime-backed GUI submission."""
        if self._is_legacy_mode:
            return self._cancel_submission_legacy(submission_id)
        snapshot = self.get_submission_snapshot(submission_id)
        if snapshot is None:
            return False
        if snapshot.is_active:
            self.facade.coordinator.controller.request_cancel()
        if not self.runtime.cancel_job(submission_id):
            return False
        with self._lock:
            tracked = self._tracked.get(submission_id)
            if tracked is not None and not tracked.started:
                self._tracked.pop(submission_id, None)
                tracked.on_outcome(ReviewExecutionOutcome(kind="cancelled"))
                tracked.on_finished()
        return True

    def _build_submission_snapshot(
        self,
        job: ReviewJob,
    ) -> ReviewExecutionSubmissionSnapshot:
        """Build an immutable UI-facing snapshot from runtime job state."""
        queue_position = self.runtime.get_queue_position(job.job_id)
        status = self._display_job_status(job, queue_position=queue_position)
        is_terminal = status in {"completed", "cancelled", "failed"}
        return ReviewExecutionSubmissionSnapshot(
            submission_id=job.job_id,
            submission_kind=("dry_run" if job.request.dry_run else "review"),
            status=status,
            cancel_requested=self.runtime.cancel_requested(job.job_id),
            is_active=queue_position is None and not is_terminal,
            thread_attached=queue_position is None and not is_terminal,
            completed_at=job.completed_at,
        )

    def _fallback_outcome(self, job: ReviewJob) -> ReviewExecutionOutcome:
        if job.state == "cancelled":
            return ReviewExecutionOutcome(kind="cancelled")
        result = job.result
        if result is None:
            return ReviewExecutionOutcome(kind="completed")
        if result.status == "dry_run":
            return ReviewExecutionOutcome(kind="dry_run_complete")
        if result.status == "issues_found":
            return ReviewExecutionOutcome(kind="issues_found", issues=list(result.issues))
        if result.status in {"no_files", "no_issues", "report_written"}:
            return ReviewExecutionOutcome(kind="no_report")
        return ReviewExecutionOutcome(kind="completed")

    def _normalize_runtime_job_outcome(
        self,
        job: ReviewJob,
        outcome: ReviewExecutionOutcome,
        sink: CallbackEventSink,
        cancel_event: threading.Event,
    ) -> None:
        """Project GUI-classified outcomes back onto the shared runtime job state."""
        if job.state in {"awaiting_gui_finalize", "completed", "cancelled", "failed"}:
            return

        if cancel_event.is_set() or outcome.kind == "cancelled":
            previous_state = job.state
            job.state = "cancelled"
            if job.completed_at is None:
                job.completed_at = datetime.now()
            sink.emit(
                JobStateChanged(
                    job_id=job.job_id,
                    kind="job.state_changed",
                    previous_state=previous_state,
                    new_state=job.state,
                    message=None,
                )
            )
            return

        if outcome.kind == "issues_found":
            result = self._pending_result_from_outcome(job, outcome)
            previous_state = job.set_pending_result(result)
            sink.emit(
                JobStateChanged(
                    job_id=job.job_id,
                    kind="job.state_changed",
                    previous_state=previous_state,
                    new_state=job.state,
                    message=None,
                )
            )
            sink.emit(
                JobResultAvailable(
                    job_id=job.job_id,
                    kind="job.result_available",
                    result=result,
                )
            )
            return

        result = self._completed_result_from_outcome(job, outcome)
        previous_state = job.complete_with_result(result)
        sink.emit(
            JobStateChanged(
                job_id=job.job_id,
                kind="job.state_changed",
                previous_state=previous_state,
                new_state=job.state,
                message=None,
            )
        )
        sink.emit(
            JobResultAvailable(
                job_id=job.job_id,
                kind="job.result_available",
                result=result,
            )
        )

    def _pending_result_from_outcome(
        self,
        job: ReviewJob,
        outcome: ReviewExecutionOutcome,
    ) -> ReviewExecutionResult:
        runner_result = self._runner_execution_result(outcome.runner)
        if runner_result is not None and runner_result.status == "issues_found":
            return runner_result

        serialized_context = getattr(outcome.runner, "serialized_report_context", None)
        if isinstance(serialized_context, dict):
            context = PendingReportContext.from_serialized_dict(
                serialized_context,
                default_backend=job.request.backend_name,
            )
        else:
            context = job.request.to_pending_report_context(0)
        return ReviewExecutionResult.from_pending_context(context, list(outcome.issues or []))

    def _completed_result_from_outcome(
        self,
        job: ReviewJob,
        outcome: ReviewExecutionOutcome,
    ) -> ReviewExecutionResult:
        runner_result = self._runner_execution_result(outcome.runner)
        if runner_result is not None:
            return runner_result

        if outcome.kind == "dry_run_complete":
            status = "dry_run"
        elif outcome.kind == "no_report":
            status = "no_issues"
        else:
            status = "completed"
        return ReviewExecutionResult(
            status=status,
            request=job.request,
            files_scanned=0,
            target_paths=[],
        )

    @staticmethod
    def _runner_execution_result(runner: Any | None) -> ReviewExecutionResult | None:
        result = getattr(runner, "last_execution", None)
        return result if isinstance(result, ReviewExecutionResult) else None

    def _job_sort_key(self, job: ReviewJob) -> tuple[int, int, str]:
        queue_position = self.runtime.get_queue_position(job.job_id)
        return (
            0 if queue_position is None else 1,
            queue_position or 0,
            job.job_id,
        )

    @staticmethod
    def _should_surface_job(job: ReviewJob) -> bool:
        return job.state != "awaiting_gui_finalize"

    @staticmethod
    def _job_status(job: ReviewJob) -> str:
        return "queued" if job.state == "created" else job.state

    def _display_job_status(self, job: ReviewJob, *, queue_position: int | None = None) -> str:
        if self._is_legacy_mode:
            return self._job_status(job)
        current_queue_position = queue_position
        if current_queue_position is None:
            current_queue_position = self.runtime.get_queue_position(job.job_id)
        if current_queue_position is None and job.state == "created":
            return "running"
        return self._job_status(job)

    @property
    def _is_legacy_mode(self) -> bool:
        return self.runtime is None

    def _submit_run_legacy(
        self,
        *,
        submission_kind: str,
        execute_run: Callable[..., ReviewExecutionOutcome],
        on_started: Callable[[ReviewExecutionSubmission], None] | None,
        on_outcome: Callable[[ReviewExecutionOutcome], None],
        on_error: Callable[[Exception], None],
        on_finished: Callable[[], None],
    ) -> ReviewExecutionSubmission:
        submission = ReviewExecutionSubmission(
            submission_id=self._legacy_next_submission_id,
            submission_kind=submission_kind,
            cancel_event=threading.Event(),
            status="queued",
        )
        self._legacy_next_submission_id += 1
        tracked = _LegacyTrackedReviewExecution(
            submission=submission,
            execute_run=execute_run,
            on_started=on_started or (lambda _submission: None),
            on_outcome=on_outcome,
            on_error=on_error,
            on_finished=on_finished,
        )
        with self._lock:
            self._legacy_tracked[submission.submission_id] = tracked
            should_start_now = self._legacy_active_submission_id is None
            if should_start_now:
                self._legacy_active_submission_id = submission.submission_id
            else:
                self._legacy_queued_submission_ids.append(submission.submission_id)
        if should_start_now:
            self._activate_legacy_submission(submission.submission_id)
        return submission

    def _activate_legacy_submission(self, submission_id: str | int) -> None:
        with self._lock:
            tracked = self._legacy_tracked.get(submission_id)
            if tracked is None:
                return
            tracked.reserved_active = False
            tracked.submission.status = "running"
            tracked.starting = True
        controller = self.facade.coordinator.controller
        controller.begin(tracked.submission.cancel_event)
        thread = self._thread_factory(
            target=lambda sid=submission_id: self._run_legacy_submission(sid),
            daemon=True,
        )
        tracked.thread = thread
        tracked.on_started(tracked.submission)
        cancelled_on_start = False
        with self._lock:
            refreshed = self._legacy_tracked.get(submission_id)
            if refreshed is None:
                return
            refreshed.starting = False
            if refreshed.submission.cancel_event.is_set():
                refreshed.submission.status = "cancelled"
                refreshed.thread = None
                cancelled_on_start = True
        if cancelled_on_start:
            self._finish_legacy_submission(
                submission_id,
                outcome=ReviewExecutionOutcome(kind="cancelled"),
                error=None,
            )
            return
        thread.start()

    def _run_legacy_submission(self, submission_id: str | int) -> None:
        tracked = self._legacy_tracked.get(submission_id)
        if tracked is None:
            return
        error: Exception | None = None
        outcome: ReviewExecutionOutcome | None = None
        try:
            outcome = tracked.execute_run(tracked.submission.cancel_event)
        except Exception as exc:
            if tracked.submission.cancel_event.is_set():
                outcome = ReviewExecutionOutcome(kind="cancelled")
            else:
                error = exc
        self._finish_legacy_submission(submission_id, outcome=outcome, error=error)

    def _finish_legacy_submission(
        self,
        submission_id: str | int,
        *,
        outcome: ReviewExecutionOutcome | None,
        error: Exception | None,
    ) -> None:
        with self._lock:
            tracked = self._legacy_tracked.get(submission_id)
            if tracked is None:
                return
        controller = self.facade.coordinator.controller
        try:
            if error is None:
                normalized_outcome = outcome or ReviewExecutionOutcome(kind="completed")
                tracked.submission.status = self._legacy_terminal_status(normalized_outcome.kind)
                tracked.on_outcome(normalized_outcome)
            else:
                tracked.submission.status = "failed"
                tracked.on_error(error)
        finally:
            with self._lock:
                self._legacy_tracked.pop(submission_id, None)
                if self._legacy_active_submission_id == submission_id:
                    self._legacy_active_submission_id = None
                next_submission_id = self._reserve_next_legacy_submission_locked()
            controller.finish()
            controller.release_client()
            tracked.on_finished()
            if next_submission_id is not None:
                self._activate_legacy_submission(next_submission_id)

    def _reserve_next_legacy_submission_locked(self) -> str | int | None:
        if not self._legacy_queued_submission_ids:
            return None
        next_submission_id = self._legacy_queued_submission_ids.pop(0)
        tracked = self._legacy_tracked.get(next_submission_id)
        if tracked is None:
            return self._reserve_next_legacy_submission_locked()
        tracked.reserved_active = True
        self._legacy_active_submission_id = next_submission_id
        return next_submission_id

    def _cancel_submission_legacy(self, submission_id: str | int) -> bool:
        with self._lock:
            tracked = self._legacy_tracked.get(submission_id)
            if tracked is None:
                return False
            if submission_id in self._legacy_queued_submission_ids:
                self._legacy_queued_submission_ids = [
                    current_submission_id
                    for current_submission_id in self._legacy_queued_submission_ids
                    if current_submission_id != submission_id
                ]
                self._legacy_tracked.pop(submission_id, None)
                tracked.submission.status = "cancelled"
                tracked.submission.cancel_event.set()
                tracked.on_outcome(ReviewExecutionOutcome(kind="cancelled"))
                tracked.on_finished()
                return True
            if self._legacy_active_submission_id != submission_id:
                return False
            if tracked.reserved_active:
                return False
            if tracked.starting:
                tracked.submission.cancel_event.set()
                tracked.submission.status = "cancelled"
                return True
            if tracked.thread is None or tracked.submission.status != "running":
                return False
            tracked.submission.cancel_event.set()
        self.facade.coordinator.controller.request_cancel()
        return True

    @staticmethod
    def _legacy_terminal_status(outcome_kind: str) -> str:
        if outcome_kind == "cancelled":
            return "cancelled"
        if outcome_kind == "failed":
            return "failed"
        return "completed"

    @staticmethod
    def _build_legacy_submission_snapshot(
        tracked: _LegacyTrackedReviewExecution,
    ) -> ReviewExecutionSubmissionSnapshot:
        return ReviewExecutionSubmissionSnapshot(
            submission_id=tracked.submission.submission_id,
            submission_kind=tracked.submission.submission_kind,
            status=tracked.submission.status,
            cancel_requested=tracked.submission.cancel_event.is_set(),
            is_active=tracked.reserved_active or tracked.submission.status == "running",
            thread_attached=tracked.thread is not None,
        )