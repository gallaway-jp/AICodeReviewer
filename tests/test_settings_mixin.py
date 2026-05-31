from __future__ import annotations

from types import SimpleNamespace

from aicodereviewer.gui.settings_mixin import SettingsTabMixin


class _SettingsHarness(SettingsTabMixin):
    def __init__(self) -> None:
        self._backend_reverse_map = {
            "Copilot": "copilot",
            "Kiro": "kiro",
            "Bedrock": "bedrock",
            "Local": "local",
        }
        self._settings_backend_var = SimpleNamespace(get=lambda: "Copilot")
        self.backend_var = SimpleNamespace(get=lambda: "copilot")
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
        harness._settings_backend_var = SimpleNamespace(get=lambda value=display_value: value)

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
        harness.backend_var = SimpleNamespace(get=lambda value=backend_name: value)

        harness._auto_populate_models()

        assert harness.calls == expected