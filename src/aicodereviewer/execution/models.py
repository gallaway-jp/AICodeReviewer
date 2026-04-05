"""Typed execution models for review runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from ..models import ReviewIssue, ReviewReport, calculate_quality_score

JobState = Literal[
    "created",
    "validating",
    "scanning",
    "reviewing",
    "awaiting_interactive_resolution",
    "awaiting_gui_finalize",
    "reporting",
    "completed",
    "cancelled",
    "failed",
]

SESSION_PAYLOAD_VERSION = 2
SESSION_REPORT_CONTEXT_KEY = "report_context"


@dataclass(frozen=True)
class ReviewRequest:
    """Normalized inputs for a single review execution."""

    path: str | None
    scope: str
    diff_file: str | None
    commits: str | None
    review_types: list[str]
    spec_content: str | None
    target_lang: str
    backend_name: str = "bedrock"
    programmers: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def diff_source(self) -> str | None:
        """Return the canonical diff source when diff scope is active."""
        if self.scope != "diff":
            return None
        return self.diff_file or self.commits

    def to_pending_report_context(self, total_files_scanned: int) -> PendingReportContext:
        """Build deferred report metadata for an issues-found execution result."""
        return PendingReportContext(
            project_path=self.path or "",
            review_types=list(self.review_types),
            scope=self.scope,
            total_files_scanned=total_files_scanned,
            language=self.target_lang,
            diff_source=self.diff_source,
            programmers=list(self.programmers),
            reviewers=list(self.reviewers),
            backend=self.backend_name,
        )


@dataclass(frozen=True)
class PendingReportContext:
    """Metadata needed to build a final review report."""

    project_path: str
    review_types: list[str]
    scope: str
    total_files_scanned: int
    language: str
    diff_source: str | None
    programmers: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    backend: str = "bedrock"

    @classmethod
    def from_serialized_dict(
        cls,
        meta: dict[str, Any],
        *,
        default_backend: str = "bedrock",
    ) -> PendingReportContext:
        """Build pending report context from a persisted metadata payload."""
        return cls(
            project_path=str(meta.get("project_path", "")),
            review_types=list(meta.get("review_types", [])),
            scope=str(meta.get("scope", "project")),
            total_files_scanned=int(meta.get("total_files_scanned", 0)),
            language=str(meta.get("language", "en")),
            diff_source=meta.get("diff_source"),
            programmers=list(meta.get("programmers", [])),
            reviewers=list(meta.get("reviewers", [])),
            backend=str(meta.get("backend", default_backend)),
        )

    def to_serialized_dict(self) -> dict[str, Any]:
        """Serialize pending-report metadata using the persisted payload structure."""
        return {
            "project_path": self.project_path,
            "review_types": list(self.review_types),
            "scope": self.scope,
            "total_files_scanned": self.total_files_scanned,
            "language": self.language,
            "diff_source": self.diff_source,
            "programmers": list(self.programmers),
            "reviewers": list(self.reviewers),
            "backend": self.backend,
        }

    def to_review_request(self) -> ReviewRequest:
        """Build a synthetic review request for restored staged-session state."""
        return ReviewRequest(
            path=self.project_path or None,
            scope=self.scope,
            diff_file=self.diff_source,
            commits=None,
            review_types=list(self.review_types),
            spec_content=None,
            target_lang=self.language,
            backend_name=self.backend,
            programmers=list(self.programmers),
            reviewers=list(self.reviewers),
            dry_run=False,
        )

    def build_report(
        self,
        issues: list[ReviewIssue],
        *,
        generated_at: datetime | None = None,
    ) -> ReviewReport:
        """Create a ReviewReport from the stored metadata and issues."""
        report_time = generated_at or datetime.now()
        return ReviewReport(
            project_path=self.project_path,
            review_type=", ".join(self.review_types),
            scope=self.scope,
            total_files_scanned=self.total_files_scanned,
            issues_found=issues,
            generated_at=report_time,
            language=self.language,
            review_types=list(self.review_types),
            diff_source=self.diff_source,
            quality_score=calculate_quality_score(issues),
            programmers=list(self.programmers),
            reviewers=list(self.reviewers),
            backend=self.backend,
        )


@dataclass(frozen=True)
class DeferredReportState:
    """Deferred report-finalization state for restored or GUI-managed review flows."""

    context: PendingReportContext

    @classmethod
    def from_context(cls, context: PendingReportContext) -> DeferredReportState:
        """Wrap an existing pending report context as deferred report state."""
        return cls(context=context)

    @classmethod
    def from_serialized_dict(
        cls,
        meta: dict[str, Any],
        *,
        default_backend: str = "bedrock",
    ) -> DeferredReportState:
        """Build deferred report state from a persisted metadata payload."""
        return cls(
            context=PendingReportContext.from_serialized_dict(
                meta,
                default_backend=default_backend,
            )
        )

    def to_serialized_dict(self) -> dict[str, Any]:
        """Serialize deferred pending-report metadata using the persisted payload structure."""
        return self.context.to_serialized_dict()

    def to_review_job(
        self,
        issues: list[ReviewIssue],
        *,
        job_id: str = "job-restored-session",
    ) -> ReviewJob:
        """Rebuild a synthetic GUI-finalize job from deferred report state."""
        result = self.to_execution_result(issues)
        return ReviewJob.from_pending_context_result(result, job_id=job_id)

    def to_execution_result(self, issues: list[ReviewIssue]) -> ReviewExecutionResult:
        """Rebuild a synthetic pending execution result from deferred report state."""
        return ReviewExecutionResult.from_pending_context(self.context, issues)

    def to_session_state(self, issues: list[ReviewIssue]) -> ReviewSessionState:
        """Wrap deferred report state as a saved-session state payload."""
        return ReviewSessionState(
            issues=list(issues),
            deferred_report_state=self,
        )

@dataclass(frozen=True)
class ReviewSessionState:
    """Serializable saved-session state for GUI restore flows."""

    issues: list[ReviewIssue] = field(default_factory=list)
    deferred_report_state: DeferredReportState | None = None

    @classmethod
    def from_serialized_dict(
        cls,
        data: dict[str, Any],
        *,
        default_backend: str = "bedrock",
    ) -> ReviewSessionState:
        """Build saved-session state from a persisted GUI session payload."""
        issues: list[ReviewIssue] = []
        for raw_issue in data.get("issues", []):
            issue_data = dict(raw_issue)
            if issue_data.get("resolved_at"):
                try:
                    issue_data["resolved_at"] = datetime.fromisoformat(issue_data["resolved_at"])
                except (ValueError, TypeError):
                    issue_data["resolved_at"] = None
            issues.append(ReviewIssue(**issue_data))

        return cls.from_report_context(
            cls._report_context_from_serialized_dict(data),
            issues=issues,
            default_backend=default_backend,
        )

    @classmethod
    def from_report_context(
        cls,
        report_context: dict[str, Any] | None,
        *,
        issues: list[ReviewIssue] | None = None,
        default_backend: str = "bedrock",
    ) -> ReviewSessionState:
        """Build saved-session state from persisted deferred report context and issues."""
        deferred_report_state = (
            DeferredReportState.from_serialized_dict(
                report_context,
                default_backend=default_backend,
            )
            if report_context
            else None
        )
        return cls(
            issues=list(issues or []),
            deferred_report_state=deferred_report_state,
        )

    def to_serialized_dict(
        self,
        *,
        saved_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Serialize the saved-session payload using the persisted GUI structure."""
        return {
            "format_version": SESSION_PAYLOAD_VERSION,
            "saved_at": (saved_at or datetime.now()).isoformat(),
            "issues": [self._issue_to_dict(issue) for issue in self.issues],
            SESSION_REPORT_CONTEXT_KEY: (
                self.deferred_report_state.to_serialized_dict()
                if self.deferred_report_state is not None
                else None
            ),
        }

    @staticmethod
    def _report_context_from_serialized_dict(
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Return serialized deferred report context from the current payload key."""
        raw_report_context = data.get(SESSION_REPORT_CONTEXT_KEY)
        if raw_report_context is None:
            return None
        return dict(raw_report_context)

    def with_issues(self, issues: list[ReviewIssue]) -> ReviewSessionState:
        """Return this session state with a replacement issue list."""
        return ReviewSessionState(
            issues=list(issues),
            deferred_report_state=self.deferred_report_state,
        )

    @property
    def backend_name(self) -> str | None:
        """Return the backend associated with this saved-session state when present."""
        if self.deferred_report_state is None:
            return None
        return self.deferred_report_state.context.backend

    def is_empty(self) -> bool:
        """Return True when this session state carries neither issues nor deferred finalize state."""
        return self.deferred_report_state is None and not self.issues

    def to_review_job(
        self,
        *,
        job_id: str = "job-restored-session",
    ) -> ReviewJob | None:
        """Rebuild a synthetic GUI-finalize job from saved-session state."""
        result = self.to_execution_result()
        if result is None:
            return None
        return ReviewJob.from_pending_context_result(result, job_id=job_id)

    def to_execution_result(self) -> ReviewExecutionResult | None:
        """Rebuild a synthetic pending execution result from saved-session state."""
        if self.deferred_report_state is None:
            return None
        return self.deferred_report_state.to_execution_result(self.issues)

    @staticmethod
    def _issue_to_dict(issue: ReviewIssue) -> dict[str, Any]:
        """Serialize a review issue for GUI session persistence."""
        issue_dict = dict(vars(issue))
        if issue.resolved_at is not None:
            issue_dict["resolved_at"] = issue.resolved_at.isoformat()
        return issue_dict


@dataclass(frozen=True)
class ReviewRunnerState:
    """Typed execution-state snapshot for AppRunner compatibility surfaces."""

    last_execution: ReviewExecutionResult | None = None
    last_job: ReviewJob | None = None
    staged_session_state: ReviewSessionState | None = None

    @classmethod
    def from_session_state(cls, session_state: ReviewSessionState) -> ReviewRunnerState:
        """Build runner state from restored saved-session state."""
        job = session_state.to_review_job()
        if job is None or job.result is None:
            return cls()
        return cls().with_execution(job.result, job=job)

    @classmethod
    def from_deferred_report_state(
        cls,
        state: DeferredReportState | None,
        *,
        issues: list[ReviewIssue] | None = None,
    ) -> ReviewRunnerState:
        """Build runner state from deferred report state restore inputs."""
        if state is None:
            return cls()
        if issues is None:
            return cls().with_staged_session_state(state.to_session_state([]))
        return cls.from_session_state(state.to_session_state(issues))

    @classmethod
    def from_report_context(
        cls,
        report_context: dict[str, Any] | None,
        *,
        issues: list[ReviewIssue] | None = None,
        default_backend: str = "bedrock",
    ) -> ReviewRunnerState:
        """Build runner state from persisted deferred report context restore inputs."""
        if report_context is None:
            return cls()
        session_state = ReviewSessionState.from_report_context(
            report_context,
            issues=issues,
            default_backend=default_backend,
        )
        if issues is None:
            return cls().with_staged_session_state(session_state)
        return cls.from_session_state(session_state)

    def with_execution(
        self,
        result: ReviewExecutionResult,
        *,
        job: ReviewJob | None = None,
    ) -> ReviewRunnerState:
        """Return runner state updated with an active execution result."""
        return ReviewRunnerState(
            last_execution=result,
            last_job=job,
            staged_session_state=None,
        )

    def with_staged_session_state(
        self,
        session_state: ReviewSessionState | None,
        *,
        clear_active_execution: bool = True,
    ) -> ReviewRunnerState:
        """Return runner state updated with staged deferred-session state only."""
        return ReviewRunnerState(
            last_execution=None if clear_active_execution else self.last_execution,
            last_job=None if clear_active_execution else self.last_job,
            staged_session_state=(
                None
                if session_state is not None and session_state.is_empty()
                else session_state
            ),
        )

    def current_session_state(self) -> ReviewSessionState | None:
        """Return the session state that should back compatibility surfaces."""
        if self.last_execution is not None and self.last_execution.report_context is not None:
            return self.last_execution.to_session_state()
        if self.staged_session_state is None or self.staged_session_state.is_empty():
            return None
        return self.staged_session_state

    def deferred_report_state(self) -> DeferredReportState | None:
        """Return the deferred report state for the active or staged session."""
        session_state = self.current_session_state()
        if session_state is None:
            return None
        return session_state.deferred_report_state

    def pending_issues(self) -> list[ReviewIssue]:
        """Return deferred issues for report finalization flows."""
        session_state = self.current_session_state()
        if session_state is None:
            return []
        return list(session_state.issues)

    def serialized_report_context(self) -> dict[str, Any] | None:
        """Return deferred report metadata using the persisted payload structure."""
        deferred_report_state = self.deferred_report_state()
        if deferred_report_state is None:
            return None
        return deferred_report_state.to_serialized_dict()

    def execution_summary(self) -> dict[str, Any]:
        """Return the execution summary payload."""
        if self.last_execution is None:
            return {}
        return self.last_execution.to_summary_dict()

    def job_from_pending_state(self, issues: list[ReviewIssue]) -> ReviewJob | None:
        """Build a synthetic GUI-finalize job from the current session state."""
        session_state = self.current_session_state()
        if session_state is None:
            return None
        return session_state.with_issues(issues).to_review_job()


@dataclass(frozen=True)
class ReviewExecutionResult:
    """Structured output of a review execution pass."""

    status: str
    request: ReviewRequest
    files_scanned: int
    target_paths: list[str] = field(default_factory=list)
    issues: list[ReviewIssue] = field(default_factory=list)
    report_context: PendingReportContext | None = None
    report: ReviewReport | None = None
    report_path: str | None = None

    @property
    def issue_count(self) -> int:
        """Return the number of discovered issues."""
        return len(self.issues)

    @classmethod
    def from_pending_context(
        cls,
        context: PendingReportContext,
        issues: list[ReviewIssue],
    ) -> ReviewExecutionResult:
        """Rebuild a synthetic execution result from restored pending metadata."""
        return cls(
            status="issues_found",
            request=context.to_review_request(),
            files_scanned=context.total_files_scanned,
            target_paths=[],
            issues=list(issues),
            report_context=context,
        )

    def with_report_output(
        self,
        report: ReviewReport,
        report_path: str,
        issues: list[ReviewIssue] | None = None,
    ) -> ReviewExecutionResult:
        """Return a report-written result derived from this execution result."""
        return ReviewExecutionResult(
            status="report_written",
            request=self.request,
            files_scanned=self.files_scanned,
            target_paths=list(self.target_paths),
            issues=list(issues) if issues is not None else list(self.issues),
            report_context=self.report_context,
            report=report,
            report_path=report_path,
        )

    def to_session_state(self) -> ReviewSessionState | None:
        """Return saved-session state when this execution still carries deferred report context."""
        if self.report_context is None:
            return None
        return DeferredReportState.from_context(self.report_context).to_session_state(self.issues)

    def to_summary_dict(self) -> dict[str, Any]:
        """Serialize the execution summary payload used by compatibility callers."""
        return {
            "status": self.status,
            "project_path": self.request.path or "",
            "scope": self.request.scope,
            "diff_source": self.request.diff_source,
            "files_scanned": self.files_scanned,
            "target_paths": list(self.target_paths),
            "issue_count": self.issue_count,
            "review_types": list(self.request.review_types),
            "language": self.request.target_lang,
            "backend": self.request.backend_name,
            "dry_run": self.request.dry_run,
        }


@dataclass
class ReviewJob:
    """One executable review unit suitable for future queueing."""

    job_id: str
    request: ReviewRequest
    state: JobState = "created"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: ReviewExecutionResult | None = None
    error_message: str | None = None

    @classmethod
    def from_pending_context_result(
        cls,
        result: ReviewExecutionResult,
        *,
        job_id: str = "job-restored-session",
    ) -> ReviewJob:
        """Rebuild a synthetic GUI-finalize job from restored execution state."""
        return cls(
            job_id=job_id,
            request=result.request,
            state="awaiting_gui_finalize",
            result=result,
        )

    @classmethod
    def from_pending_context(
        cls,
        context: PendingReportContext,
        issues: list[ReviewIssue],
        *,
        job_id: str = "job-restored-session",
    ) -> ReviewJob:
        """Rebuild a synthetic GUI-finalize job directly from restored pending metadata."""
        result = ReviewExecutionResult.from_pending_context(context, issues)
        return cls.from_pending_context_result(result, job_id=job_id)

    def transition_to(
        self,
        new_state: JobState,
        *,
        started_at: datetime | None = None,
    ) -> JobState:
        """Move the job to a new lifecycle state and stamp start time when needed."""
        previous_state = self.state
        self.state = new_state
        if new_state not in {"created", "validating"} and self.started_at is None:
            self.started_at = started_at or datetime.now()
        return previous_state

    def set_pending_result(
        self,
        result: ReviewExecutionResult,
        *,
        started_at: datetime | None = None,
    ) -> JobState:
        """Store a review result awaiting later report finalization."""
        self.result = result
        return self.transition_to("awaiting_gui_finalize", started_at=started_at)

    def complete_with_result(
        self,
        result: ReviewExecutionResult,
        *,
        completed_at: datetime | None = None,
    ) -> JobState:
        """Mark the job completed with a successful result and timestamp."""
        previous_state = self.transition_to("completed")
        self.result = result
        self.completed_at = completed_at or datetime.now()
        return previous_state

    def fail_with_error(
        self,
        error_message: str,
        *,
        completed_at: datetime | None = None,
    ) -> JobState:
        """Mark the job failed with an error message and completion timestamp."""
        previous_state = self.transition_to("failed")
        self.error_message = error_message
        self.completed_at = completed_at or datetime.now()
        return previous_state