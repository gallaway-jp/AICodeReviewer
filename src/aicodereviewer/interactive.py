# src/aicodereviewer/interactive.py
"""
Interactive CLI workflow for reviewing AI-identified issues.

Users can resolve, ignore, request AI fixes, or view source code for
each issue, with backup creation and diff preview for fixes.
"""
import shutil
import logging
import difflib
from datetime import datetime
from pathlib import Path
from typing import List

from .models import ReviewIssue
from .reviewer import verify_issue_resolved
from .fixer import apply_ai_fix
from .i18n import t
from .backends.base import AIBackend

__all__ = ["get_valid_choice", "interactive_review_confirmation"]

logger = logging.getLogger(__name__)


def get_valid_choice(prompt: str, valid_options: List[str]) -> str:
    """Prompt until a valid option is chosen or the user cancels."""
    while True:
        try:
            choice = input(prompt).strip().lower()
            if choice in [v.lower() for v in valid_options]:
                return choice
            logger.warning(t("interactive.invalid_choice", options=", ".join(valid_options)))
        except (KeyboardInterrupt, EOFError):
            logger.info(t("interactive.cancelled"))
            return "cancel"


def interactive_review_confirmation(
    issues: List[ReviewIssue],
    client: AIBackend,
    review_type: str,
    lang: str,
) -> List[ReviewIssue]:
    """
    Walk through each issue interactively and let the user decide.

    Actions per issue:
        1. RESOLVED  – mark resolved (re-verifies with AI)
        2. IGNORE    – ignore with a reason
        3. AI FIX    – generate and preview an AI-suggested fix
        4. VIEW CODE – display the full file
        5. SKIP      – leave pending and move on

    Returns the (mutated) list of issues.
    """
    total = len(issues)
    for idx, issue in enumerate(issues, 1):
        _print_issue_header(idx, total, issue)

        while issue.status == "pending":
            print(f"\n{t('interactive.actions')}")
            print(t("interactive.opt_resolved"))
            print(t("interactive.opt_ignore"))
            print(t("interactive.opt_ai_fix"))
            print(t("interactive.opt_view_code"))
            print(t("interactive.opt_skip"))

            choice = get_valid_choice(t("interactive.choose"), ["1", "2", "3", "4", "5"])
            if choice == "cancel":
                return issues
            if choice == "5":
                break

            if choice == "1":
                _action_resolve(issue, client, review_type, lang)
            elif choice == "2":
                _action_ignore(issue)
            elif choice == "3":
                _action_ai_fix(issue, client, review_type, lang)
            elif choice == "4":
                _action_view_code(issue)

    return issues


# ── actions ────────────────────────────────────────────────────────────────

def _action_resolve(
    issue: ReviewIssue, client: AIBackend, review_type: str, lang: str
) -> None:
    if verify_issue_resolved(issue, client, review_type, lang):
        issue.status = "resolved"
        issue.resolved_at = datetime.now()
        print(t("interactive.verified"))
    else:
        print(t("interactive.verify_failed"))
        force = get_valid_choice(t("interactive.force_resolve"), ["y", "n"])
        if force == "y":
            issue.status = "resolved"
            issue.resolved_at = datetime.now()
            issue.resolution_reason = t("interactive.force_reason")
            print(t("interactive.force_resolved"))


def _action_ignore(issue: ReviewIssue) -> None:
    try:
        reason = input(t("interactive.ignore_reason")).strip()
    except (KeyboardInterrupt, EOFError):
        return
    if len(reason) >= 3:
        issue.status = "ignored"
        issue.resolution_reason = reason
        issue.resolved_at = datetime.now()
        print(t("interactive.ignored"))
    else:
        print(t("interactive.reason_too_short"))


def _action_ai_fix(
    issue: ReviewIssue, client: AIBackend, review_type: str, lang: str
) -> None:
    fix_result = apply_ai_fix(issue, client, review_type, lang)
    if not fix_result:
        print(t("interactive.fix_failed"))
        return

    file_path = issue.file_path or ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            current = fh.read()
    except Exception as exc:
        print(t("interactive.diff_read_error", error=exc))
        return

    _show_diff(current, fix_result, file_path)

    confirm = get_valid_choice(t("interactive.apply_fix"), ["y", "n"])
    if confirm == "y":
        backup = f"{issue.file_path}.backup"
        try:
            shutil.copy2(issue.file_path, backup)
            print(t("interactive.backup_created", path=backup))
            with open(issue.file_path, "w", encoding="utf-8") as fh:
                fh.write(fix_result)
            issue.status = "ai_fixed"
            issue.ai_fix_applied = fix_result
            issue.resolved_at = datetime.now()
            print(t("interactive.fix_applied"))
        except Exception as exc:
            print(t("interactive.fix_error", error=exc))
    else:
        print(t("interactive.fix_cancelled"))


def _action_view_code(issue: ReviewIssue) -> None:
    file_path = issue.file_path or ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
        print(f"\n{'─' * 60}")
        print(content)
        print(f"{'─' * 60}")
    except Exception as exc:
        print(t("interactive.view_error", error=exc))


# ── helpers ────────────────────────────────────────────────────────────────

def _print_issue_header(idx: int, total: int, issue: ReviewIssue) -> None:
    print(f"\n{'=' * 80}")
    print(t("interactive.header", idx=idx, total=total, type=issue.issue_type, severity=issue.severity))
    print(f"{'=' * 80}")
    print(t("interactive.file", path=issue.file_path))
    snippet = issue.code_snippet or ""
    print(t("interactive.snippet", snippet=snippet[:120]))
    print(t("interactive.feedback", feedback=issue.ai_feedback))


def _show_diff(original: str, fixed: str, filepath: str):
    name = Path(filepath).name
    diff = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
        )
    )
    print(f"\n{'=' * 60}")
    if diff:
        print("".join(diff))
    else:
        print("(no changes detected)")
    print(f"{'=' * 60}")
