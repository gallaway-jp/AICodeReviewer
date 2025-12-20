# src/aicodereviewer/models.py
"""
Data models for AICodeReviewer.

This module defines the core data structures used throughout the application
for representing code review issues and comprehensive review reports.

Classes:
    ReviewIssue: Represents individual code review findings with metadata
    ReviewReport: Contains complete review results with statistics and issues
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class ReviewIssue:
    """
    Represents a single code review issue found during analysis.

    This class encapsulates all information about a specific code quality issue,
    including its location, severity, description, and resolution status.

    Attributes:
        file_path (str): Path to the file containing the issue
        line_number (Optional[int]): Line number where issue occurs (None for file-level issues)
        issue_type (str): Category of issue (e.g., 'security', 'performance', 'style')
        severity (str): Severity level ('low', 'medium', 'high', 'critical')
        description (str): Human-readable description of the issue
        code_snippet (str): Relevant code snippet showing the issue
        ai_feedback (str): AI-generated explanation and recommendations
        status (str): Current status ('pending', 'resolved', 'ignored', 'ai_fixed')
        resolution_reason (Optional[str]): Reason for resolution if applicable
        resolved_at (Optional[datetime]): Timestamp when issue was resolved
        ai_fix_applied (Optional[str]): Code fix applied by AI if any
    """
    file_path: str
    line_number: Optional[int] = None
    issue_type: str = ""
    severity: str = "medium"  # 'low', 'medium', 'high', 'critical'
    description: str = ""
    code_snippet: str = ""
    ai_feedback: str = ""
    status: str = "pending"  # 'pending', 'resolved', 'ignored', 'ai_fixed'
    resolution_reason: Optional[str] = None
    resolved_at: Optional[datetime] = None
    ai_fix_applied: Optional[str] = None


@dataclass
class ReviewReport:
    """
    Complete review report containing all issues and metadata.

    This class represents the final output of a code review session,
    including statistics, all found issues, and generation metadata.

    Attributes:
        project_path (str): Root path of the reviewed project
        review_type (str): Type of review performed (e.g., 'security', 'performance')
        scope (str): Review scope ('project' or 'diff')
        total_files_scanned (int): Number of files analyzed
        issues_found (List[ReviewIssue]): All issues discovered during review
        generated_at (datetime): Timestamp when report was generated
        language (str): Language used for AI responses ('en' or 'ja')
        diff_source (Optional[str]): Diff source for diff-based reviews
    """
    project_path: str
    review_type: str
    scope: str
    total_files_scanned: int
    issues_found: List[ReviewIssue]
    generated_at: datetime
    language: str
    diff_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert report to dictionary for JSON serialization.

        Handles datetime conversion to ISO format strings for JSON compatibility.

        Returns:
            Dict[str, Any]: Dictionary representation suitable for JSON serialization
        """
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data['generated_at'] = self.generated_at.isoformat()
        for issue in data['issues_found']:
            if issue['resolved_at']:
                issue['resolved_at'] = issue['resolved_at'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReviewReport':
        """
        Create ReviewReport instance from dictionary.

        Used for loading saved reports from JSON files. Handles conversion
        of ISO datetime strings back to datetime objects.

        Args:
            data (Dict[str, Any]): Dictionary containing report data

        Returns:
            ReviewReport: New instance with deserialized data
        """
        # Convert ISO strings back to datetime objects
        data['generated_at'] = datetime.fromisoformat(data['generated_at'])
        for issue in data['issues_found']:
            if issue['resolved_at']:
                issue['resolved_at'] = datetime.fromisoformat(issue['resolved_at'])
        # Convert issue dictionaries to ReviewIssue objects
        data['issues_found'] = [ReviewIssue(**issue) for issue in data['issues_found']]
        return cls(**data)