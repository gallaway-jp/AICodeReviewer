# tests/test_orchestration.py
"""
Tests for the AppRunner orchestration layer.

Verifies that scanning, review collection, interactive confirmation,
and reporting are wired together correctly.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from aicodereviewer.orchestration import AppRunner
from aicodereviewer.models import ReviewIssue


class TestAppRunner:
    """Test the AppRunner orchestration class."""

    def _make_runner(self, *, scan_return=None, backend_name="bedrock"):
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

    @patch("aicodereviewer.orchestration.generate_review_report", return_value="/out.json")
    @patch("aicodereviewer.orchestration.interactive_review_confirmation")
    @patch("aicodereviewer.orchestration.collect_review_issues")
    def test_full_run(self, mock_collect, mock_interactive, mock_report):
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

        runner, client, scan_fn = self._make_runner(
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

    @patch("aicodereviewer.orchestration.collect_review_issues", return_value=[])
    def test_no_issues_returns_none(self, mock_collect):
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
