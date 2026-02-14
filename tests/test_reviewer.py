# tests/test_reviewer.py
"""
Tests for AI Code Reviewer reviewer functionality.

Updated for v2.0 API: collect_review_issues now takes review_types (List[str])
instead of a single review_type string.
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from aicodereviewer.reviewer import collect_review_issues, verify_issue_resolved
from aicodereviewer.models import ReviewIssue


class TestCollectReviewIssues:
    """Test review issue collection functionality"""

    def test_collect_review_issues_project_scope(self):
        """Test collecting issues from project scope files"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "This code has security issues"

        mock_file = Path("/path/to/test.py")
        target_files = [mock_file]

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "print('test code')"
            issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 1
        assert issues[0].file_path == str(mock_file)
        assert issues[0].issue_type == "security"
        assert issues[0].severity == "medium"
        assert "security issues" in issues[0].ai_feedback

    def test_collect_review_issues_diff_scope(self):
        """Test collecting issues from diff scope files"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "This code has performance issues"

        target_files = [{
            'path': Path("/path/to/test.py"),
            'content': "print('modified code')",
            'filename': 'test.py'
        }]

        issues = collect_review_issues(target_files, ["performance"], mock_client, "en")

        assert len(issues) == 1
        assert issues[0].file_path == str(Path("/path/to/test.py"))
        assert issues[0].issue_type == "performance"
        assert "performance issues" in issues[0].ai_feedback

    def test_collect_review_issues_multiple_types(self):
        """Test collecting issues across multiple review types (combined prompt)."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Security vulnerability found"

        target_files = [{
            'path': Path("/path/to/test.py"),
            'content': "print('code')",
            'filename': 'test.py'
        }]

        issues = collect_review_issues(
            target_files, ["security", "performance"], mock_client, "en"
        )

        # Combined into a single prompt, so one call and one issue
        assert len(issues) == 1
        assert issues[0].issue_type == "security+performance"
        mock_client.get_review.assert_called_once()

    def test_collect_review_issues_no_feedback(self):
        """Test collecting issues when AI returns error"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Error: Something went wrong"

        target_files = [Path("/path/to/test.py")]

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "print('test')"
            issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 0

    def test_collect_review_issues_file_read_error(self):
        """Test handling file read errors"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Issues found"

        target_files = [Path("/nonexistent/file.py")]

        issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 0

    def test_collect_review_issues_progress_callback(self):
        """Test that progress callback is invoked."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Some feedback"

        target_files = [{
            'path': Path("/path/to/test.py"),
            'content': "print('code')",
            'filename': 'test.py'
        }]
        cb = MagicMock()

        collect_review_issues(target_files, ["security"], mock_client, "en", progress_callback=cb)

        cb.assert_called()


class TestVerifyIssueResolved:
    """Test issue resolution verification functionality"""

    def test_verify_issue_resolved_success(self):
        """Test successful issue resolution verification"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "No issues found"

        issue = ReviewIssue(
            file_path="/path/to/test.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="old code",
            ai_feedback="Long detailed feedback about security issues" * 10
        )

        with patch('builtins.open', MagicMock()) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "fixed code"
            result = verify_issue_resolved(issue, mock_client, "security", "en")

        assert result is True

    def test_verify_issue_resolved_still_issues(self):
        """Test when issues are still present"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Still has security issues"

        issue = ReviewIssue(
            file_path="/path/to/test.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="old code",
            ai_feedback="Short feedback"
        )

        with patch('builtins.open', MagicMock()) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "modified code"
            result = verify_issue_resolved(issue, mock_client, "security", "en")

        assert result is False

    def test_verify_issue_resolved_file_error(self):
        """Test handling file read errors during verification"""
        mock_client = MagicMock()

        issue = ReviewIssue(
            file_path="/nonexistent/file.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="old code",
            ai_feedback="Some feedback"
        )

        result = verify_issue_resolved(issue, mock_client, "security", "en")

        assert result is False
