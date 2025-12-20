# tests/test_reviewer.py
"""
Tests for AI Code Reviewer reviewer functionality
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
        # Mock client
        mock_client = MagicMock()
        mock_client.get_review.return_value = "This code has security issues"

        # Create mock file info (Path objects for project scope)
        mock_file = Path("/path/to/test.py")

        target_files = [mock_file]

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "print('test code')"
            issues = collect_review_issues(target_files, "security", mock_client, "en")

        assert len(issues) == 1
        assert issues[0].file_path == str(mock_file)
        assert issues[0].issue_type == "security"
        assert issues[0].severity == "medium"
        assert "security issues" in issues[0].ai_feedback

    def test_collect_review_issues_diff_scope(self):
        """Test collecting issues from diff scope files"""
        # Mock client
        mock_client = MagicMock()
        mock_client.get_review.return_value = "This code has performance issues"

        # Create mock file info (dict for diff scope)
        target_files = [{
            'path': Path("/path/to/test.py"),
            'content': "print('modified code')",
            'filename': 'test.py'
        }]

        issues = collect_review_issues(target_files, "performance", mock_client, "en")

        assert len(issues) == 1
        assert issues[0].file_path == str(Path("/path/to/test.py"))
        assert issues[0].issue_type == "performance"
        assert "performance issues" in issues[0].ai_feedback

    def test_collect_review_issues_no_feedback(self):
        """Test collecting issues when AI returns error"""
        # Mock client
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Error: Something went wrong"

        target_files = [Path("/path/to/test.py")]

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "print('test')"
            issues = collect_review_issues(target_files, "security", mock_client, "en")

        assert len(issues) == 0

    def test_collect_review_issues_file_read_error(self):
        """Test handling file read errors"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Issues found"

        # File that doesn't exist
        target_files = [Path("/nonexistent/file.py")]

        issues = collect_review_issues(target_files, "security", mock_client, "en")

        assert len(issues) == 0


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
            ai_feedback="Long detailed feedback about security issues" * 10  # Make it long
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
            code_snippet="code",
            ai_feedback="feedback"
        )

        result = verify_issue_resolved(issue, mock_client, "security", "en")

        assert result is False