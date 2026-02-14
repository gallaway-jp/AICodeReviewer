# tests/test_fixer.py
"""
Tests for AI Code Reviewer fixer functionality.

Updated for v2.0: apply_ai_fix prefers client.get_fix() when available,
falling back to client.get_review() with a fix prompt.
"""
import pytest
from unittest.mock import MagicMock, patch
from aicodereviewer.fixer import apply_ai_fix
from aicodereviewer.models import ReviewIssue


class TestApplyAIFix:
    """Test AI fix application functionality"""

    def test_apply_ai_fix_via_get_fix(self):
        """Test fix generation using the preferred get_fix method."""
        mock_client = MagicMock()
        mock_client.get_fix.return_value = "def fixed_function():\n    return 'fixed'"

        issue = ReviewIssue(
            file_path="/path/to/test.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="def broken_function(): pass",
            ai_feedback="This function is insecure"
        )

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "def broken_function(): pass"
            result = apply_ai_fix(issue, mock_client, "security", "en")

        assert result == "def fixed_function():\n    return 'fixed'"
        mock_client.get_fix.assert_called_once()

    def test_apply_ai_fix_fallback_to_get_review(self):
        """Test fix generation via get_review when get_fix is unavailable."""
        mock_client = MagicMock(spec=[])  # no get_fix attribute
        mock_client.get_review = MagicMock(return_value="def fixed(): pass")

        issue = ReviewIssue(
            file_path="/path/to/test.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="code",
            ai_feedback="feedback"
        )

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "code"
            result = apply_ai_fix(issue, mock_client, "security", "en")

        assert result == "def fixed(): pass"

    def test_apply_ai_fix_error_response(self):
        """Test handling error responses from AI"""
        mock_client = MagicMock()
        mock_client.get_fix.return_value = None
        # hasattr(mock_client, 'get_fix') will be True -> calls get_fix

        issue = ReviewIssue(
            file_path="/path/to/test.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="code",
            ai_feedback="feedback"
        )

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "code"
            result = apply_ai_fix(issue, mock_client, "security", "en")

        assert result is None

    def test_apply_ai_fix_file_read_error(self):
        """Test handling file read errors"""
        mock_client = MagicMock()
        mock_client.get_fix.return_value = "fixed code"

        issue = ReviewIssue(
            file_path="/nonexistent/file.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="code",
            ai_feedback="feedback"
        )

        result = apply_ai_fix(issue, mock_client, "security", "en")

        assert result is None

    def test_apply_ai_fix_client_error(self):
        """Test handling client errors during fix generation"""
        mock_client = MagicMock()
        mock_client.get_fix.side_effect = Exception("API Error")

        issue = ReviewIssue(
            file_path="/path/to/test.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="code",
            ai_feedback="feedback"
        )

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "code"
            result = apply_ai_fix(issue, mock_client, "security", "en")

        assert result is None
