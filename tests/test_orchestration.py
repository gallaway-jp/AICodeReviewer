# tests/test_orchestration.py
"""Tests for the AppRunner orchestration layer."""

from typing import Any
from unittest.mock import MagicMock, patch

from aicodereviewer.execution import CallbackEventSink, DeferredReportState, JobProgressUpdated, ReviewSessionState
from aicodereviewer.orchestration import AppRunner
from aicodereviewer.models import ReviewIssue


class TestAppRunner:
    """Test the AppRunner orchestration class."""

    def _make_runner(
        self,
        *,
        scan_return: list[str] | None = None,
        backend_name: str = "bedrock",
    ) -> tuple[AppRunner, MagicMock, MagicMock]:
        client = MagicMock()
        scan_fn = MagicMock(return_value=scan_return or [])
        return AppRunner(client, scan_fn=scan_fn, backend_name=backend_name), client, scan_fn

    def test_no_files_returns_none(self):
        runner, _, _ = self._make_runner(scan_return=[])

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            programmers=["dev"],
            reviewers=["rev"],
        )

        assert result is None
        assert runner.last_execution is not None
        assert runner.last_execution.status == "no_files"
        assert runner.execution_summary["status"] == "no_files"

    def test_dry_run_returns_none(self):
        runner, _, _ = self._make_runner(scan_return=["/fake/file.py"])

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            programmers=[],
            reviewers=[],
            dry_run=True,
        )

        assert result is None
        assert runner.last_execution is not None
        assert runner.last_execution.status == "dry_run"
        assert runner.execution_summary["files_scanned"] == 1

    @patch("aicodereviewer.execution.service.generate_review_report", return_value="/out.json")
    @patch("aicodereviewer.execution.service.interactive_review_confirmation")
    @patch("aicodereviewer.orchestration.collect_review_issues")
    def test_full_run(
        self,
        mock_collect: Any,
        mock_interactive: Any,
        mock_report: Any,
    ) -> None:
        issue = ReviewIssue(
            file_path="/f.py",
            issue_type="security",
            severity="high",
            description="desc",
            code_snippet="code",
            ai_feedback="feedback",
        )
        mock_collect.return_value = [issue]
        mock_interactive.return_value = [issue]

        runner, _, _ = self._make_runner(
            scan_return=["/f.py"], backend_name="kiro"
        )

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security", "performance"],
            spec_content=None,
            target_lang="en",
            programmers=["dev"],
            reviewers=["rev"],
        )

        assert result == "/out.json"
        mock_collect.assert_called_once()
        mock_interactive.assert_called_once()
        mock_report.assert_called_once()

        # Verify the report object has correct metadata
        report_arg = mock_report.call_args[0][0]
        assert report_arg.review_types == ["security", "performance"]
        assert report_arg.backend == "kiro"
        assert report_arg.programmers == ["dev"]
        assert runner.last_execution is not None
        assert runner.last_execution.status == "report_written"
        assert runner.last_job is not None
        assert runner.last_job.state == "completed"

    @patch("aicodereviewer.orchestration.collect_review_issues", return_value=[])
    def test_no_issues_returns_none(self, mock_collect: Any) -> None:
        runner, _, _ = self._make_runner(scan_return=["/f.py"])

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            programmers=["dev"],
            reviewers=["rev"],
        )

        assert result is None
        assert runner.last_execution is not None
        assert runner.last_execution.status == "no_issues"

    @patch("aicodereviewer.orchestration.collect_review_issues")
    def test_last_execution_builds_pending_report_context(self, mock_collect: Any) -> None:
        issue = ReviewIssue(
            file_path="/f.py",
            issue_type="security",
            severity="medium",
            description="desc",
            code_snippet="code",
            ai_feedback="feedback",
        )
        mock_collect.return_value = [issue]

        runner, _, _ = self._make_runner(scan_return=["/f.py"], backend_name="copilot")

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            programmers=["dev"],
            reviewers=["rev"],
            interactive=False,
        )

        assert isinstance(result, list)
        assert result == [issue]
        assert runner.last_execution is not None
        assert runner.last_execution.status == "issues_found"
        assert runner.last_job is not None
        assert runner.last_job.state == "awaiting_gui_finalize"
        assert runner.serialized_report_context is not None
        assert runner.serialized_report_context["backend"] == "copilot"
        report = runner.build_report(result)
        assert report is not None
        assert report.backend == "copilot"
        assert report.review_types == ["security"]

    @patch("aicodereviewer.execution.service.generate_review_report", return_value="/restored-report.json")
    def test_generate_report_from_restored_pending_context_uses_typed_service_path(self, mock_report: Any) -> None:
        runner, _, _ = self._make_runner(scan_return=[])
        issue = ReviewIssue(
            file_path="/restored.py",
            issue_type="security",
            severity="high",
            description="restored",
            code_snippet="snippet",
            ai_feedback="feedback",
        )

        runner.restore_serialized_report_context(
            {
                "project_path": "./restored",
                "review_types": ["security"],
                "scope": "project",
                "total_files_scanned": 3,
                "language": "ja",
                "diff_source": None,
                "programmers": ["dev"],
                "reviewers": ["rev"],
                "backend": "copilot",
            }
        )

        report_path = runner.generate_report([issue])

        assert report_path == "/restored-report.json"
        mock_report.assert_called_once()
        assert runner.last_execution is not None
        assert runner.last_execution.status == "report_written"
        assert runner.last_job is not None
        assert runner.last_job.state == "completed"
        assert runner.last_job.result is runner.last_execution
        assert runner.serialized_report_context is not None
        assert runner.serialized_report_context["project_path"] == "./restored"

    def test_build_report_without_pending_state_returns_none(self) -> None:
        runner, _, _ = self._make_runner(scan_return=[])

        assert runner.build_report() is None

    @patch("aicodereviewer.orchestration.collect_review_issues")
    def test_run_forwards_progress_events_to_event_sink(self, mock_collect: Any) -> None:
        issue = ReviewIssue(
            file_path="/f.py",
            issue_type="security",
            severity="medium",
            description="desc",
            code_snippet="code",
            ai_feedback="feedback",
        )
        seen_events: list[Any] = []

        def _collect(*args: Any, **kwargs: Any) -> list[ReviewIssue]:
            kwargs["progress_callback"](1, 1, "Reviewing")
            return [issue]

        mock_collect.side_effect = _collect
        runner, _, _ = self._make_runner(scan_return=["/f.py"], backend_name="local")

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            programmers=["dev"],
            reviewers=["rev"],
            interactive=False,
            event_sink=CallbackEventSink(seen_events.append),
        )

        assert isinstance(result, list)
        assert any(isinstance(event, JobProgressUpdated) for event in seen_events)

    @patch("aicodereviewer.orchestration.collect_review_issues")
    def test_restore_serialized_report_context_without_issues_clears_stale_execution_state(self, mock_collect: Any) -> None:
        issue = ReviewIssue(
            file_path="/f.py",
            issue_type="security",
            severity="medium",
            description="desc",
            code_snippet="code",
            ai_feedback="feedback",
        )
        mock_collect.return_value = [issue]

        runner, _, _ = self._make_runner(scan_return=["/f.py"], backend_name="local")

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            programmers=["dev"],
            reviewers=["rev"],
            interactive=False,
        )

        assert isinstance(result, list)
        assert runner.last_execution is not None
        assert runner.last_job is not None
        assert runner.pending_issues == [issue]

        runner.restore_serialized_report_context(
            {
                "project_path": "./restored",
                "review_types": ["performance"],
                "scope": "project",
                "total_files_scanned": 3,
                "language": "ja",
                "diff_source": None,
                "programmers": ["restored-dev"],
                "reviewers": ["restored-rev"],
                "backend": "copilot",
            }
        )

        assert runner.serialized_report_context is not None
        assert runner.serialized_report_context["project_path"] == "./restored"
        assert runner.last_execution is None
        assert runner.last_job is None
        assert runner.execution_summary == {}
        assert runner.pending_issues == []

    def test_clear_serialized_report_context_clears_pending_state(self) -> None:
        runner, _, _ = self._make_runner(scan_return=[])

        runner.restore_serialized_report_context(
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
            issues=[],
        )

        assert runner.serialized_report_context is not None

        runner.restore_serialized_report_context(None)

        assert runner.serialized_report_context is None
        assert runner.last_execution is None
        assert runner.last_job is None
        assert runner.execution_summary == {}
        assert runner.pending_issues == []

    def test_restore_serialized_report_context_with_issues_restores_execution_state(self) -> None:
        runner, _, _ = self._make_runner(scan_return=[])
        issue = ReviewIssue(
            file_path="/restored.py",
            issue_type="security",
            severity="high",
            description="restored",
            code_snippet="snippet",
            ai_feedback="feedback",
        )

        runner.restore_serialized_report_context(
            {
                "project_path": "./restored",
                "review_types": ["security"],
                "scope": "project",
                "total_files_scanned": 3,
                "language": "ja",
                "diff_source": None,
                "programmers": ["dev"],
                "reviewers": ["rev"],
                "backend": "copilot",
            },
            issues=[issue],
        )

        assert runner.last_execution is not None
        assert runner.last_execution.status == "issues_found"
        assert runner.last_execution.request.path == "./restored"
        assert runner.last_execution.request.target_lang == "ja"
        assert runner.last_execution.request.backend_name == "copilot"
        assert runner.last_execution.issues == [issue]
        assert runner.last_job is not None
        assert runner.last_job.state == "awaiting_gui_finalize"
        assert runner.last_job.result is runner.last_execution
        assert runner.pending_issues == [issue]

    def test_restore_deferred_report_state_with_issues_restores_execution_state(self) -> None:
        runner, _, _ = self._make_runner(scan_return=[])
        issue = ReviewIssue(
            file_path="/restored.py",
            issue_type="security",
            severity="high",
            description="restored",
            code_snippet="snippet",
            ai_feedback="feedback",
        )

        runner.restore_deferred_report_state(
            DeferredReportState.from_serialized_dict(
                {
                    "project_path": "./restored",
                    "review_types": ["security"],
                    "scope": "project",
                    "total_files_scanned": 3,
                    "language": "ja",
                    "diff_source": None,
                    "programmers": ["dev"],
                    "reviewers": ["rev"],
                    "backend": "copilot",
                }
            ),
            [issue],
        )

        assert runner.deferred_report_state is not None
        assert runner.serialized_report_context is not None
        assert runner.serialized_report_context["project_path"] == "./restored"
        assert runner.last_execution is not None
        assert runner.last_execution.status == "issues_found"
        assert runner.last_job is not None
        assert runner.last_job.state == "awaiting_gui_finalize"

    def test_restore_session_state_restores_execution_state(self) -> None:
        runner, _, _ = self._make_runner(scan_return=[])
        issue = ReviewIssue(
            file_path="/restored.py",
            issue_type="security",
            severity="high",
            description="restored",
            code_snippet="snippet",
            ai_feedback="feedback",
        )

        runner.restore_session_state(
            ReviewSessionState(
                issues=[issue],
                deferred_report_state=DeferredReportState.from_serialized_dict(
                    {
                        "project_path": "./restored",
                        "review_types": ["security"],
                        "scope": "project",
                        "total_files_scanned": 3,
                        "language": "ja",
                        "diff_source": None,
                        "programmers": ["dev"],
                        "reviewers": ["rev"],
                        "backend": "copilot",
                    }
                ),
            )
        )

        assert runner.deferred_report_state is not None
        assert runner.last_execution is not None
        assert runner.last_execution.status == "issues_found"
        assert runner.last_job is not None
        assert runner.last_job.state == "awaiting_gui_finalize"

    def test_restore_session_state_without_deferred_state_clears_runner_state(self) -> None:
        runner, _, _ = self._make_runner(scan_return=[])
        issue = ReviewIssue(
            file_path="/restored.py",
            issue_type="security",
            severity="high",
            description="restored",
            code_snippet="snippet",
            ai_feedback="feedback",
        )

        runner.restore_session_state(
            ReviewSessionState(
                issues=[issue],
                deferred_report_state=DeferredReportState.from_serialized_dict(
                    {
                        "project_path": "./restored",
                        "review_types": ["security"],
                        "scope": "project",
                        "total_files_scanned": 3,
                        "language": "ja",
                        "diff_source": None,
                        "programmers": ["dev"],
                        "reviewers": ["rev"],
                        "backend": "copilot",
                    }
                ),
            )
        )

        runner.restore_session_state(ReviewSessionState(issues=[issue]))

        assert runner.deferred_report_state is None
        assert runner.session_state is None
        assert runner.last_execution is None
        assert runner.last_job is None

    def test_session_state_exposes_current_typed_restore_state(self) -> None:
        runner, _, _ = self._make_runner(scan_return=[])
        issue = ReviewIssue(
            file_path="/restored.py",
            issue_type="security",
            severity="high",
            description="restored",
            code_snippet="snippet",
            ai_feedback="feedback",
        )

        runner.restore_session_state(
            ReviewSessionState(
                issues=[issue],
                deferred_report_state=DeferredReportState.from_serialized_dict(
                    {
                        "project_path": "./restored",
                        "review_types": ["security"],
                        "scope": "project",
                        "total_files_scanned": 3,
                        "language": "ja",
                        "diff_source": None,
                        "programmers": ["dev"],
                        "reviewers": ["rev"],
                        "backend": "copilot",
                    }
                ),
            )
        )

        session_state = runner.session_state

        assert session_state is not None
        assert session_state.issues == [issue]
        assert session_state.deferred_report_state is not None
        assert session_state.deferred_report_state.to_serialized_dict()["project_path"] == "./restored"

    @patch("aicodereviewer.orchestration.collect_review_issues")
    def test_serialized_report_context_prefers_pending_context_over_private_mirror(self, mock_collect: Any) -> None:
        issue = ReviewIssue(
            file_path="/f.py",
            issue_type="security",
            severity="medium",
            description="desc",
            code_snippet="code",
            ai_feedback="feedback",
        )
        mock_collect.return_value = [issue]

        runner, _, _ = self._make_runner(scan_return=["/f.py"], backend_name="local")

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            programmers=["dev"],
            reviewers=["rev"],
            interactive=False,
        )

        assert isinstance(result, list)

        meta = runner.serialized_report_context

        assert meta is not None
        assert meta["project_path"] == "./proj"
        assert meta["backend"] == "local"

    @patch("aicodereviewer.orchestration.collect_review_issues")
    def test_serialized_report_context_prefers_last_execution_report_context_over_pending_context(self, mock_collect: Any) -> None:
        issue = ReviewIssue(
            file_path="/f.py",
            issue_type="security",
            severity="medium",
            description="desc",
            code_snippet="code",
            ai_feedback="feedback",
        )
        mock_collect.return_value = [issue]

        runner, _, _ = self._make_runner(scan_return=["/f.py"], backend_name="local")

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            programmers=["dev"],
            reviewers=["rev"],
            interactive=False,
        )

        assert isinstance(result, list)
        runner._runner_state = runner._runner_state.with_staged_session_state(
            ReviewSessionState(
                deferred_report_state=DeferredReportState.from_serialized_dict(
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
            ),
            clear_active_execution=False,
        )

        meta = runner.serialized_report_context

        assert meta is not None
        assert meta["project_path"] == "./proj"
        assert meta["backend"] == "local"

    @patch("aicodereviewer.orchestration.collect_review_issues")
    def test_execution_summary_prefers_last_execution_over_private_mirror(self, mock_collect: Any) -> None:
        issue = ReviewIssue(
            file_path="/f.py",
            issue_type="security",
            severity="medium",
            description="desc",
            code_snippet="code",
            ai_feedback="feedback",
        )
        mock_collect.return_value = [issue]

        runner, _, _ = self._make_runner(scan_return=["/f.py"], backend_name="copilot")

        result = runner.run(
            path="./proj",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            programmers=["dev"],
            reviewers=["rev"],
            interactive=False,
        )

        assert isinstance(result, list)

        run_state = runner.execution_summary

        assert run_state["status"] == "issues_found"
        assert run_state["files_scanned"] == 1
        assert run_state["backend"] == "copilot"

    def test_pending_issues_prefers_pending_context_over_private_mirror(self) -> None:
        runner, _, _ = self._make_runner(scan_return=[])

        runner.restore_serialized_report_context(
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

        assert runner.pending_issues == []

    def test_public_runner_state_ignores_removed_private_compatibility_state(self) -> None:
        runner, _, _ = self._make_runner(scan_return=[])

        assert runner.execution_summary == {}
        assert runner.serialized_report_context is None
        assert runner.pending_issues == []
        assert not hasattr(runner, "_pending_issues")
