# src/aicodereviewer/reporter.py
import json

from .models import ReviewReport


def generate_review_report(report: ReviewReport, output_file: str = None) -> str:
    """Generate and save a review report"""
    if not output_file:
        timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
        output_file = f"review_report_{timestamp}.json"

    # Save JSON report
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

    # Generate human-readable summary
    summary_file = output_file.replace('.json', '_summary.txt')
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("AI Code Review Report\n")
        f.write("="*50 + "\n\n")
        f.write(f"Project: {report.project_path}\n")
        f.write(f"Review Type: {report.review_type}\n")
        f.write(f"Scope: {report.scope}\n")
        f.write(f"Files Scanned: {report.total_files_scanned}\n")
        f.write(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Language: {report.language}\n")
        if report.diff_source:
            f.write(f"Diff Source: {report.diff_source}\n")
        f.write("\nIssues Summary:\n")
        f.write("-"*30 + "\n")

        status_counts = {}
        for issue in report.issues_found:
            status_counts[issue.status] = status_counts.get(issue.status, 0) + 1

        for status, count in status_counts.items():
            f.write(f"{status.capitalize()}: {count}\n")

        f.write("\nDetailed Issues:\n")
        f.write("="*50 + "\n")

        for i, issue in enumerate(report.issues_found, 1):
            f.write(f"\nIssue {i}:\n")
            f.write(f"  File: {issue.file_path}\n")
            f.write(f"  Type: {issue.issue_type}\n")
            f.write(f"  Severity: {issue.severity}\n")
            f.write(f"  Status: {issue.status}\n")
            if issue.resolution_reason:
                f.write(f"  Resolution: {issue.resolution_reason}\n")
            f.write(f"  Description: {issue.description}\n")
            f.write(f"  Code: {issue.code_snippet}\n")
            f.write(f"  AI Feedback: {issue.ai_feedback[:200]}...\n")

    return output_file