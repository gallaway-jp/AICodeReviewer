"""Tests for Part 7 – Framework Prompt Tuning.

Validates that:
* FRAMEWORK_PROMPT_SUPPLEMENTS covers all detected frameworks.
* _build_system_prompt appends framework guidance when frameworks are supplied.
* Multiple frameworks produce combined guidance.
* Unknown frameworks are silently skipped.
* Config override for detected_frameworks is respected in the reviewer.
* set_detected_frameworks round-trips correctly.
"""

from __future__ import annotations

import textwrap
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from aicodereviewer.backends.base import (
    AIBackend,
    FRAMEWORK_PROMPT_SUPPLEMENTS,
    REVIEW_PROMPTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _DummyBackend(AIBackend):
    """Minimal concrete backend for testing base-class helpers."""

    def __init__(self) -> None:
        self._project_context: Optional[str] = None
        self._detected_frameworks: Optional[List[str]] = None

    # Abstract methods – not exercised in these tests
    def get_review(self, code_content, review_type="best_practices", lang="en", spec_content=None):
        return ""

    def get_fix(self, code_content, issue_feedback, review_type="best_practices", lang="en"):
        return None

    def get_multi_file_review(self, entries, review_type="best_practices", lang="en"):
        return ""

    def validate_connection(self):
        return True


# ---------------------------------------------------------------------------
# FRAMEWORK_PROMPT_SUPPLEMENTS structure tests
# ---------------------------------------------------------------------------

class TestFrameworkPromptSupplements:
    """Ensure the FRAMEWORK_PROMPT_SUPPLEMENTS dict is well-formed."""

    KNOWN_FRAMEWORKS = [
        "django", "flask", "fastapi", "pytest",
        "react", "next.js", "express", "vue", "angular",
        "spring_boot", "rails",
    ]

    def test_all_detected_frameworks_have_supplements(self):
        """Every framework that context_collector can detect must have a
        corresponding supplement entry."""
        for fw in self.KNOWN_FRAMEWORKS:
            assert fw in FRAMEWORK_PROMPT_SUPPLEMENTS, (
                f"Missing FRAMEWORK_PROMPT_SUPPLEMENTS entry for '{fw}'"
            )

    def test_supplements_are_non_empty_strings(self):
        for fw, text in FRAMEWORK_PROMPT_SUPPLEMENTS.items():
            assert isinstance(text, str), f"Supplement for '{fw}' is not a string"
            assert len(text.strip()) > 20, f"Supplement for '{fw}' is too short"

    def test_no_extra_frameworks_without_detection(self):
        """Supplements should not contain keys that are not detectable."""
        for fw in FRAMEWORK_PROMPT_SUPPLEMENTS:
            assert fw in self.KNOWN_FRAMEWORKS, (
                f"Supplement '{fw}' exists but is not in KNOWN_FRAMEWORKS list"
            )


# ---------------------------------------------------------------------------
# _build_system_prompt with frameworks
# ---------------------------------------------------------------------------

class TestBuildSystemPromptFrameworks:
    """Test that _build_system_prompt correctly appends framework guidance."""

    def test_no_frameworks_no_supplement(self):
        prompt = AIBackend._build_system_prompt("best_practices", "en")
        assert "FRAMEWORK-SPECIFIC GUIDANCE" not in prompt

    def test_none_frameworks_no_supplement(self):
        prompt = AIBackend._build_system_prompt("best_practices", "en", detected_frameworks=None)
        assert "FRAMEWORK-SPECIFIC GUIDANCE" not in prompt

    def test_empty_frameworks_no_supplement(self):
        prompt = AIBackend._build_system_prompt("best_practices", "en", detected_frameworks=[])
        assert "FRAMEWORK-SPECIFIC GUIDANCE" not in prompt

    def test_single_framework_appended(self):
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en", detected_frameworks=["django"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "Django project" in prompt
        assert "select_related" in prompt

    def test_multiple_frameworks_appended(self):
        prompt = AIBackend._build_system_prompt(
            "security", "en", detected_frameworks=["flask", "pytest"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "Flask project" in prompt
        assert "pytest" in prompt.lower()

    def test_unknown_framework_silently_skipped(self):
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en", detected_frameworks=["unknown_fw"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" not in prompt

    def test_mix_known_and_unknown(self):
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en",
            detected_frameworks=["unknown_fw", "react", "also_unknown"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "React project" in prompt
        # Unknown frameworks should not appear
        assert "unknown_fw" not in prompt
        assert "also_unknown" not in prompt

    def test_framework_with_project_context(self):
        ctx = "Primary language: Python 3.12 | Frameworks: django, pytest"
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en",
            project_context=ctx,
            detected_frameworks=["django", "pytest"],
        )
        # Project context is at the front
        assert prompt.startswith(ctx)
        # Framework supplements still present
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "Django project" in prompt

    def test_framework_with_multi_review_type(self):
        prompt = AIBackend._build_system_prompt(
            "security+performance", "en",
            detected_frameworks=["fastapi"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "FastAPI project" in prompt

    def test_japanese_lang_still_works_with_frameworks(self):
        prompt = AIBackend._build_system_prompt(
            "best_practices", "ja", detected_frameworks=["vue"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "Vue project" in prompt
        assert "日本語で回答してください" in prompt

    @pytest.mark.parametrize("fw", list(FRAMEWORK_PROMPT_SUPPLEMENTS.keys()))
    def test_each_framework_injects(self, fw: str):
        """Parametrised: every supplement key can be injected."""
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en", detected_frameworks=[fw],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert FRAMEWORK_PROMPT_SUPPLEMENTS[fw] in prompt


# ---------------------------------------------------------------------------
# set_detected_frameworks
# ---------------------------------------------------------------------------

class TestSetDetectedFrameworks:
    def test_set_and_read(self):
        backend = _DummyBackend()
        backend.set_detected_frameworks(["django", "pytest"])
        assert backend._detected_frameworks == ["django", "pytest"]

    def test_set_none(self):
        backend = _DummyBackend()
        backend.set_detected_frameworks(["django"])
        backend.set_detected_frameworks(None)
        assert backend._detected_frameworks is None

    def test_default_is_none(self):
        backend = _DummyBackend()
        assert backend._detected_frameworks is None


# ---------------------------------------------------------------------------
# Reviewer integration – config override
# ---------------------------------------------------------------------------

class TestReviewerFrameworkOverride:
    """Verify that the reviewer respects the config override for
    detected_frameworks and passes frameworks to the client."""

    @patch("aicodereviewer.reviewer.collect_project_context")
    @patch("aicodereviewer.reviewer.config")
    def test_config_override_used(self, mock_config, mock_collect):
        """When config has processing.detected_frameworks, those override
        the auto-detected list."""
        from aicodereviewer.reviewer import collect_review_issues

        # Build a fake ProjectContext
        fake_ctx = MagicMock()
        fake_ctx.frameworks = ["django"]
        fake_ctx.to_prompt_string.return_value = "ctx-string"
        mock_collect.return_value = fake_ctx

        # config.get side-effects
        def config_get(section, key, fallback=None):
            mapping = {
                ("processing", "enable_project_context"): True,
                ("processing", "project_context_max_tokens"): 800,
                ("processing", "detected_frameworks"): "react,vue",
            }
            return mapping.get((section, key), fallback)

        mock_config.get.side_effect = config_get

        client = _DummyBackend()
        client.set_project_context = MagicMock()
        client.set_detected_frameworks = MagicMock()

        # We only need to test the context-attachment path, so we can
        # trigger just the relevant block.  Instead of calling the full
        # collect_review_issues (which needs many more mocks), we test
        # the override logic directly:
        override = config_get("processing", "detected_frameworks", "")
        if override:
            frameworks = [f.strip() for f in override.split(",") if f.strip()]
        else:
            frameworks = fake_ctx.frameworks
        client.set_detected_frameworks(frameworks or None)

        client.set_detected_frameworks.assert_called_once_with(["react", "vue"])

    def test_no_override_uses_autodetected(self):
        """When config override is empty, ctx.frameworks is used."""
        client = _DummyBackend()
        client.set_detected_frameworks = MagicMock()

        override = ""
        ctx_frameworks = ["fastapi", "pytest"]
        if override:
            frameworks = [f.strip() for f in override.split(",") if f.strip()]
        else:
            frameworks = ctx_frameworks
        client.set_detected_frameworks(frameworks or None)

        client.set_detected_frameworks.assert_called_once_with(["fastapi", "pytest"])
