# src/aicodereviewer/fixer.py
"""
AI-powered code fix generation.

Delegates to the active :class:`AIBackend` to produce corrected source code
for a given review issue.
"""
import os
import logging
from dataclasses import dataclass
from typing import Optional

from .models import ReviewIssue
from .config import config
from .backends.base import AIBackend
from .diagnostics import build_failure_diagnostic, diagnostic_from_exception, FailureDiagnostic

__all__ = ["FixGenerationResult", "generate_ai_fix_result", "apply_ai_fix"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FixGenerationResult:
    """Structured result for one AI fix generation attempt."""

    content: str | None
    diagnostic: FailureDiagnostic | None = None

    @property
    def ok(self) -> bool:
        return isinstance(self.content, str) and bool(self.content)


def generate_ai_fix_result(
    issue: ReviewIssue,
    client: AIBackend,
    review_type: str,
    lang: str,
) -> FixGenerationResult:
    """Ask the AI backend to produce a fixed version of the file with failure diagnostics."""
    file_path = issue.file_path or ""
    issue_feedback = issue.ai_feedback or issue.description or ""
    try:
        file_size = os.path.getsize(file_path)
        max_fix_size = config.get("performance", "max_fix_file_size_mb")
        if file_size > max_fix_size:
            logger.warning(
                "File too large for AI fix: %s (%d bytes)", file_path, file_size
            )
            return FixGenerationResult(
                content=None,
                diagnostic=build_failure_diagnostic(
                    category="configuration",
                    origin="fix_generation",
                    detail=(
                        f"File exceeds the configured AI fix size limit: {file_size} bytes > {max_fix_size}"
                    ),
                ),
            )

        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            current_code = fh.read()

        max_content = config.get("performance", "max_fix_content_length")
        if not current_code or len(current_code) > max_content:
            logger.warning(
                "Content too large for fix: %s (%d chars)", issue.file_path, len(current_code)
            )
            return FixGenerationResult(
                content=None,
                diagnostic=build_failure_diagnostic(
                    category="configuration",
                    origin="fix_generation",
                    detail=(
                        f"File content exceeds the configured AI fix content limit: {len(current_code)} chars > {max_content}"
                    ),
                ),
            )

        if hasattr(client, "get_fix"):
            result = client.get_fix(
                current_code,
                issue_feedback=issue_feedback,
                review_type=review_type,
                lang=lang,
            )
        else:
            fix_prompt = (
                f"You are an expert code fixer. Fix this specific issue:\n\n"
                f"ISSUE TYPE: {review_type}\n"
                f"FEEDBACK: {issue_feedback}\n\n"
                f"CODE TO FIX:\n{current_code}\n\n"
                "Return ONLY the complete corrected code, no explanations or markdown."
            )
            result = client.get_review(fix_prompt, review_type="fix", lang=lang)

        if result and not result.startswith("Error:"):
            return FixGenerationResult(content=result.strip())

        detail = "Backend returned no usable fix content."
        if isinstance(result, str) and result.strip():
            detail = result.strip()
        return FixGenerationResult(
            content=None,
            diagnostic=build_failure_diagnostic(
                category="provider",
                origin="fix_generation",
                detail=detail,
            ),
        )

    except FileNotFoundError as exc:
        logger.error("Error generating AI fix: %s", exc)
        return FixGenerationResult(
            content=None,
            diagnostic=build_failure_diagnostic(
                category="configuration",
                origin="fix_generation",
                detail=str(exc),
                exception_type=type(exc).__name__,
            ),
        )
    except Exception as exc:
        logger.error("Error generating AI fix: %s", exc)
        return FixGenerationResult(content=None, diagnostic=diagnostic_from_exception(exc, origin="fix_generation"))


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
    return generate_ai_fix_result(issue, client, review_type, lang).content
