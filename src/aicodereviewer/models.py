# src/aicodereviewer/models.py
"""
Data models for AICodeReviewer.

Defines core data structures for review issues, reports, and quality scoring.
Supports multi-type reviews where a single session can combine several
review categories.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any

__all__ = ["ReviewIssue", "ReviewReport", "calculate_quality_score"]


@dataclass
class ReviewIssue:
    """
    Represents a single code review issue found during analysis.

    Attributes:
        file_path: Path to the file containing the issue.
        line_number: Line where the issue occurs (None for file-level).
        issue_type: Review category (e.g. 'security', 'performance').
        severity: One of 'critical', 'high', 'medium', 'low', 'info'.
        description: Human-readable summary.
        code_snippet: Relevant code excerpt.
        ai_feedback: Full AI-generated explanation.
        status: 'pending', 'resolved', 'ignored', or 'ai_fixed'.
        resolution_reason: User-provided reason when ignoring.
        resolved_at: Timestamp when the issue was resolved.
        ai_fix_applied: Code content of the applied fix.
    """
    file_path: str
    line_number: int | None = None
    issue_type: str = ""
    severity: str = "medium"
    description: str = ""
    code_snippet: str = ""
    ai_feedback: str = ""
    status: str = "pending"
    resolution_reason: str | None = None
    resolved_at: datetime | None = None
    ai_fix_applied: str | None = None


@dataclass
class ReviewReport:
    """
    Aggregated review report for one session.

    A session may span multiple *review_types* when the user requests a
    combined review.

    Attributes:
        project_path: Root directory that was reviewed.
        review_type: Comma-separated list of review types performed.
        review_types: Ordered list of individual types (canonical source).
        scope: 'project' or 'diff'.
        total_files_scanned: Number of files analysed.
        issues_found: All issues discovered.
        generated_at: Report generation timestamp.
        language: Response language code.
        diff_source: Diff file/commit range (diff scope only).
        quality_score: Aggregated 0-100 score.
        programmers: People who wrote the code.
        reviewers: People who performed the review.
        backend: AI backend used (bedrock / kiro / copilot).
    """
    project_path: str
    review_type: str  # kept for backward compat – comma-joined
    scope: str
    total_files_scanned: int
    issues_found: list[ReviewIssue]
    generated_at: datetime
    language: str
    review_types: list[str] = field(default_factory=list)
    diff_source: str | None = None
    quality_score: int | None = None
    programmers: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    backend: str = "bedrock"

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        data = asdict(self)
        data["generated_at"] = self.generated_at.isoformat()
        for issue in data["issues_found"]:
            if issue["resolved_at"]:
                issue["resolved_at"] = issue["resolved_at"].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewReport:
        """Deserialise from a dictionary (e.g. loaded from JSON)."""
        data["generated_at"] = datetime.fromisoformat(data["generated_at"])
        for issue in data["issues_found"]:
            if issue.get("resolved_at"):
                issue["resolved_at"] = datetime.fromisoformat(issue["resolved_at"])
        data["issues_found"] = [ReviewIssue(**issue) for issue in data["issues_found"]]
        # Handle old reports that lack new fields
        data.setdefault("review_types", [])
        data.setdefault("backend", "bedrock")
        return cls(**data)


# ── Quality scoring ────────────────────────────────────────────────────────

_SEVERITY_DEDUCTIONS = {
    "critical": 20,
    "high": 10,
    "medium": 5,
    "low": 2,
    "info": 1,
}


def calculate_quality_score(issues: list[ReviewIssue]) -> int:
    """
    Calculate an aggregated quality score (0-100) based on issues.

    Starts at 100 and deducts points per issue based on severity.
    """
    if not issues:
        return 100
    score = 100
    for issue in issues:
        score -= _SEVERITY_DEDUCTIONS.get(issue.severity, 1)
    return max(0, score)
