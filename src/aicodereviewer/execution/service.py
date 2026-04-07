"""Typed execution models and orchestration services for review runs."""

from __future__ import annotations
from dataclasses import replace
from typing import Any, Callable, Optional
from uuid import uuid4

from ..backends.base import AIBackend
from ..diagnostics import diagnostic_from_exception
from ..interactive import interactive_review_confirmation
from ..models import ReviewIssue, ReviewReport
from ..registries import get_backend_registry, get_review_registry
from ..reporter import generate_review_report
from ..reviewer import collect_review_issues
from ..scanner import scan_project_with_scope as default_scan
from .events import (
    ExecutionEventSink,
    JobFailed,
    JobProgressUpdated,
    JobResultAvailable,
    JobStateChanged,
    NullEventSink,
)
from .models import (
    JobState,
    PendingReportContext,
    ReviewExecutionResult,
    ReviewJob,
    ReviewRequest,
)

ScanFunction = Callable[
    [Optional[str], str, Optional[str], Optional[str]],
    list[dict[str, Any]],
]
ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]


def _target_file_path(target_file: Any) -> str:
    """Extract a displayable path from a scan result item."""
    if isinstance(target_file, dict):
        mapping = dict(target_file)
        raw_path = mapping.get("path")
        if raw_path is not None:
            return str(raw_path)
        return str(mapping)
    return str(target_file)


class ReviewExecutionService:
    """Execute the scan and issue-collection phases of a review run."""

    def __init__(
        self,
        scan_fn: ScanFunction | None = None,
        *,
        collect_issues_fn: Callable[..., list[ReviewIssue]] = collect_review_issues,
        interactive_resolver_fn: Callable[..., list[ReviewIssue]] | None = None,
    ) -> None:
        self.scan_fn = scan_fn or default_scan
        self.collect_issues_fn = collect_issues_fn
        self.interactive_resolver_fn = interactive_resolver_fn or interactive_review_confirmation

    def validate_request(self, request: ReviewRequest) -> None:
        """Validate normalized request state before execution."""
        if request.scope not in {"project", "diff"}:
            raise ValueError(f"Unknown review scope '{request.scope}'")
        if request.scope == "project" and not request.path:
            raise ValueError("Project scope requires a path")
        if request.scope == "diff" and not request.diff_source:
            raise ValueError("Diff scope requires a diff file or commit range")
        if not request.review_types:
            raise ValueError("At least one review type is required")
        get_backend_registry().resolve_descriptor(request.backend_name)
        review_registry = get_review_registry()
        unknown_review_types: list[str] = []
        resolved_definitions = []
        for review_type in request.review_types:
            try:
                resolved_definitions.append(review_registry.resolve(review_type))
            except KeyError:
                unknown_review_types.append(review_type)
        if unknown_review_types:
            unknown_list = ", ".join(sorted(unknown_review_types))
            raise ValueError(f"Unknown review types: {unknown_list}")
        if any(definition.requires_spec_content for definition in resolved_definitions) and request.spec_content is None:
            raise ValueError("Specification reviews require spec content")

    def normalize_request(self, request: ReviewRequest) -> ReviewRequest:
        """Return a copy of the request with canonical review type keys."""
        review_registry = get_review_registry()
        normalized_review_types: list[str] = []
        seen: set[str] = set()
        for review_type in request.review_types:
            try:
                canonical_key = review_registry.resolve_key(review_type)
            except KeyError:
                canonical_key = review_type
            if canonical_key not in seen:
                normalized_review_types.append(canonical_key)
                seen.add(canonical_key)
        if normalized_review_types == request.review_types:
            return request
        return replace(request, review_types=normalized_review_types)

    def create_job(self, request: ReviewRequest) -> ReviewJob:
        """Create a new review job for the request."""
        return ReviewJob(job_id=f"job-{uuid4().hex}", request=request)

    def execute(
        self,
        request: ReviewRequest,
        client: AIBackend | None,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> ReviewExecutionResult:
        """Run scanning and issue collection for a review request."""
        job = self.create_job(request)
        return self.execute_job(
            job,
            client,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def execute_job(
        self,
        job: ReviewJob,
        client: AIBackend | None,
        *,
        sink: ExecutionEventSink | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> ReviewExecutionResult:
        """Run scanning and issue collection for a review job."""
        sink = sink or NullEventSink()
        request = self.normalize_request(job.request)
        if request is not job.request:
            job.request = request
        self.validate_request(request)
        self._set_job_state(job, sink, "validating")
        self._set_job_state(job, sink, "scanning")
        target_files = self.scan_fn(
            request.path,
            request.scope,
            request.diff_file,
            request.commits,
        )
        target_paths = [_target_file_path(target_file) for target_file in target_files]

        if not target_files:
            result = ReviewExecutionResult(
                status="no_files",
                request=request,
                files_scanned=0,
                target_paths=[],
            )
            self._complete_job(job, sink, result)
            return result

        if request.dry_run:
            result = ReviewExecutionResult(
                status="dry_run",
                request=request,
                files_scanned=len(target_files),
                target_paths=target_paths,
            )
            self._complete_job(job, sink, result)
            return result

        if client is None:
            error = RuntimeError("AI backend client is required for non-dry-run review")
            self._fail_job(job, sink, error)
            raise error

        self._set_job_state(job, sink, "reviewing")
        if hasattr(client, "reset_tool_access_audit"):
            try:
                client.reset_tool_access_audit()
            except Exception:
                pass

        def _progress(current: int, total: int, message: str) -> None:
            sink.emit(
                JobProgressUpdated(
                    job_id=job.job_id,
                    kind="job.progress",
                    current=current,
                    total=total,
                    message=message,
                )
            )
            if progress_callback is not None:
                progress_callback(current, total, message)

        try:
            issues = self.collect_issues_fn(
                target_files,
                request.review_types,
                client,
                request.target_lang,
                request.spec_content,
                progress_callback=_progress,
                cancel_check=cancel_check,
                project_root=request.path,
            )
        except Exception as exc:
            self._fail_job(job, sink, exc)
            raise
        tool_access_audit = None
        if hasattr(client, "consume_tool_access_audit"):
            try:
                tool_access_audit = client.consume_tool_access_audit()
            except Exception:
                tool_access_audit = None
        if not issues:
            result = ReviewExecutionResult(
                status="no_issues",
                request=request,
                files_scanned=len(target_files),
                target_paths=target_paths,
                tool_access_audit=tool_access_audit,
            )
            self._complete_job(job, sink, result)
            return result

        report_context = request.to_pending_report_context(len(target_files))
        result = ReviewExecutionResult(
            status="issues_found",
            request=request,
            files_scanned=len(target_files),
            target_paths=target_paths,
            issues=issues,
            report_context=report_context,
            tool_access_audit=tool_access_audit,
        )
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
        return result

    def build_report(
        self,
        job: ReviewJob,
        issues: list[ReviewIssue] | None = None,
    ) -> ReviewReport | None:
        """Build a review report for a completed review job."""
        result = job.result
        if result is None or result.report_context is None:
            return None
        report_issues = list(issues) if issues is not None else list(result.issues)
        return result.report_context.build_report(report_issues)

    def generate_report(
        self,
        job: ReviewJob,
        issues: list[ReviewIssue] | None = None,
        output_file: str | None = None,
        sink: ExecutionEventSink | None = None,
    ) -> ReviewExecutionResult | None:
        """Generate and write a report for a completed review job."""
        sink = sink or NullEventSink()
        report = self.build_report(job, issues)
        if report is None:
            return None

        self._set_job_state(job, sink, "reporting")

        report_path = generate_review_report(report, output_file)
        result = job.result
        if result is None:
            return None

        updated_result = result.with_report_output(report, report_path, issues)
        self._complete_job(job, sink, updated_result)
        return updated_result

    def complete_interactive_review(
        self,
        job: ReviewJob,
        client: AIBackend,
        *,
        output_file: str | None = None,
        sink: ExecutionEventSink | None = None,
    ) -> ReviewExecutionResult | None:
        """Resolve issues through the interactive CLI flow, then write the report."""
        sink = sink or NullEventSink()
        result = job.result
        if result is None:
            return None

        issues = list(result.issues)
        if not issues:
            return self.generate_report(job, [], output_file, sink=sink)

        self._set_job_state(job, sink, "awaiting_interactive_resolution")

        resolved_issues = self.interactive_resolver_fn(
            issues,
            client,
            result.request.review_types[0],
            result.request.target_lang,
        )
        return self.generate_report(job, resolved_issues, output_file, sink=sink)

    def _set_job_state(
        self,
        job: ReviewJob,
        sink: ExecutionEventSink,
        new_state: JobState,
        *,
        message: str | None = None,
    ) -> None:
        previous_state = job.transition_to(new_state)
        sink.emit(
            JobStateChanged(
                job_id=job.job_id,
                kind="job.state_changed",
                previous_state=previous_state,
                new_state=new_state,
                message=message,
            )
        )

    def _complete_job(
        self,
        job: ReviewJob,
        sink: ExecutionEventSink,
        result: ReviewExecutionResult,
    ) -> None:
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

    def _fail_job(
        self,
        job: ReviewJob,
        sink: ExecutionEventSink,
        exc: Exception,
    ) -> None:
        error_message = str(exc)
        error_diagnostic = diagnostic_from_exception(exc, origin="review")
        previous_state = job.fail_with_error(error_message, diagnostic=error_diagnostic)
        sink.emit(
            JobStateChanged(
                job_id=job.job_id,
                kind="job.state_changed",
                previous_state=previous_state,
                new_state=job.state,
                message=error_message,
            )
        )
        sink.emit(
            JobFailed(
                job_id=job.job_id,
                kind="job.failed",
                error_message=error_message,
                exception_type=type(exc).__name__,
                error_diagnostic=error_diagnostic,
            )
        )