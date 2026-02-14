# src/aicodereviewer/gui/app.py
"""
Main CustomTkinter application for AICodeReviewer.

Provides full feature parity with the CLI:
- Project / diff scope selection
- Multi-type review selection
- Backend selection (Bedrock / Kiro / Copilot / Local LLM)
- Programmer / reviewer metadata
- Dry-run and full review execution
- Live log output
- Inline results with per-issue actions on the Review tab
- Connection testing & backend health checking
- Localised UI (English / Japanese) with theme support
"""
import logging
import os
import threading
import queue
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk

from aicodereviewer.backends import create_backend
from aicodereviewer.backends.base import REVIEW_TYPE_KEYS, REVIEW_TYPE_META
from aicodereviewer.backends.health import check_backend
from aicodereviewer.config import config
from aicodereviewer.auth import get_system_language
from aicodereviewer.scanner import scan_project_with_scope
from aicodereviewer.orchestration import AppRunner
from aicodereviewer.models import ReviewIssue
from aicodereviewer.i18n import t, set_locale, get_locale

logger = logging.getLogger(__name__)


# ── queue-based log handler for the GUI ────────────────────────────────────

class QueueLogHandler(logging.Handler):
    """Send log records to a :class:`queue.Queue` for GUI consumption."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            self.log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass


# ── tooltip helper ─────────────────────────────────────────────────────────

class InfoTooltip:
    """Attach a hover tooltip to any widget via an 🛈 icon label."""

    @staticmethod
    def add(parent, text: str, row: int, column: int, **grid_kw):
        """Place an 🛈 label at the given grid position with a hover tooltip."""
        lbl = ctk.CTkLabel(parent, text="🛈", width=20,
                           font=ctk.CTkFont(size=14),
                           text_color=("gray50", "gray60"),
                           cursor="question_arrow")
        lbl.grid(row=row, column=column, padx=(0, 4), **grid_kw)
        _tip = _Tooltip(lbl, text)
        return lbl


class _Tooltip:
    """Simple hover tooltip for CustomTkinter widgets."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._tipwindow = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self._tipwindow:
            return
        import tkinter as tk
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        # Use a normal tk.Label for the tooltip (theme-independent)
        label = tk.Label(tw, text=self.text, justify="left",
                         background="#333333", foreground="#ffffff",
                         relief="solid", borderwidth=1,
                         font=("Segoe UI", 9), wraplength=350,
                         padx=8, pady=4)
        label.pack()
        self._tipwindow = tw

    def _hide(self, event=None):
        if self._tipwindow:
            self._tipwindow.destroy()
            self._tipwindow = None


# ═══════════════════════════════════════════════════════════════════════════

class App(ctk.CTk):
    """Root window of the AICodeReviewer GUI."""

    WIDTH = 1100
    HEIGHT = 820

    def __init__(self):
        super().__init__()

        # ── Detect language & apply saved preferences ──────────────────────
        saved_lang = config.get("gui", "language", "").strip()
        if saved_lang and saved_lang != "system":
            self._ui_lang = saved_lang
        else:
            self._ui_lang = get_system_language()
        set_locale(self._ui_lang)

        # ── Apply saved theme ──────────────────────────────────────────────
        saved_theme = config.get("gui", "theme", "").strip() or "system"
        theme_map = {"system": "System", "dark": "Dark", "light": "Light"}
        ctk.set_appearance_mode(theme_map.get(saved_theme, "System"))
        ctk.set_default_color_theme("blue")

        self.title(t("common.app_title"))
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(900, 680)

        # Logging queue
        self._log_queue: queue.Queue = queue.Queue(maxsize=5000)
        self._install_log_handler()

        # State
        self._issues: List[ReviewIssue] = []
        self._running = False
        self._review_client = None  # keep reference for AI fix

        # Layout
        self._build_ui()
        self._poll_log_queue()

        # Auto-run health check on startup (silent if all pass)
        self.after(500, self._auto_health_check)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(self, anchor="nw")
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self._build_review_tab()
        self._build_settings_tab()
        self._build_log_tab()

        # Bottom status
        self.status_var = ctk.StringVar(value=t("common.ready"))
        status = ctk.CTkLabel(self, textvariable=self.status_var, anchor="w")
        status.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 6))

    # ══════════════════════════════════════════════════════════════════════
    #  REVIEW TAB  – includes inline results panel
    # ══════════════════════════════════════════════════════════════════════

    def _build_review_tab(self):
        tab = self.tabs.add(t("gui.tab.review"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(9, weight=1)  # results area gets leftover space

        row = 0

        # ── Project path ──────────────────────────────────────────────────
        path_frame = ctk.CTkFrame(tab)
        path_frame.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        path_frame.grid_columnconfigure(2, weight=1)
        InfoTooltip.add(path_frame, t("gui.tip.project_path"), row=0, column=0)
        ctk.CTkLabel(path_frame, text=t("gui.review.project_path")).grid(row=0, column=1, padx=(0, 4))
        self.path_entry = ctk.CTkEntry(path_frame, placeholder_text=t("gui.review.placeholder_path"))
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
        ctk.CTkRadioButton(scope_frame, text=t("gui.review.scope_project"),
                            variable=self.scope_var, value="project").grid(row=0, column=2, padx=6)
        ctk.CTkRadioButton(scope_frame, text=t("gui.review.scope_diff"),
                            variable=self.scope_var, value="diff").grid(row=0, column=3, padx=6)

        # Diff sub-options
        diff_frame = ctk.CTkFrame(scope_frame)
        diff_frame.grid(row=1, column=0, columnspan=5, sticky="ew", padx=6, pady=3)
        diff_frame.grid_columnconfigure(2, weight=1)
        InfoTooltip.add(diff_frame, t("gui.tip.diff_file"), row=0, column=0)
        ctk.CTkLabel(diff_frame, text=t("gui.review.diff_file")).grid(row=0, column=1, padx=4)
        self.diff_file_entry = ctk.CTkEntry(diff_frame, placeholder_text=t("gui.review.diff_placeholder"))
        self.diff_file_entry.grid(row=0, column=2, sticky="ew", padx=4)
        ctk.CTkButton(diff_frame, text="…", width=30,
                       command=self._browse_diff).grid(row=0, column=3, padx=4)
        InfoTooltip.add(diff_frame, t("gui.tip.commits"), row=1, column=0)
        ctk.CTkLabel(diff_frame, text=t("gui.review.commits")).grid(row=1, column=1, padx=4, pady=(3, 0))
        self.commits_entry = ctk.CTkEntry(diff_frame, placeholder_text=t("gui.review.commits_placeholder"))
        self.commits_entry.grid(row=1, column=2, sticky="ew", padx=4, pady=(3, 0))
        row += 1

        # ── Review types ──────────────────────────────────────────────────
        types_hdr = ctk.CTkFrame(tab, fg_color="transparent")
        types_hdr.grid(row=row, column=0, sticky="w", padx=6, pady=(4, 1))
        InfoTooltip.add(types_hdr, t("gui.tip.review_types"), row=0, column=0)
        ctk.CTkLabel(types_hdr, text=t("gui.review.types_label"),
                      anchor="w").grid(row=0, column=1)
        row += 1

        types_frame = ctk.CTkScrollableFrame(tab, height=110)
        types_frame.grid(row=row, column=0, sticky="ew", padx=6)
        self.type_vars = {}
        col = 0
        r = 0
        for i, key in enumerate(REVIEW_TYPE_KEYS):
            meta = REVIEW_TYPE_META.get(key, {})
            label = meta.get("label", key)
            var = ctk.BooleanVar(value=(key == "best_practices"))
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
        self.programmers_entry = ctk.CTkEntry(meta_frame,
                                               placeholder_text=t("gui.review.programmers_ph"))
        self.programmers_entry.grid(row=0, column=2, sticky="ew", padx=4)

        InfoTooltip.add(meta_frame, t("gui.tip.reviewers"), row=0, column=3)
        ctk.CTkLabel(meta_frame, text=t("gui.review.reviewers")).grid(row=0, column=4, padx=(0, 4))
        self.reviewers_entry = ctk.CTkEntry(meta_frame,
                                             placeholder_text=t("gui.review.reviewers_ph"))
        self.reviewers_entry.grid(row=0, column=5, sticky="ew", padx=4)

        InfoTooltip.add(meta_frame, t("gui.tip.language"), row=1, column=0)
        ctk.CTkLabel(meta_frame, text=t("gui.review.language")).grid(row=1, column=1, padx=(0, 4), pady=(3, 0))

        # Review language dropdown (system / English / Japanese) – persisted
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
        self.spec_entry = ctk.CTkEntry(meta_frame, placeholder_text=t("gui.review.spec_placeholder"))
        self.spec_entry.grid(row=1, column=5, sticky="ew", padx=4, pady=(3, 0))
        row += 1

        # ── Action buttons ────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=row, column=0, sticky="ew", pady=(6, 2))
        self.run_btn = ctk.CTkButton(btn_frame, text=t("gui.review.start"),
                                      fg_color="green", hover_color="#228B22",
                                      command=self._start_review)
        self.run_btn.grid(row=0, column=0, padx=6)
        self.dry_btn = ctk.CTkButton(btn_frame, text=t("gui.review.dry_run"),
                                      command=self._start_dry_run)
        self.dry_btn.grid(row=0, column=1, padx=6)
        self.conn_btn = ctk.CTkButton(btn_frame, text=t("gui.review.test_connection"),
                                       command=self._test_connection)
        self.conn_btn.grid(row=0, column=2, padx=6)
        self.health_btn = ctk.CTkButton(btn_frame, text=t("health.check_btn"),
                                         command=self._check_backend_health)
        self.health_btn.grid(row=0, column=3, padx=6)

        self.progress = ctk.CTkProgressBar(tab, width=400)
        self.progress.grid(row=row + 1, column=0, sticky="ew", padx=6, pady=3)
        self.progress.set(0)
        row += 2

        # ── Inline Results Panel ──────────────────────────────────────────
        self._results_row = row
        self.results_summary = ctk.CTkLabel(tab, text="", anchor="w",
                                             font=ctk.CTkFont(weight="bold"))
        self.results_summary.grid(row=row, column=0, sticky="ew", padx=8, pady=(6, 2))
        self.results_summary.grid_remove()  # hidden until results exist
        row += 1

        self.results_frame = ctk.CTkScrollableFrame(tab)
        self.results_frame.grid(row=row, column=0, sticky="nsew", padx=8, pady=(0, 4))
        self.results_frame.grid_columnconfigure(0, weight=1)
        self.results_frame.grid_remove()

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
        row = [0]  # mutable counter

        def _section_header(text: str):
            ctk.CTkLabel(scroll, text=text,
                          font=ctk.CTkFont(size=14, weight="bold"),
                          anchor="w").grid(
                row=row[0], column=0, columnspan=4, sticky="w",
                padx=6, pady=(12, 4),
            )
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
                          values: list, tooltip_key: str = "",
                          var_store_name: str = ""):
            InfoTooltip.add(scroll, t(tooltip_key) if tooltip_key else label,
                            row=row[0], column=0)
            ctk.CTkLabel(scroll, text=label + ":").grid(
                row=row[0], column=1, sticky="w", padx=(0, 4), pady=3)
            var = ctk.StringVar(value=default)
            menu = ctk.CTkOptionMenu(scroll, variable=var, values=values,
                                      width=200)
            menu.grid(row=row[0], column=2, sticky="w", padx=6, pady=3)
            self._setting_entries[(section, key)] = var  # StringVar for dropdowns
            if var_store_name:
                setattr(self, var_store_name, var)
            row[0] += 1

        # ── General section ────────────────────────────────────────────────
        _section_header(t("gui.settings.section_general"))

        # Theme dropdown
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

        # Language dropdown
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

        _add_entry(t("gui.settings.backend"), "backend", "type",
                   config.get("backend", "type", "bedrock"),
                   tooltip_key="gui.tip.backend")

        # ── AWS Bedrock section ────────────────────────────────────────────
        _section_header(t("gui.settings.section_bedrock"))
        _add_entry(t("gui.settings.model_id"), "model", "model_id",
                   config.get("model", "model_id", ""),
                   tooltip_key="gui.tip.model_id")
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
        _section_header(t("gui.settings.section_kiro"))
        _add_entry(t("gui.settings.kiro_distro"), "kiro", "wsl_distro",
                   config.get("kiro", "wsl_distro", ""),
                   tooltip_key="gui.tip.kiro_distro")
        _add_entry(t("gui.settings.kiro_command"), "kiro", "cli_command",
                   config.get("kiro", "cli_command", "kiro"),
                   tooltip_key="gui.tip.kiro_command")
        _add_entry(t("gui.settings.kiro_timeout"), "kiro", "timeout",
                   config.get("kiro", "timeout", "300"),
                   tooltip_key="gui.tip.kiro_timeout")

        # ── GitHub Copilot section ─────────────────────────────────────────
        _section_header(t("gui.settings.section_copilot"))
        _add_entry(t("gui.settings.gh_path"), "copilot", "gh_path",
                   config.get("copilot", "gh_path", "gh"),
                   tooltip_key="gui.tip.gh_path")
        _add_entry(t("gui.settings.copilot_timeout"), "copilot", "timeout",
                   config.get("copilot", "timeout", "300"),
                   tooltip_key="gui.tip.copilot_timeout")
        _add_entry(t("gui.settings.copilot_model"), "copilot", "model",
                   config.get("copilot", "model", ""),
                   tooltip_key="gui.tip.copilot_model")

        # ── Local LLM section ─────────────────────────────────────────────
        _section_header(t("gui.settings.section_local"))
        _add_entry(t("gui.settings.local_api_url"), "local_llm", "api_url",
                   config.get("local_llm", "api_url", "http://localhost:1234/v1"),
                   tooltip_key="gui.tip.local_api_url")
        _add_entry(t("gui.settings.local_api_type"), "local_llm", "api_type",
                   config.get("local_llm", "api_type", "openai"),
                   tooltip_key="gui.tip.local_api_type")
        _add_entry(t("gui.settings.local_model"), "local_llm", "model",
                   config.get("local_llm", "model", "default"),
                   tooltip_key="gui.tip.local_model")
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
        max_fs = max_fs_raw // (1024 * 1024) if isinstance(max_fs_raw, int) and max_fs_raw > 100 else max_fs_raw
        _add_entry(t("gui.settings.max_file_size"), "performance",
                   "max_file_size_mb", str(max_fs),
                   tooltip_key="gui.tip.max_file_size")
        _add_entry(t("gui.settings.batch_size"), "processing", "batch_size",
                   str(config.get("processing", "batch_size", 5)),
                   tooltip_key="gui.tip.batch_size")

        # ── Note + save button ─────────────────────────────────────────────
        note = ctk.CTkLabel(scroll, text=t("gui.settings.restart_note"),
                             text_color="gray50", font=ctk.CTkFont(size=11))
        note.grid(row=row[0], column=0, columnspan=4, pady=(10, 2))
        row[0] += 1

        save_btn = ctk.CTkButton(scroll, text=t("gui.settings.save"),
                                  command=self._save_settings)
        save_btn.grid(row=row[0], column=0, columnspan=4, pady=8)

    # ══════════════════════════════════════════════════════════════════════
    #  LOG TAB
    # ══════════════════════════════════════════════════════════════════════

    def _build_log_tab(self):
        tab = self.tabs.add(t("gui.tab.log"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.log_box = ctk.CTkTextbox(tab, state="disabled", wrap="word",
                                       font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        clear_btn = ctk.CTkButton(tab, text=t("gui.log.clear"), width=100,
                                   command=self._clear_log)
        clear_btn.grid(row=1, column=0, pady=4)

    # ══════════════════════════════════════════════════════════════════════
    #  ACTIONS – file browsing, validation, review execution
    # ══════════════════════════════════════════════════════════════════════

    def _browse_path(self):
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

    def _get_selected_types(self) -> List[str]:
        return [k for k, v in self.type_vars.items() if v.get()]

    def _validate_inputs(self, dry_run: bool = False) -> Optional[dict]:
        """Validate form and return a params dict, or None on failure."""
        path = self.path_entry.get().strip()
        scope = self.scope_var.get()
        diff_file = self.diff_file_entry.get().strip() or None
        commits = self.commits_entry.get().strip() or None

        if scope == "project" and not path:
            messagebox.showerror(t("common.validation"), t("gui.val.path_required"))
            return None
        if scope == "diff" and not diff_file and not commits:
            messagebox.showerror(t("common.validation"), t("gui.val.diff_required"))
            return None

        review_types = self._get_selected_types()
        if not review_types:
            messagebox.showerror(t("common.validation"), t("gui.val.type_required"))
            return None

        programmers = [n.strip() for n in self.programmers_entry.get().split(",") if n.strip()] if not dry_run else []
        reviewers = [n.strip() for n in self.reviewers_entry.get().split(",") if n.strip()] if not dry_run else []

        if not dry_run and (not programmers or not reviewers):
            messagebox.showerror(t("common.validation"), t("gui.val.meta_required"))
            return None

        spec_content = None
        spec_path = self.spec_entry.get().strip()
        if "specification" in review_types and spec_path:
            try:
                with open(spec_path, "r", encoding="utf-8") as fh:
                    spec_content = fh.read()
            except Exception as exc:
                messagebox.showerror(t("common.validation"),
                                      t("gui.val.spec_read_error", error=exc))
                return None

        # Resolve review language display label to language code
        lang_display = self.lang_var.get()
        review_lang = self._review_lang_reverse.get(lang_display, "system")
        if review_lang == "system":
            review_lang = self._ui_lang
        # Persist choice
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
        )

    def _start_review(self):
        if self._running:
            return
        params = self._validate_inputs()
        if not params:
            return
        self._run_review(params, dry_run=False)

    def _start_dry_run(self):
        if self._running:
            return
        params = self._validate_inputs(dry_run=True)
        if not params:
            return
        self._run_review(params, dry_run=True)

    def _run_review(self, params: dict, dry_run: bool):
        """Execute the review in a background thread."""
        self._running = True
        self.run_btn.configure(state="disabled")
        self.dry_btn.configure(state="disabled")
        self.progress.set(0)
        self.status_var.set(t("common.running"))

        def _worker():
            try:
                backend_name = params.pop("backend")
                client = None if dry_run else create_backend(backend_name)
                self._review_client = client
                runner = AppRunner(client, scan_fn=scan_project_with_scope,
                                   backend_name=backend_name)

                def progress_cb(current, total, msg):
                    if total > 0:
                        self.progress.set(current / total)
                    self.status_var.set(f"{msg} {current}/{total}")

                report_path = runner.run(
                    **params,
                    dry_run=dry_run,
                    progress_callback=progress_cb,
                )
                self._issues = (runner.client
                                and getattr(runner, '_last_issues', [])
                                or [])
                if report_path:
                    self.after(0, lambda: self._show_inline_results(report_path))
                else:
                    self.after(0, lambda: self.status_var.set(t("gui.val.no_report")))
            except Exception as exc:
                logger.error("Review failed: %s", exc)
                self.after(0, lambda: messagebox.showerror(t("common.error"),
                                                            str(exc)))
            finally:
                self._running = False
                self.after(0, lambda: self.run_btn.configure(state="normal"))
                self.after(0, lambda: self.dry_btn.configure(state="normal"))
                self.after(0, lambda: self.progress.set(1.0))

        threading.Thread(target=_worker, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════
    #  INLINE RESULTS  – displayed below the review form
    # ══════════════════════════════════════════════════════════════════════

    def _show_inline_results(self, report_path: str):
        """Load a JSON report and populate inline results on the Review tab."""
        import json
        from aicodereviewer.models import ReviewReport

        self.status_var.set(t("gui.val.report_saved", path=report_path))

        try:
            with open(report_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            report = ReviewReport.from_dict(data)
        except Exception as exc:
            self.results_summary.configure(
                text=t("gui.val.report_load_error", error=exc))
            self.results_summary.grid()
            return

        # Show results panel
        self.results_summary.grid()
        self.results_frame.grid()

        # Clear old results
        for w in self.results_frame.winfo_children():
            w.destroy()

        types_str = (", ".join(report.review_types)
                     if report.review_types else report.review_type)
        self.results_summary.configure(
            text=t("gui.results.summary",
                   score=report.quality_score,
                   issues=len(report.issues_found),
                   types=types_str,
                   backend=report.backend))

        if not report.issues_found:
            ctk.CTkLabel(self.results_frame,
                          text=t("gui.results.no_results")).grid(
                row=0, column=0, padx=8, pady=8)
            return

        for i, issue in enumerate(report.issues_found):
            self._add_issue_card(i, issue)

    def _add_issue_card(self, index: int, issue: ReviewIssue):
        """Add a single issue card to the inline results frame."""
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

        desc = issue.description[:120]
        ctk.CTkLabel(card, text=desc, anchor="w", wraplength=700).grid(
            row=1, column=0, columnspan=6, sticky="w", padx=6)

        # Status label
        status_map = {
            "resolved": ("gui.results.resolved", "green"),
            "ignored": ("gui.results.ignored", "gray50"),
            "skipped": ("gui.results.skipped", "gray50"),
        }
        s_key, s_color = status_map.get(
            issue.status, ("gui.results.pending", color))
        status_lbl = ctk.CTkLabel(card, text=t(s_key), text_color=s_color)
        status_lbl.grid(row=2, column=0, sticky="w", padx=6, pady=(0, 4))

        # Action buttons
        btn_kw = dict(width=65, height=26,
                      font=ctk.CTkFont(size=11))
        ctk.CTkButton(
            card, text=t("gui.results.action_view"), **btn_kw,
            command=lambda iss=issue: self._show_issue_detail(iss),
        ).grid(row=2, column=2, padx=2, pady=(0, 4))

        ctk.CTkButton(
            card, text=t("gui.results.action_fix"), **btn_kw,
            fg_color="#2563eb",
            command=lambda iss=issue, c=card, sl=status_lbl:
                self._ai_fix_issue(iss, c, sl),
        ).grid(row=2, column=3, padx=2, pady=(0, 4))

        ctk.CTkButton(
            card, text=t("gui.results.action_resolve"), **btn_kw,
            fg_color="green",
            command=lambda iss=issue, sl=status_lbl:
                self._resolve_issue(iss, sl),
        ).grid(row=2, column=4, padx=2, pady=(0, 4))

        ctk.CTkButton(
            card, text=t("gui.results.action_skip"), **btn_kw,
            fg_color="gray50",
            command=lambda iss=issue, sl=status_lbl:
                self._skip_issue(iss, sl),
        ).grid(row=2, column=5, padx=2, pady=(0, 4))

    def _resolve_issue(self, issue: ReviewIssue, status_lbl):
        issue.status = "resolved"
        status_lbl.configure(text=t("gui.results.resolved"),
                              text_color="green")

    def _skip_issue(self, issue: ReviewIssue, status_lbl):
        issue.status = "skipped"
        status_lbl.configure(text=t("gui.results.skipped"),
                              text_color="gray50")

    def _ai_fix_issue(self, issue: ReviewIssue, card, status_lbl):
        """Generate an AI fix for an issue in a background thread."""
        if not self._review_client:
            messagebox.showinfo(t("common.error"),
                                 t("gui.results.no_fix"))
            return

        status_lbl.configure(text=t("gui.results.applying_fix"),
                              text_color="#2563eb")

        def _worker():
            try:
                code = ""
                try:
                    with open(issue.file_path, "r", encoding="utf-8") as fh:
                        code = fh.read()
                except Exception:
                    pass

                fix = self._review_client.get_fix(
                    code_content=code,
                    issue_feedback=issue.ai_feedback or issue.description,
                    review_type=issue.issue_type,
                    lang=self.lang_var.get(),
                )
                if fix:
                    self.after(0, lambda: self._show_fix_popup(
                        issue, fix, status_lbl))
                else:
                    self.after(0, lambda: status_lbl.configure(
                        text=t("gui.results.no_fix"),
                        text_color="#dc2626"))
            except Exception as exc:
                logger.error("AI fix failed: %s", exc)
                self.after(0, lambda: status_lbl.configure(
                    text=t("gui.results.no_fix"),
                    text_color="#dc2626"))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_fix_popup(self, issue: ReviewIssue, fix: str, status_lbl):
        """Show a popup with the proposed fix."""
        win = ctk.CTkToplevel(self)
        win.title(t("gui.results.fix_ready"))
        win.geometry("750x500")
        win.grab_set()

        ctk.CTkLabel(win, text=t("gui.results.fix_ready"),
                      font=ctk.CTkFont(weight="bold")).pack(
            padx=10, pady=(10, 4))

        text = ctk.CTkTextbox(win, wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=4)
        text.insert("0.0", fix)
        text.configure(state="disabled")

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=8)

        def _apply():
            try:
                with open(issue.file_path, "w", encoding="utf-8") as fh:
                    fh.write(fix)
                issue.status = "resolved"
                status_lbl.configure(text=t("gui.results.resolved"),
                                      text_color="green")
            except Exception as exc:
                messagebox.showerror(t("common.error"), str(exc))
            win.destroy()

        ctk.CTkButton(btn_frame, text=t("common.yes"), fg_color="green",
                       command=_apply).grid(row=0, column=0, padx=6)
        ctk.CTkButton(btn_frame, text=t("common.cancel"),
                       command=win.destroy).grid(row=0, column=1, padx=6)

    def _show_issue_detail(self, issue: ReviewIssue):
        """Show a detail popup for an issue."""
        win = ctk.CTkToplevel(self)
        win.title(t("gui.results.issue_title", type=issue.issue_type))
        win.geometry("700x500")
        win.grab_set()

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

    # ══════════════════════════════════════════════════════════════════════
    #  SETTINGS save
    # ══════════════════════════════════════════════════════════════════════

    def _save_settings(self):
        # Reverse-map theme / language display values to config keys
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
                # Translate display values back to config values
                if section == "gui" and key == "theme":
                    raw = theme_reverse.get(raw, "system")
                elif section == "gui" and key == "language":
                    raw = lang_reverse.get(raw, "system")
                config.set_value(section, key, raw)
            else:
                config.set_value(section, key, widget.get().strip())

        # Apply theme immediately
        theme_val = config.get("gui", "theme", "system")
        theme_map = {"system": "System", "dark": "Dark", "light": "Light"}
        ctk.set_appearance_mode(theme_map.get(theme_val, "System"))

        try:
            config.save()
            messagebox.showinfo(t("common.settings"),
                                 t("gui.settings.saved_ok"))
        except Exception as exc:
            messagebox.showerror(t("common.error"),
                                  t("gui.settings.save_error", error=exc))

    # ══════════════════════════════════════════════════════════════════════
    #  CONNECTION TEST
    # ══════════════════════════════════════════════════════════════════════

    def _test_connection(self):
        """Test the selected backend's connectivity in a background thread."""
        if self._running:
            return
        backend_name = self.backend_var.get()
        self.status_var.set(t("gui.conn.testing", backend=backend_name))
        self.conn_btn.configure(state="disabled")

        def _worker():
            details = ""
            try:
                client = create_backend(backend_name)
                ok = client.validate_connection()

                if backend_name == "bedrock":
                    details = (
                        f"{t('conn.details_model', model=config.get('model', 'model_id', ''))}\n"
                        f"{t('conn.details_region', region=config.get('aws', 'region', ''))}")
                elif backend_name == "local":
                    details = (
                        f"{t('conn.details_url', url=config.get('local_llm', 'api_url', ''))}\n"
                        f"{t('conn.details_model', model=config.get('local_llm', 'model', ''))}")
            except Exception as exc:
                ok = False
                details = str(exc)

            if ok:
                msg = t("gui.conn.success", backend=backend_name,
                        details=details)
                self.after(0, lambda: messagebox.showinfo(
                    t("gui.conn.title"), msg))
            else:
                hints = ""
                if backend_name == "bedrock":
                    hints = (f"\n{t('conn.hint_bedrock_sso')}\n"
                             f"{t('conn.hint_bedrock_profile')}\n"
                             f"{t('conn.hint_bedrock_model')}")
                elif backend_name == "kiro":
                    hints = (f"\n{t('conn.hint_kiro_wsl')}\n"
                             f"{t('conn.hint_kiro_cli')}")
                elif backend_name == "copilot":
                    hints = (f"\n{t('conn.hint_copilot_gh')}\n"
                             f"{t('conn.hint_copilot_auth')}\n"
                             f"{t('conn.hint_copilot_ext')}")
                elif backend_name == "local":
                    hints = (f"\n{t('conn.hint_local_url')}\n"
                             f"{t('conn.hint_local_model')}\n"
                             f"{t('conn.hint_local_api_type')}")
                msg = t("gui.conn.failure", backend=backend_name,
                        details=details + hints)
                self.after(0, lambda: messagebox.showerror(
                    t("gui.conn.title"), msg))

            self.after(0, lambda: self.conn_btn.configure(state="normal"))
            self.after(0, lambda: self.status_var.set(t("common.ready")))

        threading.Thread(target=_worker, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════
    #  BACKEND HEALTH CHECK
    # ══════════════════════════════════════════════════════════════════════

    def _on_backend_changed(self, *_args):
        """Called when the backend radio button changes — save and re-check."""
        backend_name = self.backend_var.get()
        config.set_value("backend", "type", backend_name)
        try:
            config.save()
        except Exception:
            pass
        # Run silent health check for the new backend
        self._auto_health_check()

    def _auto_health_check(self):
        """Run health check silently; show dialog only if something fails."""
        if self._running:
            return
        backend_name = self.backend_var.get()
        self.status_var.set(t("health.checking", backend=backend_name))

        def _worker():
            report = check_backend(backend_name)
            if report.ready:
                self.after(0, lambda: self.status_var.set(
                    t("health.auto_ok", backend=backend_name)))
            else:
                self.after(0, lambda: self._show_health_dialog(report))
                self.after(0, lambda: self.status_var.set(t("common.ready")))

        threading.Thread(target=_worker, daemon=True).start()

    def _check_backend_health(self):
        """Run prerequisite health checks for the selected backend (manual)."""
        if self._running:
            return
        backend_name = self.backend_var.get()
        self.status_var.set(t("health.checking", backend=backend_name))
        self.health_btn.configure(state="disabled")

        def _worker():
            report = check_backend(backend_name)
            self.after(0, lambda: self._show_health_dialog(report))
            self.after(0, lambda: self.health_btn.configure(state="normal"))
            self.after(0, lambda: self.status_var.set(t("common.ready")))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_health_dialog(self, report):
        """Show a dialog with health check results."""
        win = ctk.CTkToplevel(self)
        win.title(t("health.dialog_title"))
        win.geometry("600x450")
        win.grab_set()

        # Summary
        summary_color = "green" if report.ready else "#dc2626"
        ctk.CTkLabel(win, text=report.summary,
                      text_color=summary_color,
                      font=ctk.CTkFont(size=14, weight="bold")).pack(
            padx=10, pady=(10, 6))

        # Checks list
        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=10, pady=4)
        scroll.grid_columnconfigure(1, weight=1)

        for i, check in enumerate(report.checks):
            icon = "✅" if check.passed else "❌"
            color = "green" if check.passed else "#dc2626"

            ctk.CTkLabel(scroll, text=icon, width=24).grid(
                row=i * 3, column=0, sticky="nw", padx=(4, 2), pady=(4, 0))
            ctk.CTkLabel(scroll, text=check.name,
                          font=ctk.CTkFont(weight="bold"),
                          text_color=color).grid(
                row=i * 3, column=1, sticky="w", padx=4, pady=(4, 0))
            ctk.CTkLabel(scroll, text=check.detail, anchor="w",
                          wraplength=450,
                          text_color=("gray30", "gray70")).grid(
                row=i * 3 + 1, column=1, sticky="w", padx=4)

            if check.fix_hint and not check.passed:
                ctk.CTkLabel(scroll, text=f"💡 {check.fix_hint}",
                              anchor="w", wraplength=450,
                              text_color="#2563eb",
                              font=ctk.CTkFont(size=11)).grid(
                    row=i * 3 + 2, column=1, sticky="w", padx=4,
                    pady=(0, 4))

        ctk.CTkButton(win, text=t("common.close"),
                       command=win.destroy).pack(pady=8)

    # ══════════════════════════════════════════════════════════════════════
    #  LOG handling
    # ══════════════════════════════════════════════════════════════════════

    def _install_log_handler(self):
        handler = QueueLogHandler(self._log_queue)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(handler)

    def _poll_log_queue(self):
        """Drain the log queue into the log textbox."""
        batch = []
        while True:
            try:
                batch.append(self._log_queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", "\n".join(batch) + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(100, self._poll_log_queue)

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("0.0", "end")
        self.log_box.configure(state="disabled")


# ── public launcher ────────────────────────────────────────────────────────

def launch():
    """Create and run the application."""
    app = App()
    app.mainloop()
