# tests/test_reporter.py
"""
Tests for AI Code Reviewer reporter functionality
"""
import pytest
import json
import tempfile
from datetime import datetime
from pathlib import Path
from aicodereviewer.reporter import generate_review_report
from aicodereviewer.models import ReviewIssue, ReviewReport


class TestGenerateReviewReport:
    """Test report generation functionality"""

    def create_test_report(self):
        """Helper to create a test report"""
        issues = [
            ReviewIssue(
                file_path="/path/to/file1.py",
                issue_type="security",
                severity="high",
                description="Security issue",
                code_snippet="insecure_code()",
                ai_feedback="This is insecure",
                status="resolved"
            ),
            ReviewIssue(
                file_path="/path/to/file2.py",
                issue_type="performance",
                severity="medium",
                description="Performance issue",
                code_snippet="slow_code()",
                ai_feedback="This is slow",
                status="ignored",
                resolution_reason="Not applicable"
            )
        ]

        return ReviewReport(
            project_path="/path/to/project",
            review_type="security",
            scope="project",
            total_files_scanned=10,
            issues_found=issues,
            generated_at=datetime(2024, 1, 1, 12, 0, 0),
            language="en"
        )

    def test_generate_review_report_with_output_file(self):
        """Test report generation with specified output file"""
        report = self.create_test_report()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "test_report.json"

            result_file = generate_review_report(report, str(output_file))

            assert result_file == str(output_file)
            assert output_file.exists()

            # Check JSON content
            with open(output_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            assert data['project_path'] == "/path/to/project"
            assert data['review_type'] == "security"
            assert len(data['issues_found']) == 2

    def test_generate_review_report_auto_filename(self):
        """Test report generation with auto-generated filename"""
        report = self.create_test_report()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Change to temp directory for relative path generation
            import os
            old_cwd = os.getcwd()
            os.chdir(temp_dir)

            try:
                result_file = generate_review_report(report)

                assert "review_report_20240101_120000.json" in result_file
                assert Path(result_file).exists()

                # Check summary file was also created
                summary_file = result_file.replace('.json', '_summary.txt')
                assert Path(summary_file).exists()

            finally:
                os.chdir(old_cwd)

    def test_generate_review_report_summary_content(self):
        """Test that summary file contains correct content"""
        report = self.create_test_report()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "test_report.json"

            generate_review_report(report, str(output_file))

            summary_file = output_file.parent / (output_file.stem + '_summary.txt')

            with open(summary_file, 'r', encoding='utf-8') as f:
                content = f.read()

            assert "AI Code Review Report" in content
            assert "/path/to/project" in content
            assert "security" in content
            assert "Files Scanned: 10" in content
            assert "Resolved: 1" in content
            assert "Ignored: 1" in content

    def test_generate_review_report_detailed_issues(self):
        """Test detailed issues in summary"""
        report = self.create_test_report()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "test_report.json"

            generate_review_report(report, str(output_file))

            summary_file = output_file.parent / (output_file.stem + '_summary.txt')

            with open(summary_file, 'r', encoding='utf-8') as f:
                content = f.read()

            assert "Issue 1:" in content
            assert "/path/to/file1.py" in content
            assert "Security issue" in content
            assert "Issue 2:" in content
            assert "/path/to/file2.py" in content
            assert "Not applicable" in content