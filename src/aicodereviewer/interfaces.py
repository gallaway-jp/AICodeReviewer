# src/aicodereviewer/interfaces.py
"""
Public protocol definitions for AICodeReviewer.

Kept for backward compatibility – the concrete hierarchy now lives in
:mod:`aicodereviewer.backends.base`.  Import :class:`AIBackend` from
either location.
"""
from typing import Protocol, Optional


class AIClient(Protocol):
    """Legacy protocol kept for type-checking backward compatibility."""

    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
    ) -> str: ...

    def get_fix(
        self,
        code_content: str,
        issue_feedback: str,
        review_type: str = "best_practices",
        lang: str = "en",
    ) -> Optional[str]: ...


# Re-export the canonical base class so old imports still work
from aicodereviewer.backends.base import AIBackend  # noqa: E402,F401

__all__ = ["AIClient", "AIBackend"]
