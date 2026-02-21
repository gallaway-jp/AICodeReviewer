# src/aicodereviewer/gui/results_mixin.py
"""Results-tab builder and issue-card logic mixin for :class:`App`.

Provides ``_build_results_tab`` plus issue cards, AI Fix mode, diff previews,
session save / load, and report finalization.
"""
from __future__ import annotations

import dataclasses
import datetime
import difflib
import json
import logging
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional, TypedDict

import tkinter as tk

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.config import config
from aicodereviewer.i18n import t
from aicodereviewer.models import ReviewIssue
from aicodereviewer.reviewer import verify_issue_resolved

from .dialogs import ConfirmDialog
from .widgets import _fix_titlebar

logger = logging.getLogger(__name__)

__all__ = ["ResultsTabMixin", "IssueCard", "_NUMERIC_SETTINGS"]


class IssueCard(TypedDict):
    """Type-safe record stored in ``App._issue_cards``."""
    issue: "ReviewIssue"
    card: Any
    status_lbl: Any
    desc_lbl: Any
    expand_btn: Any
    view_btn: Any
    resolve_btn: Any
    skip_btn: Any
    fix_checkbox: Any
    fix_check_var: Any
    skip_frame: Any
    skip_entry: Any
    color: str


# Fields in _setting_entries that must be numeric.
_NUMERIC_SETTINGS: dict[tuple[str, str], tuple[str, type, float]] = {
    ("kiro",        "timeout"):                    ("Kiro timeout",             int,   1),
    ("copilot",     "timeout"):                    ("Copilot timeout",          int,   1),
    ("local_llm",   "timeout"):                    ("Local LLM timeout",        int,   1),
    ("local_llm",   "max_tokens"):                 ("Max tokens",               int,   1),
    ("performance", "max_requests_per_minute"):    ("Max requests/min",         int,   1),
    ("performance", "min_request_interval_seconds"): ("Min request interval",  float, 0),
    ("performance", "max_file_size_mb"):            ("Max file size (MB)",       float, 0),
    ("processing",  "batch_size"):                  ("Batch size",              int,   1),
}


class ResultsTabMixin:
    """Mixin supplying Results-tab construction and all issue-card logic."""

    # ══════════════════════════════════════════════════════════════════════
    #  RESULTS TAB  – full-page issue cards
    # ══════════════════════════════════════════════════════════════════════

    def _build_results_tab(self):
        tab = self.tabs.add(t("gui.tab.results"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        self.results_summary = ctk.CTkLabel(tab, text=t("gui.results.no_results"),
                                             anchor="w",
                                             font=ctk.CTkFont(weight="bold"))
        self.results_summary.grid(row=0, column=0, sticky="ew",
                                   padx=8, pady=(6, 0))

        # ── Severity breakdown bar ─────────────────────────────────────────
        self.results_severity_bar = ctk.CTkLabel(
            tab, text="", anchor="w",
            font=ctk.CTkFont(size=12))
        self.results_severity_bar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 2))
        self.results_severity_bar.grid_remove()

        # ── Filter bar ────────────────────────────────────────────────────
        self._filter_bar = ctk.CTkFrame(tab, fg_color="transparent")
        self._filter_bar.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 2))
        self._filter_bar.grid_columnconfigure(7, weight=1)

        ctk.CTkLabel(self._filter_bar,
                     text=t("gui.results.filter_severity")).grid(
            row=0, column=0, padx=(0, 2))
        self._filter_sev_var = ctk.StringVar(value=t("gui.results.filter_all"))
        self._filter_severity_menu = ctk.CTkOptionMenu(
            self._filter_bar, variable=self._filter_sev_var, width=110,
            values=[t("gui.results.filter_all"),
                    "Critical", "High", "Medium", "Low", "Info"],
            command=lambda _: self._apply_filters())
        self._filter_severity_menu.grid(row=0, column=1, padx=(0, 8))

        ctk.CTkLabel(self._filter_bar,
                     text=t("gui.results.filter_status")).grid(
            row=0, column=2, padx=(0, 2))
        self._filter_status_var = ctk.StringVar(value=t("gui.results.filter_all"))
        self._filter_status_menu = ctk.CTkOptionMenu(
            self._filter_bar, variable=self._filter_status_var, width=120,
            values=[t("gui.results.filter_all"),
                    "Pending", "Resolved", "Ignored",
                    "Skipped", "Fixed", "AI Fixed", "Fix Failed"],
            command=lambda _: self._apply_filters())
        self._filter_status_menu.grid(row=0, column=3, padx=(0, 8))

        ctk.CTkLabel(self._filter_bar,
                     text=t("gui.results.filter_type")).grid(
            row=0, column=4, padx=(0, 2))
        self._filter_type_var = ctk.StringVar(value=t("gui.results.filter_all_types"))
        self._filter_type_menu = ctk.CTkOptionMenu(
            self._filter_bar, variable=self._filter_type_var, width=150,
            values=[t("gui.results.filter_all_types")],
            command=lambda _: self._apply_filters())
        self._filter_type_menu.grid(row=0, column=5, padx=(0, 8))

        ctk.CTkButton(
            self._filter_bar, text=t("gui.results.filter_clear"),
            width=80, fg_color="gray50", hover_color="gray40",
            command=self._clear_filters,
        ).grid(row=0, column=6, padx=(0, 8))

        self._filter_count_lbl = ctk.CTkLabel(
            self._filter_bar, text="", anchor="e",
            font=ctk.CTkFont(size=11))
        self._filter_count_lbl.grid(row=0, column=7, padx=4, sticky="e")

        self._filter_bar.grid_remove()

        self.results_frame = ctk.CTkScrollableFrame(tab)
        self.results_frame.grid(row=3, column=0, sticky="nsew",
                                 padx=8, pady=(0, 4))
        self.results_frame.grid_columnconfigure(0, weight=1)

        # Bottom action buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 6))

        self.ai_fix_mode_btn = ctk.CTkButton(
            btn_frame, text=t("gui.results.ai_fix_mode"),
            fg_color="#7c3aed", hover_color="#6d28d9",
            state="disabled", command=self._enter_ai_fix_mode)
        self.ai_fix_mode_btn.grid(row=0, column=0, padx=6)

        self.review_changes_btn = ctk.CTkButton(
            btn_frame, text=t("gui.results.review_changes"),
            fg_color="#2563eb", hover_color="#1d4ed8",
            state="disabled", command=self._review_changes)
        self.review_changes_btn.grid(row=0, column=1, padx=6)

        self.finalize_btn = ctk.CTkButton(
            btn_frame, text=t("gui.results.finalize"),
            fg_color="green", hover_color="#228B22",
            state="disabled", command=self._finalize_report)
        self.finalize_btn.grid(row=0, column=2, padx=6)

        self.save_session_btn = ctk.CTkButton(
            btn_frame, text=t("gui.results.save_session"),
            fg_color="#0e7490", hover_color="#0c6983",
            width=110, state="disabled", command=self._save_session)
        self.save_session_btn.grid(row=0, column=3, padx=(18, 6))

        self.load_session_btn = ctk.CTkButton(
            btn_frame, text=t("gui.results.load_session"),
            fg_color="#374151", hover_color="#1f2937",
            width=110, command=self._load_session)
        self.load_session_btn.grid(row=0, column=4, padx=6)

        # AI Fix mode buttons (hidden initially)
        self.start_ai_fix_btn = ctk.CTkButton(
            btn_frame, text=t("gui.results.start_ai_fix"),
            fg_color="#7c3aed", hover_color="#6d28d9",
            command=self._start_batch_ai_fix)
        self.cancel_ai_fix_btn = ctk.CTkButton(
            btn_frame, text=t("gui.results.cancel_ai_fix"),
            fg_color="gray50",
            command=self._exit_ai_fix_mode)

        # AI Fix mode state
        self._ai_fix_mode = False
        self._ai_fix_running = False

        # Issue cards
        self._issue_cards: List[IssueCard] = []

        # Active toast frames
        self._active_toasts: List[ctk.CTkFrame] = []

    # ══════════════════════════════════════════════════════════════════════
    #  RESULTS logic
    # ══════════════════════════════════════════════════════════════════════

    def _show_issues(self, issues: List[ReviewIssue]):
        self._issues = issues
        for w in self.results_frame.winfo_children():
            w.destroy()
        self._issue_cards.clear()

        if not issues:
            self.results_summary.configure(text=t("gui.results.no_results"))
            self.review_changes_btn.configure(state="disabled")
            self.finalize_btn.configure(state="disabled")
            self.save_session_btn.configure(state="disabled")
            self._filter_bar.grid_remove()
            self.results_severity_bar.grid_remove()
            self.tabs.set(t("gui.tab.results"))
            return

        self.results_summary.configure(
            text=t("gui.results.summary",
                   score="—",
                   issues=len(issues),
                   types=", ".join(set(
                       it for iss in issues
                       for it in (iss.issue_type.split("+")
                                  if "+" in iss.issue_type
                                  else [iss.issue_type])
                   )),
                   backend=self.backend_var.get()))

        sev_order = [("critical", "🔴"), ("high", "🟠"),
                     ("medium", "🟡"), ("low", "🔵"), ("info", "⚪")]
        counts = {sev: sum(1 for iss in issues if iss.severity == sev)
                  for sev, _ in sev_order}
        parts = [
            f"{icon} {sev.capitalize()}: {counts[sev]}"
            for sev, icon in sev_order
            if counts[sev] > 0
        ]
        self.results_severity_bar.configure(text="  ".join(parts))
        self.results_severity_bar.grid()

        self._issues_header = ctk.CTkLabel(
            self.results_frame, text=t("gui.results.issues_section"),
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
        self._issues_header.grid(row=0, column=0, sticky="w", padx=6, pady=(4, 2))

        for i, issue in enumerate(issues):
            self._add_issue_card(i + 1, issue)

        self._fixed_header_row = len(issues) + 2
        self._fixed_header = ctk.CTkLabel(
            self.results_frame, text=t("gui.results.fixed_section"),
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w")

        self._populate_filter_bar(issues)
        self._apply_filters()
        self._update_bottom_buttons()
        self.tabs.set(t("gui.tab.results"))

    def _populate_filter_bar(self, issues: "List[ReviewIssue]") -> None:
        types = sorted({
            itype
            for iss in issues
            for itype in (
                iss.issue_type.split("+") if "+" in iss.issue_type else [iss.issue_type]
            )
        })
        all_types_label = t("gui.results.filter_all_types")
        self._filter_type_menu.configure(values=[all_types_label] + types)
        self._filter_type_var.set(all_types_label)
        self._filter_sev_var.set(t("gui.results.filter_all"))
        self._filter_status_var.set(t("gui.results.filter_all"))
        self._filter_bar.grid()

    def _apply_filters(self) -> None:
        all_label = t("gui.results.filter_all")
        all_types_label = t("gui.results.filter_all_types")
        sev_sel = self._filter_sev_var.get()
        status_sel = self._filter_status_var.get()
        type_sel = self._filter_type_var.get()

        sev_map = {
            "Critical": "critical", "High": "high", "Medium": "medium",
            "Low": "low", "Info": "info",
        }
        status_map = {
            "Pending": "pending", "Resolved": "resolved", "Ignored": "ignored",
            "Skipped": "skipped", "Fixed": "fixed",
            "AI Fixed": "ai_fixed", "Fix Failed": "fix_failed",
        }

        filter_sev = sev_map.get(sev_sel) if sev_sel != all_label else None
        filter_status = status_map.get(status_sel) if status_sel != all_label else None
        filter_type = type_sel if type_sel != all_types_label else None

        visible = 0
        total = len(self._issue_cards)
        for rec in self._issue_cards:
            issue = rec["issue"]
            issue_types = (
                issue.issue_type.split("+") if "+" in issue.issue_type
                else [issue.issue_type]
            )
            match = (
                (filter_sev is None or issue.severity == filter_sev)
                and (filter_status is None or issue.status == filter_status)
                and (filter_type is None or filter_type in issue_types)
            )
            if match:
                rec["card"].grid()
                visible += 1
            else:
                rec["card"].grid_remove()

        if visible < total:
            self._filter_count_lbl.configure(
                text=t("gui.results.filter_count", visible=visible, total=total))
        else:
            self._filter_count_lbl.configure(text="")

    def _clear_filters(self) -> None:
        self._filter_sev_var.set(t("gui.results.filter_all"))
        self._filter_status_var.set(t("gui.results.filter_all"))
        self._filter_type_var.set(t("gui.results.filter_all_types"))
        self._apply_filters()

    # ── Issue card ─────────────────────────────────────────────────────────

    def _add_issue_card(self, index: int, issue: ReviewIssue):
        sev_colors = {
            "critical": "#dc2626", "high": "#ea580c",
            "medium": "#ca8a04", "low": "#2563eb", "info": "#6b7280",
        }
        color = sev_colors.get(issue.severity, "#6b7280")

        card = ctk.CTkFrame(self.results_frame, border_width=1,
                             border_color=color)
        card.grid(row=index, column=0, sticky="ew", padx=4, pady=3)
        card.grid_columnconfigure(1, weight=1)

        header_text = (f"[{issue.severity.upper()}] [{issue.issue_type}] "
                       f"{Path(issue.file_path).name}")
        ctk.CTkLabel(card, text=header_text, text_color=color,
                      font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=6, sticky="w", padx=6, pady=(4, 0))

        _TRUNC = 120
        full_desc = issue.description
        truncated = len(full_desc) > _TRUNC
        desc_text = full_desc[:_TRUNC] + "…" if truncated else full_desc
        desc_lbl = ctk.CTkLabel(card, text=desc_text, anchor="w", wraplength=680)
        desc_lbl.grid(row=1, column=0, columnspan=5, sticky="w", padx=6)

        expand_btn: Any = None
        if truncated:
            _expanded = [False]

            def _toggle_desc(
                lbl=desc_lbl,
                full=full_desc,
                short=desc_text,
                state=_expanded,
            ) -> None:
                if state[0]:
                    lbl.configure(text=short)
                    expand_btn.configure(text=t("gui.results.desc_more"))
                    state[0] = False
                else:
                    lbl.configure(text=full)
                    expand_btn.configure(text=t("gui.results.desc_less"))
                    state[0] = True

            expand_btn = ctk.CTkButton(
                card,
                text=t("gui.results.desc_more"),
                width=70, height=20,
                font=ctk.CTkFont(size=10),
                fg_color="transparent",
                border_width=1,
                text_color=("gray40", "gray70"),
                hover_color=("gray85", "gray25"),
                command=_toggle_desc,
            )
            expand_btn.grid(row=1, column=5, padx=(0, 6), pady=(0, 2), sticky="e")

        s_key, s_color = self._status_display(issue, color)
        status_lbl = ctk.CTkLabel(card, text=t(s_key), text_color=s_color)
        status_lbl.grid(row=2, column=0, sticky="w", padx=6, pady=(0, 4))

        btn_kw = dict(width=65, height=26, font=ctk.CTkFont(size=11))
        view_btn = ctk.CTkButton(
            card, text=t("gui.results.action_view"), **btn_kw,  # type: ignore[reportArgumentType]
            command=lambda iss=issue: self._show_issue_detail(iss),
        )
        view_btn.grid(row=2, column=2, padx=2, pady=(0, 4))

        fix_check_var = ctk.BooleanVar(value=False)
        fix_checkbox = ctk.CTkCheckBox(
            card, text=t("gui.results.select_for_fix"),
            variable=fix_check_var,
            font=ctk.CTkFont(size=11), width=20,
        )

        resolve_btn = ctk.CTkButton(
            card, text=t("gui.results.action_resolve"), **btn_kw,  # type: ignore[reportArgumentType]
            fg_color="green",
            command=lambda idx=len(self._issue_cards):
                self._resolve_issue(idx),
        )
        resolve_btn.grid(row=2, column=4, padx=2, pady=(0, 4))

        skip_btn = ctk.CTkButton(
            card, text=t("gui.results.action_skip"), **btn_kw,  # type: ignore[reportArgumentType]
            fg_color="gray50",
            command=lambda idx=len(self._issue_cards):
                self._toggle_skip(idx),
        )
        skip_btn.grid(row=2, column=5, padx=2, pady=(0, 4))

        skip_frame = ctk.CTkFrame(card, fg_color="transparent")
        skip_entry = ctk.CTkEntry(skip_frame, width=500,
                                   placeholder_text=t("gui.results.skip_reason_ph"))
        skip_entry.grid(row=0, column=0, sticky="ew", padx=(20, 6), pady=4)
        skip_frame.grid_columnconfigure(0, weight=1)

        self._issue_cards.append(IssueCard(
            issue=issue,
            card=card,
            status_lbl=status_lbl,
            desc_lbl=desc_lbl,
            expand_btn=expand_btn,
            view_btn=view_btn,
            resolve_btn=resolve_btn,
            skip_btn=skip_btn,
            fix_checkbox=fix_checkbox,
            fix_check_var=fix_check_var,
            skip_frame=skip_frame,
            skip_entry=skip_entry,
            color=color,
        ))

    @staticmethod
    def _status_display(issue: ReviewIssue, default_color: str):
        m = {
            "resolved":   ("gui.results.resolved", "green"),
            "ignored":    ("gui.results.ignored", "gray50"),
            "skipped":    ("gui.results.skipped", "gray50"),
            "fixed":      ("gui.results.fixed", "green"),
            "ai_fixed":   ("gui.results.ai_fixed", "green"),
            "fix_failed": ("gui.results.fix_failed", "#dc2626"),
        }
        return m.get(issue.status, ("gui.results.pending", default_color))

    def _refresh_status(self, idx: int):
        rec = self._issue_cards[idx]
        s_key, s_color = self._status_display(rec["issue"], rec["color"])
        rec["status_lbl"].configure(text=t(s_key), text_color=s_color)
        self._update_bottom_buttons()
        self._apply_filters()

    def _update_bottom_buttons(self):
        all_done = all(c["issue"].status != "pending" for c in self._issue_cards)
        any_to_check = any(c["issue"].status in ("resolved",) for c in self._issue_cards)
        any_pending = any(c["issue"].status == "pending" for c in self._issue_cards)

        if all_done and any_to_check:
            self.review_changes_btn.configure(state="normal")
        else:
            self.review_changes_btn.configure(state="disabled")

        if all_done:
            self.finalize_btn.configure(state="normal")
            self.save_session_btn.configure(state="normal")
        else:
            self.finalize_btn.configure(state="disabled")
            self.save_session_btn.configure(state="normal")

        if any_pending and (self._review_client or self._testing_mode):
            self.ai_fix_mode_btn.configure(state="normal")
        else:
            self.ai_fix_mode_btn.configure(state="disabled")

    # ── Resolve ────────────────────────────────────────────────────────────

    def _resolve_issue(self, idx: int):
        rec = self._issue_cards[idx]
        issue = rec["issue"]
        editor_cmd = config.get("gui", "editor_command", "").strip()

        if editor_cmd and not self._testing_mode:
            try:
                subprocess.Popen([editor_cmd, issue.file_path])
            except Exception as exc:
                logger.error("Cannot open editor '%s': %s", editor_cmd, exc)
                self._show_toast(str(exc), error=True)
                return
            issue.status = "resolved"
        else:
            self._open_builtin_editor(idx)
            return

        self._refresh_status(idx)

    def _open_builtin_editor(  # noqa: PLR0915
        self,
        idx: int,
        _initial_content: str | None = None,
        _on_save: Any = None,
    ):
        rec = self._issue_cards[idx]
        issue = rec["issue"]
        fname = Path(issue.file_path).name
        file_ext = Path(issue.file_path).suffix.lower()

        # ── mutable state ──────────────────────────────────────────────────
        _find_bar_visible = [False]
        _search_positions: list[str] = []
        _search_idx = [-1]
        _highlight_timer: list[Any] = [None]

        # ── window ─────────────────────────────────────────────────────────
        base_title = t("gui.results.editor_title", file=fname)
        win = ctk.CTkToplevel(self)
        win.title(base_title)
        win.geometry("980x700")
        win.minsize(700, 480)
        win.grab_set()
        win.after(10, lambda w=win: _fix_titlebar(w))

        # ── theme-aware colours ────────────────────────────────────────────
        dark = ctk.get_appearance_mode().lower() == "dark"
        if dark:
            bg        = "#1e1e1e"
            fg        = "#d4d4d4"
            ln_bg     = "#252526"
            ln_fg     = "#858585"
            sel_bg    = "#264f78"
            cur_line  = "#2a2d2e"
            insert_c  = "#aeafad"
            kw_c      = "#569cd6"
            str_c     = "#ce9178"
            cmt_c     = "#6a9955"
            bi_c      = "#4ec9b0"
            num_c     = "#b5cea8"
            dec_c     = "#dcdcaa"
        else:
            bg        = "#ffffff"
            fg        = "#1f1f1f"
            ln_bg     = "#f3f3f3"
            ln_fg     = "#888888"
            sel_bg    = "#add6ff"
            cur_line  = "#f0f8ff"
            insert_c  = "#000000"
            kw_c      = "#0000ff"
            str_c     = "#a31515"
            cmt_c     = "#008000"
            bi_c      = "#267f99"
            num_c     = "#098658"
            dec_c     = "#795e26"

        # ── feedback label ─────────────────────────────────────────────────
        fb_frame = ctk.CTkFrame(win, fg_color=("gray88", "gray17"),
                                corner_radius=6)
        fb_frame.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(
            fb_frame,
            text=f"⚠  {issue.ai_feedback[:260]}",
            wraplength=900, anchor="w", justify="left",
            text_color=("gray30", "gray65"),
            font=ctk.CTkFont(size=11),
        ).pack(padx=10, pady=6, anchor="w")

        # ── editor area ────────────────────────────────────────────────────
        editor_outer = tk.Frame(win, bd=0, highlightthickness=0)
        editor_outer.pack(fill="both", expand=True, padx=10, pady=(6, 0))
        # Use grid so scrollbars can be removed/restored without breaking layout
        editor_outer.configure(bg=ln_bg)  # prevent white flash in corner gaps
        editor_outer.columnconfigure(2, weight=1)
        editor_outer.rowconfigure(0, weight=1)

        # Create CTkScrollbar instances (styled with theme colors)
        vscroll = ctk.CTkScrollbar(
            editor_outer,
            orientation="vertical",
            border_spacing=0,
            fg_color=("gray90", "gray17"),
            button_color=("gray70", "gray30"),
            button_hover_color=("gray60", "gray40"),
        )
        vscroll.grid(row=0, column=3, sticky="ns")

        hscroll = ctk.CTkScrollbar(
            editor_outer,
            orientation="horizontal",
            border_spacing=0,
            fg_color=("gray90", "gray17"),
            button_color=("gray70", "gray30"),
            button_hover_color=("gray60", "gray40"),
        )
        hscroll.grid(row=1, column=2, sticky="ew")

        # line-numbers pane
        ln_pane = tk.Text(
            editor_outer, width=5, padx=6, takefocus=0,
            bg=ln_bg, fg=ln_fg, bd=0, highlightthickness=0,
            selectbackground=ln_bg, selectforeground=ln_fg,
            state="disabled", wrap="none", cursor="arrow",
            font=("Consolas", 13),
        )
        ln_pane.grid(row=0, column=0, rowspan=2, sticky="ns")

        # thin separator between line-nums and code
        sep = tk.Frame(editor_outer, width=1,
                       bg="#3c3c3c" if dark else "#d0d0d0")
        sep.grid(row=0, column=1, rowspan=2, sticky="ns")

        # Auto-hide callbacks: use actual scroll fractions (lo=0, hi=1 → fits)
        def _autohide_vscroll(*args: Any) -> None:
            vscroll.set(*args)
            lo, hi = float(args[0]), float(args[1])
            if lo <= 0.0 and hi >= 1.0:
                vscroll.grid_remove()
            else:
                vscroll.grid()
            _update_ln()

        def _autohide_hscroll(*args: Any) -> None:
            hscroll.set(*args)
            lo, hi = float(args[0]), float(args[1])
            if lo <= 0.0 and hi >= 1.0:
                hscroll.grid_remove()
            else:
                hscroll.grid()

        # main editor
        text = tk.Text(
            editor_outer,
            bg=bg, fg=fg, bd=0, highlightthickness=0,
            insertbackground=insert_c,
            selectbackground=sel_bg,
            wrap="none",
            font=("Consolas", 13),
            undo=True, autoseparators=True, maxundo=-1,
            tabs=("4c",),
            yscrollcommand=_autohide_vscroll,
            xscrollcommand=_autohide_hscroll,
            padx=10, pady=4,
            spacing1=1, spacing3=2,
        )
        text.grid(row=0, column=2, sticky="nsew")
        vscroll.configure(command=lambda *a: (text.yview(*a), _update_ln()))
        hscroll.configure(command=text.xview)

        # ── syntax-highlight tags ──────────────────────────────────────────
        _TAGS = {
            "keyword":    {"foreground": kw_c,  "font": ("Consolas", 13, "bold")},
            "string":     {"foreground": str_c},
            "comment":    {"foreground": cmt_c, "font": ("Consolas", 13, "italic")},
            "builtin":    {"foreground": bi_c},
            "number":     {"foreground": num_c},
            "decorator":  {"foreground": dec_c},
            "cur_line":   {"background": cur_line},
            "find_match": {"background": "#f8c112", "foreground": "#000000"},
            "find_cur":   {"background": "#ff8c00", "foreground": "#000000"},
        }
        for tag, opts in _TAGS.items():
            text.tag_configure(tag, **opts)
        # keep cur_line below syntax tags
        text.tag_lower("cur_line")

        _KW = frozenset({
            "False", "None", "True", "and", "as", "assert", "async", "await",
            "break", "class", "continue", "def", "del", "elif", "else",
            "except", "finally", "for", "from", "global", "if", "import",
            "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise",
            "return", "try", "while", "with", "yield",
        })
        _BI = frozenset({
            "print", "len", "range", "int", "str", "list", "dict", "set",
            "tuple", "bool", "float", "type", "isinstance", "hasattr",
            "getattr", "setattr", "super", "zip", "map", "filter",
            "enumerate", "sorted", "reversed", "open", "input", "abs",
            "min", "max", "sum", "any", "all", "id", "hash", "repr",
            "format", "object", "property", "staticmethod", "classmethod",
            "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
            "AttributeError", "RuntimeError", "StopIteration", "OSError",
        })

        def _highlight_python() -> None:
            for tag in ("keyword", "string", "comment", "builtin",
                        "number", "decorator"):
                text.tag_remove(tag, "1.0", "end")
            import io
            import token as _t
            import tokenize as _tok
            src = text.get("1.0", "end")
            try:
                toks = list(_tok.generate_tokens(io.StringIO(src).readline))
            except _tok.TokenError:
                toks = []
            for kind, val, (r1, c1), (r2, c2), _ in toks:
                s, e = f"{r1}.{c1}", f"{r2}.{c2}"
                if kind == _t.NAME:
                    if val in _KW:
                        text.tag_add("keyword", s, e)
                    elif val in _BI:
                        text.tag_add("builtin", s, e)
                elif kind == _t.STRING:
                    text.tag_add("string", s, e)
                elif kind == _t.COMMENT:
                    text.tag_add("comment", s, e)
                elif kind == _t.NUMBER:
                    text.tag_add("number", s, e)
            # decorators via regex
            import re as _re
            for m in _re.finditer(r"^[ \t]*(@\w+)", src, _re.MULTILINE):
                ln = src[: m.start()].count("\n") + 1
                col = m.start() - src.rfind("\n", 0, m.start()) - 1
                text.tag_add("decorator",
                             f"{ln}.{col}", f"{ln}.{col + len(m.group(1))}")

        def _schedule_highlight(*_a: Any) -> None:
            if _highlight_timer[0]:
                win.after_cancel(_highlight_timer[0])
            _highlight_timer[0] = win.after(
                260, _highlight_python if file_ext == ".py" else lambda: None
            )

        # ── line-number updater ────────────────────────────────────────────
        def _update_ln(*_a: Any) -> None:
            try:
                first = int(text.index("@0,0").split(".")[0])
                last  = int(text.index(f"@0,{text.winfo_height()}").split(".")[0])
                total = int(text.index("end-1c").split(".")[0])
                ln_pane.configure(state="normal")
                ln_pane.delete("1.0", "end")
                ln_pane.insert("end", "\n".join(
                    f"{n:>4}" for n in range(first, min(last + 3, total + 1))
                ))
                ln_pane.configure(state="disabled")
            except Exception:
                pass

        # ── current-line highlight ─────────────────────────────────────────
        def _update_cur_line(*_a: Any) -> None:
            text.tag_remove("cur_line", "1.0", "end")
            row = text.index("insert").split(".")[0]
            text.tag_add("cur_line", f"{row}.0", f"{row}.end+1c")
            text.tag_lower("cur_line")
            _update_status()

        # ── status bar ─────────────────────────────────────────────────────
        sb = ctk.CTkFrame(win, fg_color=("gray80", "gray22"),
                          height=24, corner_radius=0)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)

        pos_lbl = ctk.CTkLabel(sb, text="Ln 1, Col 1",
                               font=ctk.CTkFont(size=11), anchor="w")
        pos_lbl.pack(side="left", padx=8)

        ctk.CTkLabel(
            sb,
            text="Ctrl+S  Save    Ctrl+F  Find    Ctrl+Z  Undo",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
            anchor="e",
        ).pack(side="right", padx=10)

        lang_lbl = ctk.CTkLabel(
            sb,
            text=(file_ext.lstrip(".").upper() or "TEXT"),
            font=ctk.CTkFont(size=11), anchor="e",
        )
        lang_lbl.pack(side="right", padx=10)

        def _update_status(*_a: Any) -> None:
            try:
                r, c = text.index("insert").split(".")
                pos_lbl.configure(text=f"Ln {r}, Col {int(c) + 1}")
            except Exception:
                pass

        # ── find bar (hidden until Ctrl+F) ─────────────────────────────────
        find_frame = ctk.CTkFrame(win, fg_color=("gray85", "gray22"),
                                  corner_radius=0)
        find_var = tk.StringVar()
        find_case = tk.BooleanVar(value=False)

        ctk.CTkLabel(find_frame, text="Find:",
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(8, 2))
        find_entry = ctk.CTkEntry(find_frame, textvariable=find_var,
                                  width=220, font=ctk.CTkFont(size=12))
        find_entry.pack(side="left", padx=4)
        ctk.CTkCheckBox(find_frame, text="Aa", variable=find_case,
                        font=ctk.CTkFont(size=11),
                        width=50, checkbox_width=16, checkbox_height=16,
                        ).pack(side="left", padx=(2, 6))

        find_count_lbl = ctk.CTkLabel(find_frame, text="",
                                      font=ctk.CTkFont(size=11),
                                      text_color=("gray50", "gray55"))
        find_count_lbl.pack(side="left", padx=4)

        def _do_find(direction: int = 1) -> None:
            text.tag_remove("find_match", "1.0", "end")
            text.tag_remove("find_cur",   "1.0", "end")
            query = find_var.get()
            if not query:
                find_count_lbl.configure(text="")
                return
            _search_positions.clear()
            pos = "1.0"
            nocase = not find_case.get()
            while True:
                pos = text.search(query, pos, stopindex="end", nocase=nocase)
                if not pos:
                    break
                end = f"{pos}+{len(query)}c"
                text.tag_add("find_match", pos, end)
                _search_positions.append(pos)
                pos = end
            if not _search_positions:
                find_count_lbl.configure(text="No results")
                find_entry.configure(border_color="red")
                return
            find_entry.configure(border_color=("gray50", "gray50"))
            _search_idx[0] = (_search_idx[0] + direction) % len(_search_positions)
            cur = _search_positions[_search_idx[0]]
            text.tag_remove("find_match", cur, f"{cur}+{len(query)}c")
            text.tag_add("find_cur", cur, f"{cur}+{len(query)}c")
            text.see(cur)
            text.mark_set("insert", cur)
            find_count_lbl.configure(
                text=f"{_search_idx[0] + 1} / {len(_search_positions)}")

        ctk.CTkButton(find_frame, text="▲", width=32,
                      command=lambda: _do_find(-1)).pack(side="left", padx=2)
        ctk.CTkButton(find_frame, text="▼", width=32,
                      command=lambda: _do_find(1)).pack(side="left", padx=2)
        ctk.CTkButton(find_frame, text="✕", width=28, fg_color="transparent",
                      hover_color=("gray70", "gray30"),
                      command=lambda: _toggle_find()).pack(side="right", padx=4)

        find_var.trace_add("write", lambda *_: (_search_idx.__setitem__(0, -1),
                                                _do_find(1) if find_var.get() else
                                                find_count_lbl.configure(text="")))
        find_entry.bind("<Return>",  lambda e: _do_find(1))
        find_entry.bind("<Shift-Return>", lambda e: _do_find(-1))

        def _toggle_find(*_a: Any) -> None:
            if _find_bar_visible[0]:
                find_frame.pack_forget()
                _find_bar_visible[0] = False
                text.focus_set()
            else:
                find_frame.pack(fill="x", side="bottom", before=sb)
                _find_bar_visible[0] = True
                find_entry.focus_set()
                try:
                    sel = text.get("sel.first", "sel.last")
                    if sel and "\n" not in sel:
                        find_var.set(sel)
                        _search_idx[0] = -1
                        _do_find(1)
                except tk.TclError:
                    pass

        # ── load content ───────────────────────────────────────────────────
        if _initial_content is not None:
            raw = _initial_content
        elif self._testing_mode:
            raw = issue.code_snippet or "(no code snippet)"
        else:
            try:
                with open(issue.file_path, "r", encoding="utf-8",
                          errors="replace") as fh:
                    raw = fh.read()
            except Exception as exc:
                raw = f"Error reading file: {exc}"

        text.insert("1.0", raw)
        original_ref = [raw]

        # initial highlighting + line numbers
        if file_ext == ".py":
            _highlight_python()
        _update_ln()
        _update_cur_line()

        # scroll to reported line if known
        if not self._testing_mode and issue.line_number:
            try:
                text.see(f"{issue.line_number}.0")
                text.mark_set("insert", f"{issue.line_number}.0")
                _update_cur_line()
            except Exception:
                pass

        # ── event bindings ─────────────────────────────────────────────────
        def _on_key(*_a: Any) -> None:
            cur = text.get("1.0", "end-1c")
            title_mark = "● " if cur != original_ref[0] else ""
            win.title(f"{title_mark}{base_title}")
            _update_ln()
            _update_cur_line()
            _schedule_highlight()

        text.bind("<KeyRelease>",     _on_key)
        text.bind("<ButtonRelease-1>", _update_cur_line)
        text.bind("<Configure>",       _update_ln)
        text.bind("<MouseWheel>",
                  lambda e: win.after(10, _update_ln))

        # Tab → 4 spaces
        text.bind("<Tab>",
                  lambda e: (text.insert("insert", "    "), "break")[1])

        # ── buttons ────────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=8, side="bottom")

        def _save() -> None:
            content_out = text.get("1.0", "end").rstrip("\n") + "\n"
            if _on_save is not None:
                _on_save(content_out)
                win.destroy()
                return
            if self._testing_mode:
                issue.status = "resolved"
                self._refresh_status(idx)
                self._show_toast(t("gui.results.editor_saved"))
                win.destroy()
                return
            try:
                with open(issue.file_path, "w", encoding="utf-8") as fh:
                    fh.write(content_out)
                issue.status = "resolved"
                self._refresh_status(idx)
                self._show_toast(t("gui.results.editor_saved"))
            except Exception as exc:
                self._show_toast(str(exc), error=True)
            win.destroy()

        def _cancel() -> None:
            if text.get("1.0", "end-1c") != original_ref[0]:
                if not ConfirmDialog(
                    win,
                    title=t("gui.results.editor_discard_title"),
                    message=t("gui.results.editor_discard_msg"),
                ).confirmed:
                    return
            win.destroy()

        ctk.CTkButton(btn_frame, text=t("gui.results.editor_save"),
                      fg_color="green", hover_color="#1a7a1a",
                      width=160, command=_save).grid(row=0, column=0, padx=6)
        ctk.CTkButton(btn_frame, text=t("common.cancel"),
                      width=100, command=_cancel).grid(row=0, column=1, padx=6)

        # ── keyboard shortcuts ─────────────────────────────────────────────
        win.bind("<Control-s>", lambda e: _save())
        win.bind("<Control-S>", lambda e: _save())
        win.bind("<Control-f>", lambda e: _toggle_find())
        win.bind("<Control-F>", lambda e: _toggle_find())
        win.bind("<Escape>",
                 lambda e: (_toggle_find() if _find_bar_visible[0]
                             else _cancel()))
        win.bind("<Control-w>", lambda e: _cancel())
        win.protocol("WM_DELETE_WINDOW", _cancel)

        text.focus_set()

    # ── Skip ───────────────────────────────────────────────────────────────

    def _toggle_skip(self, idx: int):
        rec = self._issue_cards[idx]
        issue = rec["issue"]

        if issue.status == "skipped":
            issue.status = "pending"
            issue.resolution_reason = None
            rec["skip_frame"].grid_remove()
        else:
            issue.status = "skipped"
            rec["skip_frame"].grid(row=3, column=0, columnspan=6, sticky="ew")
            def _on_reason_change(*_a, _entry=rec["skip_entry"], _iss=issue):
                _iss.resolution_reason = _entry.get().strip() or None
            rec["skip_entry"].bind("<KeyRelease>", _on_reason_change)

        self._refresh_status(idx)

    # ── AI Fix Mode ──────────────────────────────────────────────────────

    def _enter_ai_fix_mode(self):
        if self._ai_fix_mode:
            return
        self._ai_fix_mode = True

        self.ai_fix_mode_btn.grid_remove()
        self.review_changes_btn.grid_remove()
        self.finalize_btn.grid_remove()
        self.start_ai_fix_btn.grid(row=0, column=0, padx=6)
        self.cancel_ai_fix_btn.grid(row=0, column=1, padx=6)

        self._set_action_buttons_state("disabled")

        for rec in self._issue_cards:
            if rec["issue"].status == "pending":
                rec["view_btn"].grid_remove()
                rec["resolve_btn"].grid_remove()
                rec["skip_btn"].grid_remove()
                rec["fix_check_var"].set(True)
                rec["fix_checkbox"].grid(row=2, column=2, columnspan=3,
                                          padx=4, pady=(0, 4), sticky="w")

    def _exit_ai_fix_mode(self):
        if self._ai_fix_running:
            if hasattr(self, '_ai_fix_cancel_event') and not self._ai_fix_cancel_event.is_set():
                self._ai_fix_cancel_event.set()
                logger.info("Cancelling AI Fix run...")
                self.cancel_ai_fix_btn.configure(state="disabled", text=t("gui.results.cancelling_ai_fix"))
                self.status_var.set(t("gui.results.cancelling_status"))
            return

        self._ai_fix_mode = False

        self.start_ai_fix_btn.grid_remove()
        self.cancel_ai_fix_btn.grid_remove()
        self.ai_fix_mode_btn.grid(row=0, column=0, padx=6)
        self.review_changes_btn.grid(row=0, column=1, padx=6)
        self.finalize_btn.grid(row=0, column=2, padx=6)

        self._set_action_buttons_state("normal")

        for rec in self._issue_cards:
            rec["fix_checkbox"].grid_remove()
            rec["fix_check_var"].set(False)
            s_key, s_color = self._status_display(rec["issue"], rec["color"])
            rec["status_lbl"].configure(text=t(s_key), text_color=s_color)
            rec["view_btn"].grid(row=2, column=2, padx=2, pady=(0, 4))
            if rec["issue"].status == "pending":
                rec["resolve_btn"].grid(row=2, column=4, padx=2, pady=(0, 4))
                rec["skip_btn"].grid(row=2, column=5, padx=2, pady=(0, 4))
            else:
                rec["resolve_btn"].grid_remove()
                rec["skip_btn"].grid_remove()

        self._update_bottom_buttons()

    def _start_batch_ai_fix(self):
        selected = [
            (i, rec) for i, rec in enumerate(self._issue_cards)
            if rec["fix_check_var"].get() and rec["issue"].status == "pending"
        ]
        if not selected:
            self._show_toast(t("gui.results.no_issues_selected"), error=True)
            return

        if not self._review_client:
            if self._testing_mode:
                fake_results: dict[int, str | None] = {}
                for idx, rec in selected:
                    issue = rec["issue"]
                    original = issue.code_snippet or (
                        f"# {Path(issue.file_path).name}\n# (no snippet available)\n"
                    )
                    fake_results[idx] = (
                        f"# Simulated AI fix\n"
                        f"# Issue: {issue.description[:80]}\n\n"
                    ) + original
                self._show_batch_fix_popup(selected, fake_results)
                return
            self._show_toast(t("gui.results.no_fix"), error=True)
            return

        self._ai_fix_cancel_event = threading.Event()
        self._ai_fix_running = True
        self.start_ai_fix_btn.configure(state="disabled")

        logger.info("Starting batch AI Fix for %d issues…", len(selected))
        self.status_var.set(t("gui.results.batch_fix_running",
                              count=len(selected)))

        for i, rec in selected:
            rec["status_lbl"].configure(
                text=t("gui.results.applying_fix"), text_color="#7c3aed")

        def _worker():
            try:
                results = {}
                cancelled = False
                for idx, rec in selected:
                    if self._ai_fix_cancel_event.is_set():
                        logger.info("AI Fix cancelled by user")
                        cancelled = True
                        break
                    issue = rec["issue"]
                    try:
                        code = ""
                        try:
                            with open(issue.file_path, "r", encoding="utf-8") as fh:
                                code = fh.read()
                        except Exception:
                            pass
                        logger.info("  AI Fix: %s …", issue.file_path)
                        if self._review_client is None:
                            continue
                        fix = self._review_client.get_fix(
                            code_content=code,
                            issue_feedback=issue.ai_feedback or issue.description,
                            review_type=issue.issue_type,
                            lang=self.lang_var.get(),
                        )
                        if self._ai_fix_cancel_event.is_set():
                            logger.info("AI Fix cancelled by user")
                            cancelled = True
                            break
                        if fix and not fix.startswith("Error:"):
                            results[idx] = fix.strip()
                            logger.info("    → fix generated")
                        else:
                            results[idx] = None
                            logger.warning("    → no fix returned")
                    except Exception as exc:
                        logger.error("  AI Fix error for %s: %s",
                                     issue.file_path, exc)
                        results[idx] = None
                        if self._ai_fix_cancel_event.is_set():
                            logger.info("AI Fix cancelled by user")
                            cancelled = True
                            break
                if cancelled:
                    self.after(0, lambda: self._on_ai_fix_cancelled(selected))
                else:
                    self.after(0, lambda: self._show_batch_fix_popup(
                        selected, results))
            finally:
                self._ai_fix_running = False

        threading.Thread(target=_worker, daemon=True).start()

    def _on_ai_fix_cancelled(self, selected):
        logger.info("AI Fix operation cancelled.")
        self.status_var.set(t("common.ready"))
        for idx, rec in selected:
            s_key, s_color = self._status_display(rec["issue"], rec["color"])
            rec["status_lbl"].configure(text=t(s_key), text_color=s_color)
        self.start_ai_fix_btn.configure(state="normal")
        self.cancel_ai_fix_btn.configure(state="normal", text=t("gui.results.cancel_ai_fix"))
        self._ai_fix_running = False

    def _show_batch_fix_popup(self, selected, results):
        success_count = sum(1 for v in results.values() if v)
        fail_count = len(results) - success_count

        if success_count == 0:
            for idx, rec in selected:
                s_key, s_color = self._status_display(
                    rec["issue"], rec["color"])
                rec["status_lbl"].configure(text=t(s_key),
                                             text_color=s_color)
            self._show_toast(t("gui.results.no_fix"), error=True)
            self.start_ai_fix_btn.configure(state="normal")
            self.cancel_ai_fix_btn.configure(state="normal", text=t("gui.results.cancel_ai_fix"))
            self._ai_fix_running = False
            logger.info("Batch AI Fix: no fixes generated.")
            self.status_var.set(t("common.ready"))
            return

        logger.info("Batch AI Fix: %d/%d fixes generated.",
                     success_count, len(results))

        self.cancel_ai_fix_btn.configure(state="normal", text=t("gui.results.cancel_ai_fix"))

        win = ctk.CTkToplevel(self)
        win.title(t("gui.results.batch_fix_title",
                     count=success_count))
        win.bind("<Control-w>", lambda e: win.destroy())
        win.geometry("950x650")
        win.grab_set()
        win.after(10, lambda w=win: _fix_titlebar(w))

        ctk.CTkLabel(
            win,
            text=t("gui.results.batch_fix_summary",
                    success=success_count, failed=fail_count),
            font=ctk.CTkFont(weight="bold"),
        ).pack(padx=10, pady=(10, 4))

        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=10, pady=4)
        scroll.grid_columnconfigure(0, weight=1)

        fix_checks = {}
        row_num = 0
        for idx, rec in selected:
            fix_text = results.get(idx)
            issue = rec["issue"]
            fname = Path(issue.file_path).name

            if fix_text:
                var = ctk.BooleanVar(value=True)
                fix_checks[idx] = (var, fix_text)

                frame = ctk.CTkFrame(scroll, border_width=1,
                                      border_color="#7c3aed")
                frame.grid(row=row_num, column=0, sticky="ew",
                           padx=4, pady=3)
                frame.grid_columnconfigure(1, weight=1)

                ctk.CTkCheckBox(
                    frame, text=fname, variable=var,
                    font=ctk.CTkFont(weight="bold"),
                ).grid(row=0, column=0, sticky="w", padx=6, pady=(4, 0))

                preview_btn = ctk.CTkButton(
                    frame, text=t("gui.results.preview_changes"),
                    width=100, height=24, font=ctk.CTkFont(size=11),
                    fg_color="#2563eb",
                    command=lambda fp=issue.file_path, ft=fix_text, fn=fname, ix=idx:
                        self._show_diff_preview(fp, ft, fn, ix),
                )
                preview_btn.grid(row=0, column=1, sticky="e", padx=6, pady=(4, 0))

                desc = (issue.description or issue.ai_feedback or "")[:100]
                ctk.CTkLabel(frame, text=desc, anchor="w",
                              wraplength=700,
                              text_color=("gray40", "gray60"),
                              font=ctk.CTkFont(size=11)).grid(
                    row=1, column=0, columnspan=2, sticky="w",
                    padx=6, pady=(0, 4))
            else:
                frame = ctk.CTkFrame(scroll, border_width=1,
                                      border_color="#dc2626")
                frame.grid(row=row_num, column=0, sticky="ew",
                           padx=4, pady=3)
                ctk.CTkLabel(
                    frame, text=f"✗ {fname} — {t('gui.results.no_fix')}",
                    text_color="#dc2626",
                ).grid(row=0, column=0, sticky="w", padx=6, pady=4)

            row_num += 1

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=8)

        def _apply_selected():
            applied = 0
            for idx, (var, fix_text) in fix_checks.items():
                if not var.get():
                    continue
                rec = self._issue_cards[idx]
                issue = rec["issue"]
                if self._testing_mode:
                    issue.status = "resolved"
                    issue.ai_fix_applied = fix_text
                    applied += 1
                    logger.info("Applied AI fix (simulated): %s", issue.file_path)
                else:
                    try:
                        with open(issue.file_path, "w", encoding="utf-8") as fh:
                            fh.write(fix_text)
                        issue.status = "resolved"
                        issue.ai_fix_applied = fix_text
                        applied += 1
                        logger.info("Applied AI fix: %s", issue.file_path)
                    except Exception as exc:
                        logger.error("Failed to apply fix to %s: %s",
                                     issue.file_path, exc)
                        self._show_toast(str(exc), error=True)
                self._refresh_status(idx)
            win.destroy()
            self._ai_fix_running = False
            self._exit_ai_fix_mode()
            self._show_toast(t("gui.results.batch_fix_applied",
                               count=applied))
            logger.info("Batch AI Fix: %d fixes applied.", applied)
            self.status_var.set(t("common.ready"))

        def _cancel():
            win.destroy()
            for idx, rec in selected:
                s_key, s_color = self._status_display(
                    rec["issue"], rec["color"])
                rec["status_lbl"].configure(text=t(s_key),
                                             text_color=s_color)
            self.start_ai_fix_btn.configure(state="normal")
            self._ai_fix_running = False
            self.status_var.set(t("common.ready"))

        ctk.CTkButton(btn_frame, text=t("gui.results.apply_fixes"),
                       fg_color="green",
                       command=_apply_selected).grid(
            row=0, column=0, padx=6)
        ctk.CTkButton(btn_frame, text=t("common.cancel"),
                       command=_cancel).grid(row=0, column=1, padx=6)

    def _show_diff_preview(self, file_path: str, new_content: str, filename: str, idx: int = 0):
        if self._testing_mode:
            original_content = ""
            for rec in self._issue_cards:
                if rec["issue"].file_path == file_path:
                    original_content = rec["issue"].code_snippet or ""
                    break
        else:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                    original_content = fh.read()
            except Exception as exc:
                original_content = f"(Error reading file: {exc})"

        win = ctk.CTkToplevel(self)
        win.title(t("gui.results.diff_preview_title", file=filename))
        win.geometry("1100x700")
        win.grab_set()
        win.after(10, lambda w=win: _fix_titlebar(w))
        win.bind("<Control-w>", lambda e: win.destroy())

        ctk.CTkLabel(
            win, text=t("gui.results.diff_preview_header", file=filename),
            font=ctk.CTkFont(weight="bold", size=14),
        ).pack(padx=10, pady=(10, 4))

        is_dark = ctk.get_appearance_mode().lower() == "dark"
        bg_color = "#1e1e1e" if is_dark else "#ffffff"
        fg_color = "#d4d4d4" if is_dark else "#1e1e1e"
        hdr_bg   = "#252526" if is_dark else "#f0f0f0"
        hdr_fg   = "#cccccc" if is_dark else "#444444"
        sash_col = "#555555" if is_dark else "#bbbbbb"

        orig_lines_list = original_content.splitlines()
        new_lines_list  = new_content.splitlines()

        matcher = difflib.SequenceMatcher(None, orig_lines_list, new_lines_list, autojunk=False)
        left_lines:  list = []
        right_lines: list = []
        left_tags:   list = []
        right_tags:  list = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    left_lines.append(orig_lines_list[i1 + k])
                    right_lines.append(new_lines_list[j1 + k])
                    left_tags.append("ctx")
                    right_tags.append("ctx")
            elif tag == "replace":
                lb = orig_lines_list[i1:i2]
                rb = new_lines_list[j1:j2]
                for k in range(max(len(lb), len(rb))):
                    left_lines.append(lb[k] if k < len(lb) else "")
                    right_lines.append(rb[k] if k < len(rb) else "")
                    left_tags.append("rem" if k < len(lb) else "pad")
                    right_tags.append("add" if k < len(rb) else "pad")
            elif tag == "delete":
                for k in range(i2 - i1):
                    left_lines.append(orig_lines_list[i1 + k])
                    right_lines.append("")
                    left_tags.append("rem")
                    right_tags.append("pad")
            elif tag == "insert":
                for k in range(j2 - j1):
                    left_lines.append("")
                    right_lines.append(new_lines_list[j1 + k])
                    left_tags.append("pad")
                    right_tags.append("add")

        rem_bg = "#4b1010" if is_dark else "#ffcccc"
        rem_fg = "#ff6b6b" if is_dark else "#8b0000"
        add_bg = "#1e4620" if is_dark else "#ccffcc"
        add_fg = "#57d15b" if is_dark else "#006400"
        pad_bg = "#2a2a2a" if is_dark else "#efefef"

        # ── content area: outer_row holds vsb + PanedWindow ───────────────
        outer_row = tk.Frame(win, bg=bg_color)
        outer_row.pack(fill="both", expand=True, padx=10, pady=4)

        vsb = ctk.CTkScrollbar(outer_row, orientation="vertical")
        vsb.pack(side="right", fill="y")
        _vsb_visible = [True]

        paned = tk.PanedWindow(
            outer_row, orient="horizontal",
            bg=sash_col, sashwidth=6,
            sashcursor="sb_h_double_arrow",
            bd=0, opaqueresize=True,
        )
        paned.pack(fill="both", expand=True)

        _syncing: list = [False]
        _all_texts: list[tk.Text] = []

        def _on_vsb(*args: Any) -> None:
            for tw in _all_texts:
                tw.yview(*args)

        vsb.configure(command=_on_vsb)

        def _sync_yscroll(source: tk.Text, first: str, last: str) -> None:
            if float(first) <= 0.0 and float(last) >= 1.0:
                if _vsb_visible[0]:
                    vsb.pack_forget()
                    _vsb_visible[0] = False
            else:
                if not _vsb_visible[0]:
                    vsb.pack(side="right", fill="y")
                    _vsb_visible[0] = True
            vsb.set(first, last)
            if not _syncing[0]:
                _syncing[0] = True
                for tw in _all_texts:
                    if tw is not source:
                        tw.yview("moveto", first)
                _syncing[0] = False

        def _make_diff_pane(header: str) -> tk.Text:
            frame = tk.Frame(paned, bg=bg_color)
            frame.rowconfigure(1, weight=1)
            frame.columnconfigure(0, weight=1)
            paned.add(frame, stretch="always", minsize=150)

            tk.Label(
                frame, text=header,
                bg=hdr_bg, fg=hdr_fg,
                font=("Consolas", 10, "bold"),
                anchor="w", padx=8, pady=3,
            ).grid(row=0, column=0, sticky="ew")

            txt = tk.Text(
                frame, wrap="none",
                font=("Consolas", 11),
                bg=bg_color, fg=fg_color,
                insertbackground=fg_color,
                selectbackground="#264f78",
                relief="flat", borderwidth=0,
                exportselection=False,
            )
            txt.grid(row=1, column=0, sticky="nsew")
            txt.tag_configure("rem", background=rem_bg, foreground=rem_fg)
            txt.tag_configure("add", background=add_bg, foreground=add_fg)
            txt.tag_configure("pad", background=pad_bg)

            hsb = ctk.CTkScrollbar(frame, orientation="horizontal", command=txt.xview)
            hsb.grid(row=2, column=0, sticky="ew")

            def _xscroll(first: str, last: str, _h: Any = hsb) -> None:
                if float(first) <= 0.0 and float(last) >= 1.0:
                    _h.grid_remove()
                else:
                    _h.grid()
                _h.set(first, last)

            txt.configure(xscrollcommand=_xscroll)
            _all_texts.append(txt)
            return txt

        left_text  = _make_diff_pane("  ─  original")
        right_text = _make_diff_pane("  +  ai fixed")

        left_text.configure(
            yscrollcommand=lambda f, l: _sync_yscroll(left_text, f, l))
        right_text.configure(
            yscrollcommand=lambda f, l: _sync_yscroll(right_text, f, l))

        # populate diff
        if left_lines:
            for ll, rl, lt, rt in zip(left_lines, right_lines, left_tags, right_tags):
                left_text.insert("end",  ll + "\n", () if lt == "ctx" else lt)
                right_text.insert("end", rl + "\n", () if rt == "ctx" else rt)
        else:
            left_text.insert("end",  t("gui.results.no_changes"))
            right_text.insert("end", t("gui.results.no_changes"))

        left_text.configure(state="disabled")
        right_text.configure(state="disabled")

        # ── user-edit pane state ──────────────────────────────────────────
        user_text_ref:    list[tk.Text | None]  = [None]
        user_frame_ref:   list[tk.Frame | None] = [None]
        undo_btn_ref:     list[Any]             = [None]
        close_btn_ref:    list[Any]             = [None]
        user_content_ref: list[str]             = [""]

        def _populate_user_pane(user_content: str) -> None:
            utxt = user_text_ref[0]
            if utxt is None:
                return
            utxt.configure(state="normal")
            utxt.delete("1.0", "end")
            ai_lines  = new_content.splitlines()
            usr_lines = user_content.splitlines()
            m2 = difflib.SequenceMatcher(None, ai_lines, usr_lines, autojunk=False)
            for op, i1, i2, j1, j2 in m2.get_opcodes():
                if op == "equal":
                    for line in usr_lines[j1:j2]:
                        utxt.insert("end", line + "\n")
                elif op in ("replace", "insert"):
                    lb2 = ai_lines[i1:i2]
                    rb2 = usr_lines[j1:j2]
                    for k in range(max(len(lb2), len(rb2))):
                        line = rb2[k] if k < len(rb2) else ""
                        tag2 = "add" if k < len(rb2) else "pad"
                        utxt.insert("end", line + "\n", tag2)
                elif op == "delete":
                    for _ in ai_lines[i1:i2]:
                        utxt.insert("end", "\n", "pad")
            utxt.configure(state="disabled")

        def _undo_user_changes() -> None:
            if user_frame_ref[0] is not None:
                if user_text_ref[0] in _all_texts:
                    _all_texts.remove(user_text_ref[0])
                paned.remove(user_frame_ref[0])
                user_frame_ref[0] = None
                user_text_ref[0]  = None
            if undo_btn_ref[0] is not None:
                undo_btn_ref[0].grid_remove()
                undo_btn_ref[0] = None
            # Restore Close button
            if close_btn_ref[0] is not None:
                close_btn_ref[0].configure(
                    text=t("common.close"),
                    fg_color=("#3b3b3b", "#565b5e"),
                    hover_color=("gray70", "gray30"),
                    command=win.destroy,
                )

        def _save_and_close() -> None:
            content = user_content_ref[0]
            if not content:
                win.destroy()
                return
            try:
                out = content if content.endswith("\n") else content + "\n"
                with open(file_path, "w", encoding="utf-8") as fh:
                    fh.write(out)
                if idx < len(self._issue_cards):
                    self._issue_cards[idx]["issue"].status = "resolved"
                    self._refresh_status(idx)
                self._show_toast(t("gui.results.editor_saved"))
            except Exception as exc:
                self._show_toast(str(exc), error=True)
                return
            win.destroy()

        def _on_user_save(user_content: str) -> None:
            user_content_ref[0] = user_content
            if user_content.rstrip("\n") == new_content.rstrip("\n"):
                # Edit matches AI fix: collapse third pane if shown
                _undo_user_changes()
                return

            if user_text_ref[0] is None:
                # First real-change save: create third pane
                utxt = _make_diff_pane("  ✎  ai + user fixed")
                user_text_ref[0]  = utxt
                user_frame_ref[0] = utxt.master
                utxt.configure(
                    yscrollcommand=lambda f, l: _sync_yscroll(utxt, f, l))
                # Reveal Undo button
                undo_btn = ctk.CTkButton(
                    btn_frame, text="↩  Undo User Changes",
                    fg_color=("gray75", "gray30"),
                    hover_color=("gray60", "gray20"),
                    command=_undo_user_changes,
                )
                undo_btn.grid(row=0, column=2, padx=6)
                undo_btn_ref[0] = undo_btn
                # Change Close -> Save and Close
                if close_btn_ref[0] is not None:
                    close_btn_ref[0].configure(
                        text="💾  Save and Close",
                        fg_color="green",
                        hover_color="#1a7a1a",
                        command=_save_and_close,
                    )
            _populate_user_pane(user_content)

        def _open_editor() -> None:
            self._open_builtin_editor(
                idx,
                _initial_content=new_content,
                _on_save=_on_user_save,
            )

        # ── buttons ───────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=8)

        ctk.CTkButton(btn_frame, text="✎  Edit",
                      command=_open_editor).grid(row=0, column=0, padx=6)
        close_btn = ctk.CTkButton(btn_frame, text=t("common.close"),
                                  command=win.destroy)
        close_btn.grid(row=0, column=1, padx=6)
        close_btn_ref[0] = close_btn

    # ── View detail ────────────────────────────────────────────────────────

    def _show_issue_detail(self, issue: ReviewIssue):
        win = ctk.CTkToplevel(self)
        win.title(t("gui.results.issue_title", type=issue.issue_type))
        win.geometry("700x500")
        win.grab_set()
        win.after(10, lambda w=win: _fix_titlebar(w))
        win.bind("<Control-w>", lambda e: win.destroy())

        text = ctk.CTkTextbox(win, wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)

        content = (
            f"{t('gui.detail.file', path=issue.file_path)}\n"
            f"{t('gui.detail.type', type=issue.issue_type)}\n"
            f"{t('gui.detail.severity', severity=issue.severity)}\n"
            f"{t('gui.detail.status', status=issue.status)}\n"
            f"{t('gui.detail.reason', reason=issue.resolution_reason) + chr(10) if issue.resolution_reason else ''}"
            f"\n{t('gui.detail.ai_feedback')}\n{issue.ai_feedback}\n"
            f"\n{t('gui.detail.code_snippet')}\n{issue.code_snippet}\n"
        )
        text.insert("0.0", content)
        text.configure(state="disabled")

        ctk.CTkButton(win, text=t("common.close"),
                       command=win.destroy).pack(pady=8)

    # ── Review Changes (verify resolved issues) ───────────────────────────

    def _review_changes(self):
        if self._running:
            return
        if not self._review_client:
            if self._testing_mode:
                for rec in self._issue_cards:
                    if rec["issue"].status == "resolved":
                        rec["issue"].status = "fixed"
                for i in range(len(self._issue_cards)):
                    self._refresh_status(i)
                self._show_toast("Testing mode: resolved issues marked as fixed")
                return
            return
        self._running = True
        self._set_action_buttons_state("disabled")
        self.review_changes_btn.configure(state="disabled")
        self.finalize_btn.configure(state="disabled")
        self.save_session_btn.configure(state="disabled")
        self.ai_fix_mode_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.status_var.set(t("gui.results.reviewing"))

        resolved_cards = [
            (i, c) for i, c in enumerate(self._issue_cards)
            if c["issue"].status == "resolved"
        ]
        logger.info("Review Changes: verifying %d resolved issues…",
                     len(resolved_cards))

        def _worker():
            for i, rec in resolved_cards:
                issue = rec["issue"]
                try:
                    logger.info("Verifying fix for %s …", issue.file_path)
                    if self._review_client is None:
                        continue
                    ok = verify_issue_resolved(
                        issue, self._review_client,
                        issue.issue_type, self.lang_var.get(),
                    )
                    if ok:
                        issue.status = "fixed"
                        logger.info("  → verified fixed: %s", issue.file_path)
                    else:
                        issue.status = "fix_failed"
                        logger.info("  → fix NOT verified: %s", issue.file_path)
                    self.after(0, lambda idx=i: self._refresh_status(idx))
                except Exception as exc:
                    logger.error("Verify failed for %s: %s", issue.file_path, exc)
                    issue.status = "fix_failed"
                    self.after(0, lambda idx=i: self._refresh_status(idx))

            fixed_count = sum(1 for c in self._issue_cards
                              if c["issue"].status == "fixed")
            failed_count = sum(1 for c in self._issue_cards
                               if c["issue"].status == "fix_failed")
            logger.info("Review Changes complete: %d fixed, %d failed.",
                         fixed_count, failed_count)

            all_done = all(
                c["issue"].status in ("fixed", "skipped", "fix_failed")
                for c in self._issue_cards
            )
            if all_done:
                self.after(0, self._auto_finalize)
            else:
                self.after(0, self._update_bottom_buttons)
                self.after(0, lambda: self.status_var.set(t("common.ready")))

            self._running = False
            self.after(0, lambda: self._set_action_buttons_state("normal"))
            self.after(0, lambda: self.cancel_btn.configure(state="disabled"))

        threading.Thread(target=_worker, daemon=True).start()

    def _auto_finalize(self):
        self._do_finalize()
        self._show_toast(t("gui.results.all_fixed"))

    # ── Session save / load ─────────────────────────────────────────────

    @property
    def _session_path(self) -> Path:
        base = (config.config_path.parent
                if config.config_path else Path.cwd())
        return base / "session.json"

    def _save_session(self):
        if not self._issues:
            return

        def _default(obj):
            if isinstance(obj, datetime.datetime):
                return obj.isoformat()
            raise TypeError(repr(obj))

        data = {
            "saved_at": datetime.datetime.now().isoformat(),
            "issues": [dataclasses.asdict(iss) for iss in self._issues],
        }
        try:
            self._session_path.write_text(
                json.dumps(data, default=_default, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._show_toast(t("gui.results.session_saved",
                               path=str(self._session_path)))
        except Exception as exc:
            messagebox.showerror(t("common.error"), str(exc))

    def _load_session(self):
        initial_dir = str(self._session_path.parent)
        initial_file = (str(self._session_path)
                        if self._session_path.exists() else "")
        path_str = filedialog.askopenfilename(
            title=t("gui.results.load_session"),
            initialdir=initial_dir,
            initialfile=initial_file if initial_file else None,
            filetypes=[("JSON session", "*.json"), ("All files", "*.*")],
        )
        if not path_str:
            return
        if self._issues:
            if not messagebox.askyesno(
                t("gui.results.load_session"),
                t("gui.results.session_overwrite"),
            ):
                return
        try:
            raw = json.loads(Path(path_str).read_text(encoding="utf-8"))
            issues: List[ReviewIssue] = []
            for d in raw.get("issues", []):
                if d.get("resolved_at"):
                    try:
                        d["resolved_at"] = datetime.datetime.fromisoformat(
                            d["resolved_at"])
                    except (ValueError, TypeError):
                        d["resolved_at"] = None
                issues.append(ReviewIssue(**d))
        except Exception as exc:
            messagebox.showerror(
                t("common.error"),
                t("gui.results.session_load_fail", err=str(exc)),
            )
            return
        self._issues = issues
        self._show_issues(issues)
        self._show_toast(t("gui.results.session_loaded", count=len(issues)))

    # ── Finalize ───────────────────────────────────────────────────────────

    def _finalize_report(self):
        self._do_finalize()
        self._show_toast(t("gui.results.finalized"))

    def _do_finalize(self):
        runner = getattr(self, "_review_runner", None)
        if runner:
            issues = [c["issue"] for c in self._issue_cards]
            report_path = runner.generate_report(issues)
            if report_path:
                self.status_var.set(t("gui.val.report_saved", path=report_path))
            else:
                self.status_var.set(t("common.ready"))
        else:
            self.status_var.set(t("common.ready"))

        for w in self.results_frame.winfo_children():
            w.destroy()
        self._issue_cards.clear()
        self.results_summary.configure(text=t("gui.results.no_results"))
        self.review_changes_btn.configure(state="disabled")
        self.finalize_btn.configure(state="disabled")
        self.save_session_btn.configure(state="disabled")

        if self._testing_mode:
            def _reload_fixtures():
                from aicodereviewer.gui.test_fixtures import create_sample_issues
                self._show_issues(create_sample_issues())
                self.status_var.set(
                    "Testing mode: sample data reloaded after finalize")
            self.after(400, _reload_fixtures)
