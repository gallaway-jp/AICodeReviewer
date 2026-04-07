"""Shared headless runtime for queued review execution."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..backends import create_backend
from ..diagnostics import diagnostic_from_exception
from .events import CallbackEventSink, ExecutionEvent, JobFailed, JobStateChanged
from .models import ReviewJob, ReviewRequest
from .service import ReviewExecutionService

BackendFactory = Callable[[str], Any]
RuntimeJobExecutor = Callable[[ReviewJob, CallbackEventSink, threading.Event], None]
RuntimeJobStartedCallback = Callable[[ReviewJob, threading.Event], None]
RuntimeJobFinishedCallback = Callable[[ReviewJob, Exception | None], None]


_shared_runtime: "ReviewExecutionRuntime | None" = None
_shared_runtime_lock = threading.Lock()


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewJobEventRecord:
    """One sequenced execution event stored by the runtime."""

    sequence: int
    event: ExecutionEvent


@dataclass(frozen=True)
class ReviewArtifact:
    """One generated artifact associated with a review job."""

    key: str
    path: str
    media_type: str
    size_bytes: int


@dataclass
class _ScheduledReviewJob:
    """Internal queued review execution entry."""

    job: ReviewJob
    output_file: str | None = None
    auto_finalize: bool = True
    executor: RuntimeJobExecutor | None = None
    on_started: RuntimeJobStartedCallback | None = None
    on_finished: RuntimeJobFinishedCallback | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class ReviewExecutionRuntime:
    """Own queued review execution above the execution service."""

    def __init__(
        self,
        execution_service: ReviewExecutionService | None = None,
        *,
        backend_factory: BackendFactory = create_backend,
        max_concurrent_jobs: int = 1,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
        event_history_limit: int = 1024,
    ) -> None:
        self.execution_service = execution_service or ReviewExecutionService()
        self.backend_factory = backend_factory
        self.max_concurrent_jobs = max(1, int(max_concurrent_jobs))
        self._thread_factory = thread_factory
        self._event_history_limit = max(1, int(event_history_limit))
        self._lock = threading.RLock()
        self._event_condition = threading.Condition(self._lock)
        self._jobs: dict[str, _ScheduledReviewJob] = {}
        self._queued_job_ids: deque[str] = deque()
        self._active_job_ids: set[str] = set()
        self._event_history: deque[ReviewJobEventRecord] = deque(maxlen=self._event_history_limit)
        self._next_event_sequence = 1

    def submit_job(
        self,
        request: ReviewRequest,
        *,
        output_file: str | None = None,
        auto_finalize: bool = True,
        executor: RuntimeJobExecutor | None = None,
        on_started: RuntimeJobStartedCallback | None = None,
        on_finished: RuntimeJobFinishedCallback | None = None,
    ) -> ReviewJob:
        normalized_request = self.execution_service.normalize_request(request)
        self.execution_service.validate_request(normalized_request)
        job = self.execution_service.create_job(normalized_request)
        scheduled = _ScheduledReviewJob(
            job=job,
            output_file=output_file,
            auto_finalize=auto_finalize,
            executor=executor,
            on_started=on_started,
            on_finished=on_finished,
        )
        with self._lock:
            self._jobs[job.job_id] = scheduled
            self._queued_job_ids.append(job.job_id)
            start_ids = self._dequeue_ready_job_ids_locked()
        self._record_event(
            JobStateChanged(
                job_id=job.job_id,
                kind="job.state_changed",
                previous_state=None,
                new_state=job.state,
                message="submitted" if job.job_id in start_ids else "queued",
            )
        )
        self._start_job_ids(start_ids)
        return job

    def list_jobs(self) -> list[ReviewJob]:
        with self._lock:
            return [scheduled.job for scheduled in self._jobs.values()]

    def get_job(self, job_id: str) -> ReviewJob:
        with self._lock:
            scheduled = self._jobs.get(job_id)
            if scheduled is None:
                raise KeyError(job_id)
            return scheduled.job

    def get_queue_position(self, job_id: str) -> int | None:
        with self._lock:
            for index, queued_job_id in enumerate(self._queued_job_ids, start=1):
                if queued_job_id == job_id:
                    return index
        return None

    def cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            scheduled = self._jobs.get(job_id)
            if scheduled is None:
                raise KeyError(job_id)
            return scheduled.cancel_event.is_set()

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            scheduled = self._jobs.get(job_id)
            if scheduled is None:
                return False
            if self._is_terminal_state(scheduled.job.state):
                return False
            if job_id in self._queued_job_ids:
                remaining: deque[str] = deque()
                removed = False
                while self._queued_job_ids:
                    queued_job_id = self._queued_job_ids.popleft()
                    if not removed and queued_job_id == job_id:
                        removed = True
                        continue
                    remaining.append(queued_job_id)
                self._queued_job_ids = remaining
                if not removed:
                    return False
                scheduled.cancel_event.set()
                previous_state = scheduled.job.state
                scheduled.job.state = "cancelled"
                scheduled.job.completed_at = datetime.now()
            elif job_id in self._active_job_ids:
                scheduled.cancel_event.set()
                previous_state = scheduled.job.state
            else:
                return False

        self._record_event(
            JobStateChanged(
                job_id=job_id,
                kind="job.state_changed",
                previous_state=previous_state,
                new_state=scheduled.job.state,
                message=("cancel_requested" if previous_state == scheduled.job.state else None),
            )
        )
        return True

    def wait_for_job(self, job_id: str, *, timeout: float = 5.0) -> ReviewJob:
        deadline = time.monotonic() + timeout
        while time.monotonic() <= deadline:
            job = self.get_job(job_id)
            if self._is_terminal_state(job.state):
                return job
            time.sleep(0.01)
        return self.get_job(job_id)

    def list_job_artifacts(self, job_id: str) -> list[ReviewArtifact]:
        job = self.get_job(job_id)
        result = job.result
        if result is None or result.report_path is None:
            return []

        artifacts: list[ReviewArtifact] = []
        seen_paths: set[str] = set()
        allowed_roots = self._artifact_allowed_roots(job)
        for key, candidate in self._report_artifact_candidates(result.report_path).items():
            if not candidate.exists() or not candidate.is_file():
                continue
            resolved_path = candidate.resolve()
            if not self._path_is_within_allowed_roots(resolved_path, allowed_roots):
                logger.warning(
                    "Skipping out-of-scope artifact for job %s: %s",
                    job.job_id,
                    resolved_path,
                )
                continue
            resolved = str(resolved_path)
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            media_type = self._artifact_media_type(candidate)
            artifacts.append(
                ReviewArtifact(
                    key=key,
                    path=resolved,
                    media_type=media_type,
                    size_bytes=candidate.stat().st_size,
                )
            )
        return artifacts

    def get_job_artifact(self, job_id: str, artifact_key: str) -> ReviewArtifact:
        for artifact in self.list_job_artifacts(job_id):
            if artifact.key == artifact_key:
                return artifact
        raise KeyError(artifact_key)

    def read_job_artifact(self, job_id: str, artifact_key: str) -> tuple[ReviewArtifact, str, Any | None]:
        artifact = self.get_job_artifact(job_id, artifact_key)
        path = Path(artifact.path)
        content = path.read_text(encoding="utf-8")
        parsed_json: Any | None = None
        if artifact.media_type == "application/json":
            try:
                parsed_json = json.loads(content)
            except json.JSONDecodeError:
                parsed_json = None
        return artifact, content, parsed_json

    def read_job_artifact_bytes(self, job_id: str, artifact_key: str) -> tuple[ReviewArtifact, bytes]:
        artifact = self.get_job_artifact(job_id, artifact_key)
        path = Path(artifact.path)
        return artifact, path.read_bytes()

    def read_events(
        self,
        *,
        job_id: str | None = None,
        after_sequence: int = 0,
        timeout: float = 0.0,
    ) -> list[ReviewJobEventRecord]:
        if after_sequence < 0:
            raise ValueError("Event sequence must be non-negative")
        if timeout < 0:
            raise ValueError("Event timeout must be non-negative")

        with self._event_condition:
            events = self._collect_event_records_locked(job_id=job_id, after_sequence=after_sequence)
            if events or timeout == 0:
                return events

            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._event_condition.wait(remaining)
                events = self._collect_event_records_locked(job_id=job_id, after_sequence=after_sequence)
                if events:
                    return events

    def shutdown(self, *, wait: bool = False, timeout: float = 1.0) -> None:
        with self._lock:
            scheduled_jobs = list(self._jobs.values())
        for scheduled in scheduled_jobs:
            scheduled.cancel_event.set()
        if not wait:
            return
        deadline = time.monotonic() + timeout
        for scheduled in scheduled_jobs:
            thread = scheduled.thread
            if thread is None:
                continue
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(remaining)

    def _dequeue_ready_job_ids_locked(self) -> list[str]:
        ready: list[str] = []
        while self._queued_job_ids and len(self._active_job_ids) < self.max_concurrent_jobs:
            job_id = self._queued_job_ids.popleft()
            self._active_job_ids.add(job_id)
            ready.append(job_id)
        return ready

    def _start_job_ids(self, job_ids: list[str]) -> None:
        for job_id in job_ids:
            with self._lock:
                scheduled = self._jobs[job_id]
            thread = self._thread_factory(target=self._run_scheduled_job, args=(job_id,), daemon=True)
            scheduled.thread = thread
            thread.start()

    def _run_scheduled_job(self, job_id: str) -> None:
        with self._lock:
            scheduled = self._jobs[job_id]
        job = scheduled.job
        sink = CallbackEventSink(self._record_event)
        error: Exception | None = None
        try:
            if scheduled.cancel_event.is_set():
                self._mark_cancelled(job)
                return
            if scheduled.on_started is not None:
                scheduled.on_started(job, scheduled.cancel_event)
            if scheduled.executor is not None:
                scheduled.executor(job, sink, scheduled.cancel_event)
            else:
                client = None
                if not job.request.dry_run:
                    client = self.backend_factory(job.request.backend_name)
                result = self.execution_service.execute_job(
                    job,
                    client,
                    sink=sink,
                    cancel_check=scheduled.cancel_event.is_set,
                )
                if scheduled.cancel_event.is_set() and not self._is_terminal_state(job.state):
                    self._mark_cancelled(job)
                    return
                if result.status == "issues_found" and scheduled.auto_finalize:
                    generated = self.execution_service.generate_report(
                        job,
                        result.issues,
                        scheduled.output_file,
                        sink=sink,
                    )
                    if generated is None:
                        self._fail_job(job, RuntimeError("Failed to generate report"))
        except Exception as exc:
            error = exc
            if scheduled.cancel_event.is_set() and not self._is_terminal_state(job.state):
                self._mark_cancelled(job)
            elif not self._is_terminal_state(job.state):
                self._fail_job(job, exc)
        finally:
            if scheduled.on_finished is not None:
                scheduled.on_finished(job, error)
            with self._lock:
                self._active_job_ids.discard(job_id)
                start_ids = self._dequeue_ready_job_ids_locked()
            self._start_job_ids(start_ids)

    def _collect_event_records_locked(
        self,
        *,
        job_id: str | None,
        after_sequence: int,
    ) -> list[ReviewJobEventRecord]:
        return [
            record
            for record in self._event_history
            if record.sequence > after_sequence and (job_id is None or record.event.job_id == job_id)
        ]

    def _record_event(self, event: ExecutionEvent) -> None:
        with self._event_condition:
            record = ReviewJobEventRecord(sequence=self._next_event_sequence, event=event)
            self._next_event_sequence += 1
            self._event_history.append(record)
            self._event_condition.notify_all()

    def _fail_job(self, job: ReviewJob, exc: Exception) -> None:
        error_message = str(exc)
        error_diagnostic = diagnostic_from_exception(exc, origin="runtime")
        previous_state = job.fail_with_error(error_message, diagnostic=error_diagnostic)
        self._record_event(
            JobStateChanged(
                job_id=job.job_id,
                kind="job.state_changed",
                previous_state=previous_state,
                new_state=job.state,
                message=error_message,
            )
        )
        self._record_event(
            JobFailed(
                job_id=job.job_id,
                kind="job.failed",
                error_message=error_message,
                exception_type=type(exc).__name__,
                error_diagnostic=error_diagnostic,
            )
        )

    def _mark_cancelled(self, job: ReviewJob) -> None:
        previous_state = job.state
        if job.state != "cancelled":
            job.state = "cancelled"
        if job.completed_at is None:
            job.completed_at = datetime.now()
        self._record_event(
            JobStateChanged(
                job_id=job.job_id,
                kind="job.state_changed",
                previous_state=previous_state,
                new_state=job.state,
                message=None,
            )
        )

    @staticmethod
    def _is_terminal_state(state: str) -> bool:
        return state in {"completed", "cancelled", "failed"}

    @staticmethod
    def _artifact_media_type(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return "application/json"
        if suffix == ".md":
            return "text/markdown"
        return "text/plain"

    @staticmethod
    def _report_artifact_candidates(report_path: str) -> dict[str, Path]:
        primary = Path(report_path).expanduser()
        stem = primary.with_suffix("")
        txt_summary = primary.with_name(f"{stem.name}_summary.txt")
        return {
            "report_primary": primary,
            "report_json": primary.with_suffix(".json"),
            "report_txt": primary.with_suffix(".txt"),
            "report_summary_txt": txt_summary,
            "report_md": primary.with_suffix(".md"),
        }

    @staticmethod
    def _path_is_within_allowed_roots(path: Path, allowed_roots: tuple[Path, ...]) -> bool:
        return any(path == root or path.is_relative_to(root) for root in allowed_roots)

    @staticmethod
    def _artifact_allowed_roots(job: ReviewJob) -> tuple[Path, ...]:
        roots: list[Path] = [Path.cwd().resolve()]
        request_path = str(job.request.path or "").strip()
        if request_path:
            request_root = Path(request_path).expanduser()
            if not request_root.is_absolute():
                request_root = Path.cwd() / request_root
            resolved_request_root = request_root.resolve(strict=False)
            roots.append(
                resolved_request_root if resolved_request_root.suffix == "" else resolved_request_root.parent
            )

        deduped: list[Path] = []
        for root in roots:
            if root not in deduped:
                deduped.append(root)
        return tuple(deduped)


def get_shared_review_execution_runtime(
    *,
    execution_service: ReviewExecutionService | None = None,
    backend_factory: BackendFactory = create_backend,
    max_concurrent_jobs: int = 1,
) -> ReviewExecutionRuntime:
    """Return the process-wide shared runtime used by GUI and local HTTP surfaces."""
    global _shared_runtime
    with _shared_runtime_lock:
        if _shared_runtime is None:
            _shared_runtime = ReviewExecutionRuntime(
                execution_service=execution_service,
                backend_factory=backend_factory,
                max_concurrent_jobs=max_concurrent_jobs,
            )
        return _shared_runtime