# tests/test_backends.py
"""
Tests for the backend factory and backend base class utilities.
"""
from typing import Optional

import pytest
from unittest.mock import patch, MagicMock

from aicodereviewer.backends import create_backend, get_backend_registry, resolve_backend_type
from aicodereviewer.backends.base import (
    AIBackend,
    REVIEW_TYPE_KEYS,
    REVIEW_TYPE_META,
    REVIEW_PROMPTS,
)
from aicodereviewer.registries import get_review_registry
from aicodereviewer.review_definitions import install_review_registry


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

    def test_backend_registry_lists_expected_choices(self):
        registry = get_backend_registry()

        assert "bedrock" in registry.backend_choices
        assert "copilot-cli" in registry.backend_choices
        assert "ollama" in registry.backend_choices

    def test_resolve_backend_type_uses_registry_aliases(self):
        canonical, overrides = resolve_backend_type("github-copilot")

        assert canonical == "copilot"
        assert overrides == {}

    def test_resolve_backend_type_uses_local_provider_alias(self):
        canonical, overrides = resolve_backend_type("anthropic")

        assert canonical == "local"
        assert overrides == {"api_type": "anthropic"}

    @patch("aicodereviewer.backends.local_llm.config")
    def test_create_local_backend_from_provider_alias(self, mock_cfg):
        mock_cfg.get.side_effect = lambda section, key, default=None: {
            ("local_llm", "api_url"): "http://localhost:11434/api",
            ("local_llm", "api_type"): "openai",
            ("local_llm", "model"): "tiny-model",
            ("local_llm", "api_key"): "",
            ("local_llm", "timeout"): "300",
            ("local_llm", "max_tokens"): "4096",
            ("performance", "min_request_interval_seconds"): 0.0,
        }.get((section, key), default)

        backend = create_backend("ollama")

        from aicodereviewer.backends.local_llm import LocalLLMBackend
        assert isinstance(backend, LocalLLMBackend)
        assert backend.api_type == "ollama"

    @patch("aicodereviewer.backends.bedrock.create_aws_session")
    def test_create_backend_accepts_bedrock_alias(self, mock_session):
        mock_sess = MagicMock()
        mock_sess.client.return_value = MagicMock()
        mock_session.return_value = (mock_sess, "mock auth")

        backend = create_backend("aws-bedrock")

        from aicodereviewer.backends.bedrock import BedrockBackend
        assert isinstance(backend, BedrockBackend)


class TestReviewTypeRegistry:
    """Test the centralized review type definitions."""

    def test_review_registry_exposes_visible_keys(self):
        registry = get_review_registry()

        assert registry.visible_keys() == REVIEW_TYPE_KEYS

    def test_review_registry_keeps_internal_prompts_non_selectable(self):
        registry = get_review_registry()

        assert registry.get("fix").selectable is False
        assert registry.get("architectural_review").selectable is False
        assert registry.get("interaction_analysis").selectable is False
        assert registry.get("security").selectable is True

    def test_review_registry_resolves_aliases_to_canonical_keys(self):
        registry = get_review_registry()

        assert registry.resolve_key("spec") == "specification"
        assert registry.resolve_key("i18n") == "localization"
        assert registry.resolve("spec").key == "specification"

    def test_review_registry_exposes_sub_review_parent_metadata(self):
        registry = get_review_registry()

        architectural_review = registry.get("architectural_review")

        assert architectural_review.parent_key == "architecture"
        assert registry.list_children("architecture") == [architectural_review]
        assert registry.list_children("architecture", visible_only=True) == []

    def test_review_registry_marks_specification_requirement_in_definition(self):
        registry = get_review_registry()

        assert registry.get("specification").requires_spec_content is True
        assert registry.get("security").requires_spec_content is False

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
            assert "summary_key" in meta

    def test_ui_ux_review_type_is_registered(self):
        assert "ui_ux" in REVIEW_TYPE_KEYS
        assert REVIEW_TYPE_META["ui_ux"]["label"] == "UI/UX Review"
        assert REVIEW_TYPE_META["ui_ux"]["group"] == "Quality"
        assert "usability" in REVIEW_PROMPTS["ui_ux"].lower()

    def test_dead_code_review_type_is_registered(self):
        assert "dead_code" in REVIEW_TYPE_KEYS
        assert REVIEW_TYPE_META["dead_code"]["label"] == "Dead Code"
        assert REVIEW_TYPE_META["dead_code"]["group"] == "Quality"
        assert "unused functions" in REVIEW_PROMPTS["dead_code"].lower()

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

    def test_build_system_prompt_includes_context_augmentation_rules(self, tmp_path):
        class _Stub(AIBackend):
            def get_review(self, code_content: str, review_type: str = "best_practices", lang: str = "en", spec_content: Optional[str] = None) -> str:
                return ""
            def get_fix(self, code_content: str, issue_feedback: str, review_type: str = "best_practices", lang: str = "en") -> Optional[str]:
                return ""
            def validate_connection(self) -> bool:
                return True

        pack_path = tmp_path / "context-pack.json"
        pack_path.write_text(
            '{"version": 1, "review_definitions": [{"key": "secure_defaults", "parent_key": "security", "prompt_append": "Check unsafe defaults.", "context_augmentation_rules": ["Inspect bootstrap and first-run config paths."]}]}',
            encoding="utf-8",
        )

        install_review_registry([pack_path])
        try:
            prompt = _Stub()._build_system_prompt("secure_defaults", "en")
        finally:
            install_review_registry([])

        assert "CONTEXT AUGMENTATION RULES" in prompt
        assert "Inspect bootstrap and first-run config paths." in prompt
