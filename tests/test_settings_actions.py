from __future__ import annotations

from pathlib import Path
from typing import Any

from aicodereviewer import auth
from aicodereviewer.config import config
import aicodereviewer.gui.settings_actions as settings_actions
from aicodereviewer.gui.settings_actions import SettingsPersistenceController
from aicodereviewer.gui.results_mixin import _NUMERIC_SETTINGS
from aicodereviewer.i18n import t


class _FakeEntry:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def delete(self, _start: int, _end: str | None = None) -> None:
        self._value = ""

    def insert(self, _index: int, value: str) -> None:
        self._value = value


class _FakeStringVar:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value


class _FakeBooleanVar:
    def __init__(self, value: bool) -> None:
        self._value = value

    def get(self) -> bool:
        return self._value

    def set(self, value: bool) -> None:
        self._value = value


class _FakeHost:
    def __init__(self) -> None:
        self.toasts: list[tuple[str, bool]] = []
        self._backend_reverse_map = {t("gui.settings.backend_local"): "local"}
        self._setting_entries: dict[tuple[str, str], Any] = {
            ("gui", "theme"): _FakeStringVar(t("gui.settings.ui_theme_dark")),
            ("gui", "language"): _FakeStringVar(t("gui.settings.ui_lang_ja")),
            ("backend", "type"): _FakeStringVar(t("gui.settings.backend_local")),
            ("local_llm", "api_url"): _FakeEntry("http://127.0.0.1:9999"),
            ("performance", "max_requests_per_minute"): _FakeEntry("24"),
            ("processing", "combine_files"): _FakeBooleanVar(False),
        }
        self._format_vars = {
            "json": _FakeBooleanVar(False),
            "txt": _FakeBooleanVar(True),
            "md": _FakeBooleanVar(True),
        }
        self.refreshed_local_http = False
        self._testing_mode = True

    def _show_toast(self, message: str, error: bool = False) -> None:
        self.toasts.append((message, error))

    def _refresh_local_http_discovery_ui(self) -> None:
        self.refreshed_local_http = True


def _install_fake_vars(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings_actions.ctk, "StringVar", _FakeStringVar)
    monkeypatch.setattr(settings_actions.ctk, "BooleanVar", _FakeBooleanVar)


def test_settings_persistence_controller_saves_values_and_refreshes_local_http(tmp_path: Path, monkeypatch: Any) -> None:
    _install_fake_vars(monkeypatch)
    config_path = tmp_path / "settings-actions.ini"
    monkeypatch.setattr(config, "config_path", config_path)
    config.config.clear()
    config._set_defaults()  # type: ignore[reportPrivateUsage]
    config.save()

    host = _FakeHost()
    controller = SettingsPersistenceController(host, numeric_settings=_NUMERIC_SETTINGS)

    controller.save()

    assert config.get("gui", "theme") == "dark"
    assert config.get("gui", "language") == "ja"
    assert config.get("backend", "type") == "local"
    assert config.get("local_llm", "api_url") == "http://127.0.0.1:9999"
    assert config.get("processing", "combine_files") == "false"
    assert config.get("output", "formats") == "txt,md"
    assert host.refreshed_local_http is True
    assert any(message == t("gui.settings.saved_ok") and not error for message, error in host.toasts)


def test_settings_persistence_controller_reenables_json_when_no_output_format_selected() -> None:
    from _pytest.monkeypatch import MonkeyPatch

    monkeypatch = MonkeyPatch()
    _install_fake_vars(monkeypatch)
    host = _FakeHost()
    host._format_vars["json"].set(False)
    host._format_vars["txt"].set(False)
    host._format_vars["md"].set(False)
    controller = SettingsPersistenceController(host, numeric_settings=_NUMERIC_SETTINGS)

    controller.save()

    assert host._format_vars["json"].get() is True
    assert any(
        message == "At least one output format must be selected. JSON has been re-enabled." and error
        for message, error in host.toasts
    )
    monkeypatch.undo()


def test_settings_persistence_controller_reports_invalid_numeric_value(monkeypatch: Any) -> None:
    _install_fake_vars(monkeypatch)
    host = _FakeHost()
    host._setting_entries[("performance", "max_requests_per_minute")] = _FakeEntry("0")
    controller = SettingsPersistenceController(host, numeric_settings=_NUMERIC_SETTINGS)

    controller.save()

    assert any("not a valid" in message and error for message, error in host.toasts)


def test_settings_persistence_controller_rotates_local_llm_api_key(monkeypatch: Any, tmp_path: Path) -> None:
    _install_fake_vars(monkeypatch)
    config_path = tmp_path / "settings-actions-rotate.ini"
    monkeypatch.setattr(config, "config_path", config_path)
    config.config.clear()
    config._set_defaults()  # type: ignore[reportPrivateUsage]
    config.set_value("local_llm", "api_key", auth.build_credential_reference("local_llm", "api_key"))
    config.save()

    cleared: list[tuple[str, str]] = []
    monkeypatch.setattr(settings_actions, "clear_config_credential", lambda section, key: cleared.append((section, key)))

    host = _FakeHost()
    host._setting_entries[("local_llm", "api_key")] = _FakeEntry("secret")
    controller = SettingsPersistenceController(host, numeric_settings=_NUMERIC_SETTINGS)

    controller.rotate_local_llm_api_key()

    assert host._setting_entries[("local_llm", "api_key")].get() == ""
    assert config.get("local_llm", "api_key") == auth.build_credential_reference("local_llm", "api_key")
    assert cleared == [("local_llm", "api_key")]
    assert any(message == t("gui.settings.local_api_key_rotated") and not error for message, error in host.toasts)


def test_settings_persistence_controller_revokes_local_llm_api_key(monkeypatch: Any, tmp_path: Path) -> None:
    _install_fake_vars(monkeypatch)
    config_path = tmp_path / "settings-actions-revoke.ini"
    monkeypatch.setattr(config, "config_path", config_path)
    config.config.clear()
    config._set_defaults()  # type: ignore[reportPrivateUsage]
    config.set_value("local_llm", "api_key", auth.build_credential_reference("local_llm", "api_key"))
    config.save()

    cleared: list[tuple[str, str]] = []
    monkeypatch.setattr(settings_actions, "clear_config_credential", lambda section, key: cleared.append((section, key)))

    host = _FakeHost()
    host._setting_entries[("local_llm", "api_key")] = _FakeEntry("secret")
    controller = SettingsPersistenceController(host, numeric_settings=_NUMERIC_SETTINGS)

    controller.revoke_local_llm_api_key()

    assert host._setting_entries[("local_llm", "api_key")].get() == ""
    assert config.get("local_llm", "api_key") == ""
    assert cleared == [("local_llm", "api_key")]
    assert any(message == t("gui.settings.local_api_key_revoked") and not error for message, error in host.toasts)