from __future__ import annotations

import threading
from typing import Any, List

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.config import config
from aicodereviewer.i18n import t
from aicodereviewer.path_utils import get_wsl_distros

from .widgets import InfoTooltip, _Tooltip


class SettingsTabBuilder:
    def __init__(self, host: Any) -> None:
        self.host = host
        self.scroll: Any = None
        self.row = 0

    def build(self) -> None:
        tab = self.host.tabs.add(t("gui.tab.settings"))
        self.host.settings_root_tab = tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkFrame(tab) if self.host._testing_mode else ctk.CTkScrollableFrame(tab)
        scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        scroll.grid_columnconfigure(2, weight=1)
        self.scroll = scroll
        self.host.settings_scroll_frame = scroll

        self.host._setting_entries = {}
        self.host._backend_section_labels = {}

        self._build_general_section()
        self._build_bedrock_section()
        self._build_kiro_section()
        self._build_copilot_section()
        self._build_local_llm_section()
        self._build_local_http_section()
        self._build_performance_section()
        self._build_editor_section()
        self._build_addons_section()
        self._build_output_formats_section()
        self._build_footer_buttons()
        self._finalize()

    def _section_header(self, text: str, backend_key: str = "") -> None:
        header_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        header_frame.grid(row=self.row, column=0, columnspan=4, sticky="ew", padx=6, pady=(12, 4))
        header_frame.grid_columnconfigure(1, weight=1)

        lbl = ctk.CTkLabel(
            header_frame,
            text=text,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        lbl.grid(row=0, column=0, sticky="w")

        if backend_key:
            active_lbl = ctk.CTkLabel(
                header_frame,
                text="",
                font=ctk.CTkFont(size=11),
                text_color="#16a34a",
                anchor="e",
            )
            active_lbl.grid(row=0, column=1, sticky="e", padx=(10, 0))
            self.host._backend_section_labels[backend_key] = active_lbl

        sep = ctk.CTkFrame(self.scroll, height=2, fg_color=("gray70", "gray30"))
        sep.grid(row=self.row + 1, column=0, columnspan=4, sticky="ew", padx=6)
        self.row += 2

    def _add_entry(self, label: str, section: str, key: str, default: str, tooltip_key: str = "") -> None:
        InfoTooltip.add(self.scroll, t(tooltip_key) if tooltip_key else label, row=self.row, column=0)
        ctk.CTkLabel(self.scroll, text=label + ":").grid(
            row=self.row,
            column=1,
            sticky="w",
            padx=(0, 4),
            pady=3,
        )
        entry = ctk.CTkEntry(self.scroll)
        entry.insert(0, str(default))
        entry.grid(row=self.row, column=2, sticky="ew", padx=6, pady=3)
        self.host._setting_entries[(section, key)] = entry
        self.row += 1

    def _add_dropdown(
        self,
        label: str,
        section: str,
        key: str,
        default: str,
        values: List[str],
        tooltip_key: str = "",
        var_store_name: str = "",
    ) -> None:
        InfoTooltip.add(self.scroll, t(tooltip_key) if tooltip_key else label, row=self.row, column=0)
        ctk.CTkLabel(self.scroll, text=label + ":").grid(
            row=self.row,
            column=1,
            sticky="w",
            padx=(0, 4),
            pady=3,
        )
        var = ctk.StringVar(value=default)
        menu = ctk.CTkOptionMenu(self.scroll, variable=var, values=values, width=200)
        menu.grid(row=self.row, column=2, sticky="w", padx=6, pady=3)
        self.host._setting_entries[(section, key)] = var
        if var_store_name:
            setattr(self.host, var_store_name, var)
        self.row += 1

    def _add_combobox(
        self,
        label: str,
        section: str,
        key: str,
        default: str,
        values: List[str],
        tooltip_key: str = "",
        widget_store_name: str = "",
        refresh_command: Any = None,
        refresh_button_tooltip: str = "",
        refresh_button_store_name: str = "",
    ) -> None:
        InfoTooltip.add(self.scroll, t(tooltip_key) if tooltip_key else label, row=self.row, column=0)
        ctk.CTkLabel(self.scroll, text=label + ":").grid(
            row=self.row,
            column=1,
            sticky="w",
            padx=(0, 4),
            pady=3,
        )
        combo = ctk.CTkComboBox(self.scroll, values=values, width=200)
        combo.set(default)
        combo.grid(row=self.row, column=2, sticky="ew", padx=6, pady=3)
        if refresh_command:
            btn = ctk.CTkButton(
                self.scroll,
                text="↻",
                width=34,
                height=28,
                command=refresh_command,
                fg_color="gray40",
                hover_color="gray30",
            )
            btn.grid(row=self.row, column=3, padx=(0, 6), pady=3)
            _Tooltip(btn, refresh_button_tooltip or "Refresh list")
            if refresh_button_store_name:
                setattr(self.host, refresh_button_store_name, btn)
        self.host._setting_entries[(section, key)] = combo
        if widget_store_name:
            setattr(self.host, widget_store_name, combo)
        self.row += 1

    def _add_checkbox(self, label: str, section: str, key: str, default: bool, tooltip_key: str = "") -> None:
        InfoTooltip.add(self.scroll, t(tooltip_key) if tooltip_key else label, row=self.row, column=0)
        var = ctk.BooleanVar(value=default)
        cb = ctk.CTkCheckBox(self.scroll, text=label, variable=var)
        cb.grid(row=self.row, column=1, columnspan=2, sticky="w", padx=(0, 4), pady=3)
        self.host._setting_entries[(section, key)] = var
        self.row += 1

    def _build_general_section(self) -> None:
        self._section_header(t("gui.settings.section_general"))

        saved_theme = config.get("gui", "theme", "").strip() or "system"
        theme_labels = {
            "system": t("gui.settings.ui_theme_system"),
            "dark": t("gui.settings.ui_theme_dark"),
            "light": t("gui.settings.ui_theme_light"),
        }
        theme_display = theme_labels.get(saved_theme, t("gui.settings.ui_theme_system"))
        self._add_dropdown(
            t("gui.settings.ui_theme"),
            "gui",
            "theme",
            theme_display,
            list(theme_labels.values()),
            tooltip_key="gui.tip.ui_theme",
            var_store_name="_theme_var",
        )

        saved_ui_lang = config.get("gui", "language", "").strip() or "system"
        lang_labels = {
            "system": t("gui.settings.ui_lang_system"),
            "en": t("gui.settings.ui_lang_en"),
            "ja": t("gui.settings.ui_lang_ja"),
        }
        lang_display = lang_labels.get(saved_ui_lang, t("gui.settings.ui_lang_system"))
        self._add_dropdown(
            t("gui.settings.ui_language"),
            "gui",
            "language",
            lang_display,
            list(lang_labels.values()),
            tooltip_key="gui.tip.ui_language",
            var_store_name="_lang_setting_var",
        )

        self.host._backend_display_map = self.host._build_backend_display_map()
        self.host._backend_reverse_map = {v: k for k, v in self.host._backend_display_map.items()}
        saved_backend = config.get("backend", "type", "bedrock")
        backend_display = self.host._backend_display_map.get(
            saved_backend,
            self.host._backend_display_map.get("bedrock", "bedrock"),
        )
        self._add_dropdown(
            t("gui.settings.backend"),
            "backend",
            "type",
            backend_display,
            list(self.host._backend_display_map.values()),
            tooltip_key="gui.tip.backend",
            var_store_name="_settings_backend_var",
        )

    def _build_bedrock_section(self) -> None:
        self._section_header(t("gui.settings.section_bedrock"), backend_key="bedrock")

        def _refresh_bedrock_with_spinner() -> None:
            if hasattr(self.host, "_bedrock_refresh_btn"):
                btn = self.host._bedrock_refresh_btn
                btn.configure(state="disabled", text="…")
                schedule_after = getattr(self.host, "_schedule_app_after", self.host.after)
                schedule_after(1000, lambda: btn.configure(state="normal", text="↻"))
            self.host._refresh_bedrock_model_list_async()

        self._add_combobox(
            t("gui.settings.model_id"),
            "model",
            "model_id",
            config.get("model", "model_id", ""),
            [],
            tooltip_key="gui.tip.model_id",
            widget_store_name="_bedrock_model_combo",
            refresh_command=_refresh_bedrock_with_spinner,
            refresh_button_tooltip="Refresh Bedrock models",
            refresh_button_store_name="_bedrock_refresh_btn",
        )
        self._add_entry(
            t("gui.settings.aws_region"),
            "aws",
            "region",
            config.get("aws", "region", "us-east-1"),
            tooltip_key="gui.tip.aws_region",
        )
        self._add_entry(
            t("gui.settings.aws_sso_session"),
            "aws",
            "sso_session",
            config.get("aws", "sso_session", ""),
            tooltip_key="gui.tip.aws_sso_session",
        )
        self._add_entry(
            t("gui.settings.aws_access_key"),
            "aws",
            "access_key_id",
            config.get("aws", "access_key_id", ""),
            tooltip_key="gui.tip.aws_access_key",
        )

    def _build_kiro_section(self) -> None:
        self._section_header(t("gui.settings.section_kiro"), backend_key="kiro")

        def _refresh_wsl_distros_with_spinner() -> None:
            if hasattr(self.host, "_wsl_refresh_btn"):
                btn = self.host._wsl_refresh_btn
                btn.configure(state="disabled", text="…")

            def _worker() -> None:
                distros = get_wsl_distros()
                values = distros if distros else ["(none available)"]

                def _apply() -> None:
                    if hasattr(self.host, "_kiro_distro_combo"):
                        current = self.host._kiro_distro_combo.get()
                        self.host._kiro_distro_combo.configure(values=values)
                        if current and current in values:
                            self.host._kiro_distro_combo.set(current)
                    if hasattr(self.host, "_wsl_refresh_btn"):
                        self.host._wsl_refresh_btn.configure(state="normal", text="↻")

                self.host._run_on_ui_thread(_apply)

            threading.Thread(target=_worker, daemon=True).start()

        kiro_distros = get_wsl_distros()
        self._add_combobox(
            t("gui.settings.kiro_distro"),
            "kiro",
            "wsl_distro",
            config.get("kiro", "wsl_distro", ""),
            kiro_distros,
            tooltip_key="gui.tip.kiro_distro",
            widget_store_name="_kiro_distro_combo",
            refresh_command=_refresh_wsl_distros_with_spinner,
            refresh_button_tooltip="Re-scan installed WSL distributions",
            refresh_button_store_name="_wsl_refresh_btn",
        )
        self._add_entry(
            t("gui.settings.kiro_command"),
            "kiro",
            "cli_command",
            config.get("kiro", "cli_command", "kiro"),
            tooltip_key="gui.tip.kiro_command",
        )
        self._add_entry(
            t("gui.settings.kiro_timeout"),
            "kiro",
            "timeout",
            config.get("kiro", "timeout", "300"),
            tooltip_key="gui.tip.kiro_timeout",
        )

        def _refresh_kiro_with_spinner() -> None:
            if hasattr(self.host, "_kiro_refresh_btn"):
                btn = self.host._kiro_refresh_btn
                btn.configure(state="disabled", text="…")
                schedule_after = getattr(self.host, "_schedule_app_after", self.host.after)
                schedule_after(3000, lambda: btn.configure(state="normal", text="↻"))
            self.host._refresh_kiro_model_list_async()

        self._add_combobox(
            t("gui.settings.kiro_model"),
            "kiro",
            "model",
            config.get("kiro", "model", ""),
            [],
            tooltip_key="gui.tip.kiro_model",
            widget_store_name="_kiro_model_combo",
            refresh_command=_refresh_kiro_with_spinner,
            refresh_button_tooltip="Refresh Kiro models",
            refresh_button_store_name="_kiro_refresh_btn",
        )

    def _build_copilot_section(self) -> None:
        self._section_header(t("gui.settings.section_copilot"), backend_key="copilot")
        self._add_entry(
            t("gui.settings.copilot_path"),
            "copilot",
            "copilot_path",
            config.get("copilot", "copilot_path", "copilot"),
            tooltip_key="gui.tip.copilot_path",
        )
        self._add_entry(
            t("gui.settings.copilot_timeout"),
            "copilot",
            "timeout",
            config.get("copilot", "timeout", "300"),
            tooltip_key="gui.tip.copilot_timeout",
        )

        def _refresh_copilot_with_spinner() -> None:
            if hasattr(self.host, "_copilot_refresh_btn"):
                btn = self.host._copilot_refresh_btn
                btn.configure(state="disabled", text="…")
                schedule_after = getattr(self.host, "_schedule_app_after", self.host.after)
                schedule_after(1000, lambda: btn.configure(state="normal", text="↻"))
            self.host._refresh_copilot_model_list_async()

        self._add_combobox(
            t("gui.settings.copilot_model"),
            "copilot",
            "model",
            config.get("copilot", "model", "auto"),
            ["auto"],
            tooltip_key="gui.tip.copilot_model",
            widget_store_name="_copilot_model_combo",
            refresh_command=_refresh_copilot_with_spinner,
            refresh_button_tooltip="Refresh Copilot models",
            refresh_button_store_name="_copilot_refresh_btn",
        )

    def _build_local_llm_section(self) -> None:
        self._section_header(t("gui.settings.section_local"), backend_key="local")
        self._add_entry(
            t("gui.settings.local_api_url"),
            "local_llm",
            "api_url",
            config.get("local_llm", "api_url", "http://localhost:1234"),
            tooltip_key="gui.tip.local_api_url",
        )
        self._add_dropdown(
            t("gui.settings.local_api_type"),
            "local_llm",
            "api_type",
            config.get("local_llm", "api_type", "lmstudio"),
            ["lmstudio", "ollama", "openai", "anthropic"],
            tooltip_key="gui.tip.local_api_type",
        )
        self._add_combobox(
            t("gui.settings.local_model"),
            "local_llm",
            "model",
            config.get("local_llm", "model", "default"),
            [],
            tooltip_key="gui.tip.local_model",
            widget_store_name="_local_model_combo",
        )
        self._add_entry(
            t("gui.settings.local_api_key"),
            "local_llm",
            "api_key",
            config.get("local_llm", "api_key", ""),
            tooltip_key="gui.tip.local_api_key",
        )
        self._add_entry(
            t("gui.settings.local_timeout"),
            "local_llm",
            "timeout",
            config.get("local_llm", "timeout", "300"),
            tooltip_key="gui.tip.local_timeout",
        )
        self._add_entry(
            t("gui.settings.local_max_tokens"),
            "local_llm",
            "max_tokens",
            config.get("local_llm", "max_tokens", "4096"),
            tooltip_key="gui.tip.local_max_tokens",
        )
        self._add_checkbox(
            t("gui.settings.local_enable_web_search"),
            "local_llm",
            "enable_web_search",
            bool(config.get("local_llm", "enable_web_search", True)),
            tooltip_key="gui.tip.local_enable_web_search",
        )

    def _build_local_http_section(self) -> None:
        self._section_header(t("gui.settings.section_local_http"))
        self._add_checkbox(
            t("gui.settings.local_http_enabled"),
            "local_http",
            "enabled",
            config.get("local_http", "enabled", False),
        )
        self._add_entry(
            t("gui.settings.local_http_port"),
            "local_http",
            "port",
            str(config.get("local_http", "port", 8765)),
        )

        ctk.CTkLabel(self.scroll, text=t("gui.settings.local_http_status_label")).grid(
            row=self.row,
            column=1,
            sticky="w",
            padx=(0, 4),
            pady=(2, 3),
        )
        self.host.local_http_status_var = ctk.StringVar(value="")
        self.host.local_http_status_label = ctk.CTkLabel(
            self.scroll,
            textvariable=self.host.local_http_status_var,
            anchor="w",
            justify="left",
            text_color="gray50",
        )
        self.host.local_http_status_label.grid(row=self.row, column=2, columnspan=2, sticky="ew", padx=6, pady=(2, 3))
        self.row += 1

        ctk.CTkLabel(self.scroll, text=t("gui.settings.local_http_base_url")).grid(
            row=self.row,
            column=1,
            sticky="w",
            padx=(0, 4),
            pady=3,
        )
        self.host.local_http_base_url_var = ctk.StringVar(value="")
        self.host.local_http_base_url_entry = ctk.CTkEntry(
            self.scroll,
            textvariable=self.host.local_http_base_url_var,
            state="readonly",
        )
        self.host.local_http_base_url_entry.grid(row=self.row, column=2, sticky="ew", padx=6, pady=3)
        self.host.local_http_copy_btn = ctk.CTkButton(
            self.scroll,
            text=t("gui.settings.local_http_copy_url"),
            width=96,
            command=self.host._copy_local_http_base_url,
            fg_color="gray40",
            hover_color="gray30",
        )
        self.host.local_http_copy_btn.grid(row=self.row, column=3, padx=(0, 6), pady=3)
        self.row += 1

        ctk.CTkLabel(self.scroll, text=t("gui.settings.local_http_docs_label")).grid(
            row=self.row,
            column=1,
            sticky="nw",
            padx=(0, 4),
            pady=3,
        )
        self.host.local_http_docs_box = ctk.CTkTextbox(self.scroll, height=126, wrap="word")
        self.host.local_http_docs_box.grid(row=self.row, column=2, columnspan=2, sticky="ew", padx=6, pady=3)
        self.row += 1
        self.host._refresh_local_http_discovery_ui()

    def _build_performance_section(self) -> None:
        self._section_header(t("gui.settings.section_perf"))
        self._add_entry(
            t("gui.settings.rate_limit"),
            "performance",
            "max_requests_per_minute",
            str(config.get("performance", "max_requests_per_minute", 10)),
            tooltip_key="gui.tip.rate_limit",
        )
        self._add_entry(
            t("gui.settings.request_interval"),
            "performance",
            "min_request_interval_seconds",
            str(config.get("performance", "min_request_interval_seconds", 6.0)),
            tooltip_key="gui.tip.request_interval",
        )
        max_fs_raw = config.get("performance", "max_file_size_mb", 10)
        max_fs = max_fs_raw // (1024 * 1024) if isinstance(max_fs_raw, int) and max_fs_raw > 100 else max_fs_raw
        self._add_entry(
            t("gui.settings.max_file_size"),
            "performance",
            "max_file_size_mb",
            str(max_fs),
            tooltip_key="gui.tip.max_file_size",
        )
        self._add_entry(
            t("gui.settings.batch_size"),
            "processing",
            "batch_size",
            str(config.get("processing", "batch_size", 5)),
            tooltip_key="gui.tip.batch_size",
        )
        combine_val = str(config.get("processing", "combine_files", "true")).lower() in ("true", "1", "yes")
        self._add_checkbox(
            t("gui.settings.combine_files"),
            "processing",
            "combine_files",
            combine_val,
            tooltip_key="gui.tip.combine_files",
        )

    def _build_editor_section(self) -> None:
        self._section_header(t("gui.settings.section_editor"))
        self._add_entry(
            t("gui.settings.editor_command"),
            "gui",
            "editor_command",
            config.get("gui", "editor_command", ""),
            tooltip_key="gui.tip.editor_command",
        )

    def _build_addons_section(self) -> None:
        self._section_header(t("gui.settings.section_addons"))
        addon_intro = ctk.CTkLabel(
            self.scroll,
            text=t("gui.settings.addons_intro"),
            anchor="w",
            justify="left",
            text_color="gray50",
            font=ctk.CTkFont(size=11),
        )
        addon_intro.grid(row=self.row, column=0, columnspan=4, sticky="ew", padx=6, pady=(0, 4))
        self.host._settings_addon_intro_label = addon_intro
        self.row += 1

        ctk.CTkLabel(self.scroll, text=t("gui.settings.addons_loaded")).grid(
            row=self.row,
            column=1,
            sticky="nw",
            padx=(0, 4),
            pady=3,
        )
        self.host.addon_summary_box = ctk.CTkTextbox(self.scroll, height=110, wrap="word")
        self.host.addon_summary_box.grid(row=self.row, column=2, sticky="ew", padx=6, pady=3)
        self.row += 1

        ctk.CTkLabel(self.scroll, text=t("gui.settings.addons_diagnostics")).grid(
            row=self.row,
            column=1,
            sticky="nw",
            padx=(0, 4),
            pady=3,
        )
        self.host.addon_diagnostics_box = ctk.CTkTextbox(self.scroll, height=120, wrap="word")
        self.host.addon_diagnostics_box.grid(row=self.row, column=2, sticky="ew", padx=6, pady=3)
        self.row += 1

        ctk.CTkLabel(self.scroll, text=t("gui.settings.addons_ui_contributions")).grid(
            row=self.row,
            column=1,
            sticky="nw",
            padx=(0, 4),
            pady=3,
        )
        self.host.addon_contributions_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.host.addon_contributions_frame.grid(row=self.row, column=2, sticky="ew", padx=6, pady=3)
        self.host.addon_contributions_frame.grid_columnconfigure(0, weight=1)
        self.row += 1

        self.host._refresh_addons_btn = ctk.CTkButton(
            self.scroll,
            text=t("gui.settings.refresh_addons"),
            width=140,
            command=self.host._refresh_addon_diagnostics,
        )
        self.host._refresh_addons_btn.grid(row=self.row, column=2, sticky="w", padx=6, pady=(0, 6))
        self.row += 1

    def _build_output_formats_section(self) -> None:
        self._section_header("Review Report Output Formats")

        saved_formats = config.get("output", "formats", "json,txt").strip()
        enabled_formats = set(saved_formats.split(",")) if saved_formats else {"json", "txt"}

        InfoTooltip.add(
            self.scroll,
            "Select which file formats to generate for review reports. At least one format must be selected.",
            row=self.row,
            column=0,
        )
        ctk.CTkLabel(self.scroll, text="Output Formats:").grid(
            row=self.row,
            column=1,
            sticky="w",
            padx=(0, 4),
            pady=3,
        )

        formats_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        formats_frame.grid(row=self.row, column=2, sticky="w", padx=6, pady=3)
        self.host._settings_output_formats_frame = formats_frame

        self.host._format_vars = {}
        self.host._settings_output_format_checkboxes = []

        json_var = ctk.BooleanVar(value=("json" in enabled_formats))
        json_checkbox = ctk.CTkCheckBox(formats_frame, text="JSON", variable=json_var)
        json_checkbox.grid(row=0, column=0, padx=(0, 15), sticky="w")
        self.host._format_vars["json"] = json_var
        self.host._settings_output_format_checkboxes.append(json_checkbox)

        txt_var = ctk.BooleanVar(value=("txt" in enabled_formats))
        txt_checkbox = ctk.CTkCheckBox(formats_frame, text="TXT", variable=txt_var)
        txt_checkbox.grid(row=0, column=1, padx=(0, 15), sticky="w")
        self.host._format_vars["txt"] = txt_var
        self.host._settings_output_format_checkboxes.append(txt_checkbox)

        md_var = ctk.BooleanVar(value=("md" in enabled_formats))
        md_checkbox = ctk.CTkCheckBox(formats_frame, text="Markdown (MD)", variable=md_var)
        md_checkbox.grid(row=0, column=2, padx=(0, 15), sticky="w")
        self.host._format_vars["md"] = md_var
        self.host._settings_output_format_checkboxes.append(md_checkbox)

        self.row += 1

    def _build_footer_buttons(self) -> None:
        note = ctk.CTkLabel(
            self.scroll,
            text=t("gui.settings.restart_note"),
            text_color="gray50",
            font=ctk.CTkFont(size=11),
        )
        note.grid(row=self.row, column=0, columnspan=4, pady=(10, 2))
        self.host._settings_note_label = note
        self.row += 1

        button_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        button_frame.grid(row=self.row, column=0, columnspan=4, pady=8)
        self.host._settings_button_frame = button_frame

        save_btn = ctk.CTkButton(button_frame, text=t("gui.settings.save"), command=self.host._save_settings)
        save_btn.grid(row=0, column=0, padx=(0, 10))
        self.host._settings_save_btn = save_btn
        _Tooltip(save_btn, t("gui.shortcut.save_settings"))

        reset_btn = ctk.CTkButton(
            button_frame,
            text="Reset Defaults",
            command=self.host._reset_defaults,
            fg_color="gray40",
            hover_color="gray30",
        )
        reset_btn.grid(row=0, column=1)
        self.host._settings_reset_btn = reset_btn

    def _finalize(self) -> None:
        if hasattr(self.host, "_settings_backend_var"):
            self.host._settings_backend_var.trace_add("write", self.host._update_backend_section_indicators)
            self.host._settings_backend_var.trace_add("write", self.host._sync_menu_to_review)
            self.host._update_backend_section_indicators()
            self.host._sync_review_to_menu()

            schedule_after = getattr(self.host, "_schedule_app_after", self.host.after)
            schedule_after(500, self.host._auto_populate_models)

        self.host._populate_addon_diagnostics()
        self.scroll.bind("<Configure>", self.host._schedule_settings_layout_refresh, add="+")
        self.host._refresh_settings_tab_layout()