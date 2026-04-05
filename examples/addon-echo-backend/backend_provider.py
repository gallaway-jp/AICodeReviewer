from __future__ import annotations

from typing import Optional

from aicodereviewer.backends.base import AIBackend


class EchoAddonBackend(AIBackend):
    """Minimal example backend contributed by an addon."""

    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
    ) -> str:
        del spec_content
        line_count = len(code_content.splitlines()) if code_content else 0
        return (
            f"EchoAddonBackend review stub for {review_type} in {lang}. "
            f"Received {line_count} lines of code."
        )

    def get_fix(
        self,
        code_content: str,
        issue_feedback: str,
        review_type: str = "best_practices",
        lang: str = "en",
    ) -> Optional[str]:
        del issue_feedback, review_type, lang
        return code_content

    def validate_connection(self) -> bool:
        return True


def build_backend(**kwargs: object) -> AIBackend:
    del kwargs
    return EchoAddonBackend()