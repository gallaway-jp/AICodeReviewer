# src/aicodereviewer/gui/settings_mixin.py
"""Settings-tab builder and persistence mixin for :class:`App`."""
from __future__ import annotations

import configparser
import logging
import threading
from typing import Any, List

import customtkinter as ctk  # type: ignore[import-untyped]

from tkinter import messagebox

from aicodereviewer.config import config
from aicodereviewer.i18n import t
from aicodereviewer.path_utils import get_wsl_distros

from .widgets import InfoTooltip, _Tooltip
from .results_mixin import _NUMERIC_SETTINGS

logger = logging.getLogger(__name__)

__all__ = ["SettingsTabMixin"]


class SettingsTabMixin:
    """Mixin supplying the Settings tab and its Save / Reset logic."""

    # ══════════════════════════════════════════════════════════════════════
    #  SETTINGS TAB  – sectioned with tooltips
    # ══════════════════════════════════════════════════════════════════════

    def _build_settings_tab(self):
        tab = self.tabs.add(t("gui.tab.settings"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(tab)
        scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        scroll.grid_columnconfigure(2, weight=1)

        self._setting_entries = {}
        self._backend_section_labels = {}
        row = [0]  # mutable counter

        def _section_header(text: str, backend_key: str = ""):
            header_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            header_frame.grid(row=row[0], column=0, columnspan=4, sticky="ew",
                              padx=6, pady=(12, 4))
            header_frame.grid_columnconfigure(1, weight=1)

            lbl = ctk.CTkLabel(header_frame, text=text,
                               font=ctk.CTkFont(size=14, weight="bold"),
                               anchor="w")
            lbl.grid(row=0, column=0, sticky="w")

            if backend_key:
                active_lbl = ctk.CTkLabel(
                    header_frame, text="",
                    font=ctk.CTkFont(size=11),
                    text_color="#16a34a",
                    anchor="e")
                active_lbl.grid(row=0, column=1, sticky="e", padx=(10, 0))
                self._backend_section_labels[backend_key] = active_lbl

            sep = ctk.CTkFrame(scroll, height=2, fg_color=("gray70", "gray30"))
            sep.grid(row=row[0] + 1, column=0, columnspan=4, sticky="ew", padx=6)
            row[0] += 2

        def _add_entry(label: str, section: str, key: str, default: str,
                       tooltip_key: str = ""):
            InfoTooltip.add(scroll, t(tooltip_key) if tooltip_key else label,
                            row=row[0], column=0)
            ctk.CTkLabel(scroll, text=label + ":").grid(
                row=row[0], column=1, sticky="w", padx=(0, 4), pady=3)
            entry = ctk.CTkEntry(scroll)
            entry.insert(0, str(default))
            entry.grid(row=row[0], column=2, sticky="ew", padx=6, pady=3)
            self._setting_entries[(section, key)] = entry
            row[0] += 1

        def _add_dropdown(label: str, section: str, key: str, default: str,
                          values: List[str], tooltip_key: str = "",
                          var_store_name: str = ""):
            InfoTooltip.add(scroll, t(tooltip_key) if tooltip_key else label,
                            row=row[0], column=0)
            ctk.CTkLabel(scroll, text=label + ":").grid(
                row=row[0], column=1, sticky="w", padx=(0, 4), pady=3)
            var = ctk.StringVar(value=default)
            menu = ctk.CTkOptionMenu(scroll, variable=var, values=values,
                                      width=200)
            menu.grid(row=row[0], column=2, sticky="w", padx=6, pady=3)
            self._setting_entries[(section, key)] = var
            if var_store_name:
                setattr(self, var_store_name, var)
            row[0] += 1

        def _add_combobox(label: str, section: str, key: str, default: str,
                          values: List[str], tooltip_key: str = "",
                          widget_store_name: str = "",
                          refresh_command=None, refresh_button_tooltip: str = "",
                          refresh_button_store_name: str = ""):
            InfoTooltip.add(scroll, t(tooltip_key) if tooltip_key else label,
                            row=row[0], column=0)
            ctk.CTkLabel(scroll, text=label + ":").grid(
                row=row[0], column=1, sticky="w", padx=(0, 4), pady=3)
            combo = ctk.CTkComboBox(scroll, values=values, width=200)
            combo.set(default)
            combo.grid(row=row[0], column=2, sticky="ew", padx=6, pady=3)
            if refresh_command:
                btn = ctk.CTkButton(scroll, text="↻", width=34, height=28,
                                    command=refresh_command,
                                    fg_color="gray40", hover_color="gray30")
                btn.grid(row=row[0], column=3, padx=(0, 6), pady=3)
                _Tooltip(btn, refresh_button_tooltip or "Refresh list")
                if refresh_button_store_name:
                    setattr(self, refresh_button_store_name, btn)
            self._setting_entries[(section, key)] = combo
            if widget_store_name:
                setattr(self, widget_store_name, combo)
            row[0] += 1

        def _add_checkbox(label: str, section: str, key: str, default: bool,
                          tooltip_key: str = ""):
            InfoTooltip.add(scroll, t(tooltip_key) if tooltip_key else label,
                            row=row[0], column=0)
            var = ctk.BooleanVar(value=default)
            cb = ctk.CTkCheckBox(scroll, text=label, variable=var)
            cb.grid(row=row[0], column=1, columnspan=2, sticky="w", padx=(0, 4), pady=3)
            self._setting_entries[(section, key)] = var
            row[0] += 1

        # ── General section ────────────────────────────────────────────────
        _section_header(t("gui.settings.section_general"))

        saved_theme = config.get("gui", "theme", "").strip() or "system"
        theme_labels = {
            "system": t("gui.settings.ui_theme_system"),
            "dark": t("gui.settings.ui_theme_dark"),
            "light": t("gui.settings.ui_theme_light"),
        }
        theme_display = theme_labels.get(saved_theme, t("gui.settings.ui_theme_system"))
        _add_dropdown(t("gui.settings.ui_theme"), "gui", "theme",
                      theme_display,
                      list(theme_labels.values()),
                      tooltip_key="gui.tip.ui_theme",
                      var_store_name="_theme_var")

        saved_ui_lang = config.get("gui", "language", "").strip() or "system"
        lang_labels = {
            "system": t("gui.settings.ui_lang_system"),
            "en": t("gui.settings.ui_lang_en"),
            "ja": t("gui.settings.ui_lang_ja"),
        }
        lang_display = lang_labels.get(saved_ui_lang, t("gui.settings.ui_lang_system"))
        _add_dropdown(t("gui.settings.ui_language"), "gui", "language",
                      lang_display,
                      list(lang_labels.values()),
                      tooltip_key="gui.tip.ui_language",
                      var_store_name="_lang_setting_var")

        self._backend_display_map = {
            "bedrock": t("gui.settings.backend_bedrock"),
            "kiro": t("gui.settings.backend_kiro"),
            "copilot": t("gui.settings.backend_copilot"),
            "local": t("gui.settings.backend_local"),
        }
        self._backend_reverse_map = {v: k for k, v in self._backend_display_map.items()}
        saved_backend = config.get("backend", "type", "bedrock")
        backend_display = self._backend_display_map.get(
            saved_backend, t("gui.settings.backend_bedrock"))
        _add_dropdown(t("gui.settings.backend"), "backend", "type",
                      backend_display,
                      list(self._backend_display_map.values()),
                      tooltip_key="gui.tip.backend",
                      var_store_name="_settings_backend_var")

        # ── AWS Bedrock section ────────────────────────────────────────────
        _section_header(t("gui.settings.section_bedrock"), backend_key="bedrock")
        def _refresh_bedrock_with_spinner():
            """Refresh Bedrock models with spinner feedback."""
            if hasattr(self, "_bedrock_refresh_btn"):
                btn = self._bedrock_refresh_btn
                btn.configure(state="disabled", text="…")
                # Schedule re-enable after 1 second (to account for API call time)
                self.after(1000, lambda: btn.configure(state="normal", text="↻"))
            self._refresh_bedrock_model_list_async()
        
        _add_combobox(t("gui.settings.model_id"), "model", "model_id",
                      config.get("model", "model_id", ""),
                      [],
                      tooltip_key="gui.tip.model_id",
                      widget_store_name="_bedrock_model_combo",
                      refresh_command=_refresh_bedrock_with_spinner,
                      refresh_button_tooltip="Refresh Bedrock models",
                      refresh_button_store_name="_bedrock_refresh_btn")
        _add_entry(t("gui.settings.aws_region"), "aws", "region",
                   config.get("aws", "region", "us-east-1"),
                   tooltip_key="gui.tip.aws_region")
        _add_entry(t("gui.settings.aws_sso_session"), "aws", "sso_session",
                   config.get("aws", "sso_session", ""),
                   tooltip_key="gui.tip.aws_sso_session")
        _add_entry(t("gui.settings.aws_access_key"), "aws", "access_key_id",
                   config.get("aws", "access_key_id", ""),
                   tooltip_key="gui.tip.aws_access_key")

        # ── Kiro CLI section ───────────────────────────────────────────────
        _section_header(t("gui.settings.section_kiro"), backend_key="kiro")

        def _refresh_wsl_distros_with_spinner():
            """Refresh WSL distros with spinner feedback."""
            if hasattr(self, "_wsl_refresh_btn"):
                btn = self._wsl_refresh_btn
                btn.configure(state="disabled", text="…")
            
            def _worker():
                distros = get_wsl_distros()
                values = distros if distros else ["(none available)"]
                def _apply():
                    if hasattr(self, "_kiro_distro_combo"):
                        current = self._kiro_distro_combo.get()
                        self._kiro_distro_combo.configure(values=values)
                        if current and current in values:
                            self._kiro_distro_combo.set(current)
                    # Re-enable button after update
                    if hasattr(self, "_wsl_refresh_btn"):
                        self._wsl_refresh_btn.configure(state="normal", text="↻")
                self.after(0, _apply)
            threading.Thread(target=_worker, daemon=True).start()

        _kiro_distros = get_wsl_distros()
        
        _add_combobox(t("gui.settings.kiro_distro"), "kiro", "wsl_distro",
                      config.get("kiro", "wsl_distro", ""),
                      _kiro_distros,
                      tooltip_key="gui.tip.kiro_distro",
                      widget_store_name="_kiro_distro_combo",
                      refresh_command=_refresh_wsl_distros_with_spinner,
                      refresh_button_tooltip="Re-scan installed WSL distributions",
                      refresh_button_store_name="_wsl_refresh_btn")
        _add_entry(t("gui.settings.kiro_command"), "kiro", "cli_command",
                   config.get("kiro", "cli_command", "kiro"),
                   tooltip_key="gui.tip.kiro_command")
        _add_entry(t("gui.settings.kiro_timeout"), "kiro", "timeout",
                   config.get("kiro", "timeout", "300"),
                   tooltip_key="gui.tip.kiro_timeout")

        # ── GitHub Copilot section ─────────────────────────────────────────
        _section_header(t("gui.settings.section_copilot"), backend_key="copilot")
        _add_entry(t("gui.settings.copilot_path"), "copilot", "copilot_path",
                   config.get("copilot", "copilot_path", "copilot"),
                   tooltip_key="gui.tip.copilot_path")
        _add_entry(t("gui.settings.copilot_timeout"), "copilot", "timeout",
                   config.get("copilot", "timeout", "300"),
                   tooltip_key="gui.tip.copilot_timeout")
        def _refresh_copilot_with_spinner():
            """Refresh Copilot models with spinner feedback."""
            if hasattr(self, "_copilot_refresh_btn"):
                btn = self._copilot_refresh_btn
                btn.configure(state="disabled", text="…")
                # Schedule re-enable after 1 second (to account for API call time)
                self.after(1000, lambda: btn.configure(state="normal", text="↻"))
            self._refresh_copilot_model_list_async()
        
        _add_combobox(t("gui.settings.copilot_model"), "copilot", "model",
                      config.get("copilot", "model", "auto"),
                      ["auto"],
                      tooltip_key="gui.tip.copilot_model",
                      widget_store_name="_copilot_model_combo",
                      refresh_command=_refresh_copilot_with_spinner,
                      refresh_button_tooltip="Refresh Copilot models",
                      refresh_button_store_name="_copilot_refresh_btn")

        # ── Local LLM section ─────────────────────────────────────────────
        _section_header(t("gui.settings.section_local"), backend_key="local")
        _add_entry(t("gui.settings.local_api_url"), "local_llm", "api_url",
                   config.get("local_llm", "api_url", "http://localhost:1234"),
                   tooltip_key="gui.tip.local_api_url")
        _add_dropdown(t("gui.settings.local_api_type"), "local_llm", "api_type",
                      config.get("local_llm", "api_type", "lmstudio"),
                      ["lmstudio", "ollama", "openai", "anthropic"],
                      tooltip_key="gui.tip.local_api_type")
        _add_combobox(t("gui.settings.local_model"), "local_llm", "model",
                      config.get("local_llm", "model", "default"),
                      [],
                      tooltip_key="gui.tip.local_model",
                      widget_store_name="_local_model_combo")
        _add_entry(t("gui.settings.local_api_key"), "local_llm", "api_key",
                   config.get("local_llm", "api_key", ""),
                   tooltip_key="gui.tip.local_api_key")
        _add_entry(t("gui.settings.local_timeout"), "local_llm", "timeout",
                   config.get("local_llm", "timeout", "300"),
                   tooltip_key="gui.tip.local_timeout")
        _add_entry(t("gui.settings.local_max_tokens"), "local_llm", "max_tokens",
                   config.get("local_llm", "max_tokens", "4096"),
                   tooltip_key="gui.tip.local_max_tokens")

        # ── Performance section ────────────────────────────────────────────
        _section_header(t("gui.settings.section_perf"))
        _add_entry(t("gui.settings.rate_limit"), "performance",
                   "max_requests_per_minute",
                   str(config.get("performance", "max_requests_per_minute", 10)),
                   tooltip_key="gui.tip.rate_limit")
        _add_entry(t("gui.settings.request_interval"), "performance",
                   "min_request_interval_seconds",
                   str(config.get("performance", "min_request_interval_seconds", 6.0)),
                   tooltip_key="gui.tip.request_interval")
        max_fs_raw = config.get("performance", "max_file_size_mb", 10)
        max_fs = (max_fs_raw // (1024 * 1024)
                  if isinstance(max_fs_raw, int) and max_fs_raw > 100
                  else max_fs_raw)
        _add_entry(t("gui.settings.max_file_size"), "performance",
                   "max_file_size_mb", str(max_fs),
                   tooltip_key="gui.tip.max_file_size")
        _add_entry(t("gui.settings.batch_size"), "processing", "batch_size",
                   str(config.get("processing", "batch_size", 5)),
                   tooltip_key="gui.tip.batch_size")
        combine_val = str(config.get("processing", "combine_files", "true")).lower() in ("true", "1", "yes")
        _add_checkbox(t("gui.settings.combine_files"), "processing", "combine_files",
                      combine_val,
                      tooltip_key="gui.tip.combine_files")

        # ── Editor section ────────────────────────────────────────────────
        _section_header(t("gui.settings.section_editor"))
        _add_entry(t("gui.settings.editor_command"), "gui", "editor_command",
                   config.get("gui", "editor_command", ""),
                   tooltip_key="gui.tip.editor_command")

        # ── Report Output Formats ──────────────────────────────────────────
        _section_header("Review Report Output Formats")

        saved_formats = config.get("output", "formats", "json,txt").strip()
        enabled_formats = set(saved_formats.split(",")) if saved_formats else {"json", "txt"}

        InfoTooltip.add(scroll,
                        "Select which file formats to generate for review reports. "
                        "At least one format must be selected.",
                        row=row[0], column=0)
        ctk.CTkLabel(scroll, text="Output Formats:").grid(
            row=row[0], column=1, sticky="w", padx=(0, 4), pady=3)

        formats_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        formats_frame.grid(row=row[0], column=2, sticky="w", padx=6, pady=3)

        self._format_vars = {}

        json_var = ctk.BooleanVar(value=("json" in enabled_formats))
        ctk.CTkCheckBox(formats_frame, text="JSON",
                        variable=json_var).grid(row=0, column=0, padx=(0, 15), sticky="w")
        self._format_vars["json"] = json_var

        txt_var = ctk.BooleanVar(value=("txt" in enabled_formats))
        ctk.CTkCheckBox(formats_frame, text="TXT",
                        variable=txt_var).grid(row=0, column=1, padx=(0, 15), sticky="w")
        self._format_vars["txt"] = txt_var

        md_var = ctk.BooleanVar(value=("md" in enabled_formats))
        ctk.CTkCheckBox(formats_frame, text="Markdown (MD)",
                        variable=md_var).grid(row=0, column=2, padx=(0, 15), sticky="w")
        self._format_vars["md"] = md_var

        row[0] += 1

        # ── Note + buttons ─────────────────────────────────────────────────
        note = ctk.CTkLabel(scroll, text=t("gui.settings.restart_note"),
                             text_color="gray50", font=ctk.CTkFont(size=11))
        note.grid(row=row[0], column=0, columnspan=4, pady=(10, 2))
        row[0] += 1

        button_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        button_frame.grid(row=row[0], column=0, columnspan=4, pady=8)

        save_btn = ctk.CTkButton(button_frame, text=t("gui.settings.save"),
                                  command=self._save_settings)
        save_btn.grid(row=0, column=0, padx=(0, 10))
        _Tooltip(save_btn, t("gui.shortcut.save_settings"))

        reset_btn = ctk.CTkButton(button_frame, text="Reset Defaults",
                                   command=self._reset_defaults,
                                   fg_color="gray40", hover_color="gray30")
        reset_btn.grid(row=0, column=1)

        # Wire up backend dropdown sync
        if hasattr(self, "_settings_backend_var"):
            self._settings_backend_var.trace_add("write",
                                                  self._update_backend_section_indicators)
            self._settings_backend_var.trace_add("write",
                                                  self._sync_menu_to_review)
            self._update_backend_section_indicators()
            self._sync_review_to_menu()
            
            # ── Auto-populate Copilot and Bedrock models on first open ────
            # Capture button references for spinner control
            for child in scroll.winfo_children():
                if isinstance(child, ctk.CTkButton):
                    # Identify buttons by their parent grid location
                    grid_info = child.grid_info()
                    if grid_info:
                        # Store references based on model context
                        # This will be set when buttons are created above
                        pass
            
            # Schedule auto-population after GUI renders
            self.after(500, self._auto_populate_models)

    def _auto_populate_models(self):
        """Auto-populate Copilot and Bedrock models when Settings tab opens."""
        self._refresh_copilot_model_list_async()
        self._refresh_bedrock_model_list_async()

    # ══════════════════════════════════════════════════════════════════════
    #  SETTINGS save / reset
    # ══════════════════════════════════════════════════════════════════════

    def _save_settings(self):
        # --- Validate numeric fields ---
        for (section, key), (label, num_type, min_val) in _NUMERIC_SETTINGS.items():
            widget = self._setting_entries.get((section, key))
            if widget is None:
                continue
            raw = widget.get().strip()
            try:
                value = num_type(raw)
                if value < min_val:
                    raise ValueError(f"{value} < {min_val}")
            except (ValueError, TypeError):
                self._show_toast(
                    f"{label}: \"{raw}\" is not a valid "
                    f"{'integer' if num_type is int else 'number'} "
                    f"(minimum {min_val})",
                    error=True,
                )
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

        for (section, key), widget in self._setting_entries.items():
            if isinstance(widget, ctk.StringVar):
                raw = widget.get()
                if section == "gui" and key == "theme":
                    raw = theme_reverse.get(raw, "system")
                elif section == "gui" and key == "language":
                    raw = lang_reverse.get(raw, "system")
                elif section == "backend" and key == "type":
                    raw = getattr(self, "_backend_reverse_map", {}).get(raw, "bedrock")
                config.set_value(section, key, raw)
            elif isinstance(widget, ctk.BooleanVar):
                config.set_value(section, key, "true" if widget.get() else "false")
            else:
                config.set_value(section, key, widget.get().strip())

        # Save report output formats
        selected_formats = [fmt for fmt, var in self._format_vars.items() if var.get()]
        if not selected_formats:
            self._format_vars["json"].set(True)
            selected_formats = ["json"]
            self._show_toast(
                "At least one output format must be selected. JSON has been re-enabled.",
                error=True)
            return
        config.set_value("output", "formats", ",".join(selected_formats))

        # Apply theme immediately
        theme_val = config.get("gui", "theme", "system")
        theme_map = {"system": "System", "dark": "Dark", "light": "Light"}
        ctk.set_appearance_mode(theme_map.get(theme_val, "System"))

        try:
            config.save()
            self._show_toast(t("gui.settings.saved_ok"))
        except Exception as exc:
            self._show_toast(t("gui.settings.save_error", error=exc),
                             error=True)

    def _reset_defaults(self):
        if self._testing_mode:
            self._show_toast(
                "Reset Defaults is disabled in testing mode — "
                "settings are isolated", error=False)
            return
        if not messagebox.askyesno(
                "Reset Defaults",
                "This will reset all settings to their default values. Continue?"):
            return

        config.config = configparser.ConfigParser()
        config._set_defaults()  # type: ignore[reportPrivateUsage]

        for widget in self.tabs.tab(t("gui.tab.settings")).winfo_children():
            widget.destroy()

        self._build_settings_tab()

        try:
            config.save()
            self._show_toast("Settings have been reset to defaults")
        except Exception as exc:
            self._show_toast(f"Error saving defaults: {exc}", error=True)

    # ── Backend sync helpers ──────────────────────────────────────────────

    def _update_backend_section_indicators(self, *args):
        if not hasattr(self, "_settings_backend_var"):
            return
        display_val = self._settings_backend_var.get()
        current_backend = getattr(self, "_backend_reverse_map", {}).get(display_val, "")
        for backend_key, label in self._backend_section_labels.items():
            if backend_key == current_backend:
                label.configure(text=t("gui.settings.active_backend"),
                                text_color=("green", "#4ade80"))
            else:
                label.configure(text="")

    def _sync_menu_to_review(self, *args):
        if not hasattr(self, "_settings_backend_var") or not hasattr(self, "backend_var"):
            return
        display_val = self._settings_backend_var.get()
        internal_val = getattr(self, "_backend_reverse_map", {}).get(display_val, "bedrock")
        if self.backend_var.get() != internal_val:
            self.backend_var.set(internal_val)

    def _sync_review_to_menu(self, *args):
        if not hasattr(self, "_settings_backend_var") or not hasattr(self, "backend_var"):
            return
        internal_val = self.backend_var.get()
        display_val = getattr(self, "_backend_display_map", {}).get(
            internal_val, t("gui.settings.backend_bedrock"))
        if self._settings_backend_var.get() != display_val:
            self._settings_backend_var.set(display_val)
