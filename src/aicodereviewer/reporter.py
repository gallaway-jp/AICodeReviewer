# src/aicodereviewer/reporter.py
"""
Report generation for code review results.

Produces JSON (machine-readable) and plain-text summary reports with
support for multi-type review sessions.
"""
import json
import logging
from typing import Dict, List, Optional, TextIO

from .models import ReviewReport
from .i18n import t
from .config import config

logger = logging.getLogger(__name__)


def generate_review_report(
    report: ReviewReport,
    output_file: Optional[str] = None,
) -> str:
    """
    Save the review report in selected formats (JSON, TXT, and/or MD).

    Args:
        report: The complete :class:`ReviewReport`.
        output_file: Custom path for the JSON file. Auto‑generated if *None*.

    Returns:
        Path to the first generated report file.
    """
    if not output_file:
        ts = report.generated_at.strftime("%Y%m%d_%H%M%S")
        output_file = f"review_report_{ts}.json"
    
    # Get enabled formats from config (default: json,txt)
    enabled_formats_str = config.get("output", "formats", "json,txt").strip()
    enabled_formats = set(enabled_formats_str.split(",")) if enabled_formats_str else {"json", "txt"}
    
    generated_files: List[str] = []
    
    # Generate JSON format
    if "json" in enabled_formats:
        json_file = output_file if output_file.endswith(".json") else output_file.replace(".txt", ".json").replace(".md", ".json")
        with open(json_file, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, indent=2, ensure_ascii=False)
        logger.info("JSON report saved to %s", json_file)
        generated_files.append(json_file)
    
    # Generate TXT format
    if "txt" in enabled_formats:
        txt_file = output_file.replace(".json", "_summary.txt") if ".json" in output_file else output_file.replace(".md", "_summary.txt")
        with open(txt_file, "w", encoding="utf-8") as fh:
            _write_summary(fh, report)
        logger.info("Summary saved to %s", txt_file)
        generated_files.append(txt_file)
    
    # Generate Markdown format
    if "md" in enabled_formats:
        md_file = output_file.replace(".json", ".md")
        with open(md_file, "w", encoding="utf-8") as fh:
            _write_markdown(fh, report)
        logger.info("Markdown report saved to %s", md_file)
        generated_files.append(md_file)
    
    # Return the first generated file (or the original output_file as fallback)
    return generated_files[0] if generated_files else output_file  # type: ignore[return-value]


def _write_summary(fh: TextIO, report: ReviewReport) -> None:
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


def _write_markdown(fh: TextIO, report: ReviewReport) -> None:
    """Write a Markdown-formatted report to an open file handle."""
    # Use the report language for the summary text
    lang = report.language or "en"

    w = fh.write
    
    # Title
    w(f"# {t('report.title', lang=lang)}\n\n")
    
    # Project Information
    w("## Project Information\n\n")
    w(f"- **{t('report.project', lang=lang)}**: {report.project_path}\n")
    w(f"- **{t('report.review_types', lang=lang)}**: {', '.join(report.review_types) if report.review_types else report.review_type}\n")
    w(f"- **{t('report.scope', lang=lang)}**: {report.scope}\n")
    w(f"- **{t('report.backend', lang=lang)}**: {report.backend}\n")
    w(f"- **{t('report.files_scanned', lang=lang)}**: {report.total_files_scanned}\n")
    w(f"- **{t('report.quality_score', lang=lang)}**: {report.quality_score}/100\n")
    w(f"- **{t('report.programmers', lang=lang)}**: {', '.join(report.programmers) or '—'}\n")
    w(f"- **{t('report.reviewers', lang=lang)}**: {', '.join(report.reviewers) or '—'}\n")
    w(f"- **{t('report.generated', lang=lang)}**: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
    w(f"- **{t('report.language', lang=lang)}**: {report.language}\n")
    if report.diff_source:
        w(f"- **{t('report.diff_source', lang=lang)}**: {report.diff_source}\n")
    w("\n")
    
    # Status breakdown
    w(f"## {t('report.issue_summary', lang=lang)}\n\n")
    status_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    for issue in report.issues_found:
        status_counts[issue.status] = status_counts.get(issue.status, 0) + 1
        severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
        type_counts[issue.issue_type] = type_counts.get(issue.issue_type, 0) + 1

    w(f"**{t('report.total_issues', lang=lang)}**: {len(report.issues_found)}\n\n")
    
    # Status counts table
    if status_counts:
        w("### By Status\n\n")
        w("| Status | Count |\n")
        w("|--------|-------|\n")
        for status, cnt in sorted(status_counts.items()):
            w(f"| {status.capitalize()} | {cnt} |\n")
        w("\n")

    # Severity counts table
    if severity_counts:
        w(f"### {t('report.by_severity', lang=lang)}\n\n")
        w("| Severity | Count |\n")
        w("|----------|-------|\n")
        for sev in ("critical", "high", "medium", "low", "info"):
            if sev in severity_counts:
                w(f"| {sev.capitalize()} | {severity_counts[sev]} |\n")
        w("\n")

    # Review type counts table
    if type_counts:
        w(f"### {t('report.by_review_type', lang=lang)}\n\n")
        w("| Review Type | Count |\n")
        w("|-------------|-------|\n")
        for rtype, cnt in sorted(type_counts.items()):
            w(f"| {rtype} | {cnt} |\n")
        w("\n")

    # Detailed issues
    w(f"## {t('report.detailed_issues', lang=lang)}\n\n")
    for i, issue in enumerate(report.issues_found, 1):
        w(f"### {t('report.issue_n', lang=lang, n=i)}\n\n")
        w(f"- **{t('report.file', lang=lang)}**: `{issue.file_path}`\n")
        w(f"- **{t('report.type', lang=lang)}**: {issue.issue_type}\n")
        w(f"- **{t('report.severity', lang=lang)}**: {issue.severity}\n")
        w(f"- **{t('report.status', lang=lang)}**: {issue.status}\n")
        if issue.resolution_reason:
            w(f"- **{t('report.reason', lang=lang)}**: {issue.resolution_reason}\n")
        w(f"- **{t('report.desc', lang=lang)}**: {issue.description}\n")
        
        # Code snippet (limited size)
        w(f"\n**{t('report.snippet', lang=lang)}**:\n")
        w("```\n")
        w(issue.code_snippet[:500])
        if len(issue.code_snippet) > 500:
            w("...\n")
        w("\n```\n\n")
        
        # AI Feedback
        w(f"**{t('report.feedback', lang=lang)}**:\n")
        w(f"{issue.ai_feedback}\n\n")
        w("---\n\n")
