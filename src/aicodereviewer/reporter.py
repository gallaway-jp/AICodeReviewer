# src/aicodereviewer/reporter.py
"""
Report generation for code review results.

Produces JSON (machine-readable) and plain-text summary reports with
support for multi-type review sessions.
"""
import json
import logging
from typing import Optional, Dict

from .models import ReviewReport
from .i18n import t

logger = logging.getLogger(__name__)


def generate_review_report(
    report: ReviewReport,
    output_file: Optional[str] = None,
) -> str:
    """
    Save the review report as JSON and a human-readable summary.

    Args:
        report: The complete :class:`ReviewReport`.
        output_file: Custom path for the JSON file. Auto‑generated if *None*.

    Returns:
        Path to the JSON report file.
    """
    if not output_file:
        ts = report.generated_at.strftime("%Y%m%d_%H%M%S")
        output_file = f"review_report_{ts}.json"

    # JSON
    with open(output_file, "w", encoding="utf-8") as fh:
        json.dump(report.to_dict(), fh, indent=2, ensure_ascii=False)
    logger.info("JSON report saved to %s", output_file)

    # Text summary
    summary_file = output_file.replace(".json", "_summary.txt")
    with open(summary_file, "w", encoding="utf-8") as fh:
        _write_summary(fh, report)
    logger.info("Summary saved to %s", summary_file)

    return output_file


def _write_summary(fh, report: ReviewReport):
    """Write a human-readable summary to an open file handle."""
    # Use the report language for the summary text
    lang = report.language or "en"

    w = fh.write
    w(t("report.title", lang=lang) + "\n")
    w("=" * 60 + "\n\n")
    w(f"{t('report.project', lang=lang):13s}: {report.project_path}\n")
    w(f"{t('report.review_types', lang=lang):13s}: {', '.join(report.review_types) if report.review_types else report.review_type}\n")
    w(f"{t('report.scope', lang=lang):13s}: {report.scope}\n")
    w(f"{t('report.backend', lang=lang):13s}: {report.backend}\n")
    w(f"{t('report.files_scanned', lang=lang):13s}: {report.total_files_scanned}\n")
    w(f"{t('report.quality_score', lang=lang):13s}: {report.quality_score}/100\n")
    w(f"{t('report.programmers', lang=lang):13s}: {', '.join(report.programmers) or '—'}\n")
    w(f"{t('report.reviewers', lang=lang):13s}: {', '.join(report.reviewers) or '—'}\n")
    w(f"{t('report.generated', lang=lang):13s}: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
    w(f"{t('report.language', lang=lang):13s}: {report.language}\n")
    if report.diff_source:
        w(f"{t('report.diff_source', lang=lang):13s}: {report.diff_source}\n")

    # Status breakdown
    w(f"\n{t('report.issue_summary', lang=lang)}\n")
    w("-" * 40 + "\n")
    status_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    for issue in report.issues_found:
        status_counts[issue.status] = status_counts.get(issue.status, 0) + 1
        severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
        type_counts[issue.issue_type] = type_counts.get(issue.issue_type, 0) + 1

    w(f"  {t('report.total_issues', lang=lang)}: {len(report.issues_found)}\n")
    for status, cnt in sorted(status_counts.items()):
        w(f"  {status.capitalize():12s}: {cnt}\n")

    if severity_counts:
        w(f"\n{t('report.by_severity', lang=lang)}\n")
        w("-" * 40 + "\n")
        for sev in ("critical", "high", "medium", "low", "info"):
            if sev in severity_counts:
                w(f"  {sev.capitalize():12s}: {severity_counts[sev]}\n")

    if type_counts:
        w(f"\n{t('report.by_review_type', lang=lang)}\n")
        w("-" * 40 + "\n")
        for rtype, cnt in sorted(type_counts.items()):
            w(f"  {rtype:20s}: {cnt}\n")

    # Detailed issues
    w(f"\n\n{t('report.detailed_issues', lang=lang)}\n")
    w("=" * 60 + "\n")
    for i, issue in enumerate(report.issues_found, 1):
        w(f"\n--- {t('report.issue_n', lang=lang, n=i)} ---\n")
        w(f"  {t('report.file', lang=lang):9s}: {issue.file_path}\n")
        w(f"  {t('report.type', lang=lang):9s}: {issue.issue_type}\n")
        w(f"  {t('report.severity', lang=lang):9s}: {issue.severity}\n")
        w(f"  {t('report.status', lang=lang):9s}: {issue.status}\n")
        if issue.resolution_reason:
            w(f"  {t('report.reason', lang=lang):9s}: {issue.resolution_reason}\n")
        w(f"  {t('report.desc', lang=lang):9s}: {issue.description}\n")
        w(f"  {t('report.snippet', lang=lang):9s}: {issue.code_snippet[:120]}\n")
        feedback_preview = issue.ai_feedback[:300]
        if len(issue.ai_feedback) > 300:
            feedback_preview += "…"
        w(f"  {t('report.feedback', lang=lang):9s}: {feedback_preview}\n")
