# src/aicodereviewer/interactive.py
"""
Interactive user interface for code review confirmation and resolution.

This module provides the interactive workflow for users to review AI-identified
issues, mark them as resolved, apply AI fixes, or ignore them with reasons.
Includes file backup functionality and comprehensive user input validation.

Functions:
    get_valid_choice: Get validated user input with error handling
    interactive_review_confirmation: Main interactive review workflow
"""
import shutil
import logging
from datetime import datetime
from typing import List
import difflib
from pathlib import Path

from .models import ReviewIssue
from .reviewer import verify_issue_resolved
from .fixer import apply_ai_fix

logger = logging.getLogger(__name__)


def get_valid_choice(prompt: str, valid_options: List[str]) -> str:
    """
    Get validated user input with comprehensive error handling.

    Continuously prompts user until valid input is provided or operation
    is cancelled via keyboard interrupt.

    Args:
        prompt (str): The prompt message to display to user
        valid_options (List[str]): List of valid input options

    Returns:
        str: User's validated choice, or "cancel" if operation cancelled
    """
    while True:
        try:
            choice = input(prompt).strip()
            if choice in valid_options:
                return choice
            logger.warning(f"Invalid choice. Please select from: {', '.join(valid_options)}")
        except KeyboardInterrupt:
            logger.info("Operation cancelled by user.")
            return "cancel"
        except EOFError:
            logger.info("Input stream ended. Operation cancelled.")
            return "cancel"


def interactive_review_confirmation(issues: List[ReviewIssue], client, review_type: str, lang: str) -> List[ReviewIssue]:
    """
    Interactive workflow for confirming and resolving code review issues.

    Presents each issue to the user with options to:
    - Mark as resolved (with verification)
    - Ignore with reason
    - Apply AI-generated fix
    - View full file content

    Includes automatic backup creation before applying fixes.

    Args:
        issues (List[ReviewIssue]): List of issues to review
        client: AI review client instance
        review_type (str): Type of review being performed
        lang (str): Language for AI responses

    Returns:
        List[ReviewIssue]: Updated issues with user resolutions applied
    """
    for i, issue in enumerate(issues, 1):
        logger.info("\n" + ("=" * 80))
        logger.info(f"ISSUE {i}/{len(issues)}")
        logger.info("" + ("=" * 80))
        logger.info(f"File: {issue.file_path}")
        logger.info(f"Type: {issue.issue_type}")
        logger.info(f"Severity: {issue.severity}")
        logger.info(f"Code snippet:\n{issue.code_snippet}")
        logger.info(f"\nAI Feedback:\n{issue.ai_feedback}")
        logger.info(f"\nStatus: {issue.status}")

        while issue.status == "pending":
            logger.info("\nActions:")
            logger.info("  1. RESOLVED - Mark as resolved (program will verify)")
            logger.info("  2. IGNORE - Ignore this issue (requires reason)")
            logger.info("  3. AI FIX - Let AI fix the code")
            logger.info("  4. VIEW CODE - Show full file content")

            choice = get_valid_choice("Choose action (1-4): ", ["1", "2", "3", "4"])
            if choice == "cancel":
                break

            if choice == "1":
                # RESOLVED - verify the issue is actually resolved
                if verify_issue_resolved(issue, client, review_type, lang):
                    issue.status = "resolved"
                    issue.resolved_at = datetime.now()
                    logger.info("✅ Issue marked as resolved!")
                else:
                    logger.warning("❌ Issue verification failed. Issue may not be fully resolved.")

            elif choice == "2":
                # IGNORE - require reason
                reason = input("Enter reason for ignoring this issue: ").strip()
                if reason and len(reason) >= 3:  # Minimum 3 characters for a valid reason
                    issue.status = "ignored"
                    issue.resolution_reason = reason
                    issue.resolved_at = datetime.now()
                    logger.info("✅ Issue ignored with reason provided.")
                else:
                    logger.warning("❌ Reason must be at least 3 characters long.")

            elif choice == "3":
                # AI FIX - apply AI-generated fix with confirmation
                fix_result = apply_ai_fix(issue, client, review_type, lang)
                if fix_result:
                    # Read current file content for diff generation
                    try:
                        with open(issue.file_path, "r", encoding="utf-8", errors="ignore") as f:
                            current_content = f.read()
                    except Exception as e:
                        logger.error(f"❌ Error reading current file for diff: {e}")
                        continue

                    # Generate unified diff
                    current_lines = current_content.splitlines(keepends=True)
                    fixed_lines = fix_result.splitlines(keepends=True)
                    diff = list(difflib.unified_diff(
                        current_lines,
                        fixed_lines,
                        fromfile=f"a/{Path(issue.file_path).name}",
                        tofile=f"b/{Path(issue.file_path).name}",
                        lineterm=""
                    ))

                    logger.info("\n🤖 AI suggests the following fix:")
                    logger.info("=" * 80)
                    if diff:
                        logger.info("".join(diff))
                    else:
                        logger.info("No changes detected in diff (files may be identical)")
                    logger.info("=" * 80)

                    confirm = get_valid_choice("Apply this AI fix? (y/n): ", ["y", "n", "yes", "no"])
                    if confirm.lower() in ["y", "yes"]:
                        # Create backup before applying
                        backup_path = f"{issue.file_path}.backup"
                        try:
                            shutil.copy2(issue.file_path, backup_path)
                            logger.info(f"📁 Backup created: {backup_path}")

                            # Apply the fix
                            with open(issue.file_path, "w", encoding="utf-8") as f:
                                f.write(fix_result)

                            issue.status = "ai_fixed"
                            issue.ai_fix_applied = fix_result
                            issue.resolved_at = datetime.now()
                            logger.info("✅ AI fix applied successfully!")
                        except Exception as e:
                            logger.error(f"❌ Error applying fix: {e}")
                    else:
                        logger.info("❌ AI fix cancelled by user.")
                else:
                    logger.error("❌ AI fix could not be generated.")

            elif choice == "4":
                # VIEW CODE - show full file content
                try:
                    with open(issue.file_path, "r", encoding="utf-8", errors="ignore") as f:
                        full_content = f.read()
                    logger.info(f"\nFull file content ({issue.file_path}):")
                    logger.info("-" * 50)
                    logger.info(full_content)
                    logger.info("-" * 50)
                except Exception as e:
                    logger.error(f"Error reading file: {e}")

            else:
                logger.warning("Invalid choice. Please select 1-4.")

    return issues