# tests/test_interactive.py
"""
Tests for AI Code Reviewer interactive functionality.

Updated for v2.0: new action "5" (SKIP), force-resolve on failed
verification, and refactored helper functions.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from aicodereviewer.interactive import get_valid_choice, interactive_review_confirmation
from aicodereviewer.models import ReviewIssue


class TestGetValidChoice:
    """Test input validation functionality"""

    @patch('builtins.input')
    def test_get_valid_choice_valid_input(self, mock_input):
        """Test valid input selection"""
        mock_input.return_value = "1"

        result = get_valid_choice("Choose: ", ["1", "2", "3"])

        assert result == "1"

    @patch('builtins.input')
    def test_get_valid_choice_invalid_then_valid(self, mock_input):
        """Test invalid input followed by valid input"""
        mock_input.side_effect = ["invalid", "2"]

        result = get_valid_choice("Choose: ", ["1", "2", "3"])

        assert result == "2"

    @patch('builtins.input')
    def test_get_valid_choice_keyboard_interrupt(self, mock_input):
        """Test keyboard interrupt handling"""
        mock_input.side_effect = KeyboardInterrupt()

        result = get_valid_choice("Choose: ", ["1", "2"])

        assert result == "cancel"

    @patch('builtins.input')
    def test_get_valid_choice_eof_error(self, mock_input):
        """Test EOF error handling"""
        mock_input.side_effect = EOFError()

        result = get_valid_choice("Choose: ", ["1", "2"])

        assert result == "cancel"


class TestInteractiveReviewConfirmation:
    """Test interactive review confirmation functionality"""

    def create_test_issue(self):
        """Helper to create a test issue"""
        return ReviewIssue(
            file_path="/path/to/test.py",
            issue_type="security",
            severity="high",
            description="Test security issue",
            code_snippet="insecure_code()",
            ai_feedback="This code is insecure"
        )

    @patch('aicodereviewer.interactive.get_valid_choice')
    @patch('aicodereviewer.interactive.verify_issue_resolved')
    def test_interactive_resolve_issue(self, mock_verify, mock_choice):
        """Test resolving an issue"""
        mock_choice.side_effect = ["1"]
        mock_verify.return_value = True

        mock_client = MagicMock()
        issues = [self.create_test_issue()]

        result = interactive_review_confirmation(issues, mock_client, "security", "en")

        assert len(result) == 1
        assert result[0].status == "resolved"
        assert isinstance(result[0].resolved_at, datetime)

    @patch('builtins.input')
    @patch('aicodereviewer.interactive.get_valid_choice')
    def test_interactive_ignore_issue(self, mock_choice, mock_input):
        """Test ignoring an issue"""
        mock_choice.side_effect = ["2"]
        mock_input.return_value = "Test reason"

        mock_client = MagicMock()
        issues = [self.create_test_issue()]

        result = interactive_review_confirmation(issues, mock_client, "security", "en")

        assert len(result) == 1
        assert result[0].status == "ignored"
        assert result[0].resolution_reason == "Test reason"

    @patch('builtins.input')
    @patch('aicodereviewer.interactive.get_valid_choice')
    @patch('aicodereviewer.interactive.apply_ai_fix')
    @patch('builtins.open', new_callable=MagicMock)
    @patch('shutil.copy2')
    def test_interactive_ai_fix_accepted(self, mock_copy, mock_open, mock_fix, mock_choice, mock_input):
        """Test accepting an AI fix"""
        mock_choice.side_effect = ["3", "y"]
        mock_input.return_value = "dummy"
        mock_fix.return_value = "fixed_code()"
        mock_open.return_value.__enter__.return_value.read.return_value = "original_code()"

        mock_client = MagicMock()
        issues = [self.create_test_issue()]

        result = interactive_review_confirmation(issues, mock_client, "security", "en")

        assert len(result) == 1
        assert result[0].status == "ai_fixed"
        assert result[0].ai_fix_applied == "fixed_code()"

    @patch('builtins.input')
    @patch('aicodereviewer.interactive.get_valid_choice')
    @patch('aicodereviewer.interactive.apply_ai_fix')
    def test_interactive_ai_fix_rejected(self, mock_fix, mock_choice, mock_input):
        """Test rejecting an AI fix"""
        mock_choice.side_effect = ["3", "n", "cancel"]  # AI FIX, reject, then cancel
        mock_input.return_value = "dummy"
        mock_fix.return_value = "fixed_code()"

        mock_client = MagicMock()
        issues = [self.create_test_issue()]

        result = interactive_review_confirmation(issues, mock_client, "security", "en")

        assert len(result) == 1
        assert result[0].status == "pending"

    @patch('aicodereviewer.interactive.get_valid_choice')
    @patch('builtins.open', new_callable=MagicMock)
    def test_interactive_view_code(self, mock_open, mock_choice):
        """Test viewing full file content"""
        mock_choice.side_effect = ["4", "1"]  # VIEW CODE, then RESOLVED
        mock_open.return_value.read.return_value = "full file content"

        mock_client = MagicMock()
        issues = [self.create_test_issue()]

        with patch('aicodereviewer.interactive.verify_issue_resolved', return_value=True):
            result = interactive_review_confirmation(issues, mock_client, "security", "en")

        mock_open.assert_called()

    @patch('aicodereviewer.interactive.get_valid_choice')
    def test_interactive_skip_issue(self, mock_choice):
        """Test skipping an issue (new v2.0 action 5)"""
        mock_choice.return_value = "5"

        mock_client = MagicMock()
        issues = [self.create_test_issue()]

        result = interactive_review_confirmation(issues, mock_client, "security", "en")

        assert len(result) == 1
        assert result[0].status == "pending"  # Still pending after skip

    @patch('aicodereviewer.interactive.get_valid_choice')
    @patch('aicodereviewer.interactive.verify_issue_resolved')
    def test_interactive_force_resolve(self, mock_verify, mock_choice):
        """Test force-resolve when verification fails."""
        mock_choice.side_effect = ["1", "y"]  # RESOLVED, verification fails, force=yes
        mock_verify.return_value = False

        mock_client = MagicMock()
        issues = [self.create_test_issue()]

        result = interactive_review_confirmation(issues, mock_client, "security", "en")

        assert len(result) == 1
        assert result[0].status == "resolved"
        assert result[0].resolution_reason == "Force-resolved by reviewer"

    @patch('aicodereviewer.interactive.get_valid_choice')
    def test_interactive_cancel_operation(self, mock_choice):
        """Test cancelling the operation"""
        mock_choice.return_value = "cancel"

        mock_client = MagicMock()
        issues = [self.create_test_issue()]

        result = interactive_review_confirmation(issues, mock_client, "security", "en")

        assert len(result) == 1
        assert result[0].status == "pending"
