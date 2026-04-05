# src/aicodereviewer/orchestration.py
"""
High-level orchestration for a code review session.

Coordinates scanning, multi-type review collection, interactive
confirmation, and report generation.
"""
import logging
from typing import Optional, List, Any, Union

from .backup import cleanup_old_backups
from .models import ReviewReport, ReviewIssue
from .i18n import t
from .backends.base import AIBackend
from .reviewer import collect_review_issues
from .execution import (
    CallbackEventSink,
    CancelCheck,
    CompositeEventSink,
    DeferredReportState,
    ExecutionEventSink,
    ProgressCallback,
    ReviewJob,
    ReviewExecutionResult,
    ReviewExecutionService,
    ReviewRequest,
    ReviewRunnerState,
    ReviewSessionState,
    ScanFunction,
)

__all__ = [
    "ScanFunction",
    "ProgressCallback",
    "CancelCheck",
    "AppRunner",
]

logger = logging.getLogger(__name__)


class AppRunner:
    """
    Orchestrates a complete review session.

    Args:
        client: An :class:`AIBackend` instance.
        scan_fn: File-scanning function (default: ``scan_project_with_scope``).
        backend_name: Name of the active backend for report metadata.
    """

    client: AIBackend | None
    scan_fn: ScanFunction
    backend_name: str
    execution_service: ReviewExecutionService
    _runner_state: ReviewRunnerState

    def __init__(
        self,
        client: AIBackend | None,
        *,
        scan_fn: Optional[ScanFunction] = None,
        backend_name: str = "bedrock",
        execution_service: ReviewExecutionService | None = None,
    ) -> None:
        self.client = client
        self.execution_service = execution_service or ReviewExecutionService(
            scan_fn,
            collect_issues_fn=collect_review_issues,
        )
        self.scan_fn = self.execution_service.scan_fn
        self.backend_name = backend_name
        self._runner_state = ReviewRunnerState()

    def run(
        self,
        path: Optional[str],
        scope: str,
        diff_file: Optional[str],
        commits: Optional[str],
        review_types: List[str],
        spec_content: Optional[str],
        target_lang: str,
        programmers: List[str],
        reviewers: List[str],
        dry_run: bool = False,
        output_file: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        event_sink: ExecutionEventSink | None = None,
        interactive: bool = True,
        cancel_check: Optional[CancelCheck] = None,
    ) -> Union[Optional[str], List[ReviewIssue]]:
        """
        Execute a full review session and return the report path (or None).

        Args:
            review_types: One or more review type keys.
            progress_callback: Optional ``(current, total, message)`` callable
                               preserved for legacy callers.
            event_sink: Optional typed execution event sink for callers that
                        want structured progress/state updates.
            interactive: If *False* skip the CLI interactive-review step
                         (used by the GUI which has its own issue cards).
            cancel_check: Optional callable returning *True* when the user
                          has requested cancellation.
        """
        # Clean old backups
        if path and not dry_run:
            cleanup_old_backups(path)

        request = ReviewRequest(
            path=path,
            scope=scope,
            diff_file=diff_file,
            commits=commits,
            review_types=list(review_types),
            spec_content=spec_content,
            target_lang=target_lang,
            backend_name=self.backend_name,
            programmers=list(programmers),
            reviewers=list(reviewers),
            dry_run=dry_run,
        )

        type_label = ", ".join(review_types)
        scope_desc = (
            t("orch.scope_project") if scope == "project"
            else t("orch.scope_diff", source=diff_file or commits)
        )
        logger.info(
            t("orch.scanning", path=path, scope=scope_desc, types=type_label, language=target_lang),
        )

        sinks: list[ExecutionEventSink] = []
        if event_sink is not None:
            sinks.append(event_sink)
        if progress_callback is not None:
            def _on_event(event: object) -> None:
                if hasattr(event, "kind") and getattr(event, "kind") == "job.progress":
                    progress_event = event
                    progress_callback(
                        getattr(progress_event, "current"),
                        getattr(progress_event, "total"),
                        getattr(progress_event, "message"),
                    )

            sinks.append(CallbackEventSink(_on_event))

        combined_sink = CompositeEventSink(*sinks) if sinks else None

        job = self.execution_service.create_job(request)
        execution = self.execution_service.execute_job(
            job,
            self.client,
            sink=combined_sink,
            cancel_check=cancel_check,
        )
        self._set_execution_result(execution, job=job)

        if execution.status == "no_files":
            logger.info(t("orch.no_files"))
            return None

        num_files = execution.files_scanned
        est = num_files * len(review_types) * 8
        logger.info(
            t("orch.found_files", files=num_files, types=len(review_types),
              minutes=est // 60, seconds=est % 60),
        )

        # ── dry run ───────────────────────────────────────────────────────
        if execution.status == "dry_run":
            logger.info(t("orch.dry_run_header"))
            for i, fp in enumerate(execution.target_paths, 1):
                logger.info("  %d. %s", i, fp)
            logger.info(t("orch.dry_run_total", count=num_files))
            logger.info(t("orch.dry_run_types", types=type_label))
            logger.info(t("orch.dry_run_lang", language=target_lang))
            logger.info(t("orch.dry_run_no_api"))
            return None

        # ── collect issues ────────────────────────────────────────────────
        logger.info(t("orch.collecting"))

        if execution.status == "no_issues":
            logger.info(t("orch.no_issues"))
            return None

        issues = execution.issues
        logger.info(t("orch.found_issues", count=len(issues)))

        if cancel_check and cancel_check():
            return None

        # When interactive=False (GUI mode), return issues without saving
        # a report — the GUI will invoke generate_report() after the user
        # has finished the interactive review.
        if not interactive:
            return issues

        if self.client is None:
            raise RuntimeError("AI backend client is required for interactive review")
        result = self.execution_service.complete_interactive_review(
            job,
            self.client,
            output_file=output_file,
        )
        if result is None:
            return None
        self._set_execution_result(result, job=job)
        if result.report_path is None:
            return None
        logger.info(t("orch.complete", path=result.report_path))
        return result.report_path

    # ── Deferred report generation (called by GUI after review) ────────
    def generate_report(
        self,
        issues: Optional[List[ReviewIssue]] = None,
        output_file: Optional[str] = None,
    ) -> Optional[str]:
        """Generate and save the report. Called by the GUI on Finalize."""
        if self.last_job is not None:
            result = self.execution_service.generate_report(
                self.last_job,
                issues,
                output_file,
            )
            if result is None:
                return None
            self._set_execution_result(result, job=self.last_job)
            if result.report_path is None:
                return None
            logger.info(t("orch.complete", path=result.report_path))
            return result.report_path

        report_issues = list(issues) if issues is not None else self.pending_issues
        job = self._runner_state.job_from_pending_state(report_issues)
        if job is None:
            return None
        result = self.execution_service.generate_report(job, report_issues, output_file)
        if result is None:
            return None
        self._set_execution_result(result, job=job)
        if result.report_path is None:
            return None
        logger.info(t("orch.complete", path=result.report_path))
        return result.report_path

    def build_report(
        self,
        issues: Optional[List[ReviewIssue]] = None,
    ) -> Optional[ReviewReport]:
        """Build a review report object without writing it to disk."""
        if self.last_job is not None:
            report = self.execution_service.build_report(self.last_job, issues)
            if report is not None:
                return report

        report_issues = list(issues) if issues is not None else self.pending_issues
        job = self._runner_state.job_from_pending_state(report_issues)
        if job is None:
            return None
        return self.execution_service.build_report(job, report_issues)

    @property
    def last_execution(self) -> ReviewExecutionResult | None:
        """Return the most recent structured execution result."""
        return self._runner_state.last_execution

    @property
    def last_job(self) -> ReviewJob | None:
        """Return the most recent structured review job."""
        return self._runner_state.last_job

    @property
    def execution_summary(self) -> dict[str, Any]:
        """Return the most recent execution summary state."""
        return self._runner_state.execution_summary()

    @property
    def serialized_report_context(self) -> dict[str, Any] | None:
        """Return deferred report metadata for GUI and CLI callers."""
        return self._runner_state.serialized_report_context()

    @property
    def deferred_report_state(self) -> DeferredReportState | None:
        """Return the current typed deferred-report state for restore/finalize flows."""
        return self._runner_state.deferred_report_state()

    @property
    def session_state(self) -> ReviewSessionState | None:
        """Return the current typed GUI session state when session data exists."""
        return self._runner_state.current_session_state()

    @property
    def pending_issues(self) -> list[ReviewIssue]:
        """Return the current deferred issue list for report finalization."""
        return self._runner_state.pending_issues()

    def restore_serialized_report_context(
        self,
        meta: dict[str, Any] | None,
        issues: list[ReviewIssue] | None = None,
    ) -> None:
        """Restore deferred report metadata from a serialized session payload."""
        self._runner_state = ReviewRunnerState.from_report_context(
            meta,
            issues=issues,
            default_backend=self.backend_name,
        )

    def restore_deferred_report_state(
        self,
        state: DeferredReportState | None,
        issues: list[ReviewIssue] | None = None,
    ) -> None:
        """Restore typed deferred-report state for session resume flows."""
        self._runner_state = ReviewRunnerState.from_deferred_report_state(
            state,
            issues=issues,
        )

    def restore_session_state(self, session_state: ReviewSessionState) -> None:
        """Restore a saved GUI session from typed execution/session state."""
        self._runner_state = ReviewRunnerState.from_session_state(session_state)

    def _set_execution_result(self, result: ReviewExecutionResult, *, job: ReviewJob | None = None) -> None:
        """Persist structured execution state for compatibility-facing properties."""
        self._runner_state = self._runner_state.with_execution(result, job=job)
