from typing import Protocol, Optional


class AIClient(Protocol):
    def get_review(self, code_content: str, review_type: str = "best_practices", lang: str = "en", spec_content: Optional[str] = None) -> str:
        ...
