# tests/test_reviewer.py
"""
Tests for AI Code Reviewer reviewer functionality.

Updated for v2.0 API: collect_review_issues now takes review_types (List[str])
instead of a single review_type string.
"""
import json
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import List
from aicodereviewer.reviewer import collect_review_issues, verify_issue_resolved, FileInfo
from aicodereviewer.models import ReviewIssue


class TestCollectReviewIssues:
    """Test review issue collection functionality"""

    def test_collect_review_issues_project_scope(self):
        """Test collecting issues from project scope files"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "This code has security issues"

        mock_file = Path("/path/to/test.py")
        target_files: List[FileInfo] = [mock_file]  # type: ignore[list-item]

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

        target_files: List[FileInfo] = [{  # type: ignore[list-item]
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

        target_files: List[FileInfo] = [{  # type: ignore[list-item]
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

        target_files: List[FileInfo] = [Path("/path/to/test.py")]  # type: ignore[list-item]

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "print('test')"
            issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 0

    def test_collect_review_issues_retries_single_file_transient_error(self):
        """Single-file reviews retry once on transient backend errors."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Request timed out",
            "Recovered feedback after retry",
        ]

        target_files: List[FileInfo] = [Path("/path/to/test.py")]  # type: ignore[list-item]

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "print('test')"
            issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 1
        assert mock_client.get_review.call_count == 2

    def test_collect_review_issues_retries_combined_batch_transient_error(self):
        """Combined multi-file reviews retry once before falling back."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Temporary backend failure",
            json.dumps({
                "files": [
                    {
                        "filename": "a.py",
                        "findings": [{
                            "severity": "high",
                            "category": "security",
                            "title": "Issue A",
                            "description": "Combined retry recovered first file",
                        }],
                    },
                    {
                        "filename": "b.py",
                        "findings": [{
                            "severity": "medium",
                            "category": "security",
                            "title": "Issue B",
                            "description": "Combined retry recovered second file",
                        }],
                    },
                ],
            }),
        ]

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path("/path/to/a.py"),
                'content': "print('a')",
                'filename': 'a.py'
            },
            {
                'path': Path("/path/to/b.py"),
                'content': "print('b')",
                'filename': 'b.py'
            },
        ]

        issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 2
        assert {Path(issue.file_path).name for issue in issues} == {"a.py", "b.py"}
        assert mock_client.get_review.call_count >= 2

    def test_collect_review_issues_adds_deterministic_cache_finding_when_model_misses_it(self):
        """Performance reviews add a narrow stale-cache supplement for obvious cross-file read/write splits."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Temporary backend failure",
            "Error: Temporary backend failure",
            "",
            "",
        ]

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/cache.py'),
                'content': (
                    'PROFILE_CACHE = {}\n\n'
                    'def get_user_profile(user_id):\n'
                    '    return PROFILE_CACHE.get(user_id)\n\n'
                    'def set_user_profile(user_id, profile):\n'
                    '    PROFILE_CACHE[user_id] = profile\n'
                ),
                'filename': 'cache.py'
            },
            {
                'path': Path('/path/to/profile_service.py'),
                'content': (
                    'def update_user_profile(store, user_id, profile):\n'
                    '    store[user_id] = profile\n'
                ),
                'filename': 'profile_service.py'
            },
        ]

        issues = collect_review_issues(target_files, ["performance"], mock_client, "en")

        assert len(issues) == 1
        issue = issues[0]
        assert issue.issue_type == "missing_cache_invalidation"
        assert issue.context_scope == "cross_file"
        assert Path(issue.file_path).name == "profile_service.py"
        assert [Path(path).name for path in issue.related_files] == ["cache.py"]
        assert "user_profile" in (issue.evidence_basis or "")

    def test_collect_review_issues_promotes_local_cache_issue_from_related_cross_file_issue(self):
        """Local cache issues are promoted when sibling issues prove a cross-file stale-state dependency."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "cache.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "medium",
                            "category": "missing_cache_invalidation",
                            "title": "Missing cache invalidation",
                            "description": "Cache entries are never invalidated.",
                            "context_scope": "local",
                            "evidence_basis": "set_user_profile updates cache but no corresponding invalidate or clear mechanism exists",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "profile_service.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "high",
                            "category": "contract_mismatch",
                            "title": "Mismatched write path",
                            "description": "The service writes via store while cache.py serves cached values.",
                            "context_scope": "cross_file",
                            "related_files": ["cache.py"],
                            "systemic_impact": "Stale cache state can reach callers.",
                            "evidence_basis": "profile_service.py updates a different store than cache.py reads.",
                        }
                    ],
                },
            ]
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/cache.py'),
                'content': 'def set_user_profile(user_id, profile):\n    PROFILE_CACHE[user_id] = profile\n',
                'filename': 'cache.py'
            },
            {
                'path': Path('/path/to/profile_service.py'),
                'content': 'def update_user_profile(store, user_id, profile):\n    store[user_id] = profile\n',
                'filename': 'profile_service.py'
            },
        ]

        issues = collect_review_issues(target_files, ["performance"], mock_client, "en")

        cache_issue = next(issue for issue in issues if issue.issue_type == "missing_cache_invalidation")
        assert cache_issue.context_scope == "cross_file"
        assert [Path(path).name for path in cache_issue.related_files] == ["profile_service.py", "cache.py"]
        assert cache_issue.systemic_impact is not None
        assert "stale" in cache_issue.systemic_impact.lower()

    def test_collect_review_issues_adds_return_shape_mismatch_finding_when_model_misses_it(self):
        """Best-practices reviews add a narrow cross-file supplement for stale caller field expectations."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Temporary backend failure",
            "Error: Temporary backend failure",
            "",
            "",
        ]

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/service.py'),
                'content': (
                    'def build_result(total: int) -> dict:\n'
                    '    return {\n'
                    '        "value": total,\n'
                    '        "status": "ok",\n'
                    '    }\n'
                ),
                'filename': 'service.py'
            },
            {
                'path': Path('/path/to/client.py'),
                'content': (
                    'from src.service import build_result\n\n'
                    'def render_total(total: int) -> str:\n'
                    '    response = build_result(total)\n'
                    '    return f"Total: {response[\'result\']}"\n'
                ),
                'filename': 'client.py'
            },
        ]

        issues = collect_review_issues(target_files, ["best_practices"], mock_client, "en")

        assert len(issues) == 1
        issue = issues[0]
        assert issue.issue_type == "api_mismatch_runtime_error"
        assert issue.context_scope == "cross_file"
        assert issue.line_number == 5
        assert Path(issue.file_path).name == "client.py"
        assert [Path(path).name for path in issue.related_files] == ["service.py"]
        assert "result" in (issue.evidence_basis or "")
        assert "value" in (issue.evidence_basis or "")

    def test_collect_review_issues_file_read_error(self):
        """Test handling file read errors"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Issues found"

        target_files: List[FileInfo] = [Path("/nonexistent/file.py")]  # type: ignore[list-item]

        issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 0

    def test_collect_review_issues_progress_callback(self):
        """Test that progress callback is invoked."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Some feedback"

        target_files: List[FileInfo] = [{  # type: ignore[list-item]
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
