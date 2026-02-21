# src/aicodereviewer/gui/review_mixin.py
"""Review-tab builder and execution logic mixin for :class:`App`.

Provides ``_build_review_tab`` plus input validation, dry-run / full review
execution, file browsing helpers and the elapsed-time / health-countdown
tickers.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.backends import create_backend
from aicodereviewer.backends.base import REVIEW_TYPE_KEYS, REVIEW_TYPE_META
from aicodereviewer.config import config
from aicodereviewer.i18n import t
from aicodereviewer.orchestration import AppRunner
from aicodereviewer.scanner import (
    scan_project_with_scope,
    parse_diff_file,
    get_diff_from_commits,
)

from .dialogs import FileSelector
from .widgets import InfoTooltip, _Tooltip, _CancelledError

logger = logging.getLogger(__name__)

__all__ = ["ReviewTabMixin"]


class ReviewTabMixin:
    """Mixin supplying Review-tab construction and review execution."""

    # ══════════════════════════════════════════════════════════════════════
    #  REVIEW TAB  – includes inline results panel
    # ══════════════════════════════════════════════════════════════════════

    def _build_review_tab(self):
        tab = self.tabs.add(t("gui.tab.review"))
        tab.grid_columnconfigure(0, weight=1)

        row = 0

        # ── Project path ──────────────────────────────────────────────────
        path_frame = ctk.CTkFrame(tab)
        path_frame.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        path_frame.grid_columnconfigure(2, weight=1)
        InfoTooltip.add(path_frame, t("gui.tip.project_path"), row=0, column=0)
        ctk.CTkLabel(path_frame, text=t("gui.review.project_path")).grid(row=0, column=1, padx=(0, 4))

        # Load saved project path
        saved_path = config.get("gui", "project_path", "").strip()
        self.path_entry = ctk.CTkEntry(path_frame, placeholder_text=t("gui.review.placeholder_path"))
        if saved_path:
            self.path_entry.insert(0, saved_path)
        self.path_entry.grid(row=0, column=2, sticky="ew", padx=4)
        ctk.CTkButton(path_frame, text=t("common.browse"), width=80,
                       command=self._browse_path).grid(row=0, column=3, padx=6)
        row += 1

        # ── Scope ─────────────────────────────────────────────────────────
        scope_frame = ctk.CTkFrame(tab)
        scope_frame.grid(row=row, column=0, sticky="ew", pady=3)
        InfoTooltip.add(scope_frame, t("gui.tip.scope"), row=0, column=0)
        ctk.CTkLabel(scope_frame, text=t("gui.review.scope")).grid(row=0, column=1, padx=(0, 4))
        self.scope_var = ctk.StringVar(value="project")
        self.scope_var.trace_add("write", self._on_scope_changed)
        ctk.CTkRadioButton(scope_frame, text=t("gui.review.scope_project"),
                            variable=self.scope_var, value="project").grid(row=0, column=2, padx=6)
        ctk.CTkRadioButton(scope_frame, text=t("gui.review.scope_diff"),
                            variable=self.scope_var, value="diff").grid(row=0, column=3, padx=6)

        # File selection sub-options (shown when Full Project is selected)
        self.file_select_frame = ctk.CTkFrame(scope_frame)
        self.file_select_frame.grid(row=1, column=0, columnspan=5, sticky="ew", padx=6, pady=3)
        _saved_file_mode = config.get("gui", "file_select_mode", "all")
        self.file_select_mode_var = ctk.StringVar(value=_saved_file_mode)
        self.file_select_mode_var.trace_add("write", self._on_file_select_mode_changed)
        ctk.CTkRadioButton(self.file_select_frame, text="All Files",
                            variable=self.file_select_mode_var, value="all").grid(row=0, column=0, padx=6, sticky="w")
        file_select_rb = ctk.CTkRadioButton(self.file_select_frame, text="Selected Files",
                            variable=self.file_select_mode_var, value="selected")
        file_select_rb.grid(row=0, column=1, padx=6, sticky="w")
        self.select_files_btn = ctk.CTkButton(self.file_select_frame, text="Select Files...", width=120,
                                              command=self._open_file_selector,
                                              state="normal" if _saved_file_mode == "selected" else "disabled")
        self.select_files_btn.grid(row=0, column=2, padx=6, sticky="w")

        # Restore previously selected files from config
        _saved_files_raw = config.get("gui", "selected_files", "").strip()
        self.selected_files: List[str] = [
            p for p in _saved_files_raw.split("|") if p
        ]
        # Count badge
        self._file_count_lbl = ctk.CTkLabel(
            self.file_select_frame, text="",
            font=ctk.CTkFont(size=11), text_color=("gray40", "gray60"))
        self._file_count_lbl.grid(row=0, column=3, padx=(0, 6), sticky="w")
        if self.selected_files:
            self._file_count_lbl.configure(
                text=f"{len(self.selected_files)} file(s) selected")

        # Optional diff filter (shown when Full Project is selected)
        self.diff_filter_frame = ctk.CTkFrame(scope_frame)
        self.diff_filter_frame.grid(row=2, column=0, columnspan=5, sticky="ew", padx=6, pady=3)
        self.diff_filter_frame.grid_columnconfigure(3, weight=1)
        self.diff_filter_var = ctk.BooleanVar(value=False)
        self.diff_filter_var.trace_add("write", self._on_diff_filter_changed)
        self.diff_filter_cb = ctk.CTkCheckBox(
            self.diff_filter_frame, text="Filter by Diff (review only changed code)",
            variable=self.diff_filter_var)
        self.diff_filter_cb.grid(row=0, column=0, columnspan=4, padx=6, pady=(2, 0), sticky="w")
        InfoTooltip.add(self.diff_filter_frame, t("gui.tip.diff_file"), row=1, column=0)
        ctk.CTkLabel(self.diff_filter_frame, text=t("gui.review.diff_file")).grid(row=1, column=1, padx=4)
        self.diff_filter_file_entry = ctk.CTkEntry(
            self.diff_filter_frame, placeholder_text=t("gui.review.diff_placeholder"), state="disabled")
        self.diff_filter_file_entry.grid(row=1, column=2, columnspan=2, sticky="ew", padx=4)
        self.diff_filter_browse_btn = ctk.CTkButton(
            self.diff_filter_frame, text="…", width=30,
            command=self._browse_diff_filter, state="disabled")
        self.diff_filter_browse_btn.grid(row=1, column=4, padx=4)
        InfoTooltip.add(self.diff_filter_frame, t("gui.tip.commits"), row=2, column=0)
        ctk.CTkLabel(self.diff_filter_frame, text=t("gui.review.commits")).grid(row=2, column=1, padx=4, pady=(3, 0))
        self.diff_filter_commits_entry = ctk.CTkEntry(
            self.diff_filter_frame, placeholder_text=t("gui.review.commits_placeholder"), state="disabled")
        self.diff_filter_commits_entry.grid(row=2, column=2, columnspan=2, sticky="ew", padx=4, pady=(3, 0))

        # Diff sub-options (shown when Diff scope is selected)
        self.diff_frame = ctk.CTkFrame(scope_frame)
        self.diff_frame.grid(row=3, column=0, columnspan=5, sticky="ew", padx=6, pady=3)
        self.diff_frame.grid_columnconfigure(2, weight=1)
        InfoTooltip.add(self.diff_frame, t("gui.tip.diff_file"), row=0, column=0)
        ctk.CTkLabel(self.diff_frame, text=t("gui.review.diff_file")).grid(row=0, column=1, padx=4)
        self.diff_file_entry = ctk.CTkEntry(self.diff_frame, placeholder_text=t("gui.review.diff_placeholder"))
        self.diff_file_entry.grid(row=0, column=2, sticky="ew", padx=4)
        ctk.CTkButton(self.diff_frame, text="…", width=30,
                       command=self._browse_diff).grid(row=0, column=3, padx=4)
        InfoTooltip.add(self.diff_frame, t("gui.tip.commits"), row=1, column=0)
        ctk.CTkLabel(self.diff_frame, text=t("gui.review.commits")).grid(row=1, column=1, padx=4, pady=(3, 0))
        self.commits_entry = ctk.CTkEntry(self.diff_frame, placeholder_text=t("gui.review.commits_placeholder"))
        self.commits_entry.grid(row=1, column=2, sticky="ew", padx=4, pady=(3, 0))

        # Initially hide diff_frame and show file_select_frame + diff_filter_frame
        self.diff_frame.grid_remove()
        row += 1

        # ── Review types ──────────────────────────────────────────────────
        types_hdr = ctk.CTkFrame(tab, fg_color="transparent")
        types_hdr.grid(row=row, column=0, sticky="w", padx=6, pady=(4, 1))
        InfoTooltip.add(types_hdr, t("gui.tip.review_types"), row=0, column=0)
        ctk.CTkLabel(types_hdr, text=t("gui.review.types_label"),
                      anchor="w").grid(row=0, column=1)
        row += 1

        types_frame = ctk.CTkFrame(tab, fg_color="transparent")
        types_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=(0, 4))
        self.type_vars = {}

        # Load previously selected review types from config
        saved_types = config.get("gui", "review_types", "").strip()
        selected_types = set(saved_types.split(",")) if saved_types else {"best_practices"}

        col = 0
        r = 0
        for i, key in enumerate(REVIEW_TYPE_KEYS):
            meta = REVIEW_TYPE_META.get(key, {})
            label = meta.get("label", key)
            var = ctk.BooleanVar(value=(key in selected_types))
            cb = ctk.CTkCheckBox(types_frame, text=label, variable=var, width=200)
            cb.grid(row=r, column=col, sticky="w", padx=4, pady=2)
            self.type_vars[key] = var
            col += 1
            if col >= 3:
                col = 0
                r += 1
        row += 1

        sel_frame = ctk.CTkFrame(tab, fg_color="transparent")
        sel_frame.grid(row=row, column=0, sticky="w", padx=6, pady=2)
        ctk.CTkButton(sel_frame, text=t("gui.review.select_all"), width=90,
                       command=lambda: self._set_all_types(True)).grid(row=0, column=0, padx=4)
        ctk.CTkButton(sel_frame, text=t("gui.review.clear_all"), width=90,
                       command=lambda: self._set_all_types(False)).grid(row=0, column=1, padx=4)
        row += 1

        # ── Backend ───────────────────────────────────────────────────────
        be_frame = ctk.CTkFrame(tab)
        be_frame.grid(row=row, column=0, sticky="ew", pady=3)
        InfoTooltip.add(be_frame, t("gui.tip.backend_select"), row=0, column=0)
        ctk.CTkLabel(be_frame, text=t("gui.review.backend_label")).grid(row=0, column=1, padx=(0, 4))
        self.backend_var = ctk.StringVar(value=config.get("backend", "type", "bedrock"))
        self.backend_var.trace_add("write", self._on_backend_changed)
        for i, (val, key) in enumerate([
            ("bedrock", "gui.review.backend_bedrock"),
            ("kiro", "gui.review.backend_kiro"),
            ("copilot", "gui.review.backend_copilot"),
            ("local", "gui.review.backend_local"),
        ]):
            ctk.CTkRadioButton(be_frame, text=t(key), variable=self.backend_var,
                                value=val).grid(row=0, column=i + 2, padx=6)
        row += 1

        # ── Metadata ──────────────────────────────────────────────────────
        meta_frame = ctk.CTkFrame(tab)
        meta_frame.grid(row=row, column=0, sticky="ew", pady=3)
        meta_frame.grid_columnconfigure(2, weight=1)
        meta_frame.grid_columnconfigure(5, weight=1)

        InfoTooltip.add(meta_frame, t("gui.tip.programmers"), row=0, column=0)
        ctk.CTkLabel(meta_frame, text=t("gui.review.programmers")).grid(row=0, column=1, padx=(0, 4))

        saved_programmers = config.get("gui", "programmers", "").strip()
        self.programmers_entry = ctk.CTkEntry(meta_frame,
                                               placeholder_text=t("gui.review.programmers_ph"))
        if saved_programmers:
            self.programmers_entry.insert(0, saved_programmers)
        self.programmers_entry.grid(row=0, column=2, sticky="ew", padx=4)

        InfoTooltip.add(meta_frame, t("gui.tip.reviewers"), row=0, column=3)
        ctk.CTkLabel(meta_frame, text=t("gui.review.reviewers")).grid(row=0, column=4, padx=(0, 4))

        saved_reviewers = config.get("gui", "reviewers", "").strip()
        self.reviewers_entry = ctk.CTkEntry(meta_frame,
                                             placeholder_text=t("gui.review.reviewers_ph"))
        if saved_reviewers:
            self.reviewers_entry.insert(0, saved_reviewers)
        self.reviewers_entry.grid(row=0, column=5, sticky="ew", padx=4)

        InfoTooltip.add(meta_frame, t("gui.tip.language"), row=1, column=0)
        ctk.CTkLabel(meta_frame, text=t("gui.review.language")).grid(row=1, column=1, padx=(0, 4), pady=(3, 0))

        # Review language dropdown
        saved_review_lang = config.get("gui", "review_language", "").strip() or "system"
        self._review_lang_labels = {
            "system": t("gui.review.lang_system"),
            "en": t("gui.review.lang_en"),
            "ja": t("gui.review.lang_ja"),
        }
        self._review_lang_reverse = {v: k for k, v in self._review_lang_labels.items()}
        lang_display = self._review_lang_labels.get(saved_review_lang,
                                                     t("gui.review.lang_system"))
        self.lang_var = ctk.StringVar(value=lang_display)
        ctk.CTkOptionMenu(meta_frame, variable=self.lang_var,
                           values=list(self._review_lang_labels.values()),
                           width=160).grid(row=1, column=2, sticky="w", padx=4, pady=(3, 0))

        InfoTooltip.add(meta_frame, t("gui.tip.spec_file"), row=1, column=3)
        ctk.CTkLabel(meta_frame, text=t("gui.review.spec_file")).grid(row=1, column=4, padx=(0, 4), pady=(3, 0))

        saved_spec = config.get("gui", "spec_file", "").strip()
        self.spec_entry = ctk.CTkEntry(meta_frame, placeholder_text=t("gui.review.spec_placeholder"))
        if saved_spec:
            self.spec_entry.insert(0, saved_spec)
        self.spec_entry.grid(row=1, column=5, sticky="ew", padx=4, pady=(3, 0))
        row += 1

        # ── Action buttons ────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=row, column=0, sticky="ew", pady=(6, 2))
        self.run_btn = ctk.CTkButton(btn_frame, text=t("gui.review.start"),
                                      fg_color="green", hover_color="#228B22",
                                      command=self._start_review)
        self.run_btn.grid(row=0, column=0, padx=6)
        _Tooltip(self.run_btn, t("gui.shortcut.start_review"))
        self.dry_btn = ctk.CTkButton(btn_frame, text=t("gui.review.dry_run"),
                                      command=self._start_dry_run)
        self.dry_btn.grid(row=0, column=1, padx=6)
        self.health_btn = ctk.CTkButton(btn_frame, text=t("health.check_btn"),
                                         command=self._check_backend_health)
        self.health_btn.grid(row=0, column=2, padx=6)

        self.progress = ctk.CTkProgressBar(tab, width=400)
        self.progress.grid(row=row + 1, column=0, sticky="ew", padx=6, pady=(3, 0))
        self.progress.set(0)

        self._elapsed_lbl = ctk.CTkLabel(
            tab, text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            anchor="e")
        self._elapsed_lbl.grid(row=row + 2, column=0, sticky="e", padx=(0, 10), pady=(0, 4))

    # ══════════════════════════════════════════════════════════════════════
    #  ACTIONS – file browsing, validation, review execution
    # ══════════════════════════════════════════════════════════════════════

    def _browse_path(self):
        if self._testing_mode:
            return
        d = filedialog.askdirectory()
        if d:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, d)

    def _browse_diff(self):
        f = filedialog.askopenfilename(
            filetypes=[("Diff/Patch", "*.diff *.patch"), ("All", "*.*")])
        if f:
            self.diff_file_entry.delete(0, "end")
            self.diff_file_entry.insert(0, f)

    def _set_all_types(self, value: bool):
        for var in self.type_vars.values():
            var.set(value)

    def _on_scope_changed(self, *_args: object) -> None:
        scope = self.scope_var.get()
        if scope == "project":
            self.file_select_frame.grid()
            self.diff_filter_frame.grid()
            self.diff_frame.grid_remove()
        else:
            self.file_select_frame.grid_remove()
            self.diff_filter_frame.grid_remove()
            self.diff_frame.grid()

    def _on_diff_filter_changed(self, *_args: object) -> None:
        enabled = self.diff_filter_var.get()
        state = "normal" if enabled else "disabled"
        self.diff_filter_file_entry.configure(state=state)
        self.diff_filter_browse_btn.configure(state=state)
        self.diff_filter_commits_entry.configure(state=state)

    def _browse_diff_filter(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Diff / Patch", "*.diff *.patch"), ("All files", "*.*")])
        if path:
            self.diff_filter_file_entry.delete(0, "end")
            self.diff_filter_file_entry.insert(0, path)

    def _on_file_select_mode_changed(self, *_args: object):
        mode = self.file_select_mode_var.get()
        if mode == "selected":
            self.select_files_btn.configure(state="normal")
        else:
            self.select_files_btn.configure(state="disabled")

    def _open_file_selector(self):
        path = self.path_entry.get().strip()
        if not path:
            self._show_toast(t("gui.val.path_required"), error=True)
            return
        if not Path(path).is_dir():
            if self._testing_mode:
                path = str(Path(__file__).resolve().parent.parent.parent.parent)
            else:
                self._show_toast("Invalid project path", error=True)
                return
        selector = FileSelector(self, path, self.selected_files)
        self.wait_window(selector)
        if hasattr(selector, 'result') and selector.result:
            self.selected_files = list(selector.result)
            self._file_count_lbl.configure(
                text=f"{len(self.selected_files)} file(s) selected")
            self._show_toast(f"{len(self.selected_files)} file(s) selected")
            try:
                config.set_value("gui", "selected_files",
                                 "|".join(self.selected_files))
                config.save()
            except Exception as exc:
                logger.warning("Could not save selected files: %s", exc)

    def _get_selected_types(self) -> List[str]:
        return [k for k, v in self.type_vars.items() if v.get()]

    def _save_form_values(self):
        try:
            config.set_value("gui", "project_path", self.path_entry.get().strip())
            config.set_value("gui", "programmers", self.programmers_entry.get().strip())
            config.set_value("gui", "reviewers", self.reviewers_entry.get().strip())
            config.set_value("gui", "spec_file", self.spec_entry.get().strip())
            selected_types = self._get_selected_types()
            config.set_value("gui", "review_types", ",".join(selected_types))
            config.set_value("gui", "file_select_mode",
                             self.file_select_mode_var.get())
            config.set_value("gui", "selected_files",
                             "|".join(self.selected_files))
            config.save()
        except Exception as exc:
            logger.warning("Failed to save form values: %s", exc)

    def _validate_inputs(self, dry_run: bool = False) -> Optional[Dict[str, Any]]:
        """Validate form and return a params dict, or None on failure."""
        path = self.path_entry.get().strip()
        scope = self.scope_var.get()
        diff_file: Optional[str] = None
        commits: Optional[str] = None
        diff_filter_file: Optional[str] = None
        diff_filter_commits: Optional[str] = None

        if scope == "diff":
            diff_file = self.diff_file_entry.get().strip() or None
            commits = self.commits_entry.get().strip() or None
        elif scope == "project" and self.diff_filter_var.get():
            diff_filter_file = self.diff_filter_file_entry.get().strip() or None
            diff_filter_commits = self.diff_filter_commits_entry.get().strip() or None

        if scope == "project" and not path:
            self._show_toast(t("gui.val.path_required"), error=True)
            return None

        selected_files: Optional[List[str]] = None
        if scope == "project":
            file_mode = self.file_select_mode_var.get()
            if file_mode == "selected":
                if not self.selected_files:
                    self._show_toast("Please select files for review", error=True)
                    return None
                selected_files = self.selected_files

        if scope == "project" and self.diff_filter_var.get():
            if not diff_filter_file and not diff_filter_commits:
                self._show_toast("Please specify a diff file or commit range for diff filtering", error=True)
                return None

        if scope == "diff" and not diff_file and not commits:
            self._show_toast(t("gui.val.diff_required"), error=True)
            return None

        review_types = self._get_selected_types()
        if not review_types:
            self._show_toast(t("gui.val.type_required"), error=True)
            return None

        programmers = [n.strip() for n in self.programmers_entry.get().split(",") if n.strip()] if not dry_run else []
        reviewers = [n.strip() for n in self.reviewers_entry.get().split(",") if n.strip()] if not dry_run else []

        if not dry_run and (not programmers or not reviewers):
            self._show_toast(t("gui.val.meta_required"), error=True)
            return None

        spec_content = None
        spec_path = self.spec_entry.get().strip()
        if "specification" in review_types and spec_path:
            try:
                with open(spec_path, "r", encoding="utf-8") as fh:
                    spec_content = fh.read()
            except Exception as exc:
                self._show_toast(t("gui.val.spec_read_error", error=exc), error=True)
                return None

        lang_display = self.lang_var.get()
        review_lang = self._review_lang_reverse.get(lang_display, "system")
        if review_lang == "system":
            review_lang = self._ui_lang
        config.set_value("gui", "review_language",
                         self._review_lang_reverse.get(lang_display, "system"))
        try:
            config.save()
        except Exception:
            pass

        return dict(
            path=path or None,
            scope=scope,
            diff_file=diff_file,
            commits=commits,
            review_types=review_types,
            spec_content=spec_content,
            target_lang=review_lang,
            programmers=programmers,
            reviewers=reviewers,
            backend=self.backend_var.get(),
            selected_files=selected_files,
            diff_filter_file=diff_filter_file,
            diff_filter_commits=diff_filter_commits,
        )

    def _start_review(self):
        if self._running:
            return
        if self._testing_mode:
            self._show_toast(
                "Start Review is simulated in testing mode — "
                "see Results tab for sample data", error=False)
            return
        params = self._validate_inputs()
        if not params:
            return
        self._save_form_values()
        self._run_review(params, dry_run=False)

    def _start_dry_run(self):
        if self._running:
            return
        params = self._validate_inputs(dry_run=True)
        if not params:
            return
        if not self._testing_mode:
            self._save_form_values()
        self._run_review(params, dry_run=True)

    def _set_action_buttons_state(self, state: str):
        self.run_btn.configure(state=state)
        self.dry_btn.configure(state=state)
        self.health_btn.configure(state=state)

    def _cancel_operation(self):
        if hasattr(self, '_cancel_event'):
            self._cancel_event.set()
        if hasattr(self, '_review_client') and self._review_client:
            if hasattr(self._review_client, 'cancel'):
                try:
                    self._review_client.cancel()
                except Exception as exc:
                    logger.warning("Failed to cancel backend: %s", exc)
        if self._health_check_backend:
            if self._health_check_timer:
                self._health_check_timer.cancel()
                self._health_check_timer = None
            self._health_check_backend = None
            self._running = False
            self._stop_health_countdown()
            self._set_action_buttons_state("normal")
            self.status_var.set(t("gui.val.cancelled"))
        self.cancel_btn.configure(state="disabled")

    # ── Health-check countdown ticker ─────────────────────────────────────

    _HEALTH_TIMEOUT_SECS = 60

    def _start_health_countdown(self) -> None:
        if self._health_countdown_after_id is not None:
            self.after_cancel(self._health_countdown_after_id)
            self._health_countdown_after_id = None
        self._health_countdown_end = time.monotonic() + self._HEALTH_TIMEOUT_SECS
        self._tick_health_countdown()

    def _tick_health_countdown(self) -> None:
        if self._health_countdown_end is None:
            return
        remaining = max(0, int(self._health_countdown_end - time.monotonic()))
        self._health_countdown_lbl.configure(text=f"⏱ {remaining}s")
        if remaining > 0:
            self._health_countdown_after_id = self.after(1000, self._tick_health_countdown)
        else:
            self._health_countdown_after_id = None

    def _stop_health_countdown(self) -> None:
        if self._health_countdown_after_id is not None:
            self.after_cancel(self._health_countdown_after_id)
            self._health_countdown_after_id = None
        self._health_countdown_end = None
        self._health_countdown_lbl.configure(text="")

    # ── Elapsed-time ticker ────────────────────────────────────────────────

    def _start_elapsed_timer(self) -> None:
        if self._elapsed_after_id is not None:
            self.after_cancel(self._elapsed_after_id)
            self._elapsed_after_id = None
        self._elapsed_start = time.monotonic()
        self._elapsed_lbl.configure(text="0:00")
        self._tick_elapsed()

    def _tick_elapsed(self) -> None:
        if not self._running or self._elapsed_start is None:
            return
        elapsed = int(time.monotonic() - self._elapsed_start)
        m, s = divmod(elapsed, 60)
        self._elapsed_lbl.configure(text=f"{m}:{s:02d}")
        self._elapsed_after_id = self.after(1000, self._tick_elapsed)

    def _stop_elapsed_timer(self) -> None:
        if self._elapsed_after_id is not None:
            self.after_cancel(self._elapsed_after_id)
            self._elapsed_after_id = None
        self._elapsed_start = None
        self._elapsed_lbl.configure(text="")

    def _run_review(self, params: Dict[str, Any], dry_run: bool):
        """Execute the review in a background thread."""
        self._running = True
        self._cancel_event = threading.Event()
        self._set_action_buttons_state("disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.set(0)
        self.status_var.set(t("common.running"))
        self._start_elapsed_timer()

        def _worker() -> None:
            try:
                backend_name: str = params.pop("backend")
                selected_files: Optional[List[str]] = params.pop("selected_files", None)
                diff_filter_file: Optional[str] = params.pop("diff_filter_file", None)
                diff_filter_commits: Optional[str] = params.pop("diff_filter_commits", None)

                client = None if dry_run else create_backend(backend_name)
                self._review_client = client

                has_diff_filter = bool(diff_filter_file or diff_filter_commits)

                def custom_scan_fn(
                    directory: Optional[str],
                    scope: str,
                    diff_file: Optional[str] = None,
                    commits: Optional[str] = None,
                ) -> List[Any]:
                    if scope == "diff":
                        return scan_project_with_scope(directory, scope, diff_file, commits)
                    all_files: List[Any] = scan_project_with_scope(directory, "project")
                    if selected_files:
                        selected_set = {Path(f).resolve() for f in selected_files}
                        all_files = [
                            f for f in all_files
                            if Path(f).resolve() in selected_set
                        ]
                    if has_diff_filter:
                        diff_content: Optional[str] = None
                        if diff_filter_file:
                            try:
                                with open(diff_filter_file, "r", encoding="utf-8") as fh:
                                    diff_content = fh.read()
                            except (IOError, OSError) as exc:
                                logger.error("Failed to read diff filter file: %s", exc)
                                return []
                        elif diff_filter_commits and directory:
                            diff_content = get_diff_from_commits(directory, diff_filter_commits)
                        if not diff_content:
                            logger.warning("No diff content available for filtering")
                            return []
                        diff_entries = parse_diff_file(diff_content)
                        diff_by_name: Dict[str, str] = {
                            entry["filename"]: entry["content"]
                            for entry in diff_entries
                        }
                        intersected: List[Any] = []
                        for file_path in all_files:
                            fp = Path(file_path)
                            rel_path: Optional[str] = None
                            if directory:
                                try:
                                    rel_path = str(fp.relative_to(directory))
                                except ValueError:
                                    rel_path = str(fp)
                            else:
                                rel_path = str(fp)
                            rel_norm = rel_path.replace("\\", "/") if rel_path else ""
                            if rel_norm in diff_by_name:
                                intersected.append({
                                    "path": fp,
                                    "content": diff_by_name[rel_norm],
                                    "filename": rel_norm,
                                })
                        return intersected
                    return all_files

                scan_fn = custom_scan_fn

                runner = AppRunner(
                    client,  # type: ignore[arg-type]
                    scan_fn=scan_fn,
                    backend_name=backend_name,
                )

                def progress_cb(current: int, total: int, msg: str) -> None:
                    if self._cancel_event.is_set():
                        raise _CancelledError(t("gui.val.cancelled"))
                    if total > 0:
                        self.progress.set(current / total)
                    self.status_var.set(f"{msg} {current}/{total}")

                result = runner.run(
                    **params,
                    dry_run=dry_run,
                    progress_callback=progress_cb,
                    interactive=False,
                    cancel_check=self._cancel_event.is_set,
                )

                if dry_run:
                    self.after(0, lambda: self._show_dry_run_complete())
                elif isinstance(result, list):
                    self._issues = result
                    self._review_runner = runner
                    self.after(0, lambda: self._show_issues(result))
                elif result is None:
                    self.after(0, lambda: self.status_var.set(t("gui.val.no_report")))
            except _CancelledError:
                logger.info(t("gui.val.cancelled"))
                self.after(0, lambda: self.status_var.set(t("gui.val.cancelled")))
            except Exception as exc:
                logger.error("Review failed: %s", exc)
                if not self._testing_mode:
                    self.after(0, lambda: messagebox.showerror(t("common.error"),
                                                                str(exc)))
            finally:
                self._running = False
                self.after(0, self._stop_elapsed_timer)
                self.after(0, lambda: self._set_action_buttons_state("normal"))
                self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
                self.after(0, lambda: self.progress.set(1.0))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_dry_run_complete(self):
        self.status_var.set(t("gui.val.dry_run_done"))
        self.tabs.set(t("gui.tab.log"))
