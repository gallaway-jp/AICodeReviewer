# src/aicodereviewer/gui/settings_mixin.py
import logging
from typing import Any

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
                self._settings_save_btn,
                self._settings_reset_btn,
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

    def _refresh_addon_diagnostics(self) -> None:
        install_addon_runtime()
        install_review_registry(merge_review_pack_paths(get_active_review_pack_paths()))
        self._populate_addon_diagnostics()
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
