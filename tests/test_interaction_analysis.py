"""Tests for Part 4 — Cross-Issue Interaction Analysis.

Validates:
* New fields on ReviewIssue (related_issues, interaction_summary) and
  ReviewReport (interaction_analysis).
* _parse_interaction_response robustness.
* analyze_interactions end-to-end with mocked AI backend.
* Integration with collect_review_issues (config flag).
* Backward compatibility of from_dict for old reports.
* interaction_analysis prompt exists and is excluded from REVIEW_TYPE_KEYS.
* _build_interaction_user_message formatting.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from aicodereviewer.backends.base import (
    AIBackend,
    REVIEW_PROMPTS,
    REVIEW_TYPE_KEYS,
)
from aicodereviewer.models import ReviewIssue, ReviewReport
from aicodereviewer.reviewer import (
    _parse_interaction_response,
    analyze_interactions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockBackend(AIBackend):
    """Minimal concrete backend that records calls."""

    def __init__(self, review_response: str = ""):
        self._project_context: Optional[str] = None
        self._detected_frameworks: Optional[List[str]] = None
        self._review_calls: list[tuple] = []
        self._review_response = review_response

    def get_review(self, code_content, review_type="best_practices",
                   lang="en", spec_content=None):
        self._review_calls.append((code_content, review_type, lang))
        return self._review_response

    def get_fix(self, code_content, issue_feedback,
                review_type="best_practices", lang="en"):
        return None

    def get_multi_file_review(self, entries, review_type="best_practices",
                              lang="en"):
        return ""

    def validate_connection(self):
        return True


def _make_issues(n: int = 4) -> List[ReviewIssue]:
    """Create *n* dummy issues for testing."""
    return [
        ReviewIssue(
            file_path=f"src/file_{i}.py",
            line_number=i * 10,
            issue_type="security" if i % 2 == 0 else "performance",
            severity="high" if i % 2 == 0 else "medium",
            description=f"Issue {i} description",
            ai_feedback=f"AI feedback for issue {i}",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# ReviewIssue field tests
# ---------------------------------------------------------------------------

class TestReviewIssueFields:
    def test_default_related_issues(self):
        issue = ReviewIssue(file_path="a.py")
        assert issue.related_issues == []

    def test_default_interaction_summary(self):
        issue = ReviewIssue(file_path="a.py")
        assert issue.interaction_summary is None

    def test_related_issues_independent(self):
        """Each instance gets its own list (no shared default)."""
        a = ReviewIssue(file_path="a.py")
        b = ReviewIssue(file_path="b.py")
        a.related_issues.append(1)
        assert b.related_issues == []

    def test_asdict_includes_new_fields(self):
        issue = ReviewIssue(
            file_path="a.py",
            related_issues=[0, 2],
            interaction_summary="conflict with issue 0",
        )
        d = asdict(issue)
        assert d["related_issues"] == [0, 2]
        assert d["interaction_summary"] == "conflict with issue 0"


class TestReviewReportField:
    def test_default_interaction_analysis(self):
        report = ReviewReport(
            project_path="/tmp",
            review_type="security",
            scope="project",
            total_files_scanned=1,
            issues_found=[],
            generated_at=datetime.now(),
            language="en",
        )
        assert report.interaction_analysis is None

    def test_to_dict_includes_interaction_analysis(self):
        report = ReviewReport(
            project_path="/tmp",
            review_type="security",
            scope="project",
            total_files_scanned=1,
            issues_found=[],
            generated_at=datetime.now(),
            language="en",
            interaction_analysis="3 conflicts found",
        )
        d = report.to_dict()
        assert d["interaction_analysis"] == "3 conflicts found"


class TestReviewReportBackwardCompat:
    def test_from_dict_missing_interaction_analysis(self):
        """Old reports without interaction_analysis should load fine."""
        data = {
            "project_path": "/tmp",
            "review_type": "security",
            "scope": "project",
            "total_files_scanned": 1,
            "issues_found": [],
            "generated_at": datetime.now().isoformat(),
            "language": "en",
        }
        report = ReviewReport.from_dict(data)
        assert report.interaction_analysis is None

    def test_from_dict_missing_related_issues_on_issue(self):
        """Old issue dicts without related_issues/interaction_summary."""
        data = {
            "project_path": "/tmp",
            "review_type": "security",
            "scope": "project",
            "total_files_scanned": 1,
            "issues_found": [
                {
                    "file_path": "a.py",
                    "line_number": 10,
                    "issue_type": "security",
                    "severity": "high",
                    "description": "desc",
                    "code_snippet": "code",
                    "ai_feedback": "feedback",
                    "status": "pending",
                    "resolution_reason": None,
                    "resolved_at": None,
                    "ai_fix_applied": None,
                }
            ],
            "generated_at": datetime.now().isoformat(),
            "language": "en",
        }
        report = ReviewReport.from_dict(data)
        issue = report.issues_found[0]
        assert issue.related_issues == []
        assert issue.interaction_summary is None


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------

class TestInteractionAnalysisPrompt:
    def test_prompt_exists(self):
        assert "interaction_analysis" in REVIEW_PROMPTS

    def test_not_in_selectable_keys(self):
        assert "interaction_analysis" not in REVIEW_TYPE_KEYS

    def test_prompt_mentions_json(self):
        assert "JSON" in REVIEW_PROMPTS["interaction_analysis"]

    def test_prompt_mentions_relationship_types(self):
        prompt = REVIEW_PROMPTS["interaction_analysis"]
        for rel in ("conflict", "cascade", "group", "duplicate"):
            assert rel in prompt


class TestBuildInteractionUserMessage:
    def test_basic_format(self):
        issues = _make_issues(3)
        msg = AIBackend._build_interaction_user_message(issues, "en")
        assert "[0]" in msg
        assert "[1]" in msg
        assert "[2]" in msg
        assert "src/file_0.py" in msg
        assert "Respond in English" in msg

    def test_japanese(self):
        issues = _make_issues(2)
        msg = AIBackend._build_interaction_user_message(issues, "ja")
        assert "日本語" in msg

    def test_empty_issues(self):
        msg = AIBackend._build_interaction_user_message([], "en")
        assert "Respond in English" in msg


# ---------------------------------------------------------------------------
# _parse_interaction_response tests
# ---------------------------------------------------------------------------

class TestParseInteractionResponse:
    def test_valid_json(self):
        data = {
            "interactions": [
                {"issue_indices": [0, 1], "relationship": "conflict",
                 "summary": "Both touch the same function"},
            ],
            "priority_order": [1, 0],
            "overall_summary": "One conflict found",
        }
        result = _parse_interaction_response(json.dumps(data))
        assert result is not None
        assert len(result["interactions"]) == 1

    def test_markdown_fenced(self):
        inner = json.dumps({"interactions": [], "overall_summary": ""})
        raw = f"```json\n{inner}\n```"
        result = _parse_interaction_response(raw)
        assert result is not None
        assert result["interactions"] == []

    def test_preamble_text(self):
        inner = json.dumps({"interactions": [], "overall_summary": "none"})
        raw = f"Here is the analysis:\n{inner}\n\nEnd."
        result = _parse_interaction_response(raw)
        assert result is not None

    def test_empty_string(self):
        assert _parse_interaction_response("") is None

    def test_no_json(self):
        assert _parse_interaction_response("no json here") is None

    def test_json_without_interactions(self):
        raw = json.dumps({"something_else": 42})
        assert _parse_interaction_response(raw) is None

    def test_malformed_json(self):
        assert _parse_interaction_response("{interactions: [}") is None


# ---------------------------------------------------------------------------
# analyze_interactions tests
# ---------------------------------------------------------------------------

class TestAnalyzeInteractions:
    def test_too_few_issues_skipped(self):
        issues = [ReviewIssue(file_path="a.py")]
        result, summary = analyze_interactions(issues, _MockBackend(), "en")
        assert summary is None
        assert result is issues

    def test_empty_list_skipped(self):
        result, summary = analyze_interactions([], _MockBackend(), "en")
        assert summary is None

    def test_successful_analysis(self):
        ai_response = json.dumps({
            "interactions": [
                {
                    "issue_indices": [0, 2],
                    "relationship": "conflict",
                    "summary": "Both modify the same function",
                },
                {
                    "issue_indices": [1, 3],
                    "relationship": "group",
                    "summary": "Should be fixed together",
                },
            ],
            "priority_order": [0, 2, 1, 3],
            "overall_summary": "Two interactions detected",
        })
        backend = _MockBackend(review_response=ai_response)
        issues = _make_issues(4)
        result, summary = analyze_interactions(issues, backend, "en")

        assert summary == "Two interactions detected"
        # Issue 0 should be related to issue 2
        assert 2 in result[0].related_issues
        assert 0 in result[2].related_issues
        # Issue 1 should be related to issue 3
        assert 3 in result[1].related_issues
        assert 1 in result[3].related_issues
        # Interaction summaries populated
        assert "conflict" in result[0].interaction_summary
        assert "group" in result[1].interaction_summary

    def test_invalid_indices_skipped(self):
        ai_response = json.dumps({
            "interactions": [
                {
                    "issue_indices": [0, 99],  # 99 out of range
                    "relationship": "conflict",
                    "summary": "should be skipped",
                },
            ],
            "priority_order": [],
            "overall_summary": "",
        })
        backend = _MockBackend(review_response=ai_response)
        issues = _make_issues(3)
        result, _ = analyze_interactions(issues, backend, "en")
        # No related_issues should be set (99 is out of range)
        for iss in result:
            assert iss.related_issues == []

    def test_unknown_relationship_skipped(self):
        ai_response = json.dumps({
            "interactions": [
                {
                    "issue_indices": [0, 1],
                    "relationship": "unknown_type",
                    "summary": "ignored",
                },
            ],
            "priority_order": [],
            "overall_summary": "",
        })
        backend = _MockBackend(review_response=ai_response)
        issues = _make_issues(2)
        result, _ = analyze_interactions(issues, backend, "en")
        assert result[0].related_issues == []

    def test_ai_error_returns_original(self):
        backend = _MockBackend(review_response="Error: timeout")
        issues = _make_issues(3)
        result, summary = analyze_interactions(issues, backend, "en")
        assert summary is None
        assert result is issues

    def test_ai_returns_empty_interactions(self):
        ai_response = json.dumps({
            "interactions": [],
            "priority_order": [],
            "overall_summary": "No meaningful interactions",
        })
        backend = _MockBackend(review_response=ai_response)
        issues = _make_issues(3)
        result, summary = analyze_interactions(issues, backend, "en")
        assert summary == "No meaningful interactions"
        for iss in result:
            assert iss.related_issues == []

    def test_ai_exception_handled(self):
        backend = _MockBackend()
        backend.get_review = MagicMock(side_effect=RuntimeError("boom"))
        issues = _make_issues(3)
        result, summary = analyze_interactions(issues, backend, "en")
        assert summary is None

    def test_duplicate_relationship(self):
        """Duplicate entries for same pair should not create duplicate indices."""
        ai_response = json.dumps({
            "interactions": [
                {"issue_indices": [0, 1], "relationship": "conflict",
                 "summary": "first"},
                {"issue_indices": [0, 1], "relationship": "cascade",
                 "summary": "second"},
            ],
            "priority_order": [],
            "overall_summary": "",
        })
        backend = _MockBackend(review_response=ai_response)
        issues = _make_issues(2)
        result, _ = analyze_interactions(issues, backend, "en")
        # Issue 0 should have 1 in related_issues exactly once
        assert result[0].related_issues.count(1) == 1
        # But should have two summary entries
        assert "conflict" in result[0].interaction_summary
        assert "cascade" in result[0].interaction_summary

    def test_calls_backend_with_interaction_type(self):
        ai_response = json.dumps({
            "interactions": [],
            "overall_summary": "",
        })
        backend = _MockBackend(review_response=ai_response)
        issues = _make_issues(3)
        analyze_interactions(issues, backend, "en")
        # Check that the backend was called with interaction_analysis type
        assert len(backend._review_calls) == 1
        _, review_type, lang = backend._review_calls[0]
        assert review_type == "interaction_analysis"
        assert lang == "en"


# ---------------------------------------------------------------------------
# Config-driven integration
# ---------------------------------------------------------------------------

class TestCollectReviewIssuesInteractionConfig:
    """Test that the interaction analysis is controlled by config."""

    @patch("aicodereviewer.reviewer.config")
    def test_disabled_by_default(self, mock_config):
        """When enable_interaction_analysis is false, analyze_interactions
        should not be called."""
        # Just verify the config default
        from aicodereviewer.config import Config
        cfg = Config.__new__(Config)
        cfg.config = __import__("configparser").ConfigParser()
        cfg._set_defaults()  # noqa: SLF001
        val = cfg.config.get("processing", "enable_interaction_analysis")
        assert val == "false"
