"""Tests for the execution-layer job and event models."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aicodereviewer.diagnostics import FailureDiagnostic
from aicodereviewer.execution import (
    CallbackEventSink,
    DeferredReportState,
    JobFailed,
    JobProgressUpdated,
    JobResultAvailable,
    JobStateChanged,
    PendingReportContext,
    ReviewExecutionResult,
    ReviewJob,
    ReviewRunnerState,
    ReviewExecutionService,
    ReviewRequest,
    ReviewSessionState,
)
from aicodereviewer.execution.models import (
    SESSION_PAYLOAD_VERSION,
    SESSION_REPORT_CONTEXT_KEY,
)
from aicodereviewer.models import ReviewIssue
from aicodereviewer.tool_access import ToolAccessAudit


def test_create_job_assigns_identity_and_created_state() -> None:
    service = ReviewExecutionService(scan_fn=lambda *_args: [])
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )

    job = service.create_job(request)

    assert job.job_id.startswith("job-")
    assert job.state == "created"
    assert job.request is request
    assert job.result is None


def test_pending_report_context_from_serialized_dict_round_trips_metadata() -> None:
    meta = {
        "project_path": "./proj",
        "review_types": ["security", "performance"],
        "scope": "diff",
        "total_files_scanned": 5,
        "language": "ja",
        "diff_source": "HEAD~1..HEAD",
        "programmers": ["dev"],
        "reviewers": ["rev"],
        "backend": "copilot",
    }

    context = PendingReportContext.from_serialized_dict(meta, default_backend="local")

    assert context.project_path == "./proj"
    assert context.review_types == ["security", "performance"]
    assert context.scope == "diff"
    assert context.total_files_scanned == 5
    assert context.language == "ja"
    assert context.diff_source == "HEAD~1..HEAD"
    assert context.programmers == ["dev"]
    assert context.reviewers == ["rev"]
    assert context.backend == "copilot"
    assert context.to_serialized_dict() == meta


def test_pending_report_context_to_review_request_preserves_restore_metadata() -> None:
    context = PendingReportContext(
        project_path="./proj",
        review_types=["security", "performance"],
        scope="diff",
        total_files_scanned=5,
        language="ja",
        diff_source="HEAD~1..HEAD",
        programmers=["dev"],
        reviewers=["rev"],
        backend="copilot",
    )

    request = context.to_review_request()

    assert request.path == "./proj"
    assert request.scope == "diff"
    assert request.diff_file == "HEAD~1..HEAD"
    assert request.commits is None
    assert request.review_types == ["security", "performance"]
    assert request.target_lang == "ja"
    assert request.backend_name == "copilot"
    assert request.programmers == ["dev"]
    assert request.reviewers == ["rev"]
    assert request.dry_run is False


def test_deferred_report_state_round_trips_serialized_metadata_and_restores_job() -> None:
    meta = {
        "project_path": "./proj",
        "review_types": ["security"],
        "scope": "project",
        "total_files_scanned": 3,
        "language": "en",
        "diff_source": None,
        "programmers": ["dev"],
        "reviewers": ["rev"],
        "backend": "local",
    }
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )

    state = DeferredReportState.from_serialized_dict(meta)
    job = state.to_review_job([issue])

    assert state.to_serialized_dict() == meta
    assert job.state == "awaiting_gui_finalize"
    assert job.result is not None
    assert job.result.request.path == "./proj"
    assert job.result.issues == [issue]


def test_review_session_state_round_trips_versioned_serialized_payload() -> None:
    resolved_at = "2026-04-02T10:11:12"
    payload = {
        "format_version": SESSION_PAYLOAD_VERSION,
        "saved_at": "2026-04-02T10:11:13",
        "issues": [
            {
                "file_path": "src/example.py",
                "issue_type": "security",
                "severity": "high",
                "description": "Unsafe subprocess usage",
                "code_snippet": "subprocess.run(cmd, shell=True)",
                "ai_feedback": "Avoid shell=True for untrusted input.",
                "resolved_at": resolved_at,
            }
        ],
        SESSION_REPORT_CONTEXT_KEY: {
            "project_path": "./proj",
            "review_types": ["security"],
            "scope": "project",
            "total_files_scanned": 3,
            "language": "en",
            "diff_source": None,
            "programmers": ["dev"],
            "reviewers": ["rev"],
            "backend": "local",
        },
    }

    session_state = ReviewSessionState.from_serialized_dict(payload)
    round_tripped = session_state.to_serialized_dict(saved_at=None)

    assert len(session_state.issues) == 1
    assert session_state.issues[0].resolved_at is not None
    assert session_state.deferred_report_state is not None
    assert round_tripped["format_version"] == SESSION_PAYLOAD_VERSION
    assert round_tripped["issues"][0]["resolved_at"] == resolved_at
    assert round_tripped[SESSION_REPORT_CONTEXT_KEY] == payload[SESSION_REPORT_CONTEXT_KEY]


def test_review_session_state_can_replace_issues_and_restore_job() -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    deferred_report_state = DeferredReportState.from_serialized_dict(
        {
            "project_path": "./proj",
            "review_types": ["security"],
            "scope": "project",
            "total_files_scanned": 3,
            "language": "en",
            "diff_source": None,
            "programmers": ["dev"],
            "reviewers": ["rev"],
            "backend": "local",
        }
    )

    session_state = deferred_report_state.to_session_state([]).with_issues([issue])
    job = session_state.to_review_job()

    assert session_state.issues == [issue]
    assert session_state.deferred_report_state is deferred_report_state
    assert job is not None
    assert job.state == "awaiting_gui_finalize"
    assert job.result is not None
    assert job.result.issues == [issue]


def test_review_session_state_restores_pending_execution_result() -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    session_state = ReviewSessionState.from_report_context(
        {
            "project_path": "./proj",
            "review_types": ["security"],
            "scope": "project",
            "total_files_scanned": 3,
            "language": "en",
            "diff_source": None,
            "programmers": ["dev"],
            "reviewers": ["rev"],
            "backend": "local",
        },
        issues=[issue],
    )

    result = session_state.to_execution_result()

    assert result is not None
    assert result.status == "issues_found"
    assert result.request.path == "./proj"
    assert result.request.backend_name == "local"
    assert result.issues == [issue]


def test_review_runner_state_prefers_active_execution_over_stale_pending_session() -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    context = PendingReportContext(
        project_path="./proj",
        review_types=["security"],
        scope="project",
        total_files_scanned=3,
        language="en",
        diff_source=None,
        programmers=["dev"],
        reviewers=["rev"],
        backend="local",
    )
    active_result = ReviewExecutionResult.from_pending_context(context, [issue])
    stale_session_state = ReviewSessionState.from_report_context(
        {
            "project_path": "./stale",
            "review_types": ["performance"],
            "scope": "project",
            "total_files_scanned": 9,
            "language": "ja",
            "diff_source": None,
            "programmers": [],
            "reviewers": [],
            "backend": "bedrock",
        }
    )

    state = ReviewRunnerState().with_execution(active_result).with_staged_session_state(
        stale_session_state,
        clear_active_execution=False,
    )

    assert state.current_session_state() is not None
    assert state.serialized_report_context() is not None
    assert state.serialized_report_context()["project_path"] == "./proj"


def test_review_runner_state_restores_from_report_context_without_issues() -> None:
    state = ReviewRunnerState.from_report_context(
        {
            "project_path": "./restored",
            "review_types": ["security"],
            "scope": "project",
            "total_files_scanned": 1,
            "language": "en",
            "diff_source": None,
            "programmers": [],
            "reviewers": [],
            "backend": "local",
        }
    )

    assert state.last_execution is None
    assert state.last_job is None
    assert state.serialized_report_context() is not None
    assert state.serialized_report_context()["project_path"] == "./restored"


def test_review_runner_state_restores_from_session_state_with_issues() -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    state = ReviewRunnerState.from_session_state(
        ReviewSessionState.from_report_context(
            {
                "project_path": "./restored",
                "review_types": ["security"],
                "scope": "project",
                "total_files_scanned": 1,
                "language": "en",
                "diff_source": None,
                "programmers": [],
                "reviewers": [],
                "backend": "local",
            },
            issues=[issue],
        )
    )

    assert state.last_execution is not None
    assert state.last_execution.status == "issues_found"
    assert state.last_job is not None
    assert state.last_job.state == "awaiting_gui_finalize"
    assert state.pending_issues() == [issue]


def test_review_session_state_exposes_backend_name_and_empty_state() -> None:
    empty_state = ReviewSessionState()
    session_state = DeferredReportState.from_serialized_dict(
        {
            "project_path": "./proj",
            "review_types": ["security"],
            "scope": "project",
            "total_files_scanned": 3,
            "language": "en",
            "diff_source": None,
            "programmers": ["dev"],
            "reviewers": ["rev"],
            "backend": "local",
        }
    ).to_session_state([])

    assert empty_state.is_empty() is True
    assert empty_state.backend_name is None
    assert session_state.is_empty() is False
    assert session_state.backend_name == "local"


def test_review_session_state_from_report_context_wraps_serialized_metadata_and_issues() -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )

    session_state = ReviewSessionState.from_report_context(
        {
            "project_path": "./proj",
            "review_types": ["security"],
            "scope": "project",
            "total_files_scanned": 3,
            "language": "en",
            "diff_source": None,
            "programmers": ["dev"],
            "reviewers": ["rev"],
            "backend": "local",
        },
        issues=[issue],
    )

    assert session_state.issues == [issue]
    assert session_state.deferred_report_state is not None
    assert session_state.backend_name == "local"


def test_review_request_to_pending_report_context_preserves_execution_metadata() -> None:
    request = ReviewRequest(
        path="./proj",
        scope="diff",
        diff_file="HEAD~1..HEAD",
        commits=None,
        review_types=["security", "performance"],
        spec_content=None,
        target_lang="ja",
        backend_name="copilot",
        programmers=["dev"],
        reviewers=["rev"],
        dry_run=False,
    )

    context = request.to_pending_report_context(5)

    assert context.project_path == "./proj"
    assert context.review_types == ["security", "performance"]
    assert context.scope == "diff"
    assert context.total_files_scanned == 5
    assert context.language == "ja"
    assert context.diff_source == "HEAD~1..HEAD"
    assert context.programmers == ["dev"]
    assert context.reviewers == ["rev"]
    assert context.backend == "copilot"


def test_review_execution_result_from_pending_context_restores_issues_found_state() -> None:
    context = PendingReportContext(
        project_path="./proj",
        review_types=["security"],
        scope="project",
        total_files_scanned=3,
        language="en",
        diff_source=None,
        programmers=["dev"],
        reviewers=["rev"],
        backend="local",
    )
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )

    result = ReviewExecutionResult.from_pending_context(context, [issue])

    assert result.status == "issues_found"
    assert result.request.path == "./proj"
    assert result.request.review_types == ["security"]
    assert result.request.backend_name == "local"
    assert result.files_scanned == 3
    assert result.target_paths == []
    assert result.issues == [issue]
    assert result.report_context is context


def test_review_job_from_pending_context_result_restores_gui_finalize_state() -> None:
    context = PendingReportContext(
        project_path="./proj",
        review_types=["security"],
        scope="project",
        total_files_scanned=3,
        language="en",
        diff_source=None,
        programmers=["dev"],
        reviewers=["rev"],
        backend="local",
    )
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    result = ReviewExecutionResult.from_pending_context(context, [issue])

    job = ReviewJob.from_pending_context_result(result)

    assert job.job_id == "job-restored-session"
    assert job.request is result.request
    assert job.state == "awaiting_gui_finalize"
    assert job.result is result
    assert job.started_at is None
    assert job.completed_at is None


def test_review_job_from_pending_context_restores_job_and_result_together() -> None:
    context = PendingReportContext(
        project_path="./proj",
        review_types=["security"],
        scope="project",
        total_files_scanned=3,
        language="en",
        diff_source=None,
        programmers=["dev"],
        reviewers=["rev"],
        backend="local",
    )
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )

    job = ReviewJob.from_pending_context(context, [issue])

    assert job.job_id == "job-restored-session"
    assert job.state == "awaiting_gui_finalize"
    assert job.result is not None
    assert job.result.status == "issues_found"
    assert job.result.request.path == "./proj"
    assert job.result.issues == [issue]


def test_review_job_transition_to_sets_started_at_once() -> None:
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )
    job = ReviewJob(job_id="job-123", request=request)

    previous_state = job.transition_to("scanning")
    first_started_at = job.started_at
    second_previous_state = job.transition_to("reviewing")

    assert previous_state == "created"
    assert second_previous_state == "scanning"
    assert job.state == "reviewing"
    assert first_started_at is not None
    assert job.started_at == first_started_at


def test_review_job_set_pending_result_stores_result_and_state() -> None:
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )
    result = ReviewExecutionResult(
        status="issues_found",
        request=request,
        files_scanned=1,
    )
    job = ReviewJob(job_id="job-123", request=request)

    previous_state = job.set_pending_result(result)

    assert previous_state == "created"
    assert job.result is result
    assert job.state == "awaiting_gui_finalize"
    assert job.started_at is not None


def test_review_execution_result_with_report_output_preserves_execution_shape() -> None:
    context = PendingReportContext(
        project_path="./proj",
        review_types=["security"],
        scope="project",
        total_files_scanned=3,
        language="en",
        diff_source=None,
        programmers=["dev"],
        reviewers=["rev"],
        backend="local",
    )
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    base_result = ReviewExecutionResult.from_pending_context(context, [issue])
    report = context.build_report([issue])

    updated_result = base_result.with_report_output(report, "report.json")

    assert updated_result.status == "report_written"
    assert updated_result.request is base_result.request
    assert updated_result.files_scanned == 3
    assert updated_result.target_paths == []
    assert updated_result.issues == [issue]
    assert updated_result.report_context is context
    assert updated_result.report is report
    assert updated_result.report_path == "report.json"


def test_review_execution_result_to_session_state_preserves_issues_and_context() -> None:
    context = PendingReportContext(
        project_path="./proj",
        review_types=["security"],
        scope="project",
        total_files_scanned=3,
        language="en",
        diff_source=None,
        programmers=["dev"],
        reviewers=["rev"],
        backend="local",
    )
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    result = ReviewExecutionResult.from_pending_context(context, [issue])

    session_state = result.to_session_state()

    assert session_state is not None
    assert session_state.issues == [issue]
    assert session_state.deferred_report_state is not None
    assert session_state.deferred_report_state.context is context


def test_review_job_complete_with_result_stores_result_and_timestamp() -> None:
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )
    result = ReviewExecutionResult(
        status="no_issues",
        request=request,
        files_scanned=1,
    )
    job = ReviewJob(job_id="job-123", request=request)

    previous_state = job.complete_with_result(result)

    assert previous_state == "created"
    assert job.result is result
    assert job.state == "completed"
    assert job.started_at is not None
    assert job.completed_at is not None


def test_review_job_fail_with_error_stores_message_and_timestamp() -> None:
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )
    job = ReviewJob(job_id="job-123", request=request)
    diagnostic = FailureDiagnostic(
        category="permission",
        origin="review",
        detail="boom",
        fix_hint="Verify access.",
        exception_type="PermissionError",
    )

    previous_state = job.fail_with_error("boom", diagnostic=diagnostic)

    assert previous_state == "created"
    assert job.error_message == "boom"
    assert job.error_diagnostic is diagnostic
    assert job.state == "failed"
    assert job.started_at is not None
    assert job.completed_at is not None


def test_execute_job_failure_emits_structured_diagnostic() -> None:
    seen_events: list[Any] = []

    def _collect_issues(*_args: object, **_kwargs: object) -> list[ReviewIssue]:
        raise PermissionError("Access denied to backend")

    service = ReviewExecutionService(
        scan_fn=lambda *_args: ["src/example.py"],
        collect_issues_fn=_collect_issues,
    )
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )
    job = service.create_job(request)

    with pytest.raises(PermissionError, match="Access denied to backend"):
        service.execute_job(job, MagicMock(), sink=CallbackEventSink(seen_events.append))

    assert job.state == "failed"
    assert job.error_message == "Access denied to backend"
    assert job.error_diagnostic is not None
    assert job.error_diagnostic.category == "permission"
    assert job.error_diagnostic.origin == "review"

    failed_event = next(event for event in seen_events if isinstance(event, JobFailed))
    assert failed_event.error_diagnostic is not None
    assert failed_event.error_diagnostic.category == "permission"
    assert failed_event.error_diagnostic.detail == "Access denied to backend"


def test_execute_job_emits_progress_state_and_result_events() -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    seen_events: list[Any] = []

    def _scan_fn(*_args: object) -> list[str]:
        return ["src/example.py"]

    def _collect_issues(
        target_files: list[str],
        review_types: list[str],
        client: object,
        target_lang: str,
        spec_content: str | None,
        *,
        project_root,
        progress_callback,
        cancel_check,
    ) -> list[ReviewIssue]:
        assert target_files == ["src/example.py"]
        assert review_types == ["security"]
        assert target_lang == "en"
        assert spec_content is None
        assert project_root == "./proj"
        assert cancel_check is None
        progress_callback(1, 1, "Reviewing")
        return [issue]

    service = ReviewExecutionService(scan_fn=_scan_fn, collect_issues_fn=_collect_issues)
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
        programmers=["dev"],
        reviewers=["rev"],
    )
    job = service.create_job(request)

    result = service.execute_job(
        job,
        MagicMock(),
        sink=CallbackEventSink(seen_events.append),
    )

    assert result.status == "issues_found"
    assert job.result is result
    assert job.state == "awaiting_gui_finalize"
    assert job.started_at is not None
    assert job.completed_at is None
    assert any(isinstance(event, JobProgressUpdated) for event in seen_events)
    assert any(isinstance(event, JobResultAvailable) for event in seen_events)

    state_events = [event for event in seen_events if isinstance(event, JobStateChanged)]
    assert [event.new_state for event in state_events] == [
        "validating",
        "scanning",
        "reviewing",
        "awaiting_gui_finalize",
    ]


def test_execute_job_captures_tool_access_audit_from_backend() -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    audit = ToolAccessAudit(
        backend_name="copilot",
        model_name="gpt-5.4",
        enabled=True,
        used_tool_access=True,
        file_read_count=2,
    )

    def _collect_issues(
        target_files: list[str],
        review_types: list[str],
        client: object,
        target_lang: str,
        spec_content: str | None,
        *,
        project_root,
        progress_callback,
        cancel_check,
    ) -> list[ReviewIssue]:
        assert project_root == "./proj"
        progress_callback(1, 1, "Reviewing")
        return [issue]

    client = MagicMock()
    client.supports_tool_file_access.return_value = True
    client.consume_tool_access_audit.return_value = audit

    service = ReviewExecutionService(
        scan_fn=lambda *_args: ["src/example.py"],
        collect_issues_fn=_collect_issues,
    )
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="copilot",
    )
    job = service.create_job(request)

    result = service.execute_job(job, client)

    client.reset_tool_access_audit.assert_called_once_with()
    client.consume_tool_access_audit.assert_called_once_with()
    assert result.tool_access_audit is audit
    assert result.to_summary_dict()["tool_access_audit"]["file_read_count"] == 2


def test_generate_report_writes_report_and_updates_job(monkeypatch) -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    def _collect_issues(
        target_files: list[str],
        review_types: list[str],
        client: object,
        target_lang: str,
        spec_content: str | None,
        *,
        project_root,
        progress_callback,
        cancel_check,
    ) -> list[ReviewIssue]:
        assert target_files == ["src/example.py"]
        assert review_types == ["security"]
        assert target_lang == "en"
        assert spec_content is None
        assert project_root == "./proj"
        assert cancel_check is None
        progress_callback(1, 1, "Reviewing")
        return [issue]

    service = ReviewExecutionService(
        scan_fn=lambda *_args: ["src/example.py"],
        collect_issues_fn=_collect_issues,
    )
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
        programmers=["dev"],
        reviewers=["rev"],
    )
    job = service.create_job(request)
    job.result = service.execute_job(
        job,
        MagicMock(),
        sink=CallbackEventSink(lambda _event: None),
        progress_callback=None,
        cancel_check=None,
    )
    monkeypatch.setattr(
        "aicodereviewer.execution.service.generate_review_report",
        lambda report, output_file=None: output_file or "report.json",
    )

    result = service.generate_report(job, [issue], "custom-report.json")

    assert result is not None
    assert result.status == "report_written"
    assert result.report is not None
    assert result.report.project_path == "./proj"
    assert result.report_path == "custom-report.json"
    assert job.result is result
    assert job.state == "completed"
    assert job.completed_at is not None


def test_complete_interactive_review_resolves_issues_and_writes_report(monkeypatch) -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    resolved_issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
        status="resolved",
    )
    service = ReviewExecutionService(
        scan_fn=lambda *_args: ["src/example.py"],
        collect_issues_fn=lambda *_args, **_kwargs: [issue],
        interactive_resolver_fn=lambda issues, client, review_type, lang: [resolved_issue],
    )
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
        programmers=["dev"],
        reviewers=["rev"],
    )
    job = service.create_job(request)
    job.result = service.execute_job(
        job,
        MagicMock(),
        sink=CallbackEventSink(lambda _event: None),
    )
    monkeypatch.setattr(
        "aicodereviewer.execution.service.generate_review_report",
        lambda report, output_file=None: output_file or "interactive-report.json",
    )

    result = service.complete_interactive_review(
        job,
        MagicMock(),
        output_file="interactive-report.json",
    )

    assert result is not None
    assert result.status == "report_written"
    assert result.issues == [resolved_issue]
    assert result.report_path == "interactive-report.json"
    assert job.result is result
    assert job.state == "completed"


def test_generate_report_emits_reporting_and_completed_states(monkeypatch) -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )
    seen_events: list[Any] = []
    service = ReviewExecutionService(
        scan_fn=lambda *_args: ["src/example.py"],
        collect_issues_fn=lambda *_args, **_kwargs: [issue],
    )
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )
    job = service.create_job(request)
    service.execute_job(
        job,
        MagicMock(),
        sink=CallbackEventSink(seen_events.append),
    )
    monkeypatch.setattr(
        "aicodereviewer.execution.service.generate_review_report",
        lambda report, output_file=None: output_file or "report.json",
    )

    service.generate_report(
        job,
        [issue],
        "report.json",
        sink=CallbackEventSink(seen_events.append),
    )

    state_events = [event for event in seen_events if isinstance(event, JobStateChanged)]
    assert [event.new_state for event in state_events] == [
        "validating",
        "scanning",
        "reviewing",
        "awaiting_gui_finalize",
        "reporting",
        "completed",
    ]


def test_validate_request_rejects_unknown_review_type() -> None:
    service = ReviewExecutionService(scan_fn=lambda *_args: [])
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security", "unknown_type"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )

    with pytest.raises(ValueError, match="Unknown review types: unknown_type"):
        service.validate_request(request)


def test_validate_request_applies_spec_requirement_to_aliases() -> None:
    service = ReviewExecutionService(scan_fn=lambda *_args: [])
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["spec"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )

    with pytest.raises(ValueError, match="Specification reviews require spec content"):
        service.validate_request(request)


def test_normalize_request_canonicalizes_aliases_and_deduplicates() -> None:
    service = ReviewExecutionService(scan_fn=lambda *_args: [])
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["i18n", "localization", "security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )

    normalized = service.normalize_request(request)

    assert normalized.review_types == ["localization", "security"]
    assert normalized is not request


def test_execute_job_normalizes_alias_review_types_before_collection() -> None:
    seen_review_types: list[str] = []

    def _collect_issues(target_files, review_types, *_args, **_kwargs):
        seen_review_types.extend(review_types)
        return []

    service = ReviewExecutionService(
        scan_fn=lambda *_args: [{"path": "src/example.py"}],
        collect_issues_fn=_collect_issues,
    )
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["i18n", "localization"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
    )

    result = service.execute(request, client=MagicMock())

    assert seen_review_types == ["localization"]
    assert result.request.review_types == ["localization"]


def test_validate_request_rejects_unknown_backend() -> None:
    service = ReviewExecutionService(scan_fn=lambda *_args: [])
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="not-a-backend",
    )

    with pytest.raises(ValueError, match="Unknown backend type 'not-a-backend'"):
        service.validate_request(request)