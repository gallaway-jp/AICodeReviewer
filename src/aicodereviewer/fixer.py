# src/aicodereviewer/fixer.py
"""
AI-powered code fix generation.

Delegates to the active :class:`AIBackend` to produce corrected source code
for a given review issue.
"""
import os
import logging
from typing import Optional

from .models import ReviewIssue
from .config import config
from .backends.base import AIBackend

logger = logging.getLogger(__name__)


def apply_ai_fix(
    issue: ReviewIssue,
    client: AIBackend,
    review_type: str,
    lang: str,
) -> Optional[str]:
    """
    Ask the AI backend to produce a fixed version of the file.

    Args:
        issue: The issue to fix.
        client: An :class:`AIBackend` instance.
        review_type: The review category.
        lang: Response language.

    Returns:
        Fixed code string, or *None* on failure.
    """
    file_path = issue.file_path or ""
    try:
        file_size = os.path.getsize(file_path)
        max_fix_size = config.get("performance", "max_fix_file_size_mb")
        if file_size > max_fix_size:
            logger.warning(
                "File too large for AI fix: %s (%d bytes)", file_path, file_size
            )
            return None

        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            current_code = fh.read()

        max_content = config.get("performance", "max_fix_content_length")
        if not current_code or len(current_code) > max_content:
            logger.warning(
                "Content too large for fix: %s (%d chars)", issue.file_path, len(current_code)
            )
            return None

        # Use the backend's dedicated get_fix method if available,
        # falling back to get_review with a fix prompt.
        if hasattr(client, "get_fix"):
            result = client.get_fix(
                current_code,
                issue_feedback=issue.ai_feedback,
                review_type=review_type,
                lang=lang,
            )
        else:
            fix_prompt = (
                f"You are an expert code fixer. Fix this specific issue:\n\n"
                f"ISSUE TYPE: {review_type}\n"
                f"FEEDBACK: {issue.ai_feedback}\n\n"
                f"CODE TO FIX:\n{current_code}\n\n"
                "Return ONLY the complete corrected code, no explanations or markdown."
            )
            result = client.get_review(fix_prompt, review_type="fix", lang=lang)

        if result and not result.startswith("Error:"):
            return result.strip()
        return None

    except Exception as exc:
        logger.error("Error generating AI fix: %s", exc)
        return None
