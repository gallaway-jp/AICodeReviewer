from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.addon_review_surface import build_addon_review_surface, review_generated_addon_preview
from aicodereviewer.config import config
from aicodereviewer.i18n import t

from .addon_review_builder import AddonReviewTabBuilder
from .addon_review_renderer import AddonReviewRenderer


class AddonReviewTabMixin:
    def _build_addon_review_tab(self) -> None:
        AddonReviewTabBuilder(self).build()

    def _schedule_addon_review_layout_refresh(self, *_args: Any) -> None:
        self._refresh_addon_review_tab_layout()

    def _refresh_addon_review_tab_layout(self) -> None:
        logical_width = float(
            getattr(self, "_benchmark_logical_width", lambda *_args: self.winfo_width())(
                getattr(self, "addon_review_root_tab", None),
                getattr(self, "addon_review_scroll_frame", None),
                self,
            )
        )
        wraplength = max(320, int(logical_width) - 80)
        for attr_name in ("addon_review_intro_subtitle_label", "addon_review_quickstart_label"):
            widget = getattr(self, attr_name, None)
            if widget is not None:
                widget.configure(wraplength=wraplength)

    def _open_addon_review_tab(self) -> None:
        if bool(getattr(self, "_detached_addon_review_window", None)) and self._app_helpers().surfaces().is_page_detached("addon_review"):
            self._focus_detached_addon_review_window()
            return
        self.tabs.set(t("gui.tab.addon_review"))

    def _default_addon_review_reviewer_name(self) -> str:
        raw_reviewers = str(config.get("gui", "reviewers", "") or "").strip()
        if not raw_reviewers:
            return ""
        return raw_reviewers.split(",")[0].strip()

    def _addon_review_renderer(self) -> AddonReviewRenderer:
        return AddonReviewRenderer()

    def _snapshot_addon_review_surface_state(self) -> dict[str, Any]:
        return {
            "preview_dir": self._addon_review_entry_value("addon_review_preview_entry"),
            "reviewer": self._addon_review_entry_value("addon_review_reviewer_entry"),
            "install_dir": self._addon_review_entry_value("addon_review_install_dir_entry"),
            "notes": self._addon_review_notes_value(),
            "selected_diff": self._addon_review_selected_diff_label(),
        }

    def _restore_addon_review_surface_state(self, state: dict[str, Any] | None) -> None:
        if not state:
            return
        preview_dir = str(state.get("preview_dir") or "").strip()
        reviewer = str(state.get("reviewer") or "").strip()
        install_dir = str(state.get("install_dir") or "").strip()
        notes = str(state.get("notes") or "")
        selected_diff = str(state.get("selected_diff") or "").strip()

        if reviewer and hasattr(self, "addon_review_reviewer_entry"):
            self.addon_review_reviewer_entry.delete(0, "end")
            self.addon_review_reviewer_entry.insert(0, reviewer)
        if install_dir and hasattr(self, "addon_review_install_dir_entry"):
            self.addon_review_install_dir_entry.delete(0, "end")
            self.addon_review_install_dir_entry.insert(0, install_dir)
        if notes and hasattr(self, "addon_review_notes_box"):
            self.addon_review_notes_box.delete("0.0", "end")
            self.addon_review_notes_box.insert("0.0", notes)
        if preview_dir and hasattr(self, "addon_review_preview_entry"):
            self.addon_review_preview_entry.delete(0, "end")
            self.addon_review_preview_entry.insert(0, preview_dir)
            if Path(preview_dir).is_dir():
                self._load_addon_review_surface(show_toast=False)
                if selected_diff:
                    self._select_addon_review_diff(selected_diff)

    def _clear_addon_review_container(self, container: Any) -> None:
        if container is None:
            return
        for child in container.winfo_children():
            child.destroy()

    def _focus_detached_addon_review_window(self) -> None:
        window = getattr(self, "_detached_addon_review_window", None)
        if window is None or not window.winfo_exists():
            return
        window.deiconify()
        window.lift()
        window.focus_force()

    def _render_detached_addon_review_placeholder(self) -> None:
        tab = getattr(self, "addon_review_root_tab", None)
        if tab is None:
            return
        self._clear_addon_review_container(tab)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(tab)
        frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text=t("gui.addon_review.detached_notice"),
            justify="left",
            anchor="w",
            wraplength=560,
            text_color=("gray35", "gray70"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10), padx=12)

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))
        ctk.CTkButton(actions, text=t("gui.addon_review.focus_window"), command=self._focus_detached_addon_review_window).grid(
            row=0, column=0, padx=(0, 10)
        )
        ctk.CTkButton(
            actions,
            text=t("gui.addon_review.redock"),
            command=self._addon_review_redock_detached_window,
            fg_color="gray40",
            hover_color="gray30",
        ).grid(row=0, column=1)

    def _rebuild_main_addon_review_surface(self, state: dict[str, Any] | None = None) -> None:
        root_tab = getattr(self, "addon_review_root_tab", None)
        if root_tab is None:
            return
        self._clear_addon_review_container(root_tab)
        AddonReviewTabBuilder(self, parent=root_tab).build()
        self._restore_addon_review_surface_state(state)

    def _rebuild_detached_addon_review_surface(self, state: dict[str, Any] | None = None) -> None:
        container = getattr(self, "_detached_addon_review_container", None)
        if container is None:
            return
        self._clear_addon_review_container(container)
        AddonReviewTabBuilder(self, parent=container, detached=True).build()
        self._app_helpers().surfaces().bind_detached_redock_shortcuts(container, self._addon_review_redock_detached_window)
        self._restore_addon_review_surface_state(state)

    def _destroy_detached_addon_review_window(self, *, persist_geometry: bool = True) -> None:
        window = getattr(self, "_detached_addon_review_window", None)
        if window is not None and window.winfo_exists():
            if persist_geometry:
                self._app_helpers().surfaces().save_detached_page_geometry("addon_review", window.geometry())
            window.destroy()
        self._detached_addon_review_window = None
        self._detached_addon_review_container = None
        self._detached_addon_review_redock_btn = None

    def _addon_review_open_detached_window(self, *, restoring: bool = False) -> None:
        existing_window = getattr(self, "_detached_addon_review_window", None)
        if existing_window is not None and existing_window.winfo_exists():
            self._focus_detached_addon_review_window()
            return

        root_tab = getattr(self, "addon_review_root_tab", None)
        if root_tab is None:
            return

        state = self._snapshot_addon_review_surface_state()
        detached_window = ctk.CTkToplevel(self)
        detached_window.title(t("gui.addon_review.detached_title"))
        saved_geometry = str(config.get("gui", "detached_addon_review_geometry", "") or "").strip()
        detached_window.geometry(saved_geometry or "1180x860")
        detached_window.minsize(900, 640)
        self._schedule_titlebar_fix(detached_window)

        container = ctk.CTkFrame(detached_window, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self._detached_addon_review_window = detached_window
        self._detached_addon_review_container = container
        self._app_helpers().surfaces().set_page_detached("addon_review", True)
        self._rebuild_detached_addon_review_surface(state)
        self._render_detached_addon_review_placeholder()

        def _persist_geometry(_event: Any = None) -> None:
            if not detached_window.winfo_exists() or getattr(self, "_app_destroying", False):
                return
            try:
                self._app_helpers().surfaces().save_detached_page_geometry("addon_review", detached_window.geometry())
            except Exception:
                pass

        def _on_close() -> None:
            if getattr(self, "_app_destroying", False):
                self._destroy_detached_addon_review_window(persist_geometry=False)
                return
            self._addon_review_redock_detached_window()

        detached_window.protocol("WM_DELETE_WINDOW", _on_close)
        detached_window.bind("<Configure>", _persist_geometry, add="+")
        if restoring:
            self._show_toast(t("gui.addon_review.window_restored"))
        self._focus_detached_addon_review_window()

    def _addon_review_redock_detached_window(self) -> None:
        window = getattr(self, "_detached_addon_review_window", None)
        if window is None or not window.winfo_exists():
            self._app_helpers().surfaces().set_page_detached("addon_review", False)
            return
        state = self._snapshot_addon_review_surface_state()
        self._destroy_detached_addon_review_window()
        self._app_helpers().surfaces().set_page_detached("addon_review", False)
        self._rebuild_main_addon_review_surface(state)
        try:
            self.tabs.set(t("gui.tab.addon_review"))
        except Exception:
            pass

    def _initialize_addon_review_surface_widgets(self) -> None:
        self._current_addon_review_surface = None
        self._current_addon_review_diffs = {}
        self._set_addon_review_action_state(enabled=False)
        self._set_readonly_textbox(self.addon_review_status_box, t("gui.settings.addons_preview_status_empty"))
        self._set_readonly_textbox(self.addon_review_metadata_box, t("gui.settings.addons_preview_metadata_empty"))
        self._set_readonly_textbox(self.addon_review_checklist_box, t("gui.settings.addons_preview_checklist_empty"))
        self._set_readonly_textbox(self.addon_review_diff_box, t("gui.settings.addons_preview_diff_empty"))
        self.addon_review_diff_menu.configure(values=[t("gui.settings.addons_preview_diff_placeholder")], state="disabled")
        self.addon_review_diff_var.set(t("gui.settings.addons_preview_diff_placeholder"))

    def _addon_review_entry_value(self, attr_name: str) -> str:
        widget = getattr(self, attr_name, None)
        if widget is None:
            return ""
        try:
            return str(widget.get()).strip()
        except Exception:
            return ""

    def _addon_review_notes_value(self) -> str:
        textbox = getattr(self, "addon_review_notes_box", None)
        if textbox is None:
            return ""
        try:
            return str(textbox.get("0.0", "end")).strip()
        except Exception:
            return ""

    def _addon_review_selected_diff_label(self) -> str:
        variable = getattr(self, "addon_review_diff_var", None)
        if variable is None:
            return ""
        try:
            return str(variable.get()).strip()
        except Exception:
            return ""

    def _set_addon_review_action_state(self, *, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        if hasattr(self, "addon_review_approve_btn"):
            self.addon_review_approve_btn.configure(state=state)
        if hasattr(self, "addon_review_reject_btn"):
            self.addon_review_reject_btn.configure(state=state)

    def _browse_addon_review_preview_dir(self) -> None:
        if self._testing_mode:
            return
        selected = filedialog.askdirectory()
        if not selected:
            return
        self.addon_review_preview_entry.delete(0, "end")
        self.addon_review_preview_entry.insert(0, selected)

    def _browse_addon_review_install_dir(self) -> None:
        if self._testing_mode:
            return
        selected = filedialog.askdirectory()
        if not selected:
            return
        self.addon_review_install_dir_entry.delete(0, "end")
        self.addon_review_install_dir_entry.insert(0, selected)

    def _load_addon_review_surface(self, *, show_toast: bool = True) -> None:
        preview_dir = self._addon_review_entry_value("addon_review_preview_entry")
        if not preview_dir:
            self._show_toast(t("gui.settings.addons_preview_path_required"), error=True)
            return
        install_dir = self._addon_review_entry_value("addon_review_install_dir_entry") or None
        try:
            surface = build_addon_review_surface(preview_dir, install_dir=install_dir)
        except Exception as exc:
            self._show_toast(t("gui.settings.addons_preview_load_error", error=exc), error=True)
            return
        self._populate_addon_review_surface(surface)
        if show_toast:
            self._show_toast(t("gui.settings.addons_preview_loaded", addon_id=surface.addon_id))

    def _populate_addon_review_surface(self, surface: Any) -> None:
        view_model = self._addon_review_renderer().build_view_model(surface)
        self._current_addon_review_surface = surface
        self._current_addon_review_diffs = {diff.label: diff.diff_text for diff in view_model.diffs}
        self._set_readonly_textbox(self.addon_review_status_box, view_model.status_text)
        self._set_readonly_textbox(self.addon_review_metadata_box, view_model.metadata_text)
        self._set_readonly_textbox(self.addon_review_checklist_box, view_model.checklist_text)
        diff_labels = list(self._current_addon_review_diffs) or [t("gui.settings.addons_preview_diff_placeholder")]
        self.addon_review_diff_menu.configure(values=diff_labels, state="normal" if self._current_addon_review_diffs else "disabled")
        self._set_addon_review_action_state(enabled=bool(self._current_addon_review_diffs))
        self._select_addon_review_diff(diff_labels[0])

    def _select_addon_review_diff(self, label: str) -> None:
        resolved_label = label if label in getattr(self, "_current_addon_review_diffs", {}) else ""
        if not resolved_label:
            self.addon_review_diff_var.set(t("gui.settings.addons_preview_diff_placeholder"))
            self._set_readonly_textbox(self.addon_review_diff_box, t("gui.settings.addons_preview_diff_empty"))
            return
        self.addon_review_diff_var.set(resolved_label)
        self._set_readonly_textbox(self.addon_review_diff_box, self._current_addon_review_diffs[resolved_label])

    def _on_addon_review_diff_selected(self, value: str) -> None:
        self._select_addon_review_diff(value)

    def _approve_loaded_addon_review_preview(self) -> None:
        self._apply_addon_review_decision("approve")

    def _reject_loaded_addon_review_preview(self) -> None:
        self._apply_addon_review_decision("reject")

    def _apply_addon_review_decision(self, decision: str) -> None:
        surface = getattr(self, "_current_addon_review_surface", None)
        if surface is None:
            self._show_toast(t("gui.settings.addons_preview_load_first"), error=True)
            return
        reviewer = self._addon_review_entry_value("addon_review_reviewer_entry")
        if not reviewer:
            self._show_toast(t("gui.settings.addons_preview_reviewer_required"), error=True)
            return
        install_dir = self._addon_review_entry_value("addon_review_install_dir_entry") or None
        try:
            result = review_generated_addon_preview(
                surface.preview_dir,
                reviewer=reviewer,
                decision=decision,
                notes=self._addon_review_notes_value(),
                install_dir=install_dir,
            )
        except Exception as exc:
            self._show_toast(t("gui.settings.addons_preview_decision_error", error=exc), error=True)
            return
        self._load_addon_review_surface(show_toast=False)
        if hasattr(self, "_refresh_addon_diagnostics"):
            self._refresh_addon_diagnostics(show_toast=False)
        self._show_toast(
            t(
                "gui.settings.addons_preview_decision_saved",
                decision=result.get("decision", decision),
                reviewer=result.get("reviewer", reviewer),
            )
        )