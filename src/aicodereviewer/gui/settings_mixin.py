# src/aicodereviewer/gui/settings_mixin.py
import logging
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.addons import get_active_addon_runtime, install_addon_runtime
from aicodereviewer.config import config
from aicodereviewer.i18n import t
from aicodereviewer.registries import get_backend_registry
from aicodereviewer.review_definitions import get_active_review_pack_paths, install_review_registry, merge_review_pack_paths

from .settings_actions import SettingsPersistenceController
from .settings_addons import SettingsAddonDiagnosticsRenderer
from .settings_builder import SettingsTabBuilder
from .settings_layout import SettingsLayoutHelper
from .results_mixin import _NUMERIC_SETTINGS

logger = logging.getLogger(__name__)

__all__ = ["SettingsTabMixin"]


class SettingsTabMixin:
    """Mixin supplying the Settings tab and its Save / Reset logic."""

    def _settings_logical_width(self, *candidates: Any) -> float:
        return SettingsLayoutHelper.resolve_logical_width(self, *candidates)

    def _schedule_settings_layout_refresh(self, *_args: Any) -> None:
        self._refresh_settings_tab_layout()

    def _refresh_settings_tab_layout(self) -> None:
        logical_width = self._settings_logical_width(getattr(self, "settings_scroll_frame", None), self)
        layout = SettingsLayoutHelper.build_state(logical_width)

        if hasattr(self, "_settings_addon_intro_label"):
            self._settings_addon_intro_label.configure(wraplength=layout.wraplength)
        if hasattr(self, "_settings_addon_review_launcher_label"):
            self._settings_addon_review_launcher_label.configure(wraplength=layout.wraplength)
        if hasattr(self, "_settings_note_label"):
            self._settings_note_label.configure(wraplength=layout.wraplength)
        if hasattr(self, "local_http_status_label"):
            self.local_http_status_label.configure(wraplength=layout.local_http_status_wraplength)

        if hasattr(self, "local_http_copy_btn"):
            self.local_http_copy_btn.configure(width=layout.local_http_copy_button_width)
        if hasattr(self, "local_http_docs_box"):
            self.local_http_docs_box.configure(height=layout.local_http_docs_height)
        if hasattr(self, "addon_summary_box"):
            self.addon_summary_box.configure(height=layout.addon_summary_height)
        if hasattr(self, "addon_diagnostics_box"):
            self.addon_diagnostics_box.configure(height=layout.addon_diagnostics_height)

        format_checkboxes = list(getattr(self, "_settings_output_format_checkboxes", []))
        if format_checkboxes:
            SettingsLayoutHelper.apply_output_format_layout(
                self._settings_output_formats_frame,
                format_checkboxes,
                layout.output_format_columns,
            )

        if hasattr(self, "_settings_button_frame"):
            SettingsLayoutHelper.apply_button_layout(
                tuple(
                    button
                    for button in (
                        getattr(self, "_settings_save_btn", None),
                        getattr(self, "_settings_reset_btn", None),
                        getattr(self, "detach_settings_btn", None),
                        getattr(self, "_detached_settings_redock_btn", None),
                    )
                    if button is not None and bool(getattr(button, "winfo_exists", lambda: False)())
                ),
                stacked=layout.stack_settings_buttons,
            )

        if hasattr(self, "_refresh_addons_btn"):
            self._refresh_addons_btn.grid_configure(sticky=layout.refresh_addons_sticky)

        if hasattr(self, "addon_contributions_frame"):
            SettingsLayoutHelper.apply_contribution_wraplength(
                self.addon_contributions_frame,
                wraplength=layout.contribution_wraplength,
            )

    # ══════════════════════════════════════════════════════════════════════
    #  SETTINGS TAB  – sectioned with tooltips
    # ══════════════════════════════════════════════════════════════════════

    def _build_settings_tab(self):
        SettingsTabBuilder(self).build()

    @staticmethod
    def _settings_bool_value(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")

    def _snapshot_settings_surface_state(self) -> dict[str, Any]:
        entry_values: dict[tuple[str, str], Any] = {}
        for key, widget in getattr(self, "_setting_entries", {}).items():
            try:
                entry_values[key] = widget.get()
            except Exception:
                continue
        format_values = {
            fmt: bool(var.get())
            for fmt, var in getattr(self, "_format_vars", {}).items()
        }
        return {
            "entries": entry_values,
            "formats": format_values,
        }

    def _restore_settings_surface_state(self, state: dict[str, Any] | None) -> None:
        if not state:
            return
        for (section, key), value in state.get("entries", {}).items():
            widget = getattr(self, "_setting_entries", {}).get((section, key))
            if widget is None:
                continue
            try:
                if isinstance(widget, ctk.BooleanVar):
                    widget.set(self._settings_bool_value(value))
                elif isinstance(widget, ctk.StringVar):
                    widget.set(str(value))
                elif hasattr(widget, "set") and not hasattr(widget, "delete"):
                    widget.set(str(value))
                elif hasattr(widget, "delete") and hasattr(widget, "insert"):
                    widget.delete(0, "end")
                    widget.insert(0, str(value))
            except Exception:
                continue

        for fmt, selected in state.get("formats", {}).items():
            if fmt in getattr(self, "_format_vars", {}):
                self._format_vars[fmt].set(bool(selected))

        self._refresh_local_http_discovery_ui()
        self._refresh_settings_tab_layout()

    @staticmethod
    def _clear_settings_container(container: Any) -> None:
        for child in container.winfo_children():
            child.destroy()

    def _render_detached_settings_placeholder(self) -> None:
        tab = self.settings_root_tab
        self._clear_settings_container(tab)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(tab)
        frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        frame.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(
            frame,
            text=t("gui.settings.detached_notice"),
            justify="left",
            anchor="w",
            wraplength=560,
            text_color=("gray35", "gray70"),
        )
        label.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._detached_settings_placeholder_label = label

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.grid(row=1, column=0, sticky="w")

        focus_btn = ctk.CTkButton(
            button_row,
            text=t("gui.settings.focus_window"),
            command=self._open_detached_settings_window,
        )
        focus_btn.grid(row=0, column=0, padx=(0, 10))

        redock_btn = ctk.CTkButton(
            button_row,
            text=t("gui.settings.redock"),
            command=self._redock_detached_settings_window,
            fg_color="gray40",
            hover_color="gray30",
        )
        redock_btn.grid(row=0, column=1)

    def _rebuild_settings_surface_from_config(self) -> None:
        if self._is_settings_detached():
            self._rebuild_detached_settings_surface()
            return
        self._rebuild_main_settings_surface()

    def _rebuild_main_settings_surface(self, state: dict[str, Any] | None = None) -> None:
        self._clear_settings_container(self.settings_root_tab)
        SettingsTabBuilder(self, parent=self.settings_root_tab).build()
        self._restore_settings_surface_state(state)

    def _rebuild_detached_settings_surface(self, state: dict[str, Any] | None = None) -> None:
        container = getattr(self, "_detached_settings_container", None)
        if container is None:
            return
        self._clear_settings_container(container)
        SettingsTabBuilder(self, parent=container, detached=True).build()
        self._app_helpers().surfaces().bind_detached_redock_shortcuts(container, self._settings_redock_detached_window)
        self._restore_settings_surface_state(state)

    def _is_settings_detached(self) -> bool:
        window = getattr(self, "_detached_settings_window", None)
        return bool(window is not None and window.winfo_exists())

    def _destroy_detached_settings_window(self, *, persist_detached_state: bool) -> None:
        window = getattr(self, "_detached_settings_window", None)
        if window is not None and window.winfo_exists():
            try:
                self._app_helpers().surfaces().save_detached_page_geometry("settings", window.geometry())
            except Exception:
                pass
            try:
                window.destroy()
            except Exception:
                pass
        self._detached_settings_window = None
        self._detached_settings_container = None
        self._detached_settings_redock_btn = None
        if persist_detached_state:
            self._app_helpers().surfaces().set_page_detached("settings", False)

    def _settings_open_detached_window(self, *, restoring: bool = False) -> None:
        existing = getattr(self, "_detached_settings_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return

        state = self._snapshot_settings_surface_state()
        win = ctk.CTkToplevel(self)
        win.title(t("gui.settings.detached_title"))
        saved_geometry = str(config.get("gui", "detached_settings_geometry", "") or "").strip()
        win.geometry(saved_geometry or "980x720")
        win.minsize(720, 520)
        self._schedule_titlebar_fix(win)

        container = ctk.CTkFrame(win, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self._detached_settings_window = win
        self._detached_settings_container = container
        self.detach_settings_btn = None
        self._rebuild_detached_settings_surface(state)
        self._render_detached_settings_placeholder()

        def _persist_geometry(_event: Any = None) -> None:
            if not win.winfo_exists() or getattr(self, "_app_destroying", False):
                return
            try:
                self._app_helpers().surfaces().save_detached_page_geometry("settings", win.geometry())
            except Exception:
                pass

        def _on_close() -> None:
            if getattr(self, "_app_destroying", False):
                self._destroy_detached_settings_window(persist_detached_state=False)
                return
            self._settings_redock_detached_window()

        win.protocol("WM_DELETE_WINDOW", _on_close)
        win.bind("<Configure>", _persist_geometry, add="+")
        self._app_helpers().surfaces().set_page_detached("settings", True)
        if restoring:
            self._show_toast(t("gui.settings.window_restored"))

    def _settings_redock_detached_window(self) -> None:
        if not self._is_settings_detached():
            return
        state = self._snapshot_settings_surface_state()
        self._destroy_detached_settings_window(persist_detached_state=True)
        self._rebuild_main_settings_surface(state)
        self.tabs.set(t("gui.tab.settings"))

    def _build_backend_display_map(self) -> dict[str, str]:
        builtin_labels = {
            "bedrock": t("gui.settings.backend_bedrock"),
            "kiro": t("gui.settings.backend_kiro"),
            "copilot": t("gui.settings.backend_copilot"),
            "local": t("gui.settings.backend_local"),
        }
        display_map: dict[str, str] = {}
        for descriptor in get_backend_registry().list_descriptors():
            display_map[descriptor.key] = builtin_labels.get(descriptor.key, descriptor.display_name)
        return display_map

    def _set_readonly_textbox(self, textbox: Any, text: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("0.0", "end")
        textbox.insert("0.0", text)
        textbox.configure(state="disabled")

    def _settings_addon_renderer(self) -> SettingsAddonDiagnosticsRenderer:
        return SettingsAddonDiagnosticsRenderer(get_active_addon_runtime())

    def _settings_persistence_controller(self) -> SettingsPersistenceController:
        return SettingsPersistenceController(self, numeric_settings=_NUMERIC_SETTINGS)

    def _populate_addon_diagnostics(self) -> None:
        view_model = self._settings_addon_renderer().build_view_model()
        if hasattr(self, "addon_summary_box"):
            self._set_readonly_textbox(self.addon_summary_box, view_model.summary_text)
        if hasattr(self, "addon_diagnostics_box"):
            self._set_readonly_textbox(self.addon_diagnostics_box, view_model.diagnostics_text)
        if hasattr(self, "addon_contributions_frame"):
            self._populate_addon_contributions()
        self._refresh_settings_tab_layout()

    def _populate_addon_contributions(self) -> None:
        self._settings_addon_renderer().populate_contributions(self.addon_contributions_frame)

    def _refresh_addon_diagnostics(self, *, show_toast: bool = True) -> None:
        install_addon_runtime()
        install_review_registry(merge_review_pack_paths(get_active_review_pack_paths()))
        self._populate_addon_diagnostics()
        if show_toast:
            self._show_toast(t("gui.settings.addons_refreshed"))

    def _auto_populate_models(self):
        """Auto-populate Copilot and Bedrock models when Settings tab opens."""
        self._refresh_copilot_model_list_async()
        self._refresh_kiro_model_list_async()
        self._refresh_bedrock_model_list_async()

    # ══════════════════════════════════════════════════════════════════════
    #  SETTINGS save / reset
    # ══════════════════════════════════════════════════════════════════════

    def _save_settings(self):
        self._settings_persistence_controller().save()

    def _rotate_local_llm_api_key(self) -> None:
        self._settings_persistence_controller().rotate_local_llm_api_key()

    def _revoke_local_llm_api_key(self) -> None:
        self._settings_persistence_controller().revoke_local_llm_api_key()

    def _reset_defaults(self):
        self._settings_persistence_controller().reset_defaults()

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

    def _copy_local_http_base_url(self) -> None:
        base_url = self._local_http_base_url_value()
        self.clipboard_clear()
        self.clipboard_append(base_url)
        self._show_toast(t("gui.settings.local_http_copied", url=base_url))

    def _local_http_status_snapshot(self) -> tuple[str, str]:
        if hasattr(self, "_local_http_runtime_status_snapshot"):
            return self._local_http_runtime_status_snapshot()
        port = int(config.get("local_http", "port", 8765))
        return t("gui.settings.local_http_status_disabled", port=port), f"http://127.0.0.1:{port}"

    def _local_http_base_url_value(self) -> str:
        _status, base_url = self._local_http_status_snapshot()
        return base_url

    def _local_http_docs_text(self) -> str:
        base_url = self._local_http_base_url_value()
        lines = [
            t("gui.settings.local_http_docs_intro", url=base_url),
            "",
            "GET /api/backends",
            "GET /api/review-types",
            "GET /api/review-presets",
            "POST /api/recommendations/review-types",
            "GET /api/jobs",
            "POST /api/jobs",
            "GET /api/jobs/{job_id}",
            "POST /api/jobs/{job_id}/cancel",
            "GET /api/jobs/{job_id}/report",
            "GET /api/jobs/{job_id}/artifacts",
            "GET /api/jobs/{job_id}/artifacts/{artifact_key}/raw",
            "GET /api/events",
            "GET /api/jobs/{job_id}/events",
        ]
        return "\n".join(lines)

    def _refresh_local_http_discovery_ui(self) -> None:
        status_text, base_url = self._local_http_status_snapshot()
        if hasattr(self, "local_http_status_var"):
            self.local_http_status_var.set(status_text)
        if hasattr(self, "local_http_base_url_var"):
            self.local_http_base_url_var.set(base_url)
        if hasattr(self, "local_http_docs_box"):
            self._set_readonly_textbox(self.local_http_docs_box, self._local_http_docs_text())
