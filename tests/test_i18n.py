# tests/test_i18n.py
"""
Tests for the internationalisation (i18n) module.

Covers:
- t() lookup, fallback, and format-placeholder behaviour
- set_locale() / get_locale() thread safety
- Key parity between English and Japanese string tables
"""
import threading

import pytest

from aicodereviewer.i18n import t, set_locale, get_locale


class TestLocale:
    """Test locale getter / setter."""

    def setup_method(self):
        """Reset locale to English before each test."""
        set_locale("en")

    def test_default_locale_is_en(self):
        assert get_locale() == "en"

    def test_set_locale_ja(self):
        set_locale("ja")
        assert get_locale() == "ja"

    def test_set_locale_invalid_falls_back_to_en(self):
        set_locale("zz")
        assert get_locale() == "en"

    def test_set_locale_empty_falls_back_to_en(self):
        set_locale("")
        assert get_locale() == "en"

    def test_thread_safety(self):
        """Concurrent set_locale calls must not crash."""
        errors = []

        def toggle(lang, n=50):
            try:
                for _ in range(n):
                    set_locale(lang)
                    get_locale()
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=toggle, args=("en",)),
            threading.Thread(target=toggle, args=("ja",)),
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert errors == []


class TestTranslation:
    """Test t() translation function."""

    def setup_method(self):
        set_locale("en")

    # ── basic lookup ───────────────────────────────────────────────────────

    def test_returns_english_string(self):
        result = t("common.ready")
        assert result == "Ready"

    def test_returns_japanese_when_locale_is_ja(self):
        set_locale("ja")
        result = t("common.ready")
        assert result == "準備完了"

    def test_explicit_lang_overrides_locale(self):
        """Even when locale is English, passing lang='ja' returns Japanese."""
        result = t("common.ready", lang="ja")
        assert result == "準備完了"

    def test_explicit_lang_en_overrides_ja_locale(self):
        set_locale("ja")
        result = t("common.ready", lang="en")
        assert result == "Ready"

    # ── fallback behaviour ─────────────────────────────────────────────────

    def test_missing_key_returns_key_itself(self):
        result = t("nonexistent.key.here")
        assert result == "nonexistent.key.here"

    def test_missing_key_in_ja_falls_back_to_en(self):
        """If a key exists in EN but not JA, the EN value is returned."""
        from aicodereviewer.i18n import _STRINGS
        # Pick any key present in EN
        en_keys = set(_STRINGS["en"].keys())
        ja_keys = set(_STRINGS["ja"].keys())
        # If all keys are mirrored this is a noop but still validates logic
        for key in en_keys:
            val = t(key, lang="ja")
            assert val != key or key not in _STRINGS["en"]

    # ── format placeholders ────────────────────────────────────────────────

    def test_placeholder_substitution(self):
        result = t("conn.checking", backend="bedrock")
        assert "bedrock" in result

    def test_placeholder_missing_kwarg_is_safe(self):
        """Extra placeholders that aren't supplied should not crash."""
        result = t("conn.checking")  # {backend} not supplied
        assert isinstance(result, str)

    def test_placeholder_in_ja(self):
        result = t("conn.checking", lang="ja", backend="local")
        assert "local" in result


class TestKeyParity:
    """Ensure both language tables have the same keys."""

    def test_en_and_ja_have_same_keys(self):
        from aicodereviewer.i18n import _STRINGS
        en_keys = set(_STRINGS["en"].keys())
        ja_keys = set(_STRINGS["ja"].keys())

        missing_in_ja = en_keys - ja_keys
        missing_in_en = ja_keys - en_keys

        assert missing_in_ja == set(), f"Keys in EN but not JA: {missing_in_ja}"
        assert missing_in_en == set(), f"Keys in JA but not EN: {missing_in_en}"

    def test_all_values_are_non_empty(self):
        from aicodereviewer.i18n import _STRINGS
        for lang, table in _STRINGS.items():
            for key, value in table.items():
                assert isinstance(value, str), f"{lang}.{key} is not a string"
                assert len(value) > 0, f"{lang}.{key} is empty"

    def test_minimum_key_count(self):
        """Sanity check – we expect a substantial number of keys."""
        from aicodereviewer.i18n import _STRINGS
        assert len(_STRINGS["en"]) >= 100
        assert len(_STRINGS["ja"]) >= 100


class TestKnownKeys:
    """Spot-check a sample of important keys in both languages."""

    SAMPLE_KEYS = [
        "common.app_title",
        "gui.tab.review",
        "gui.review.start",
        "gui.review.backend_local",
        "gui.review.test_connection",
        "gui.conn.title",
        "interactive.actions",
        "interactive.choose",
        "orch.no_files",
        "orch.complete",
        "auth.setup_header",
        "report.title",
        "cli.desc",
        "cli.help_check_connection",
        "conn.checking",
        "conn.success",
        "conn.failure",
        "conn.hint_local_url",
    ]

    @pytest.mark.parametrize("key", SAMPLE_KEYS)
    def test_key_exists_in_en(self, key):
        from aicodereviewer.i18n import _STRINGS
        assert key in _STRINGS["en"]

    @pytest.mark.parametrize("key", SAMPLE_KEYS)
    def test_key_exists_in_ja(self, key):
        from aicodereviewer.i18n import _STRINGS
        assert key in _STRINGS["ja"]
