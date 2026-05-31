from __future__ import annotations

from typing import Any

from aicodereviewer.gui.settings_mixin import SettingsTabMixin


class _DummyLabel:
    def __init__(self) -> None:
        self.configure_calls: list[dict[str, Any]] = []

    def configure(self, **kwargs: Any) -> None:
        self.configure_calls.append(kwargs)


class _DummyVar:
    def __init__(self, value: str) -> None:
        self.value = value
        self.set_calls: list[str] = []

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value
        self.set_calls.append(value)


class _SettingsHarness(SettingsTabMixin):
    def __init__(self) -> None:
        self._backend_reverse_map = {
            "Copilot": "copilot",
            "Kiro": "kiro",
            "Bedrock": "bedrock",
            "Local": "local",
        }
        self._backend_display_map = {
            "copilot": "Copilot",
            "kiro": "Kiro",
            "bedrock": "Bedrock",
            "local": "Local",
        }
        self._settings_backend_var = _DummyVar("Copilot")
        self.backend_var = _DummyVar("copilot")
        self._backend_section_labels = {
            "copilot": _DummyLabel(),
            "kiro": _DummyLabel(),
            "bedrock": _DummyLabel(),
            "local": _DummyLabel(),
        }
        self.calls: list[str] = []

    def _refresh_copilot_model_list_async(self) -> None:
        self.calls.append("copilot")

    def _refresh_kiro_model_list_async(self) -> None:
        self.calls.append("kiro")

    def _refresh_bedrock_model_list_async(self) -> None:
        self.calls.append("bedrock")

    def _refresh_local_model_list_async(self) -> None:
        self.calls.append("local")


def test_auto_populate_models_dispatches_selected_settings_backend() -> None:
    harness = _SettingsHarness()

    for display_value, expected in (
        ("Copilot", ["copilot"]),
        ("Kiro", ["kiro"]),
        ("Bedrock", ["bedrock"]),
        ("Local", ["local"]),
        ("Unknown", []),
    ):
        harness.calls.clear()
        harness._settings_backend_var = _DummyVar(display_value)
        harness._auto_populate_models()

        assert harness.calls == expected


def test_auto_populate_models_falls_back_to_review_backend_when_settings_var_missing() -> None:
    harness = _SettingsHarness()
    delattr(harness, "_settings_backend_var")

    for backend_name, expected in (
        ("copilot", ["copilot"]),
        ("kiro", ["kiro"]),
        ("bedrock", ["bedrock"]),
        ("local", ["local"]),
        ("unknown", []),
    ):
        harness.calls.clear()
        harness.backend_var = _DummyVar(backend_name)

        harness._auto_populate_models()

        assert harness.calls == expected


def test_settings_backend_sync_helpers_ignore_none_prebuild_state() -> None:
    harness = _SettingsHarness()
    harness._settings_backend_var = None
    harness.backend_var = _DummyVar("kiro")

    harness._auto_populate_models()
    harness._update_backend_section_indicators()
    harness._sync_menu_to_review()
    harness._sync_review_to_menu()

    assert harness.calls == ["kiro"]
    assert harness.backend_var.value == "kiro"


def test_sync_menu_to_review_updates_backend_from_settings_selection() -> None:
    harness = _SettingsHarness()
    harness._settings_backend_var = _DummyVar("Local")
    harness.backend_var = _DummyVar("copilot")

    harness._sync_menu_to_review()

    assert harness.backend_var.value == "local"
    assert harness.backend_var.set_calls == ["local"]


def test_update_backend_section_indicators_marks_only_active_backend() -> None:
    harness = _SettingsHarness()
    harness._settings_backend_var = _DummyVar("Kiro")

    harness._update_backend_section_indicators()

    assert harness._backend_section_labels["kiro"].configure_calls[-1]["text"]
    assert harness._backend_section_labels["copilot"].configure_calls[-1] == {"text": ""}
    assert harness._backend_section_labels["bedrock"].configure_calls[-1] == {"text": ""}
    assert harness._backend_section_labels["local"].configure_calls[-1] == {"text": ""}