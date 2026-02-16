# tests/test_backends.py
"""
Tests for the backend factory and backend base class utilities.
"""
from typing import Optional

import pytest
from unittest.mock import patch, MagicMock

from aicodereviewer.backends import create_backend
from aicodereviewer.backends.base import (
    AIBackend,
    REVIEW_TYPE_KEYS,
    REVIEW_TYPE_META,
    REVIEW_PROMPTS,
)


class TestBackendFactory:
    """Test create_backend factory function."""

    @patch("aicodereviewer.backends.bedrock.create_aws_session")
    def test_create_bedrock_backend(self, mock_session):
        mock_sess = MagicMock()
        mock_sess.client.return_value = MagicMock()
        mock_session.return_value = (mock_sess, "mock auth")

        backend = create_backend("bedrock")

        from aicodereviewer.backends.bedrock import BedrockBackend
        assert isinstance(backend, BedrockBackend)

    def test_create_kiro_backend(self):
        backend = create_backend("kiro")

        from aicodereviewer.backends.kiro import KiroBackend
        assert isinstance(backend, KiroBackend)

    def test_create_copilot_backend(self):
        backend = create_backend("copilot")

        from aicodereviewer.backends.copilot import CopilotBackend
        assert isinstance(backend, CopilotBackend)

    @patch("aicodereviewer.backends.local_llm.config")
    def test_create_local_backend(self, mock_cfg):
        mock_cfg.get.side_effect = lambda section, key, default=None: {
            ("local_llm", "api_url"): "http://localhost:1234/v1",
            ("local_llm", "api_type"): "openai",
            ("local_llm", "model"): "default",
            ("local_llm", "api_key"): "",
            ("local_llm", "timeout"): "300",
            ("local_llm", "max_tokens"): "4096",
            ("performance", "min_request_interval_seconds"): 0.0,
        }.get((section, key), default)

        backend = create_backend("local")

        from aicodereviewer.backends.local_llm import LocalLLMBackend
        assert isinstance(backend, LocalLLMBackend)

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown backend"):
            create_backend("nonexistent")


class TestReviewTypeRegistry:
    """Test the centralized review type definitions."""

    def test_review_type_keys_not_empty(self):
        assert len(REVIEW_TYPE_KEYS) >= 15

    def test_all_keys_have_prompts(self):
        for key in REVIEW_TYPE_KEYS:
            assert key in REVIEW_PROMPTS, f"Missing prompt for {key}"

    def test_all_keys_have_metadata(self):
        for key in REVIEW_TYPE_KEYS:
            meta = REVIEW_TYPE_META.get(key)
            assert meta is not None, f"Missing meta for {key}"
            assert "label" in meta
            assert "group" in meta

    def test_fix_prompt_exists(self):
        """The special 'fix' prompt for code correction should exist."""
        assert "fix" in REVIEW_PROMPTS


class TestAIBackendABC:
    """Test the abstract base class."""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            AIBackend()  # type: ignore[abstract]

    def test_build_helpers_available(self):
        """Subclasses have access to prompt builder helpers."""
        # Create a minimal concrete subclass
        class _Stub(AIBackend):
            def get_review(self, code_content: str, review_type: str = "best_practices", lang: str = "en", spec_content: Optional[str] = None) -> str:
                return ""
            def get_fix(self, code_content: str, issue_feedback: str, review_type: str = "best_practices", lang: str = "en") -> Optional[str]:
                return ""
            def validate_connection(self) -> bool:
                return True

        stub = _Stub()
        prompt = stub._build_system_prompt("security", "en")
        assert isinstance(prompt, str)
        assert len(prompt) > 0
