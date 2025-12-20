# src/aicodereviewer/models.py
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class ReviewIssue:
    """Represents a single code review issue"""
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
    """Complete review report with all issues and metadata"""
    project_path: str
    review_type: str
    scope: str
    total_files_scanned: int
    issues_found: List[ReviewIssue]
    generated_at: datetime
    language: str
    diff_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data['generated_at'] = self.generated_at.isoformat()
        for issue in data['issues_found']:
            if issue['resolved_at']:
                issue['resolved_at'] = issue['resolved_at'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReviewReport':
        """Create from dictionary (for loading saved reports)"""
        # Convert ISO strings back to datetime objects
        data['generated_at'] = datetime.fromisoformat(data['generated_at'])
        for issue in data['issues_found']:
            if issue['resolved_at']:
                issue['resolved_at'] = datetime.fromisoformat(issue['resolved_at'])
        # Convert issue dictionaries to ReviewIssue objects
        data['issues_found'] = [ReviewIssue(**issue) for issue in data['issues_found']]
        return cls(**data)