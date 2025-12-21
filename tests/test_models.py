# tests/test_models.py
"""
Tests for AI Code Reviewer data models
"""
import pytest
from datetime import datetime
from aicodereviewer.models import ReviewIssue, ReviewReport, calculate_quality_score


class TestReviewIssue:
    """Test ReviewIssue dataclass"""

    def test_review_issue_creation(self):
        """Test creating a ReviewIssue"""
        issue = ReviewIssue(
            file_path="/path/to/file.py",
            line_number=10,
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="print('hello')",
            ai_feedback="This is insecure"
        )

        assert issue.file_path == "/path/to/file.py"
        assert issue.line_number == 10
        assert issue.issue_type == "security"
        assert issue.severity == "high"
        assert issue.description == "Test issue"
        assert issue.code_snippet == "print('hello')"
        assert issue.ai_feedback == "This is insecure"
        assert issue.status == "pending"
        assert issue.resolution_reason is None
        assert issue.resolved_at is None
        assert issue.ai_fix_applied is None

    def test_review_issue_with_defaults(self):
        """Test ReviewIssue with default values"""
        issue = ReviewIssue(
            file_path="/path/to/file.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="print('hello')",
            ai_feedback="This is insecure"
        )

        assert issue.line_number is None
        assert issue.status == "pending"


class TestReviewReport:
    """Test ReviewReport dataclass"""

    def test_review_report_creation(self):
        """Test creating a ReviewReport"""
        issues = [
            ReviewIssue(
                file_path="/path/to/file.py",
                issue_type="security",
                severity="high",
                description="Test issue",
                code_snippet="print('hello')",
                ai_feedback="This is insecure"
            )
        ]

        generated_at = datetime.now()
        report = ReviewReport(
            project_path="/path/to/project",
            review_type="security",
            scope="project",
            total_files_scanned=5,
            issues_found=issues,
            generated_at=generated_at,
            language="en"
        )

        assert report.project_path == "/path/to/project"
        assert report.review_type == "security"
        assert report.scope == "project"
        assert report.total_files_scanned == 5
        assert len(report.issues_found) == 1
        assert report.generated_at == generated_at
        assert report.language == "en"
        assert report.diff_source is None

    def test_review_report_to_dict(self):
        """Test converting ReviewReport to dictionary"""
        issues = [
            ReviewIssue(
                file_path="/path/to/file.py",
                issue_type="security",
                severity="high",
                description="Test issue",
                code_snippet="print('hello')",
                ai_feedback="This is insecure",
                status="resolved",
                resolved_at=datetime.now()
            )
        ]

        generated_at = datetime.now()
        report = ReviewReport(
            project_path="/path/to/project",
            review_type="security",
            scope="project",
            total_files_scanned=5,
            issues_found=issues,
            generated_at=generated_at,
            language="en"
        )

        data = report.to_dict()

        assert data['project_path'] == "/path/to/project"
        assert data['review_type'] == "security"
        assert isinstance(data['generated_at'], str)  # Should be ISO string
        assert len(data['issues_found']) == 1

    def test_review_report_from_dict(self):
        """Test creating ReviewReport from dictionary"""
        issues_data = [
            {
                'file_path': "/path/to/file.py",
                'line_number': None,
                'issue_type': "security",
                'severity': "high",
                'description': "Test issue",
                'code_snippet': "print('hello')",
                'ai_feedback': "This is insecure",
                'status': "resolved",
                'resolution_reason': None,
                'resolved_at': datetime.now().isoformat(),
                'ai_fix_applied': None
            }
        ]

        data = {
            'project_path': "/path/to/project",
            'review_type': "security",
            'scope': "project",
            'total_files_scanned': 5,
            'issues_found': issues_data,
            'generated_at': datetime.now().isoformat(),
            'language': "en",
            'diff_source': None
        }

        report = ReviewReport.from_dict(data)

        assert report.project_path == "/path/to/project"
        assert report.review_type == "security"
        assert len(report.issues_found) == 1
        assert isinstance(report.generated_at, datetime)
        assert isinstance(report.issues_found[0].resolved_at, datetime)


class TestCalculateQualityScore:
    """Test quality score calculation"""

    def test_quality_score_no_issues(self):
        """Score should stay at 100 when there are no issues"""
        assert calculate_quality_score([]) == 100

    def test_quality_score_deductions(self):
        """Score should deduct per severity with a lower bound of 0"""
        issues = [
            ReviewIssue(file_path="a.py", severity="critical"),
            ReviewIssue(file_path="b.py", severity="high"),
            ReviewIssue(file_path="c.py", severity="medium"),
            ReviewIssue(file_path="d.py", severity="low"),
            ReviewIssue(file_path="e.py", severity="info"),
        ]

        score = calculate_quality_score(issues)

        # 100 - (20 + 10 + 5 + 2 + 1) = 62
        assert score == 62

    def test_quality_score_never_negative(self):
        """Score should not drop below zero even with many high severity issues"""
        issues = [ReviewIssue(file_path=f"f{i}.py", severity="critical") for i in range(10)]

        assert calculate_quality_score(issues) == 0