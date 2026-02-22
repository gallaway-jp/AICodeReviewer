# tests/test_response_parser.py
"""
Tests for the multi-strategy response parser.

Covers all four parsing strategies, severity normalisation,
line-number extraction, and deduplication.
"""
import json
import pytest
from aicodereviewer.response_parser import (
    parse_review_response,
    parse_single_file_response,
    _normalize_severity,
    _extract_line_number,
    _deduplicate_issues,
    _try_json_parse,
    _try_markdown_json_parse,
    _try_delimiter_parse,
    _try_heuristic_parse,
)
from aicodereviewer.models import ReviewIssue


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def file_entries():
    return [
        {"name": "src/app.py", "path": "/project/src/app.py", "content": "print('hello')"},
        {"name": "src/utils.py", "path": "/project/src/utils.py", "content": "def helper(): pass"},
    ]


@pytest.fixture
def single_entry():
    return [
        {"name": "main.py", "path": "/project/main.py", "content": "x = 1\ny = 2"},
    ]


# ── Severity normalisation ────────────────────────────────────────────────

class TestNormalizeSeverity:
    def test_canonical_values(self):
        assert _normalize_severity("critical") == "critical"
        assert _normalize_severity("high") == "high"
        assert _normalize_severity("medium") == "medium"
        assert _normalize_severity("low") == "low"
        assert _normalize_severity("info") == "info"

    def test_aliases(self):
        assert _normalize_severity("crit") == "critical"
        assert _normalize_severity("severe") == "high"
        assert _normalize_severity("major") == "high"
        assert _normalize_severity("minor") == "low"
        assert _normalize_severity("trivial") == "low"
        assert _normalize_severity("informational") == "info"
        assert _normalize_severity("note") == "info"

    def test_case_insensitive(self):
        assert _normalize_severity("CRITICAL") == "critical"
        assert _normalize_severity("High") == "high"

    def test_whitespace(self):
        assert _normalize_severity("  medium  ") == "medium"

    def test_unknown_defaults_to_medium(self):
        assert _normalize_severity("banana") == "medium"
        assert _normalize_severity("") == "medium"


# ── Line number extraction ────────────────────────────────────────────────

class TestExtractLineNumber:
    def test_line_keyword(self):
        assert _extract_line_number("Found issue at line 42") == 42

    def test_at_line(self):
        assert _extract_line_number("Error at line 10 of the file") == 10

    def test_l_prefix(self):
        assert _extract_line_number("See L15 for details") == 15

    def test_colon_format(self):
        assert _extract_line_number("file.py:73: warning") == 73

    def test_no_match(self):
        assert _extract_line_number("No line number here") is None

    def test_unreasonable_number(self):
        # Numbers above 100000 are rejected
        assert _extract_line_number("line 999999") is None


# ── Strategy 1: Raw JSON ──────────────────────────────────────────────────

class TestJsonParse:
    def test_valid_json(self, file_entries):
        response = json.dumps({
            "review_type": "security",
            "language": "en",
            "files": [
                {
                    "filename": "src/app.py",
                    "findings": [
                        {
                            "severity": "high",
                            "line": 1,
                            "category": "security",
                            "title": "Hardcoded output",
                            "description": "Using print for output",
                            "suggestion": "Use logging instead",
                        }
                    ],
                }
            ],
        })
        issues = _try_json_parse(response, file_entries, "security")
        assert len(issues) == 1
        assert issues[0].severity == "high"
        assert issues[0].line_number == 1
        assert issues[0].file_path == "/project/src/app.py"
        assert "Hardcoded output" in issues[0].description

    def test_flat_array_response(self, single_entry):
        response = json.dumps([
            {
                "severity": "low",
                "title": "Minor issue",
                "description": "Something small",
            }
        ])
        issues = _try_json_parse(response, single_entry, "best_practices")
        assert len(issues) == 1
        assert issues[0].severity == "low"

    def test_rejects_non_json(self, file_entries):
        with pytest.raises(ValueError):
            _try_json_parse("This is plain text", file_entries, "security")

    def test_json_with_extra_fields(self, file_entries):
        response = json.dumps({
            "files": [{
                "filename": "src/app.py",
                "findings": [{
                    "severity": "medium",
                    "title": "Test",
                    "description": "Desc",
                    "cwe_id": "CWE-79",
                    "suggestion": "Fix it",
                    "code_context": "x = 1",
                }],
            }],
        })
        issues = _try_json_parse(response, file_entries, "security")
        assert len(issues) == 1
        assert "CWE-79" in issues[0].ai_feedback


# ── Strategy 2: Markdown-fenced JSON ──────────────────────────────────────

class TestMarkdownJsonParse:
    def test_fenced_json(self, file_entries):
        response = (
            "Here are the findings:\n\n"
            "```json\n"
            + json.dumps({
                "files": [{
                    "filename": "src/app.py",
                    "findings": [{
                        "severity": "critical",
                        "title": "SQL Injection",
                        "description": "Vulnerable query",
                    }],
                }],
            })
            + "\n```\n"
        )
        issues = _try_markdown_json_parse(response, file_entries, "security")
        assert len(issues) == 1
        assert issues[0].severity == "critical"

    def test_no_fence(self, file_entries):
        with pytest.raises((ValueError, Exception)):
            _try_markdown_json_parse("No fences here", file_entries, "security")


# ── Strategy 3: Delimiter parse ───────────────────────────────────────────

class TestDelimiterParse:
    def test_file_and_finding_delimiters(self, file_entries):
        response = (
            "=== FILE: src/app.py ===\n"
            "--- FINDING [high] ---\n"
            "Found a hardcoded credential in the source.\n\n"
            "--- FINDING [low] ---\n"
            "Missing type annotation for function parameters.\n\n"
            "=== FILE: src/utils.py ===\n"
            "--- FINDING [medium] ---\n"
            "Unused import detected.\n"
        )
        issues = _try_delimiter_parse(response, file_entries, "security")
        assert len(issues) == 3
        assert issues[0].severity == "high"
        assert issues[0].file_path == "/project/src/app.py"
        assert issues[2].file_path == "/project/src/utils.py"

    def test_no_delimiters_raises(self, file_entries):
        with pytest.raises(ValueError):
            _try_delimiter_parse("Just some text feedback", file_entries, "security")

    def test_file_delimiter_only(self, file_entries):
        response = (
            "=== FILE: src/app.py ===\n"
            "This file has some issues with error handling.\n"
        )
        issues = _try_delimiter_parse(response, file_entries, "security")
        assert len(issues) == 1


# ── Strategy 4: Heuristic parse ──────────────────────────────────────────

class TestHeuristicParse:
    def test_bulleted_list_with_severity(self, single_entry):
        response = (
            "- **[high]** SQL injection vulnerability found\n"
            "  User input is not sanitized before query\n"
            "- **[low]** Missing docstring\n"
            "  Function lacks documentation\n"
        )
        issues = _try_heuristic_parse(response, single_entry, "security")
        assert len(issues) >= 2

    def test_numbered_list(self, single_entry):
        response = (
            "1. Variable naming issue: x and y are not descriptive\n"
            "2. Missing type hints for return values\n"
            "3. No error handling for edge cases\n"
        )
        issues = _try_heuristic_parse(response, single_entry, "best_practices")
        assert len(issues) >= 3

    def test_no_structure_raises(self, single_entry):
        with pytest.raises(ValueError):
            _try_heuristic_parse("OK", single_entry, "security")


# ── Deduplication ─────────────────────────────────────────────────────────

class TestDeduplication:
    def test_removes_near_duplicates(self):
        issues = [
            ReviewIssue(
                file_path="a.py", description="Missing type hint for function foo",
                ai_feedback="Type hint is missing for foo function",
            ),
            ReviewIssue(
                file_path="a.py", description="Missing type hint for function foo bar",
                ai_feedback="The function foo is missing a type hint annotation which should be added",
            ),
        ]
        result = _deduplicate_issues(issues)
        assert len(result) == 1
        # Keeps the longer feedback
        assert "annotation" in result[0].ai_feedback

    def test_keeps_different_issues(self):
        issues = [
            ReviewIssue(file_path="a.py", description="SQL injection", ai_feedback="SQL"),
            ReviewIssue(file_path="a.py", description="XSS vulnerability", ai_feedback="XSS"),
        ]
        result = _deduplicate_issues(issues)
        assert len(result) == 2

    def test_keeps_same_desc_different_files(self):
        issues = [
            ReviewIssue(file_path="a.py", description="Missing docstring", ai_feedback="fb1"),
            ReviewIssue(file_path="b.py", description="Missing docstring", ai_feedback="fb2"),
        ]
        result = _deduplicate_issues(issues)
        assert len(result) == 2


# ── Full pipeline tests ──────────────────────────────────────────────────

class TestParseReviewResponse:
    def test_json_strategy_wins(self, file_entries):
        response = json.dumps({
            "files": [{
                "filename": "src/app.py",
                "findings": [{
                    "severity": "high",
                    "title": "Issue",
                    "description": "Details",
                }],
            }],
        })
        issues = parse_review_response(response, file_entries, "security")
        assert len(issues) == 1
        assert issues[0].severity == "high"

    def test_delimiter_fallback(self, file_entries):
        response = (
            "=== FILE: src/app.py ===\n"
            "--- FINDING [medium] ---\n"
            "Some issue found.\n"
        )
        issues = parse_review_response(response, file_entries, "security")
        assert len(issues) == 1

    def test_empty_response(self, file_entries):
        issues = parse_review_response("", file_entries, "security")
        assert issues == []

    def test_generic_fallback(self, file_entries):
        """Completely unstructured text should still produce at least one issue."""
        response = "The code looks OK but could be improved in several ways maybe."
        issues = parse_review_response(response, file_entries, "security")
        assert len(issues) >= 1


class TestParseSingleFileResponse:
    def test_single_file_json(self):
        response = json.dumps({
            "files": [{
                "filename": "test.py",
                "findings": [{
                    "severity": "low",
                    "title": "Minor",
                    "description": "Something",
                }],
            }],
        })
        issues = parse_single_file_response(
            response, "/project/test.py", "test.py", "code", "best_practices"
        )
        assert len(issues) == 1
        assert issues[0].file_path == "/project/test.py"
