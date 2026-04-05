# src/aicodereviewer/gui/results_mixin.py
"""Results-tab builder and issue-card logic mixin for :class:`App`.

Provides ``_build_results_tab`` plus issue cards, AI Fix mode, diff previews,
session save / load, and report finalization.
"""
from __future__ import annotations

import datetime
import json
import logging
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional, TypedDict

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.execution import DeferredReportState, ReviewSessionState
from aicodereviewer.backends import create_backend
from aicodereviewer.config import config
from aicodereviewer.i18n import t
from aicodereviewer.models import ReviewIssue
from aicodereviewer.reviewer import verify_issue_resolved

from .dialogs import ConfirmDialog
from .popup_surfaces import ResultsPopupSurfaceController
from .results_builder import ResultsTabBuilder
from .results_layout import ResultsLayoutHelper
from .results_popups import ResultsPopupHelper
from .shared_ui import MUTED_TEXT, SECTION_BORDER, SECTION_SURFACE

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
    undo_btn: Any
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
    ("local_http",  "port"):                       ("Local HTTP port",          int,   1),
    ("performance", "max_requests_per_minute"):    ("Max requests/min",         int,   1),
    ("performance", "min_request_interval_seconds"): ("Min request interval",  float, 0),
    ("performance", "max_file_size_mb"):            ("Max file size (MB)",       float, 0),
    ("processing",  "batch_size"):                  ("Batch size",              int,   1),
}


class ResultsTabMixin:
    """Mixin supplying Results-tab construction and all issue-card logic."""

    _CARD_ACTION_ROW = 3
    _CARD_SKIP_ROW = 4
    _SECTION_SURFACE = SECTION_SURFACE
    _SECTION_BORDER = SECTION_BORDER
    _MUTED_TEXT = MUTED_TEXT

    def _results_popup_helper(self) -> ResultsPopupHelper:
        helper = getattr(self, "_results_popup_helper_instance", None)
        if helper is None:
            helper = ResultsPopupHelper(self)
            self._results_popup_helper_instance = helper
        return helper

    def _results_layout_helper(self) -> ResultsLayoutHelper:
        return ResultsLayoutHelper(self)

    def _results_logical_width(self, *candidates: Any) -> float:
        return ResultsLayoutHelper.resolve_base_logical_width(self, *candidates)

    def _schedule_results_layout_refresh(self, *_args: Any) -> None:
        self._refresh_results_tab_layout()

    def _refresh_results_tab_layout(self) -> None:
        self._results_layout_helper().refresh_tab_layout()

    def _layout_results_quick_filters(self, logical_width: float) -> None:
        self._results_layout_helper().layout_quick_filters(logical_width)

    def _layout_results_filter_bar(self, logical_width: float) -> None:
        self._results_layout_helper().layout_filter_bar(logical_width)

    def _layout_results_bottom_actions(self, logical_width: float) -> None:
        self._results_layout_helper().layout_bottom_actions(logical_width)

    # ══════════════════════════════════════════════════════════════════════
    #  RESULTS TAB  – full-page issue cards
    # ══════════════════════════════════════════════════════════════════════

    def _build_results_tab(self):
        ResultsTabBuilder(self).build()

    # ══════════════════════════════════════════════════════════════════════
    #  RESULTS logic
    # ══════════════════════════════════════════════════════════════════════

    def _show_issues(self, issues: List[ReviewIssue]):
        logger.info("Displaying %d issues on the Results tab", len(issues))
        self._issues = issues
        for w in self.results_frame.winfo_children():
            w.destroy()
        self._issue_cards.clear()

        if not issues:
            self.results_summary.configure(text=t("gui.results.no_results"))
            self.results_subsummary.grid_remove()
            self.review_changes_btn.configure(state="disabled")
            self.finalize_btn.configure(state="disabled")
            self.save_session_btn.configure(state="disabled")
            self._overview_frame.grid_remove()
            self._quick_filter_bar.grid_remove()
            self._filter_bar.grid_remove()
            self.results_severity_bar.grid_remove()
            self.tabs.set(t("gui.tab.results"))
            return

        issue_types = sorted({
            it
            for iss in issues
            for it in (iss.issue_type.split("+") if "+" in iss.issue_type else [iss.issue_type])
        })
        self.results_summary.configure(
            text=t("gui.results.summary_title", issues=len(issues)))
        self.results_subsummary.configure(
            text=t(
                "gui.results.summary",
                score="—",
                issues=len(issues),
                types=", ".join(issue_types),
                backend=self.backend_var.get(),
            )
        )
        self.results_subsummary.grid()

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
        self._update_overview_cards(issues, counts)
        self._overview_frame.grid()
        self._quick_filter_bar.grid()
        self._set_quick_filter("all", apply=False)

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
        translated_types = [t(f"review_type.{typ}") for typ in types]
        self._filter_type_reverse_map = dict(zip(translated_types, types))
        self._filter_type_menu.configure(values=[all_types_label] + translated_types)
        self._filter_type_var.set(all_types_label)
        self._filter_sev_var.set(t("gui.results.filter_all"))
        self._filter_status_var.set(t("gui.results.filter_all"))
        self._filter_bar.grid()

    def _update_overview_cards(self, issues: List[ReviewIssue], counts: Dict[str, int]) -> None:
        pending_count = sum(1 for issue in issues if issue.status == "pending")
        attention_count = counts.get("critical", 0) + counts.get("high", 0)
        self._overview_cards["issues"].configure(text=str(len(issues)))
        self._overview_cards["pending"].configure(text=str(pending_count))
        self._overview_cards["attention"].configure(text=str(attention_count))
        self._overview_cards["backend"].configure(text=self.backend_var.get().capitalize())

    def _set_quick_filter(self, mode: str, *, apply: bool = True) -> None:
        self._quick_filter_mode = mode
        active_fg = "#2563eb"
        inactive_fg = ("#e5edf9", "#303744")
        active_hover = "#1d4ed8"
        inactive_hover = ("#d7e4f7", "#3a4352")
        for button_mode, button in self._quick_filter_buttons.items():
            selected = button_mode == mode
            button.configure(
                fg_color=active_fg if selected else inactive_fg,
                hover_color=active_hover if selected else inactive_hover,
                text_color="#ffffff" if selected else ("gray15", "gray92"),
            )
        if apply:
            self._apply_filters()

    def _on_filter_controls_changed(self) -> None:
        self._set_quick_filter("all", apply=False)
        self._apply_filters()

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
        filter_type = None
        if type_sel != all_types_label:
            filter_type = getattr(self, "_filter_type_reverse_map", {}).get(type_sel, type_sel)

        quick_mode = getattr(self, "_quick_filter_mode", "all")

        visible = 0
        total = len(self._issue_cards)
        for rec in self._issue_cards:
            issue = rec["issue"]
            # In AI fix selection mode only pending items are shown
            if getattr(self, "_ai_fix_mode", False) and issue.status != "pending":
                rec["card"].grid_remove()
                continue
            issue_types = (
                issue.issue_type.split("+") if "+" in issue.issue_type
                else [issue.issue_type]
            )
            match = (
                (filter_sev is None or issue.severity == filter_sev)
                and (filter_status is None or issue.status == filter_status)
                and (filter_type is None or filter_type in issue_types)
            )
            if match and quick_mode != "all":
                if quick_mode == "pending":
                    match = issue.status == "pending"
                elif quick_mode == "critical":
                    match = issue.severity == "critical"
                elif quick_mode == "attention":
                    match = issue.severity in {"critical", "high"}
                elif quick_mode == "cross_file":
                    match = issue.context_scope in {"cross_file", "project"}
                elif quick_mode == "fix_failed":
                    match = issue.status == "fix_failed"
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
        self._set_quick_filter("all", apply=False)
        self._apply_filters()

    @staticmethod
    def _badge_colors(role: str, accent: str | None = None) -> tuple[Any, Any]:
        if role == "severity" and accent is not None:
            return accent, "#ffffff"
        if role == "type":
            return ("#e8edf4", "#323844"), ("gray10", "gray92")
        if role == "scope":
            return ("#dbeafe", "#1e3a5f"), ("#1d4ed8", "#bfdbfe")
        if role == "related":
            return ("#ede9fe", "#312e81"), ("#6d28d9", "#ddd6fe")
        if role == "status":
            return ("#eef2f7", "#282d36"), ("gray15", "gray92")
        return ("#eef2f7", "#2a3039"), ("gray10", "gray92")

    def _make_badge(
        self,
        parent: Any,
        text: str,
        *,
        role: str = "default",
        accent: str | None = None,
    ) -> Any:
        fg_color, text_color = self._badge_colors(role, accent)
        return ctk.CTkLabel(
            parent,
            text=text,
            fg_color=fg_color,
            text_color=text_color,
            corner_radius=999,
            padx=10,
            pady=3,
            font=ctk.CTkFont(size=11, weight="bold"),
        )

    # ── Issue card ─────────────────────────────────────────────────────────

    def _add_issue_card(self, index: int, issue: ReviewIssue):
        sev_colors = {
            "critical": "#dc2626", "high": "#ea580c",
            "medium": "#ca8a04", "low": "#2563eb", "info": "#6b7280",
        }
        color = sev_colors.get(issue.severity, "#6b7280")

        card = ctk.CTkFrame(self.results_frame, fg_color=self._SECTION_SURFACE, border_width=1,
                     border_color=color)
        card.grid(row=index, column=0, sticky="ew", padx=4, pady=3)
        card.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        header_frame.grid_columnconfigure(2, weight=1)

        severity_badge = self._make_badge(
            header_frame,
            issue.severity.upper(),
            role="severity",
            accent=color,
        )
        severity_badge.grid(row=0, column=0, padx=(0, 6), sticky="w")

        issue_type_badge = self._make_badge(header_frame, issue.issue_type, role="type")
        issue_type_badge.grid(row=0, column=1, padx=(0, 6), sticky="w")

        file_lbl = ctk.CTkLabel(
            header_frame,
            text=Path(issue.file_path).name,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        file_lbl.grid(row=0, column=2, sticky="w")

        scope_text = t(f"gui.results.scope_{issue.context_scope}")
        scope_badge = self._make_badge(header_frame, scope_text, role="scope")
        scope_badge.grid(row=0, column=3, padx=(6, 0), sticky="e")

        related = getattr(issue, "related_issues", None) or []
        if related:
            _tip = getattr(issue, "interaction_summary", "") or ""
            badge = self._make_badge(header_frame, t("gui.results.related_badge", count=len(related)), role="related")
            badge.configure(cursor="hand2")
            badge.grid(row=0, column=4, padx=(6, 0), sticky="e")
            if _tip:
                badge.bind(
                    "<Enter>",
                    lambda e, w=badge, txt=_tip: w.configure(
                        text=txt[:60] + ("\u2026" if len(txt) > 60 else "")
                    ),
                )
                badge.bind(
                    "<Leave>",
                    lambda e, w=badge, n=len(related): w.configure(
                        text=t("gui.results.related_badge", count=n)
                    ),
                )

        _TRUNC = 120
        full_desc = issue.description
        truncated = len(full_desc) > _TRUNC
        desc_text = full_desc[:_TRUNC] + "…" if truncated else full_desc
        desc_lbl = ctk.CTkLabel(
            card,
            text=desc_text,
            anchor="w",
            wraplength=740,
            justify="left",
            font=ctk.CTkFont(size=14),
        )
        desc_lbl.grid(row=1, column=0, sticky="ew", padx=10)

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
            expand_btn.grid(row=1, column=1, padx=(0, 10), pady=(0, 2), sticky="e")

        meta_parts = []
        if issue.line_number:
            meta_parts.append(t("gui.results.meta_line", line=issue.line_number))
        if issue.related_files:
            meta_parts.append(t("gui.results.meta_related_files", count=len(issue.related_files)))
        if issue.systemic_impact:
            meta_parts.append(t("gui.results.meta_systemic"))
        if meta_parts:
            meta_lbl = ctk.CTkLabel(
                card,
                text="  •  ".join(meta_parts),
                anchor="w",
                justify="left",
                text_color=self._MUTED_TEXT,
                font=ctk.CTkFont(size=11),
            )
            meta_lbl.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))

        s_key, s_color = self._status_display(issue, color)
        action_frame = ctk.CTkFrame(card, fg_color="transparent")
        action_frame.grid(row=self._CARD_ACTION_ROW, column=0, sticky="ew", padx=8, pady=(0, 8))
        action_frame.grid_columnconfigure(0, weight=1)

        status_lbl = self._make_badge(action_frame, t(s_key), role="status")
        status_lbl.configure(text_color=s_color)
        status_lbl.grid(row=0, column=0, sticky="w", padx=(0, 4))

        btn_kw = dict(width=65, height=26, font=ctk.CTkFont(size=11))
        view_btn = ctk.CTkButton(
            action_frame, text=t("gui.results.action_view"), **btn_kw,  # type: ignore[reportArgumentType]
            command=lambda iss=issue: self._show_issue_detail(iss),
        )
        view_btn.grid(row=0, column=1, padx=2, pady=(0, 0))

        fix_check_var = ctk.BooleanVar(value=False)
        fix_checkbox = ctk.CTkCheckBox(
            action_frame, text=t("gui.results.select_for_fix"),
            variable=fix_check_var,
            font=ctk.CTkFont(size=11), width=20,
        )

        resolve_btn = ctk.CTkButton(
            action_frame, text=t("gui.results.action_resolve"), **btn_kw,  # type: ignore[reportArgumentType]
            fg_color="green",
            command=lambda idx=len(self._issue_cards):
                self._resolve_issue(idx),
        )

        skip_btn = ctk.CTkButton(
            action_frame, text=t("gui.results.action_skip"), **btn_kw,  # type: ignore[reportArgumentType]
            fg_color="gray50",
            command=lambda idx=len(self._issue_cards):
                self._toggle_skip(idx),
        )

        undo_btn = ctk.CTkButton(
            action_frame, text=t("gui.results.action_undo"), **btn_kw,  # type: ignore[reportArgumentType]
            fg_color=("gray70", "gray35"),
            hover_color=("gray60", "gray45"),
            command=lambda idx=len(self._issue_cards):
                self._undo_issue(idx),
        )

        # Show the correct buttons for the initial status
        if issue.status == "pending":
            resolve_btn.grid(row=0, column=2, padx=2, pady=(0, 0))
            skip_btn.grid(row=0, column=3, padx=2, pady=(0, 0))
        else:
            undo_btn.grid(row=0, column=2, padx=2, pady=(0, 0))

        skip_frame = ctk.CTkFrame(card, fg_color="transparent")
        skip_entry = ctk.CTkEntry(skip_frame, width=500,
                                   placeholder_text=t("gui.results.skip_reason_ph"))
        skip_entry.grid(row=0, column=0, sticky="ew", padx=(20, 6), pady=4)
        skip_frame.grid_columnconfigure(0, weight=1)
        if issue.status == "skipped":
            skip_frame.grid(row=self._CARD_SKIP_ROW, column=0, sticky="ew", padx=8, pady=(0, 4))

        self._issue_cards.append(IssueCard(
            issue=issue,
            card=card,
            status_lbl=status_lbl,
            desc_lbl=desc_lbl,
            expand_btn=expand_btn,
            view_btn=view_btn,
            resolve_btn=resolve_btn,
            skip_btn=skip_btn,
            undo_btn=undo_btn,
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
        issue = rec["issue"]
        s_key, s_color = self._status_display(issue, rec["color"])
        rec["status_lbl"].configure(text=t(s_key), text_color=s_color)
        if issue.status == "pending":
            rec["undo_btn"].grid_remove()
            rec["resolve_btn"].grid(row=0, column=2, padx=2, pady=(0, 0))
            rec["skip_btn"].grid(row=0, column=3, padx=2, pady=(0, 0))
        else:
            rec["resolve_btn"].grid_remove()
            rec["skip_btn"].grid_remove()
            rec["undo_btn"].grid(row=0, column=2, padx=2, pady=(0, 0))
        self._update_bottom_buttons()
        self._apply_filters()

    def _get_runner_report_context(self) -> dict[str, Any]:
        """Return deferred report metadata from the active runner if available."""
        runner = self._current_session_runner()
        if runner is None:
            return {}

        meta = getattr(runner, "serialized_report_context", None)
        if callable(meta):
            meta = meta()
        if meta:
            return dict(meta)

        return {}

    def _ensure_popup_surface_controller(self) -> ResultsPopupSurfaceController:
        return self._results_popup_helper().ensure_surface_controller()

    def _restore_popup_recovery_if_available(self) -> None:
        self._results_popup_helper().restore_recovery_if_available()

    def _restore_editor_popup_recovery(self, recovery_state: dict[str, Any]) -> None:
        self._results_popup_helper().restore_editor_recovery(recovery_state)

    def _restore_batch_fix_popup_recovery(self, recovery_state: dict[str, Any]) -> None:
        self._results_popup_helper().restore_batch_fix_recovery(recovery_state)

    def _update_bottom_buttons(self):
        all_done = all(c["issue"].status != "pending" for c in self._issue_cards)
        any_to_check = any(c["issue"].status in ("resolved",) for c in self._issue_cards)
        any_pending = any(c["issue"].status == "pending" for c in self._issue_cards)
        has_backend_context = self._has_backend_context_for_ai_fix()

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

        if any_pending and has_backend_context:
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
            issue.set_resolution(
                status="resolved",
                provenance="external_editor",
                resolved_at=datetime.datetime.now(),
            )
        else:
            self._open_builtin_editor(idx)
            return

        self._refresh_status(idx)

    def _open_builtin_editor(
        self,
        idx: int,
        _initial_content: str | None = None,
        _on_save: Any = None,
        _recovery_state: dict[str, Any] | None = None,
        _on_draft_change: Callable[[str, str], None] | None = None,
        _on_discard: Callable[[], None] | None = None,
    ):
        self._ensure_popup_surface_controller().open_builtin_editor(
            idx,
            self._issue_cards[idx]["issue"],
            initial_content=_initial_content,
            on_save=_on_save,
            recovery_state=_recovery_state,
            on_draft_change=_on_draft_change,
            on_discard=_on_discard,
        )

    # ── Skip ───────────────────────────────────────────────────────────────

    def _toggle_skip(self, idx: int):
        rec = self._issue_cards[idx]
        issue = rec["issue"]

        issue.set_resolution(
            status="skipped",
            provenance="skipped",
            resolved_at=datetime.datetime.now(),
        )
        rec["skip_frame"].grid(row=self._CARD_SKIP_ROW, column=0, sticky="ew", padx=8, pady=(0, 4))
        def _on_reason_change(*_a, _entry=rec["skip_entry"], _iss=issue):
            _iss.resolution_reason = _entry.get().strip() or None
        rec["skip_entry"].bind("<KeyRelease>", _on_reason_change)

        self._refresh_status(idx)

    # ── Undo ───────────────────────────────────────────────────────────────

    def _undo_issue(self, idx: int):
        """Revert the issue status back to pending and hide the Undo button."""
        rec = self._issue_cards[idx]
        issue = rec["issue"]
        issue.clear_resolution()
        rec["skip_frame"].grid_remove()
        self._refresh_status(idx)

    # ── AI Fix Mode ──────────────────────────────────────────────────────

    def _enter_ai_fix_mode(self):
        if self._ai_fix_mode:
            return
        self._ai_fix_mode = True

        self.ai_fix_mode_btn.grid_remove()
        self.review_changes_btn.grid_remove()
        self.finalize_btn.grid_remove()
        self.results_action_hint.configure(text=t("gui.results.ai_fix_hint"))
        self.start_ai_fix_btn.grid(row=0, column=1, padx=6)
        self.cancel_ai_fix_btn.grid(row=0, column=2, padx=6)

        self._set_action_buttons_state("disabled")

        for rec in self._issue_cards:
            # Hide all action buttons on every card regardless of status
            rec["view_btn"].grid_remove()
            rec["resolve_btn"].grid_remove()
            rec["skip_btn"].grid_remove()
            rec["undo_btn"].grid_remove()
            if rec["issue"].status == "pending":
                rec["fix_check_var"].set(True)
                rec["fix_checkbox"].grid(row=0, column=1, columnspan=3,
                                          padx=4, pady=(0, 0), sticky="w")

        self._apply_filters()
        self._refresh_results_tab_layout()

    def _exit_ai_fix_mode(self):
        if self._is_ai_fix_running():
            cancel_event = self._active_ai_fix_cancel_event()
            if cancel_event is not None and not cancel_event.is_set():
                self._request_active_ai_fix_cancel()
                logger.info("Cancelling AI Fix run...")
                self.cancel_ai_fix_btn.configure(state="disabled", text=t("gui.results.cancelling_ai_fix"))
                self.status_var.set(t("gui.results.cancelling_status"))
            return

        self._ai_fix_mode = False

        self.start_ai_fix_btn.grid_remove()
        self.cancel_ai_fix_btn.grid_remove()
        self.results_action_hint.configure(text=t("gui.results.next_action_hint"))
        self.ai_fix_mode_btn.grid(row=0, column=1, padx=6)
        self.review_changes_btn.grid(row=0, column=2, padx=6)
        self.finalize_btn.grid(row=0, column=3, padx=6)

        self._set_action_buttons_state("normal")

        for rec in self._issue_cards:
            rec["fix_checkbox"].grid_remove()
            rec["fix_check_var"].set(False)
            s_key, s_color = self._status_display(rec["issue"], rec["color"])
            rec["status_lbl"].configure(text=t(s_key), text_color=s_color)
            rec["view_btn"].grid(row=0, column=1, padx=2, pady=(0, 0))
            if rec["issue"].status == "pending":
                rec["undo_btn"].grid_remove()
                rec["resolve_btn"].grid(row=0, column=2, padx=2, pady=(0, 0))
                rec["skip_btn"].grid(row=0, column=3, padx=2, pady=(0, 0))
            else:
                rec["resolve_btn"].grid_remove()
                rec["skip_btn"].grid_remove()
                rec["undo_btn"].grid(row=0, column=2, padx=2, pady=(0, 0))

        self._update_bottom_buttons()
        self._apply_filters()
        self._refresh_results_tab_layout()

    def _start_batch_ai_fix(self):
        if self._is_busy():
            return
        selected = [
            (i, rec) for i, rec in enumerate(self._issue_cards)
            if rec["fix_check_var"].get() and rec["issue"].status == "pending"
        ]
        if not selected:
            self._show_toast(t("gui.results.no_issues_selected"), error=True)
            return

        if not self._current_ai_fix_client() and self._testing_mode:
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

        ai_fix_cancel_event = self._begin_active_ai_fix()
        self.start_ai_fix_btn.configure(state="disabled")
        review_language = self.lang_var.get()
        runner_meta = self._get_runner_report_context()
        fix_backend = runner_meta.get("backend") or self.backend_var.get()

        logger.info("Starting batch AI Fix for %d issues…", len(selected))
        self.status_var.set(t("gui.results.batch_fix_running",
                              count=len(selected)))

        for i, rec in selected:
            rec["status_lbl"].configure(
                text=t("gui.results.applying_fix"), text_color="#7c3aed")

        def _worker():
            cancelled = False
            try:
                client = self._current_ai_fix_client()
                if client is None:
                    logger.info(
                        "AI Fix: recreating backend client for %s fixes",
                        fix_backend,
                    )
                    client = create_backend(fix_backend)
                    self._attach_active_ai_fix_client(client)

                results = {}
                for idx, rec in selected:
                    if ai_fix_cancel_event.is_set():
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
                        fix = client.get_fix(
                            code_content=code,
                            issue_feedback=issue.ai_feedback or issue.description,
                            review_type=issue.issue_type,
                            lang=review_language,
                        )
                        if ai_fix_cancel_event.is_set():
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
                        if ai_fix_cancel_event.is_set():
                            logger.info("AI Fix cancelled by user")
                            cancelled = True
                            break
                if cancelled:
                    self._run_on_ui_thread(self._on_ai_fix_cancelled, selected)
                else:
                    self._run_on_ui_thread(self._show_batch_fix_popup, selected, results)
            finally:
                if not cancelled:
                    self._finish_active_ai_fix()
                    self._release_ai_fix_client()

        threading.Thread(target=_worker, daemon=True).start()

    def _on_ai_fix_cancelled(self, selected):
        logger.info("AI Fix operation cancelled.")
        self.status_var.set(t("common.ready"))
        for idx, rec in selected:
            s_key, s_color = self._status_display(rec["issue"], rec["color"])
            rec["status_lbl"].configure(text=t(s_key), text_color=s_color)
        self.start_ai_fix_btn.configure(state="normal")
        self.cancel_ai_fix_btn.configure(state="normal", text=t("gui.results.cancel_ai_fix"))
        self._release_ai_fix_client()
        self._finish_active_ai_fix()

    def _show_batch_fix_popup(self, selected, results, recovery_state: dict[str, Any] | None = None):
        self._results_popup_helper().show_batch_fix_popup(
            selected,
            results,
            recovery_state=recovery_state,
        )

    def _show_diff_preview(
        self,
        file_path: str,
        new_content: str,
        filename: str,
        idx: int = 0,
        _on_content_update: Any = None,
        _ai_fix_content: str | None = None,
        _recovery_state: dict[str, Any] | None = None,
        _on_preview_state_change: Callable[[dict[str, Any] | None], None] | None = None,
        _on_preview_closed: Callable[[], None] | None = None,
    ):
        self._ensure_popup_surface_controller().show_diff_preview(
            file_path=file_path,
            new_content=new_content,
            filename=filename,
            idx=idx,
            on_content_update=_on_content_update,
            ai_fix_content=_ai_fix_content,
            recovery_state=_recovery_state,
            on_preview_state_change=_on_preview_state_change,
            on_preview_closed=_on_preview_closed,
        )

    # ── View detail ────────────────────────────────────────────────────────

    def _show_issue_detail(self, issue: ReviewIssue):
        self._results_popup_helper().show_issue_detail(issue)

    # ── Review Changes (verify resolved issues) ───────────────────────────

    def _review_changes(self):
        if self._is_busy():
            return
        if not self._active_review_client() and self._testing_mode:
            for rec in self._issue_cards:
                if rec["issue"].status == "resolved":
                    rec["issue"].status = "fixed"
            for i in range(len(self._issue_cards)):
                self._refresh_status(i)
            self._show_toast("Testing mode: resolved issues marked as fixed")
            return
        self._review_changes_controller().begin()
        self._set_action_buttons_state("disabled")
        self.review_changes_btn.configure(state="disabled")
        self.finalize_btn.configure(state="disabled")
        self.save_session_btn.configure(state="disabled")
        self.ai_fix_mode_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        self.status_var.set(t("gui.results.reviewing"))

        resolved_cards = [
            (i, c) for i, c in enumerate(self._issue_cards)
            if c["issue"].status == "resolved"
        ]
        review_language = self.lang_var.get()
        runner_meta = self._get_runner_report_context()
        verification_backend = runner_meta.get("backend") or self.backend_var.get()
        logger.info("Review Changes: verifying %d resolved issues…",
                     len(resolved_cards))

        def _worker():
            try:
                client = self._active_review_client()
                if client is None:
                    logger.info(
                        "Review Changes: recreating backend client for %s verification",
                        verification_backend,
                    )
                    client = create_backend(verification_backend)
                    self._bind_active_review_client(client)

                for i, rec in resolved_cards:
                    issue = rec["issue"]
                    try:
                        logger.info("Verifying fix for %s …", issue.file_path)
                        ok = verify_issue_resolved(
                            issue, client,
                            issue.issue_type, review_language,
                        )
                        if ok:
                            issue.status = "fixed"
                            logger.info("  → verified fixed: %s", issue.file_path)
                        else:
                            issue.status = "fix_failed"
                            logger.info("  → fix NOT verified: %s", issue.file_path)
                        self._run_on_ui_thread(self._refresh_status, i)
                    except Exception as exc:
                        logger.error("Verify failed for %s: %s", issue.file_path, exc)
                        issue.status = "fix_failed"
                        self._run_on_ui_thread(self._refresh_status, i)

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
                    self._run_on_ui_thread(self._auto_finalize)
                else:
                    self._run_on_ui_thread(self._update_bottom_buttons)
                    self._run_on_ui_thread(self.status_var.set, t("common.ready"))
            except Exception as exc:
                logger.error("Review Changes failed: %s", exc)
                self._run_on_ui_thread(self._show_toast, str(exc), error=True)
                self._run_on_ui_thread(self._update_bottom_buttons)
                self._run_on_ui_thread(self.status_var.set, t("common.ready"))
            finally:
                self._review_changes_controller().finish()
                self._release_review_client()
                self._run_on_ui_thread(self._set_action_buttons_state, "normal")
                self._run_on_ui_thread(self.cancel_btn.configure, state="disabled")

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

    def _get_session_report_context(self) -> dict[str, Any] | None:
        meta = self._get_runner_report_context()
        return dict(meta) if meta else None

    def _get_session_state(self) -> ReviewSessionState:
        runner = self._current_session_runner()
        session_state = getattr(runner, "session_state", None) if runner is not None else None
        if callable(session_state):
            session_state = session_state()
        if session_state is not None:
            return session_state.with_issues(self._issues)

        deferred_report_state = getattr(runner, "deferred_report_state", None) if runner is not None else None
        if callable(deferred_report_state):
            deferred_report_state = deferred_report_state()
        if deferred_report_state is None:
            report_context = self._get_session_report_context()
            return ReviewSessionState.from_report_context(report_context, issues=list(self._issues))
        return deferred_report_state.to_session_state(self._issues)

    def _restore_session_state(self, session_state: ReviewSessionState) -> None:
        if session_state.backend_name is None:
            self._clear_session_runner()
            return

        from aicodereviewer.orchestration import AppRunner

        runner = AppRunner(None, backend_name=session_state.backend_name)
        runner.restore_session_state(session_state)
        self._bind_session_runner(runner)

    def _restore_session_report_context(
        self,
        report_context: dict[str, Any] | None,
        issues: list[ReviewIssue] | None = None,
    ) -> None:
        if not report_context:
            self._clear_session_runner()
            return
        self._restore_session_state(
            ReviewSessionState.from_report_context(
                dict(report_context),
                issues=list(issues or []),
                default_backend=report_context.get("backend", "bedrock"),
            )
        )

    def _save_session(self):
        if not self._issues:
            return

        data = self._get_session_state().to_serialized_dict(saved_at=datetime.datetime.now())
        try:
            self._session_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
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
            session_state = ReviewSessionState.from_serialized_dict(raw)
        except Exception as exc:
            messagebox.showerror(
                t("common.error"),
                t("gui.results.session_load_fail", err=str(exc)),
            )
            return
        self._restore_session_state(session_state)
        self._issues = list(session_state.issues)
        self._show_issues(session_state.issues)
        self._show_toast(t("gui.results.session_loaded", count=len(session_state.issues)))

    # ── Finalize ───────────────────────────────────────────────────────────

    def _finalize_report(self):
        self._do_finalize()
        self._show_toast(t("gui.results.finalized"))

    def _do_finalize(self):
        runner = self._current_session_runner()
        if not runner:
            if self._testing_mode:
                self.status_var.set(t("common.ready"))
            else:
                message = t("gui.results.finalize_unavailable")
                self.status_var.set(message)
                self._show_toast(message, error=True)
                return

        report_saved = False
        if runner:
            issues = [c["issue"] for c in self._issue_cards]
            report_path = runner.generate_report(issues)
            if report_path:
                self.status_var.set(t("gui.val.report_saved", path=report_path))
                report_saved = True
            else:
                if self._testing_mode:
                    self.status_var.set(t("common.ready"))
                    report_saved = True
                else:
                    message = t("gui.results.finalize_unavailable")
                    self.status_var.set(message)
                    self._show_toast(message, error=True)
                    return

        for w in self.results_frame.winfo_children():
            w.destroy()
        self._issue_cards.clear()
        self.results_summary.configure(text=t("gui.results.no_results"))
        self.review_changes_btn.configure(state="disabled")
        self.finalize_btn.configure(state="disabled")
        self.save_session_btn.configure(state="disabled")
        if report_saved:
            self._issues = []
            self._clear_session_runner()

        if self._testing_mode:
            def _reload_fixtures():
                from aicodereviewer.gui.test_fixtures import create_sample_issues
                self._show_issues(create_sample_issues())
                self.status_var.set(
                    "Testing mode: sample data reloaded after finalize")
            schedule_after = getattr(self, "_schedule_app_after", self.after)
            schedule_after(400, _reload_fixtures)
