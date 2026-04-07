from __future__ import annotations

import configparser
from tkinter import messagebox
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.auth import clear_config_credential, store_config_credential
from aicodereviewer.config import config
from aicodereviewer.i18n import t


class SettingsPersistenceController:
    def __init__(self, host: Any, *, numeric_settings: dict[tuple[str, str], tuple[str, type, int | float]]) -> None:
        self._host = host
        self._numeric_settings = numeric_settings

    def save(self) -> None:
        validation_error = self._validate_numeric_fields()
        if validation_error is not None:
            self._host._show_toast(validation_error, error=True)
            return

        theme_reverse = {
            t("gui.settings.ui_theme_system"): "system",
            t("gui.settings.ui_theme_dark"): "dark",
            t("gui.settings.ui_theme_light"): "light",
        }
        lang_reverse = {
            t("gui.settings.ui_lang_system"): "system",
            t("gui.settings.ui_lang_en"): "en",
            t("gui.settings.ui_lang_ja"): "ja",
        }

        for (section, key), widget in self._host._setting_entries.items():
            if isinstance(widget, ctk.StringVar):
                raw = widget.get()
                if section == "gui" and key == "theme":
                    raw = theme_reverse.get(raw, "system")
                elif section == "gui" and key == "language":
                    raw = lang_reverse.get(raw, "system")
                elif section == "backend" and key == "type":
                    raw = getattr(self._host, "_backend_reverse_map", {}).get(raw, "bedrock")
                elif section == "local_llm" and key == "api_key":
                    raw = store_config_credential(section, key, raw)
                config.set_value(section, key, raw)
            elif isinstance(widget, ctk.BooleanVar):
                config.set_value(section, key, "true" if widget.get() else "false")
            else:
                raw = widget.get().strip()
                if section == "local_llm" and key == "api_key":
                    raw = store_config_credential(section, key, raw)
                config.set_value(section, key, raw)

        selected_formats = [fmt for fmt, var in self._host._format_vars.items() if var.get()]
        if not selected_formats:
            self._host._format_vars["json"].set(True)
            self._host._show_toast(
                "At least one output format must be selected. JSON has been re-enabled.",
                error=True,
            )
            return
        config.set_value("output", "formats", ",".join(selected_formats))

        theme_val = config.get("gui", "theme", "system")
        theme_map = {"system": "System", "dark": "Dark", "light": "Light"}
        ctk.set_appearance_mode(theme_map.get(theme_val, "System"))

        try:
            config.save()
            self._host._refresh_local_http_discovery_ui()
            self._host._show_toast(t("gui.settings.saved_ok"))
        except Exception as exc:
            self._host._show_toast(t("gui.settings.save_error", error=exc), error=True)

    def rotate_local_llm_api_key(self) -> None:
        self._clear_entry_value("local_llm", "api_key")
        try:
            clear_config_credential("local_llm", "api_key")
            self._host._show_toast(t("gui.settings.local_api_key_rotated"))
        except Exception as exc:
            self._host._show_toast(t("gui.settings.local_api_key_rotate_error", error=exc), error=True)

    def revoke_local_llm_api_key(self) -> None:
        self._clear_entry_value("local_llm", "api_key")
        try:
            clear_config_credential("local_llm", "api_key")
            config.set_value("local_llm", "api_key", "")
            config.save()
            self._host._show_toast(t("gui.settings.local_api_key_revoked"))
        except Exception as exc:
            self._host._show_toast(t("gui.settings.local_api_key_revoke_error", error=exc), error=True)

    def reset_defaults(self) -> None:
        if self._host._testing_mode:
            self._host._show_toast(
                "Reset Defaults is disabled in testing mode — settings are isolated",
                error=False,
            )
            return
        if not messagebox.askyesno(
            "Reset Defaults",
            "This will reset all settings to their default values. Continue?",
        ):
            return

        config.config = configparser.ConfigParser()
        config._set_defaults()  # type: ignore[reportPrivateUsage]

        self._host._rebuild_settings_surface_from_config()

        try:
            config.save()
            self._host._show_toast("Settings have been reset to defaults")
        except Exception as exc:
            self._host._show_toast(f"Error saving defaults: {exc}", error=True)

    def _validate_numeric_fields(self) -> str | None:
        for (section, key), (label, num_type, min_val) in self._numeric_settings.items():
            widget = self._host._setting_entries.get((section, key))
            if widget is None:
                continue
            raw = widget.get().strip()
            try:
                value = num_type(raw)
                if value < min_val:
                    raise ValueError(f"{value} < {min_val}")
            except (ValueError, TypeError):
                return (
                    f'{label}: "{raw}" is not a valid '
                    f"{'integer' if num_type is int else 'number'} "
                    f"(minimum {min_val})"
                )
        return None

    def _clear_entry_value(self, section: str, key: str) -> None:
        widget = self._host._setting_entries.get((section, key))
        if widget is None:
            return
        if hasattr(widget, "delete"):
            try:
                widget.delete(0, "end")
                return
            except Exception:
                pass
        if hasattr(widget, "set"):
            try:
                widget.set("")
            except Exception:
                pass