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
import configparser
import difflib
import logging
import re
import subprocess
import threading
import queue
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional, TypedDict

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.backends import create_backend
from aicodereviewer.backends.base import REVIEW_TYPE_KEYS, REVIEW_TYPE_META
from aicodereviewer.backends.health import (
    check_backend,
    get_copilot_models,
    get_bedrock_models,
    get_local_models,
)
from aicodereviewer.config import config
from aicodereviewer.auth import get_system_language
from aicodereviewer.scanner import (
    scan_project_with_scope,
    scan_project,
    parse_diff_file,
    get_diff_from_commits,
)
from aicodereviewer.orchestration import AppRunner
from aicodereviewer.reviewer import verify_issue_resolved
from aicodereviewer.models import ReviewIssue
from aicodereviewer.i18n import t, set_locale

logger = logging.getLogger(__name__)


class _CancelledError(Exception):
    """Raised when the user cancels a running operation."""


# ── queue-based log handler for the GUI ────────────────────────────────────

class QueueLogHandler(logging.Handler):
    """Send log records to a :class:`queue.Queue` for GUI consumption."""

    def __init__(self, log_queue: queue.Queue[str]):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord):
        try:
            self.log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass


# ── tooltip helper ─────────────────────────────────────────────────────────

class InfoTooltip:
    """Attach a hover tooltip to any widget via an 🛈 icon label."""

    @staticmethod
    def add(parent: Any, text: str, row: int, column: int, **grid_kw: Any):
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

    def __init__(self, widget: Any, text: str):
        self.widget = widget
        self.text = text
        self._tipwindow: Any = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event: Any = None):
        if self._tipwindow:
            return
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

    def _hide(self, event: Any = None):
        if self._tipwindow:
            self._tipwindow.destroy()
            self._tipwindow = None


# ── File Selector Window ───────────────────────────────────────────────────

class FileSelector(ctk.CTkToplevel):
    """Custom file selector window with tree structure and checkboxes."""
    
    def __init__(self, parent: Any, project_path: str, preselected: List[str]):
        super().__init__(parent)
        self.result = []
        self.project_path = Path(project_path)
        self.preselected = set(preselected)
        self.file_vars = {}  # Maps file path to BooleanVar
        
        self.title("Select Files for Review")
        self.geometry("700x600")
        
        # Make window modal
        self.transient(parent)
        self.grab_set()
        
        # Build UI
        self._build_ui()
        
        # Center window
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
    
    def _build_ui(self):
        """Build the file selector UI shell, then scan for files in the background."""
        # Header with select all/deselect all
        header_frame = ctk.CTkFrame(self)
        header_frame.pack(fill="x", padx=10, pady=10)

        self.select_all_var = ctk.BooleanVar(value=False)
        select_all_cb = ctk.CTkCheckBox(header_frame, text="Select All / Deselect All",
                                        variable=self.select_all_var,
                                        command=self._toggle_all)
        select_all_cb.pack(side="left", padx=5)

        # Scrollable file tree (populated asynchronously)
        self._file_frame = ctk.CTkScrollableFrame(self, label_text="Reviewable Files")
        self._file_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Loading indicator shown while the background scan runs
        self._loading_lbl = ctk.CTkLabel(
            self._file_frame, text="⏳ Scanning project files…",
            text_color=("gray40", "gray60"))
        self._loading_lbl.pack(pady=20)

        # Bottom buttons — OK disabled until scan completes
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        self._ok_btn = ctk.CTkButton(btn_frame, text="OK", width=100,
                                     state="disabled", command=self._on_ok)
        self._ok_btn.pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", width=100,
                      command=self._on_cancel).pack(side="right", padx=5)

        # Run the potentially-slow scan off the main thread
        threading.Thread(target=self._scan_files, daemon=True).start()

    def _scan_files(self) -> None:
        """Run scan_project in a background thread, then hand results to GUI thread."""
        try:
            files = scan_project(str(self.project_path))
        except Exception:
            files = []
        # Schedule the tree population back on the Tk main thread
        try:
            self.after(0, lambda: self._populate_tree(files))
        except Exception:
            pass  # window may have been closed before scan finished

    def _populate_tree(self, files: List[Path]) -> None:
        """Called on the main thread once the background scan finishes."""
        # Remove loading indicator
        self._loading_lbl.destroy()

        if not files:
            ctk.CTkLabel(self._file_frame,
                         text="No reviewable files found in project").pack(pady=20)
        else:
            self._build_file_tree(self._file_frame, files)

        # Enable OK now that the tree is ready
        self._ok_btn.configure(state="normal")
    
    def _build_file_tree(self, parent_frame: Any, files: List[Path]):
        """Build the file tree with checkboxes."""
        # Organize files by directory
        tree_dict = {}
        for file_path in sorted(files):
            try:
                rel_path = file_path.relative_to(self.project_path)
            except ValueError:
                continue
            
            parts = rel_path.parts
            current = tree_dict
            for part in parts[:-1]:  # Directories
                if part not in current:
                    current[part] = {}
                current = current[part]
            
            # File (leaf node)
            filename = parts[-1]
            current[filename] = str(file_path)
        
        # Render the tree
        self._render_tree(parent_frame, tree_dict, indent=0)
    
    def _render_tree(self, parent_frame: Any, tree_dict: Dict[str, Any], indent: int):
        """Recursively render the file tree."""
        for key in sorted(tree_dict.keys()):
            value = tree_dict[key]
            
            if isinstance(value, dict):
                # Directory
                dir_label = ctk.CTkLabel(parent_frame, text="📁 " + key,
                                        anchor="w", text_color=("gray30", "gray70"))
                dir_label.pack(fill="x", padx=(indent * 20, 0), pady=1)
                
                # Recursively render children
                self._render_tree(parent_frame, value, indent + 1)
            else:
                # File - add checkbox
                file_path = value
                is_selected = file_path in self.preselected
                
                var = ctk.BooleanVar(value=is_selected)
                self.file_vars[file_path] = var
                
                cb = ctk.CTkCheckBox(parent_frame, text="📄 " + key,
                                    variable=var, width=500)
                cb.pack(fill="x", anchor="w", padx=(indent * 20, 0), pady=1)
    
    def _toggle_all(self):
        """Select or deselect all files."""
        value = self.select_all_var.get()
        for var in self.file_vars.values():
            var.set(value)
    
    def _on_ok(self):
        """Collect selected files and close."""
        self.result = [path for path, var in self.file_vars.items() if var.get()]
        self.grab_release()
        self.destroy()
    
    def _on_cancel(self):
        """Close without saving."""
        self.result = self.preselected
        self.grab_release()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════

class IssueCard(TypedDict):
    """Type-safe record stored in ``App._issue_cards``."""
    issue: "ReviewIssue"
    card: Any
    status_lbl: Any
    view_btn: Any
    resolve_btn: Any
    skip_btn: Any
    fix_checkbox: Any
    fix_check_var: Any
    skip_frame: Any
    skip_entry: Any
    color: str


class App(ctk.CTk):
    """Root window of the AICodeReviewer GUI."""

    WIDTH = 1100
    HEIGHT = 820

    def __init__(self, *, testing_mode: bool = False):
        super().__init__()
        self._testing_mode = testing_mode

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
        self._log_queue: queue.Queue[str] = queue.Queue(maxsize=5000)
        self._install_log_handler()

        # State
        self._issues: List[ReviewIssue] = []
        self._running = False
        self._review_client = None  # keep reference for AI fix
        self._health_check_backend = None  # Track which backend is being checked
        self._health_check_timer = None    # Timeout timer for health checks
        self._model_refresh_in_progress: set[str] = set()  # Track background refreshes

        # Forward declarations for dynamically-set attributes
        self._settings_backend_var: Any = None
        self._copilot_model_combo: Any = None
        self._bedrock_model_combo: Any = None
        self._local_model_combo: Any = None
        self._review_runner: Optional[AppRunner] = None

        # Layout
        self._build_ui()
        self._poll_log_queue()

        # Refresh model list for current backend in background (non-blocking)
        if not self._testing_mode:
            self.after(100, self._refresh_current_backend_models_async)

            # Auto-run health check on startup (silent if all pass)
            self.after(500, self._auto_health_check)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(self, anchor="nw")
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self._build_review_tab()
        self._build_results_tab()
        self._build_settings_tab()
        self._build_log_tab()

        # Bottom status bar with cancel button
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 6))
        status_frame.grid_columnconfigure(0, weight=1)

        self.status_var = ctk.StringVar(value=t("common.ready"))
        status = ctk.CTkLabel(status_frame, textvariable=self.status_var,
                              anchor="w")
        status.grid(row=0, column=0, sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            status_frame, text=t("gui.cancel_btn"), width=80,
            fg_color="#dc2626", hover_color="#b91c1c",
            state="disabled", command=self._cancel_operation)
        self.cancel_btn.grid(row=0, column=1, padx=(8, 0))

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
        self.file_select_mode_var = ctk.StringVar(value="all")
        self.file_select_mode_var.trace_add("write", self._on_file_select_mode_changed)
        ctk.CTkRadioButton(self.file_select_frame, text="All Files",
                            variable=self.file_select_mode_var, value="all").grid(row=0, column=0, padx=6, sticky="w")
        file_select_rb = ctk.CTkRadioButton(self.file_select_frame, text="Selected Files",
                            variable=self.file_select_mode_var, value="selected")
        file_select_rb.grid(row=0, column=1, padx=6, sticky="w")
        self.select_files_btn = ctk.CTkButton(self.file_select_frame, text="Select Files...", width=120,
                                              command=self._open_file_selector, state="disabled")
        self.select_files_btn.grid(row=0, column=2, padx=6, sticky="w")
        self.selected_files: List[str] = []  # Store selected file paths

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
        
        # Load saved programmers
        saved_programmers = config.get("gui", "programmers", "").strip()
        self.programmers_entry = ctk.CTkEntry(meta_frame,
                                               placeholder_text=t("gui.review.programmers_ph"))
        if saved_programmers:
            self.programmers_entry.insert(0, saved_programmers)
        self.programmers_entry.grid(row=0, column=2, sticky="ew", padx=4)

        InfoTooltip.add(meta_frame, t("gui.tip.reviewers"), row=0, column=3)
        ctk.CTkLabel(meta_frame, text=t("gui.review.reviewers")).grid(row=0, column=4, padx=(0, 4))
        
        # Load saved reviewers
        saved_reviewers = config.get("gui", "reviewers", "").strip()
        self.reviewers_entry = ctk.CTkEntry(meta_frame,
                                             placeholder_text=t("gui.review.reviewers_ph"))
        if saved_reviewers:
            self.reviewers_entry.insert(0, saved_reviewers)
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
        
        # Load saved spec file
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
        self.dry_btn = ctk.CTkButton(btn_frame, text=t("gui.review.dry_run"),
                                      command=self._start_dry_run)
        self.dry_btn.grid(row=0, column=1, padx=6)
        self.health_btn = ctk.CTkButton(btn_frame, text=t("health.check_btn"),
                                         command=self._check_backend_health)
        self.health_btn.grid(row=0, column=2, padx=6)

        self.progress = ctk.CTkProgressBar(tab, width=400)
        self.progress.grid(row=row + 1, column=0, sticky="ew", padx=6, pady=3)
        self.progress.set(0)

    # ══════════════════════════════════════════════════════════════════════
    #  RESULTS TAB  – full-page issue cards
    # ══════════════════════════════════════════════════════════════════════

    def _build_results_tab(self):
        tab = self.tabs.add(t("gui.tab.results"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        self.results_summary = ctk.CTkLabel(tab, text=t("gui.results.no_results"),
                                             anchor="w",
                                             font=ctk.CTkFont(weight="bold"))
        self.results_summary.grid(row=0, column=0, sticky="ew",
                                   padx=8, pady=(6, 2))

        self.results_frame = ctk.CTkScrollableFrame(tab)
        self.results_frame.grid(row=1, column=0, sticky="nsew",
                                 padx=8, pady=(0, 4))
        self.results_frame.grid_columnconfigure(0, weight=1)

        # Bottom action buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 6))

        # Normal mode buttons
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
        self._ai_fix_running = False  # Track if batch AI fix is currently running

        # Tracking state for issue cards
        self._issue_cards: List[IssueCard] = []

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
        self._backend_section_labels = {}  # Track section header labels
        row = [0]  # mutable counter

        def _section_header(text: str, backend_key: str = ""):
            """Create a section header, optionally with an 'active' indicator."""
            header_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            header_frame.grid(row=row[0], column=0, columnspan=4, sticky="ew",
                              padx=6, pady=(12, 4))
            header_frame.grid_columnconfigure(1, weight=1)
            
            lbl = ctk.CTkLabel(header_frame, text=text,
                               font=ctk.CTkFont(size=14, weight="bold"),
                               anchor="w")
            lbl.grid(row=0, column=0, sticky="w")
            
            # Add "active" indicator label for backend sections
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
            self._setting_entries[(section, key)] = var  # StringVar for dropdowns
            if var_store_name:
                setattr(self, var_store_name, var)
            row[0] += 1

        def _add_combobox(label: str, section: str, key: str, default: str,
                          values: List[str], tooltip_key: str = "",
                          widget_store_name: str = ""):
            """Editable combobox – user can type freely or pick from the list."""
            InfoTooltip.add(scroll, t(tooltip_key) if tooltip_key else label,
                            row=row[0], column=0)
            ctk.CTkLabel(scroll, text=label + ":").grid(
                row=row[0], column=1, sticky="w", padx=(0, 4), pady=3)
            combo = ctk.CTkComboBox(scroll, values=values, width=200)
            combo.set(default)
            combo.grid(row=row[0], column=2, sticky="ew", padx=6, pady=3)
            self._setting_entries[(section, key)] = combo
            if widget_store_name:
                setattr(self, widget_store_name, combo)
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

        # Backend dropdown (maps display name to internal value)
        self._backend_display_map = {
            "bedrock": t("gui.settings.backend_bedrock"),
            "kiro": t("gui.settings.backend_kiro"),
            "copilot": t("gui.settings.backend_copilot"),
            "local": t("gui.settings.backend_local"),
        }
        self._backend_reverse_map = {v: k for k, v in self._backend_display_map.items()}
        saved_backend = config.get("backend", "type", "bedrock")
        backend_display = self._backend_display_map.get(saved_backend, 
                                                         t("gui.settings.backend_bedrock"))
        _add_dropdown(t("gui.settings.backend"), "backend", "type",
                      backend_display,
                      list(self._backend_display_map.values()),
                      tooltip_key="gui.tip.backend",
                      var_store_name="_settings_backend_var")

        # ── AWS Bedrock section ────────────────────────────────────────────
        _section_header(t("gui.settings.section_bedrock"), backend_key="bedrock")
        _add_combobox(t("gui.settings.model_id"), "model", "model_id",
                      config.get("model", "model_id", ""),
                      [],  # populated dynamically
                      tooltip_key="gui.tip.model_id",
                      widget_store_name="_bedrock_model_combo")
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
        _section_header(t("gui.settings.section_copilot"), backend_key="copilot")
        _add_entry(t("gui.settings.copilot_path"), "copilot", "copilot_path",
                   config.get("copilot", "copilot_path", "copilot"),
                   tooltip_key="gui.tip.copilot_path")
        _add_entry(t("gui.settings.copilot_timeout"), "copilot", "timeout",
                   config.get("copilot", "timeout", "300"),
                   tooltip_key="gui.tip.copilot_timeout")
        _add_combobox(t("gui.settings.copilot_model"), "copilot", "model",
                      config.get("copilot", "model", "auto"),
                      ["auto"],  # populated after Check Setup
                      tooltip_key="gui.tip.copilot_model",
                      widget_store_name="_copilot_model_combo")

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
                      [],  # populated dynamically
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
        max_fs = max_fs_raw // (1024 * 1024) if isinstance(max_fs_raw, int) and max_fs_raw > 100 else max_fs_raw
        _add_entry(t("gui.settings.max_file_size"), "performance",
                   "max_file_size_mb", str(max_fs),
                   tooltip_key="gui.tip.max_file_size")
        _add_entry(t("gui.settings.batch_size"), "processing", "batch_size",
                   str(config.get("processing", "batch_size", 5)),
                   tooltip_key="gui.tip.batch_size")
        combine_val = str(config.get("processing", "combine_files", "true")).lower()
        _add_dropdown(t("gui.settings.combine_files"), "processing",
                      "combine_files", combine_val,
                      ["true", "false"],
                      tooltip_key="gui.tip.combine_files")

        # ── Editor section ────────────────────────────────────────────────
        _section_header(t("gui.settings.section_editor"))
        _add_entry(t("gui.settings.editor_command"), "gui", "editor_command",
                   config.get("gui", "editor_command", ""),
                   tooltip_key="gui.tip.editor_command")

        # ── Report Output Formats ──────────────────────────────────────────
        _section_header("Review Report Output Formats")
        
        # Load saved formats or default to all enabled
        saved_formats = config.get("output", "formats", "json,txt").strip()
        enabled_formats = set(saved_formats.split(",")) if saved_formats else {"json", "txt"}
        
        # Add tooltip and description
        InfoTooltip.add(scroll, "Select which file formats to generate for review reports. At least one format must be selected.",
                        row=row[0], column=0)
        ctk.CTkLabel(scroll, text="Output Formats:").grid(
            row=row[0], column=1, sticky="w", padx=(0, 4), pady=3)
        
        # Create frame for checkboxes
        formats_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        formats_frame.grid(row=row[0], column=2, sticky="w", padx=6, pady=3)
        
        # Store checkbox variables
        self._format_vars = {}
        
        # JSON checkbox
        json_var = ctk.BooleanVar(value=("json" in enabled_formats))
        json_cb = ctk.CTkCheckBox(formats_frame, text="JSON", variable=json_var)
        json_cb.grid(row=0, column=0, padx=(0, 15), sticky="w")
        self._format_vars["json"] = json_var
        
        # TXT checkbox
        txt_var = ctk.BooleanVar(value=("txt" in enabled_formats))
        txt_cb = ctk.CTkCheckBox(formats_frame, text="TXT", variable=txt_var)
        txt_cb.grid(row=0, column=1, padx=(0, 15), sticky="w")
        self._format_vars["txt"] = txt_var
        
        # MD checkbox
        md_var = ctk.BooleanVar(value=("md" in enabled_formats))
        md_cb = ctk.CTkCheckBox(formats_frame, text="Markdown (MD)", variable=md_var)
        md_cb.grid(row=0, column=2, padx=(0, 15), sticky="w")
        self._format_vars["md"] = md_var
        
        row[0] += 1

        # ── Note + save button ─────────────────────────────────────────────
        note = ctk.CTkLabel(scroll, text=t("gui.settings.restart_note"),
                             text_color="gray50", font=ctk.CTkFont(size=11))
        note.grid(row=row[0], column=0, columnspan=4, pady=(10, 2))
        row[0] += 1

        # Button container
        button_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        button_frame.grid(row=row[0], column=0, columnspan=4, pady=8)
        
        save_btn = ctk.CTkButton(button_frame, text=t("gui.settings.save"),
                                  command=self._save_settings)
        save_btn.grid(row=0, column=0, padx=(0, 10))
        
        reset_btn = ctk.CTkButton(button_frame, text="Reset Defaults",
                                   command=self._reset_defaults,
                                   fg_color="gray40", hover_color="gray30")
        reset_btn.grid(row=0, column=1)

        # Wire up backend dropdown to update active indicators and sync to review tab
        if hasattr(self, "_settings_backend_var"):
            self._settings_backend_var.trace_add("write", self._update_backend_section_indicators)
            self._settings_backend_var.trace_add("write", self._sync_menu_to_review)
            self._update_backend_section_indicators()
            # Ensure both are initially in sync
            self._sync_review_to_menu()

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
        if self._testing_mode:
            return
        d = filedialog.askdirectory()
        if d:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, d)

    def _browse_diff(self):
        if self._testing_mode:
            return
        f = filedialog.askopenfilename(
            filetypes=[("Diff/Patch", "*.diff *.patch"), ("All", "*.*")])
        if f:
            self.diff_file_entry.delete(0, "end")
            self.diff_file_entry.insert(0, f)

    def _set_all_types(self, value: bool):
        for var in self.type_vars.values():
            var.set(value)

    def _on_scope_changed(self, *_args: object) -> None:
        """Handle scope radio button changes - show/hide file selection and diff frames."""
        scope = self.scope_var.get()
        if scope == "project":
            self.file_select_frame.grid()
            self.diff_filter_frame.grid()
            self.diff_frame.grid_remove()
        else:  # diff
            self.file_select_frame.grid_remove()
            self.diff_filter_frame.grid_remove()
            self.diff_frame.grid()

    def _on_diff_filter_changed(self, *_args: object) -> None:
        """Enable/disable diff filter entry fields when checkbox toggled."""
        enabled = self.diff_filter_var.get()
        state = "normal" if enabled else "disabled"
        self.diff_filter_file_entry.configure(state=state)
        self.diff_filter_browse_btn.configure(state=state)
        self.diff_filter_commits_entry.configure(state=state)

    def _browse_diff_filter(self) -> None:
        """Open file dialog for diff filter file."""
        if self._testing_mode:
            return
        path = filedialog.askopenfilename(
            filetypes=[("Diff / Patch", "*.diff *.patch"), ("All files", "*.*")])
        if path:
            self.diff_filter_file_entry.delete(0, "end")
            self.diff_filter_file_entry.insert(0, path)

    def _on_file_select_mode_changed(self, *_args: object):
        """Handle file selection mode changes - enable/disable Select Files button."""
        mode = self.file_select_mode_var.get()
        if mode == "selected":
            self.select_files_btn.configure(state="normal")
        else:
            self.select_files_btn.configure(state="disabled")

    def _open_file_selector(self):
        """Open the custom file selector window."""
        if self._testing_mode:
            return
        path = self.path_entry.get().strip()
        if not path:
            self._show_toast(t("gui.val.path_required"), error=True)
            return
        
        if not Path(path).is_dir():
            self._show_toast("Invalid project path", error=True)
            return
        
        # Open the custom file selector window
        selector = FileSelector(self, path, self.selected_files)
        self.wait_window(selector)
        
        # Update selected_files after the window closes
        if hasattr(selector, 'result') and selector.result:
            self.selected_files = list(selector.result)
            self._show_toast(f"{len(self.selected_files)} file(s) selected")

    def _get_selected_types(self) -> List[str]:
        return [k for k, v in self.type_vars.items() if v.get()]

    def _save_form_values(self):
        """Save current form values to config for next session."""
        try:
            # Save project path
            config.set_value("gui", "project_path", self.path_entry.get().strip())
            
            # Save programmers
            config.set_value("gui", "programmers", self.programmers_entry.get().strip())
            
            # Save reviewers
            config.set_value("gui", "reviewers", self.reviewers_entry.get().strip())
            
            # Save spec file
            config.set_value("gui", "spec_file", self.spec_entry.get().strip())
            
            # Save selected review types
            selected_types = self._get_selected_types()
            config.set_value("gui", "review_types", ",".join(selected_types))
            
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
            # Diff filter entries (project mode with optional diff)
            diff_filter_file = self.diff_filter_file_entry.get().strip() or None
            diff_filter_commits = self.diff_filter_commits_entry.get().strip() or None

        if scope == "project" and not path:
            self._show_toast(t("gui.val.path_required"), error=True)
            return None
        
        # Validate selected files mode
        selected_files: Optional[List[str]] = None
        if scope == "project":
            file_mode = self.file_select_mode_var.get()
            if file_mode == "selected":
                if not self.selected_files:
                    self._show_toast("Please select files for review", error=True)
                    return None
                selected_files = self.selected_files

        # Validate diff filter has at least one source when enabled
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
        # Save form values for next session
        self._save_form_values()
        self._run_review(params, dry_run=False)

    def _start_dry_run(self):
        if self._running:
            return
        params = self._validate_inputs(dry_run=True)
        if not params:
            return
        # Save form values for next session (safe in testing mode — redirected to temp file)
        if not self._testing_mode:
            self._save_form_values()
        self._run_review(params, dry_run=True)

    def _set_action_buttons_state(self, state: str):
        """Enable or disable all action buttons together."""
        self.run_btn.configure(state=state)
        self.dry_btn.configure(state=state)
        self.health_btn.configure(state=state)

    def _cancel_operation(self):
        """Cancel the currently running operation."""
        # Signal review/dry-run cancellation
        if hasattr(self, '_cancel_event'):
            self._cancel_event.set()

        # Terminate active backend subprocess if possible
        if hasattr(self, '_review_client') and self._review_client:
            if hasattr(self._review_client, 'cancel'):
                try:
                    self._review_client.cancel()
                except Exception as exc:
                    logger.warning("Failed to cancel backend: %s", exc)

        # Signal health-check cancellation
        if self._health_check_backend:
            if self._health_check_timer:
                self._health_check_timer.cancel()
                self._health_check_timer = None
            self._health_check_backend = None
            self._running = False
            self._set_action_buttons_state("normal")
            self.status_var.set(t("gui.val.cancelled"))

        self.cancel_btn.configure(state="disabled")

    def _run_review(self, params: Dict[str, Any], dry_run: bool):
        """Execute the review in a background thread."""
        self._running = True
        self._cancel_event = threading.Event()
        self._set_action_buttons_state("disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.set(0)
        self.status_var.set(t("common.running"))

        def _worker() -> None:
            try:
                backend_name: str = params.pop("backend")
                selected_files: Optional[List[str]] = params.pop("selected_files", None)
                diff_filter_file: Optional[str] = params.pop("diff_filter_file", None)
                diff_filter_commits: Optional[str] = params.pop("diff_filter_commits", None)
                
                client = None if dry_run else create_backend(backend_name)
                self._review_client = client
                
                # Build a scan function that handles file selection + diff filtering
                has_diff_filter = bool(diff_filter_file or diff_filter_commits)
                
                def custom_scan_fn(
                    directory: Optional[str],
                    scope: str,
                    diff_file: Optional[str] = None,
                    commits: Optional[str] = None,
                ) -> List[Any]:
                    """Scan with optional file selection and diff intersection."""
                    if scope == "diff":
                        # Pure diff mode — use default scanner
                        return scan_project_with_scope(directory, scope, diff_file, commits)
                    
                    # Full project mode — start with all project files
                    all_files: List[Any] = scan_project_with_scope(directory, "project")
                    
                    # Apply file selection filter
                    if selected_files:
                        selected_set = {Path(f).resolve() for f in selected_files}
                        all_files = [
                            f for f in all_files
                            if Path(f).resolve() in selected_set
                        ]
                    
                    # Apply diff filter (intersection with diff + use diff content only)
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
                        
                        # Parse diff to get changed file names and their diff content
                        diff_entries = parse_diff_file(diff_content)
                        diff_by_name: Dict[str, str] = {
                            entry["filename"]: entry["content"]
                            for entry in diff_entries
                        }
                        
                        # Intersect: keep only files that appear in the diff,
                        # and replace content with diff-only content
                        intersected: List[Any] = []
                        for file_path in all_files:
                            fp = Path(file_path)
                            # Try matching by relative path from project root
                            rel_path: Optional[str] = None
                            if directory:
                                try:
                                    rel_path = str(fp.relative_to(directory))
                                except ValueError:
                                    rel_path = str(fp)
                            else:
                                rel_path = str(fp)
                            
                            # Normalize path separators for comparison
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
                    client,  # type: ignore[arg-type]  # None is safe for dry_run
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
                    # GUI mode: got list of issues; defer report generation
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
                self.after(0, lambda: self._set_action_buttons_state("normal"))
                self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
                self.after(0, lambda: self.progress.set(1.0))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_dry_run_complete(self):
        """Switch to the Log tab and update status after a dry run."""
        self.status_var.set(t("gui.val.dry_run_done"))
        # Switch to the Log tab so the user can see the file listing
        self.tabs.set(t("gui.tab.log"))

    # ══════════════════════════════════════════════════════════════════════
    #  RESULTS  – displayed on the Results tab
    # ══════════════════════════════════════════════════════════════════════

    def _show_issues(self, issues: List[ReviewIssue]):
        """Populate the Results tab with issue cards (no report saved yet)."""
        # Clear old results
        for w in self.results_frame.winfo_children():
            w.destroy()
        self._issue_cards.clear()

        if not issues:
            self.results_summary.configure(text=t("gui.results.no_results"))
            self.review_changes_btn.configure(state="disabled")
            self.finalize_btn.configure(state="disabled")
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

        # Issues section header
        self._issues_header = ctk.CTkLabel(
            self.results_frame, text=t("gui.results.issues_section"),
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
        self._issues_header.grid(row=0, column=0, sticky="w", padx=6, pady=(4, 2))

        for i, issue in enumerate(issues):
            self._add_issue_card(i + 1, issue)

        # Fixed section header (hidden initially)
        self._fixed_header_row = len(issues) + 2
        self._fixed_header = ctk.CTkLabel(
            self.results_frame, text=t("gui.results.fixed_section"),
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
        # Will be shown later: self._fixed_header.grid(...)

        self._update_bottom_buttons()
        self.tabs.set(t("gui.tab.results"))

    # ── Issue card ─────────────────────────────────────────────────────────

    def _add_issue_card(self, index: int, issue: ReviewIssue):
        """Add a single issue card to the results frame."""
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
        s_key, s_color = self._status_display(issue, color)
        status_lbl = ctk.CTkLabel(card, text=t(s_key), text_color=s_color)
        status_lbl.grid(row=2, column=0, sticky="w", padx=6, pady=(0, 4))

        # Action buttons
        btn_kw = dict(width=65, height=26, font=ctk.CTkFont(size=11))
        view_btn = ctk.CTkButton(
            card, text=t("gui.results.action_view"), **btn_kw,  # type: ignore[reportArgumentType]
            command=lambda iss=issue: self._show_issue_detail(iss),
        )
        view_btn.grid(row=2, column=2, padx=2, pady=(0, 4))

        # AI Fix checkbox (hidden by default — shown in AI Fix mode)
        fix_check_var = ctk.BooleanVar(value=False)
        fix_checkbox = ctk.CTkCheckBox(
            card, text=t("gui.results.select_for_fix"),
            variable=fix_check_var,
            font=ctk.CTkFont(size=11), width=20,
        )
        # Not gridded yet — will appear in AI Fix mode

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

        # Skip reason frame (hidden by default) — indented below card
        skip_frame = ctk.CTkFrame(card, fg_color="transparent")
        skip_entry = ctk.CTkEntry(skip_frame, width=500,
                                   placeholder_text=t("gui.results.skip_reason_ph"))
        skip_entry.grid(row=0, column=0, sticky="ew", padx=(20, 6), pady=4)
        skip_frame.grid_columnconfigure(0, weight=1)
        # Not gridded yet — toggled by _toggle_skip

        self._issue_cards.append(IssueCard(
            issue=issue,
            card=card,
            status_lbl=status_lbl,
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
        """Return (i18n_key, color) for the issue's current status."""
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
        """Update the status label and bottom buttons for a card."""
        rec = self._issue_cards[idx]
        s_key, s_color = self._status_display(rec["issue"], rec["color"])
        rec["status_lbl"].configure(text=t(s_key), text_color=s_color)
        self._update_bottom_buttons()

    def _update_bottom_buttons(self):
        """Enable/disable Review Changes and Finalize based on issue states."""
        all_done = all(c["issue"].status != "pending" for c in self._issue_cards)
        any_to_check = any(c["issue"].status in ("resolved",) for c in self._issue_cards)
        any_pending = any(c["issue"].status == "pending" for c in self._issue_cards)

        if all_done and any_to_check:
            self.review_changes_btn.configure(state="normal")
        else:
            self.review_changes_btn.configure(state="disabled")

        # Allow finalize when everything is resolved/fixed/skipped/fix_failed
        if all_done:
            self.finalize_btn.configure(state="normal")
        else:
            self.finalize_btn.configure(state="disabled")

        # AI Fix mode button — enabled when there are pending issues
        # In testing mode, allow AI Fix mode even without a live review client
        if any_pending and (self._review_client or self._testing_mode):
            self.ai_fix_mode_btn.configure(state="normal")
        else:
            self.ai_fix_mode_btn.configure(state="disabled")

    # ── Resolve: open editor ───────────────────────────────────────────────

    def _resolve_issue(self, idx: int):
        """Open the file in an editor so the user can fix the issue."""
        rec = self._issue_cards[idx]
        issue = rec["issue"]
        editor_cmd = config.get("gui", "editor_command", "").strip()

        if editor_cmd and not self._testing_mode:
            # Open in external editor (skip in testing mode — files are fake)
            try:
                subprocess.Popen([editor_cmd, issue.file_path])
            except Exception as exc:
                logger.error("Cannot open editor '%s': %s", editor_cmd, exc)
                self._show_toast(str(exc), error=True)
                return
            issue.status = "resolved"
        else:
            # Built-in text editor
            self._open_builtin_editor(idx)
            return  # status updated on save

        self._refresh_status(idx)

    def _open_builtin_editor(self, idx: int):
        """Open a built-in text editor in a Toplevel window."""
        rec = self._issue_cards[idx]
        issue = rec["issue"]
        fname = Path(issue.file_path).name

        win = ctk.CTkToplevel(self)
        win.title(t("gui.results.editor_title", file=fname))
        win.geometry("850x600")
        win.grab_set()

        # Show AI feedback at top for context
        fb_lbl = ctk.CTkLabel(win, text=issue.ai_feedback[:200],
                               wraplength=800, anchor="w",
                               text_color=("gray30", "gray70"),
                               font=ctk.CTkFont(size=11))
        fb_lbl.pack(fill="x", padx=10, pady=(8, 2))

        text = ctk.CTkTextbox(win, wrap="none",
                               font=ctk.CTkFont(family="Consolas", size=12))
        text.pack(fill="both", expand=True, padx=10, pady=4)

        if self._testing_mode:
            # In testing mode, show code snippet (files are fictitious)
            text.insert("0.0", issue.code_snippet or "(no code snippet)")
        else:
            try:
                with open(issue.file_path, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                text.insert("0.0", content)
            except Exception as exc:
                text.insert("0.0", f"Error reading file: {exc}")

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=8)

        def _save():
            if self._testing_mode:
                # In testing mode, simulate a successful save
                issue.status = "resolved"
                self._refresh_status(idx)
                self._show_toast(t("gui.results.editor_saved"))
                win.destroy()
                return
            try:
                with open(issue.file_path, "w", encoding="utf-8") as fh:
                    fh.write(text.get("0.0", "end").rstrip("\n") + "\n")
                issue.status = "resolved"
                self._refresh_status(idx)
                self._show_toast(t("gui.results.editor_saved"))
            except Exception as exc:
                self._show_toast(str(exc), error=True)
            win.destroy()

        ctk.CTkButton(btn_frame, text=t("gui.results.editor_save"),
                       fg_color="green", command=_save).grid(
            row=0, column=0, padx=6)
        ctk.CTkButton(btn_frame, text=t("common.cancel"),
                       command=win.destroy).grid(row=0, column=1, padx=6)

    # ── Skip: inline reason toggle ─────────────────────────────────────────

    def _toggle_skip(self, idx: int):
        """Toggle skip state: show/hide reason textbox inline."""
        rec = self._issue_cards[idx]
        issue = rec["issue"]

        if issue.status == "skipped":
            # Revert to pending — hide reason box
            issue.status = "pending"
            issue.resolution_reason = None
            rec["skip_frame"].grid_remove()
        else:
            # Mark as skipped — show reason box
            issue.status = "skipped"
            rec["skip_frame"].grid(row=3, column=0, columnspan=6, sticky="ew")
            # Capture reason on every keystroke
            def _on_reason_change(*_a, _entry=rec["skip_entry"], _iss=issue):
                _iss.resolution_reason = _entry.get().strip() or None
            rec["skip_entry"].bind("<KeyRelease>", _on_reason_change)

        self._refresh_status(idx)

    # ── AI Fix Mode ──────────────────────────────────────────────────────

    def _enter_ai_fix_mode(self):
        """Enter AI Fix selection mode – show checkboxes, hide action buttons."""
        if self._ai_fix_mode:
            return
        self._ai_fix_mode = True

        # Hide normal bottom buttons, show AI Fix mode buttons
        self.ai_fix_mode_btn.grid_remove()
        self.review_changes_btn.grid_remove()
        self.finalize_btn.grid_remove()
        self.start_ai_fix_btn.grid(row=0, column=0, padx=6)
        self.cancel_ai_fix_btn.grid(row=0, column=1, padx=6)

        # Disable review tab action buttons
        self._set_action_buttons_state("disabled")

        # Toggle each issue card: hide View/Resolve/Skip, show checkbox
        for rec in self._issue_cards:
            if rec["issue"].status == "pending":
                rec["view_btn"].grid_remove()
                rec["resolve_btn"].grid_remove()
                rec["skip_btn"].grid_remove()
                rec["fix_check_var"].set(True)
                rec["fix_checkbox"].grid(row=2, column=2, columnspan=3,
                                          padx=4, pady=(0, 4), sticky="w")

    def _exit_ai_fix_mode(self):
        """Exit AI Fix mode or cancel current run if one is active."""
        # If a fix is running, just cancel it (stay in AI Fix mode)
        if self._ai_fix_running:
            if hasattr(self, '_ai_fix_cancel_event') and not self._ai_fix_cancel_event.is_set():
                self._ai_fix_cancel_event.set()
                logger.info("Cancelling AI Fix run...")
                # Disable cancel button and update text to show cancellation in progress
                self.cancel_ai_fix_btn.configure(state="disabled", text=t("gui.results.cancelling_ai_fix"))
                self.status_var.set(t("gui.results.cancelling_status"))
            return

        # Otherwise, exit AI Fix mode
        self._ai_fix_mode = False

        # Restore bottom buttons
        self.start_ai_fix_btn.grid_remove()
        self.cancel_ai_fix_btn.grid_remove()
        self.ai_fix_mode_btn.grid(row=0, column=0, padx=6)
        self.review_changes_btn.grid(row=0, column=1, padx=6)
        self.finalize_btn.grid(row=0, column=2, padx=6)

        # Re-enable review tab action buttons
        self._set_action_buttons_state("normal")

        # Restore card buttons and status labels
        for rec in self._issue_cards:
            rec["fix_checkbox"].grid_remove()
            rec["fix_check_var"].set(False)
            # Restore status label to current state
            s_key, s_color = self._status_display(rec["issue"], rec["color"])
            rec["status_lbl"].configure(text=t(s_key), text_color=s_color)
            # View is always restored regardless of status
            rec["view_btn"].grid(row=2, column=2, padx=2, pady=(0, 4))
            # Resolve / Skip only make sense while an issue is still pending
            if rec["issue"].status == "pending":
                rec["resolve_btn"].grid(row=2, column=4, padx=2, pady=(0, 4))
                rec["skip_btn"].grid(row=2, column=5, padx=2, pady=(0, 4))
            else:
                rec["resolve_btn"].grid_remove()
                rec["skip_btn"].grid_remove()

        self._update_bottom_buttons()

    def _start_batch_ai_fix(self):
        """Send a batch AI Fix request for all selected issues."""
        selected = [
            (i, rec) for i, rec in enumerate(self._issue_cards)
            if rec["fix_check_var"].get() and rec["issue"].status == "pending"
        ]
        if not selected:
            self._show_toast(t("gui.results.no_issues_selected"), error=True)
            return

        if not self._review_client:
            if self._testing_mode:
                # Simulate AI Fix: generate fake fix content and route through
                # the normal batch-fix popup so the diff preview can be tested.
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

        # Create cancellation event and disable only Start button (keep Cancel enabled)
        self._ai_fix_cancel_event = threading.Event()
        self._ai_fix_running = True
        self.start_ai_fix_btn.configure(state="disabled")
        # Keep cancel button enabled for user to cancel mid-operation

        logger.info("Starting batch AI Fix for %d issues…", len(selected))
        self.status_var.set(t("gui.results.batch_fix_running",
                              count=len(selected)))

        # Update status labels
        for i, rec in selected:
            rec["status_lbl"].configure(
                text=t("gui.results.applying_fix"), text_color="#7c3aed")

        def _worker():
            try:
                results = {}  # idx → (fix_text | None)
                cancelled = False
                for idx, rec in selected:
                    # Check for cancellation before each file
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
                        
                        # Check for cancellation immediately after get_fix() returns
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
                        
                        # Check for cancellation after exception handling
                        if self._ai_fix_cancel_event.is_set():
                            logger.info("AI Fix cancelled by user")
                            cancelled = True
                            break

                # If cancelled, just restore UI without showing popup
                if cancelled:
                    self.after(0, lambda: self._on_ai_fix_cancelled(selected))
                else:
                    # Show results popup on main thread
                    self.after(0, lambda: self._show_batch_fix_popup(
                        selected, results))
            finally:
                # Always mark as not running when done
                self._ai_fix_running = False

        threading.Thread(target=_worker, daemon=True).start()

    def _on_ai_fix_cancelled(self, selected):
        """Handle AI Fix cancellation - restore UI state."""
        logger.info("AI Fix operation cancelled.")
        self.status_var.set(t("common.ready"))
        # Restore status labels
        for idx, rec in selected:
            s_key, s_color = self._status_display(rec["issue"], rec["color"])
            rec["status_lbl"].configure(text=t(s_key), text_color=s_color)
        # Re-enable buttons and restore cancel button text
        self.start_ai_fix_btn.configure(state="normal")
        self.cancel_ai_fix_btn.configure(state="normal", text=t("gui.results.cancel_ai_fix"))
        self._ai_fix_running = False

    def _show_batch_fix_popup(self, selected, results):
        """Show a popup with all batch fix results for review."""
        success_count = sum(1 for v in results.values() if v)
        fail_count = len(results) - success_count

        if success_count == 0:
            # All failed — restore UI
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

        # Restore cancel button state for popup interaction
        self.cancel_ai_fix_btn.configure(state="normal", text=t("gui.results.cancel_ai_fix"))

        win = ctk.CTkToplevel(self)
        win.title(t("gui.results.batch_fix_title",
                     count=success_count))
        win.geometry("950x650")
        win.grab_set()

        ctk.CTkLabel(
            win,
            text=t("gui.results.batch_fix_summary",
                    success=success_count, failed=fail_count),
            font=ctk.CTkFont(weight="bold"),
        ).pack(padx=10, pady=(10, 4))

        # Scrollable area with per-file fixes
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

                # Row 0: Checkbox + Preview button
                ctk.CTkCheckBox(
                    frame, text=fname, variable=var,
                    font=ctk.CTkFont(weight="bold"),
                ).grid(row=0, column=0, sticky="w", padx=6, pady=(4, 0))

                # Preview changes button
                preview_btn = ctk.CTkButton(
                    frame, text=t("gui.results.preview_changes"),
                    width=100, height=24, font=ctk.CTkFont(size=11),
                    fg_color="#2563eb",
                    command=lambda fp=issue.file_path, ft=fix_text, fn=fname:
                        self._show_diff_preview(fp, ft, fn),
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
                    # In testing mode, simulate apply without file I/O
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
            self._ai_fix_running = False  # Mark as not running before exiting mode
            self._exit_ai_fix_mode()
            self._show_toast(t("gui.results.batch_fix_applied",
                               count=applied))
            logger.info("Batch AI Fix: %d fixes applied.", applied)
            self.status_var.set(t("common.ready"))

        def _cancel():
            win.destroy()
            # Restore status labels
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

    def _show_diff_preview(self, file_path: str, new_content: str, filename: str):
        """Show a side-by-side diff preview of the proposed fix."""
        # Read original content
        if self._testing_mode:
            # In testing mode, use the code snippet from the issue
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
        win.geometry("1000x700")
        win.grab_set()

        # Header
        ctk.CTkLabel(
            win, text=t("gui.results.diff_preview_header", file=filename),
            font=ctk.CTkFont(weight="bold", size=14),
        ).pack(padx=10, pady=(10, 4))

        # Generate unified diff
        original_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            original_lines, new_lines,
            fromfile=f"original/{filename}",
            tofile=f"fixed/{filename}",
            lineterm=""
        ))

        # Diff text view — use tk.Text (not CTkTextbox) so we can apply colour tags
        is_dark = ctk.get_appearance_mode().lower() == "dark"
        bg_color  = "#1e1e1e"  if is_dark else "#ffffff"
        fg_color  = "#d4d4d4"  if is_dark else "#1e1e1e"

        diff_frame = ctk.CTkFrame(win, fg_color=bg_color)
        diff_frame.pack(fill="both", expand=True, padx=10, pady=4)
        diff_frame.grid_rowconfigure(0, weight=1)
        diff_frame.grid_columnconfigure(0, weight=1)

        diff_text = tk.Text(
            diff_frame, wrap="none",
            font=("Consolas", 12),
            bg=bg_color, fg=fg_color,
            insertbackground=fg_color,
            selectbackground="#264f78",
            relief="flat",
            borderwidth=0,
        )
        diff_text.grid(row=0, column=0, sticky="nsew")

        vsb = ctk.CTkScrollbar(diff_frame, orientation="vertical",   command=diff_text.yview)
        hsb = ctk.CTkScrollbar(diff_frame, orientation="horizontal", command=diff_text.xview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Auto-hide: remove the bar when all content fits; restore it when it doesn't.
        # grid_remove() preserves grid options so grid() (no args) restores the slot.
        def _yscroll(first, last):
            if float(first) <= 0.0 and float(last) >= 1.0:
                vsb.grid_remove()
            else:
                vsb.grid()
            vsb.set(first, last)

        def _xscroll(first, last):
            if float(first) <= 0.0 and float(last) >= 1.0:
                hsb.grid_remove()
            else:
                hsb.grid()
            hsb.set(first, last)

        diff_text.configure(yscrollcommand=_yscroll, xscrollcommand=_xscroll)

        # Colour tags: added lines (green), removed lines (red), hunk headers (cyan), file headers (grey)
        diff_text.tag_configure(
            "add",
            background="#1e4620" if is_dark else "#ccffcc",
            foreground="#57d15b" if is_dark else "#006400",
        )
        diff_text.tag_configure(
            "remove",
            background="#4b1010" if is_dark else "#ffcccc",
            foreground="#ff6b6b" if is_dark else "#8b0000",
        )
        diff_text.tag_configure(
            "hunk",
            foreground="#4ec9b0" if is_dark else "#005f5f",
        )
        diff_text.tag_configure(
            "header",
            background="#2c2c3c" if is_dark else "#e8e8f0",
            foreground="#9ba8bf" if is_dark else "#555577",
        )

        if diff:
            for line in diff:
                text = line + ("\n" if not line.endswith("\n") else "")
                if line.startswith("+") and not line.startswith("+++"):
                    diff_text.insert("end", text, "add")
                elif line.startswith("-") and not line.startswith("---"):
                    diff_text.insert("end", text, "remove")
                elif line.startswith("@@"):
                    diff_text.insert("end", text, "hunk")
                elif line.startswith("---") or line.startswith("+++"):
                    diff_text.insert("end", text, "header")
                else:
                    diff_text.insert("end", text)
        else:
            diff_text.insert("end", t("gui.results.no_changes"))

        diff_text.configure(state="disabled")

        # Side-by-side comparison tabs
        tabs = ctk.CTkTabview(win, height=250)
        tabs.pack(fill="x", padx=10, pady=4)

        # Original tab
        orig_tab = tabs.add(t("gui.results.original_code"))
        orig_text = ctk.CTkTextbox(
            orig_tab, wrap="none",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        orig_text.pack(fill="both", expand=True, padx=4, pady=4)
        orig_text.insert("0.0", original_content)
        orig_text.configure(state="disabled")

        # Fixed tab
        fixed_tab = tabs.add(t("gui.results.fixed_code"))
        fixed_text = ctk.CTkTextbox(
            fixed_tab, wrap="none",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        fixed_text.pack(fill="both", expand=True, padx=4, pady=4)
        fixed_text.insert("0.0", new_content)
        fixed_text.configure(state="disabled")

        ctk.CTkButton(win, text=t("common.close"),
                       command=win.destroy).pack(pady=8)

    # ── View detail ────────────────────────────────────────────────────────

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

    # ── Review Changes ─────────────────────────────────────────────────────

    def _review_changes(self):
        """Re-check resolved issues to verify fixes, then update the UI."""
        if self._running:
            return
        if not self._review_client:
            if self._testing_mode:
                # Simulate verification: mark all resolved → fixed
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

            # Check if all issues are now fixed or skipped
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
        """All issues verified — save and reset."""
        self._do_finalize()
        self._show_toast(t("gui.results.all_fixed"))

    # ── Finalize ───────────────────────────────────────────────────────────

    def _finalize_report(self):
        """Save the report with current issue states and reset the Results page."""
        self._do_finalize()
        self._show_toast(t("gui.results.finalized"))

    def _do_finalize(self):
        """Generate the report and reset the results page."""
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

        # Reset results page
        for w in self.results_frame.winfo_children():
            w.destroy()
        self._issue_cards.clear()
        self.results_summary.configure(text=t("gui.results.no_results"))
        self.review_changes_btn.configure(state="disabled")
        self.finalize_btn.configure(state="disabled")

        # In testing mode, reload sample data so the tester can continue
        if self._testing_mode:
            def _reload_fixtures():
                from aicodereviewer.gui.test_fixtures import create_sample_issues
                self._show_issues(create_sample_issues())
                self.status_var.set(
                    "Testing mode: sample data reloaded after finalize")
            self.after(400, _reload_fixtures)

    # ══════════════════════════════════════════════════════════════════════
    #  TOAST NOTIFICATIONS
    # ══════════════════════════════════════════════════════════════════════

    def _show_toast(self, message: str, *, duration: int = 6000,
                    error: bool = False):
        """Show a transient toast notification at the bottom of the window."""
        bg = "#dc2626" if error else ("#1a7f37", "#2ea043")
        fg = "white"

        toast = ctk.CTkFrame(self, corner_radius=8,
                              fg_color=bg, border_width=0)
        toast.place(relx=0.5, rely=0.96, anchor="s")
        toast.lift()

        lbl = ctk.CTkLabel(toast, text=message, text_color=fg,
                            font=ctk.CTkFont(size=12),
                            wraplength=600, anchor="center")
        lbl.pack(padx=16, pady=8)

        def _dismiss():
            try:
                toast.destroy()
            except Exception:
                pass

        self.after(duration, _dismiss)

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
                elif section == "backend" and key == "type":
                    # Map backend display names back to internal values
                    raw = getattr(self, "_backend_reverse_map", {}).get(raw, "bedrock")
                config.set_value(section, key, raw)
            else:
                config.set_value(section, key, widget.get().strip())
        
        # Save report output formats
        selected_formats = [fmt for fmt, var in self._format_vars.items() if var.get()]
        if not selected_formats:
            # Prevent disabling all formats - re-enable at least JSON
            self._format_vars["json"].set(True)
            selected_formats = ["json"]
            self._show_toast("At least one output format must be selected. JSON has been re-enabled.", error=True)
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
        """Reset all settings to their default values."""
        if self._testing_mode:
            self._show_toast(
                "Reset Defaults is disabled in testing mode — "
                "settings are isolated", error=False)
            return
        # Confirm with user
        if not messagebox.askyesno("Reset Defaults", 
                          "This will reset all settings to their default values. Continue?"):
            return
        
        # Reset the config to defaults
        config.config = configparser.ConfigParser()
        config._set_defaults()  # type: ignore[reportPrivateUsage]
        
        # Reload the settings tab with default values
        # Destroy and rebuild the settings tab
        for widget in self.tabs.tab(t("gui.tab.settings")).winfo_children():
            widget.destroy()
        
        self._build_settings_tab()
        
        # Save to file
        try:
            config.save()
            self._show_toast("Settings have been reset to defaults")
        except Exception as exc:
            self._show_toast(f"Error saving defaults: {exc}", error=True)

    # ══════════════════════════════════════════════════════════════════════
    #  BACKEND HEALTH CHECK
    # ══════════════════════════════════════════════════════════════════════

    def _on_backend_changed(self, *_args: object):
        """Called when the backend radio button changes — save and re-check."""
        backend_name = self.backend_var.get()
        config.set_value("backend", "type", backend_name)
        try:
            config.save()
        except Exception:
            pass
        # Sync to settings dropdown
        self._sync_review_to_menu()
        # Run silent health check for the new backend
        if not self._testing_mode:
            self._auto_health_check()

    def _auto_health_check(self):
        """Run health check silently; show dialog only if something fails."""
        self._run_health_check(self.backend_var.get(), always_show_dialog=False)

    def _check_backend_health(self):
        """Run prerequisite health checks for the selected backend (manual)."""
        if self._testing_mode:
            self._show_toast(
                "Check Setup is simulated in testing mode — "
                "backend connectivity is not tested", error=False)
            return
        self._run_health_check(self.backend_var.get(), always_show_dialog=True)

    def _run_health_check(self, backend_name: str, *, always_show_dialog: bool):
        """Shared implementation for auto and manual backend health checks.

        Parameters
        ----------
        backend_name:
            The backend identifier to check (e.g. ``"copilot"``, ``"bedrock"``).
        always_show_dialog:
            When *True* (manual check), the results dialog is always shown.
            When *False* (auto check), the dialog is shown only on failure;
            a silent status-bar message is used on success, and the model list
            is refreshed directly in the worker thread callback.
        """
        if self._running:
            return

        # If already checking this backend, don't start another
        if self._health_check_backend == backend_name:
            return

        # Cancel any previous timeout timer
        if self._health_check_timer:
            self._health_check_timer.cancel()
            self._health_check_timer = None

        self._health_check_backend = backend_name
        self._set_action_buttons_state("disabled")
        self.cancel_btn.configure(state="normal")
        self.status_var.set(t("health.checking", backend=backend_name))

        # Start 60-second timeout timer (includes connection test)
        def _on_timeout():
            if self._health_check_backend == backend_name:
                self._health_check_backend = None
                self._health_check_timer = None
                self.after(0, lambda: self._show_health_error(
                    t("health.timeout", backend=backend_name)))
                self.after(0, lambda: self._set_action_buttons_state("normal"))
                self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
                self.after(0, lambda: self.status_var.set(t("common.ready")))

        self._health_check_timer = threading.Timer(60, _on_timeout)
        self._health_check_timer.daemon = True
        self._health_check_timer.start()

        def _worker():
            try:
                report = check_backend(backend_name)

                # Only process if still checking this backend
                if self._health_check_backend == backend_name:
                    # Cancel timeout timer
                    if self._health_check_timer:
                        self._health_check_timer.cancel()
                        self._health_check_timer = None

                    self._health_check_backend = None

                    if always_show_dialog:
                        # Manual check: always show the full results dialog.
                        # Model list refresh is handled inside _show_health_dialog.
                        self.after(0, lambda: self._show_health_dialog(report))
                        self.after(0, lambda: self.status_var.set(t("common.ready")))
                    else:
                        # Auto check: silent success; dialog only on failure.
                        if report.ready:
                            self.after(0, lambda: self.status_var.set(
                                t("health.auto_ok", backend=backend_name)))
                            # Refresh model combobox with discovered models
                            if backend_name == "copilot":
                                self.after(0, self._refresh_copilot_model_list)
                            elif backend_name == "bedrock":
                                self.after(0, self._refresh_bedrock_model_list)
                            elif backend_name == "local":
                                self.after(0, self._refresh_local_model_list)
                        else:
                            self.after(0, lambda: self._show_health_dialog(report))
                            self.after(0, lambda: self.status_var.set(t("common.ready")))

                    self.after(0, lambda: self._set_action_buttons_state("normal"))
                    self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
            except Exception as exc:
                if self._health_check_backend == backend_name:
                    logger.error("Health check failed: %s", exc)
                    if self._health_check_timer:
                        self._health_check_timer.cancel()
                        self._health_check_timer = None
                    self._health_check_backend = None
                    self.after(0, lambda: self._show_health_error(str(exc)))
                    self.after(0, lambda: self._set_action_buttons_state("normal"))
                    self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
                    self.after(0, lambda: self.status_var.set(t("common.ready")))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_health_dialog(self, report):
        """Show a dialog with health check results."""
        if self._testing_mode:
            logger.info("Health dialog suppressed in testing: %s", report.summary)
            return
        win = ctk.CTkToplevel(self)
        win.title(t("health.dialog_title"))
        win.geometry("600x450")
        win.grab_set()

        # Refresh Copilot model list if health check passed
        if report.backend == "copilot" and report.ready:
            self._refresh_copilot_model_list()
        elif report.backend == "bedrock" and report.ready:
            self._refresh_bedrock_model_list()
        elif report.backend == "local" and report.ready:
            self._refresh_local_model_list()

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
                # Check if the fix_hint contains a URL
                url_match = re.search(r'https?://[^\s]+', check.fix_hint)
                if url_match:
                    # Split into text before URL and the URL itself
                    url = url_match.group(0)
                    text_before = check.fix_hint[:url_match.start()].rstrip(': ')
                    
                    # Create a frame to hold text + link horizontally
                    hint_frame = ctk.CTkFrame(scroll, fg_color="transparent")
                    hint_frame.grid(row=i * 3 + 2, column=1, sticky="w", padx=4, pady=(0, 4))
                    
                    # Display the text part
                    if text_before:
                        ctk.CTkLabel(hint_frame, text=f"💡 {text_before}: ",
                                      anchor="w",
                                      text_color="#2563eb",
                                      font=ctk.CTkFont(size=11)).pack(
                            side="left", padx=(0, 2))
                    else:
                        ctk.CTkLabel(hint_frame, text="💡 ",
                                      text_color="#2563eb",
                                      font=ctk.CTkFont(size=11)).pack(
                            side="left")
                    
                    # Display the URL as a clickable link
                    link_label = ctk.CTkLabel(hint_frame, text=url,
                                               anchor="w",
                                               text_color="#0066cc",
                                               font=ctk.CTkFont(size=11, underline=True),
                                               cursor="hand2")
                    link_label.pack(side="left")
                    link_label.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                else:
                    # No URL, display as regular text
                    ctk.CTkLabel(scroll, text=f"💡 {check.fix_hint}",
                                  anchor="w", wraplength=450,
                                  text_color="#2563eb",
                                  font=ctk.CTkFont(size=11)).grid(
                        row=i * 3 + 2, column=1, sticky="w", padx=4,
                        pady=(0, 4))

        ctk.CTkButton(win, text=t("common.close"),
                       command=win.destroy).pack(pady=8)

    def _show_health_error(self, error_msg: str):
        """Show an error dialog for health check failures."""
        if self._testing_mode:
            logger.warning("Health check error (suppressed in testing): %s", error_msg)
            return
        messagebox.showerror(t("health.dialog_title"), error_msg)

    def _refresh_current_backend_models_async(self):
        """Refresh models for the currently selected backend in a background thread."""
        backend = self.backend_var.get()
        if backend == "copilot":
            self._refresh_copilot_model_list_async()
        elif backend == "bedrock":
            self._refresh_bedrock_model_list_async()
        elif backend == "local":
            self._refresh_local_model_list_async()

    def _refresh_copilot_model_list(self):
        """Update the Copilot model combobox with dynamically discovered models (GUI thread)."""
        models = get_copilot_models()
        if models and hasattr(self, "_copilot_model_combo"):
            current = self._copilot_model_combo.get()
            self._copilot_model_combo.configure(values=["auto"] + models)
            self._copilot_model_combo.set(current)

    def _refresh_copilot_model_list_async(self):
        """Discover Copilot models in background thread, update GUI when done."""
        if "copilot" in self._model_refresh_in_progress:
            return
        self._model_refresh_in_progress.add("copilot")

        def _worker():
            try:
                models = get_copilot_models()
                self.after(0, lambda: self._apply_copilot_models(models))
            finally:
                self._model_refresh_in_progress.discard("copilot")

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_copilot_models(self, models: list):
        """Apply discovered Copilot models to combobox (GUI thread)."""
        if models and hasattr(self, "_copilot_model_combo"):
            current = self._copilot_model_combo.get()
            self._copilot_model_combo.configure(values=["auto"] + models)
            self._copilot_model_combo.set(current)

    def _refresh_bedrock_model_list(self):
        """Update the Bedrock model combobox with dynamically discovered models (GUI thread)."""
        models = get_bedrock_models()
        if models and hasattr(self, "_bedrock_model_combo"):
            current = self._bedrock_model_combo.get()
            self._bedrock_model_combo.configure(values=models)
            if current:
                self._bedrock_model_combo.set(current)

    def _refresh_bedrock_model_list_async(self):
        """Discover Bedrock models in background thread, update GUI when done."""
        if "bedrock" in self._model_refresh_in_progress:
            return
        self._model_refresh_in_progress.add("bedrock")

        def _worker():
            try:
                models = get_bedrock_models()
                self.after(0, lambda: self._apply_bedrock_models(models))
            finally:
                self._model_refresh_in_progress.discard("bedrock")

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_bedrock_models(self, models: list):
        """Apply discovered Bedrock models to combobox (GUI thread)."""
        if models and hasattr(self, "_bedrock_model_combo"):
            current = self._bedrock_model_combo.get()
            self._bedrock_model_combo.configure(values=models)
            if current:
                self._bedrock_model_combo.set(current)

    def _refresh_local_model_list(self):
        """Update the Local LLM model combobox with dynamically discovered models (GUI thread)."""
        api_url = config.get("local_llm", "api_url", "http://localhost:1234")
        api_type = config.get("local_llm", "api_type", "lmstudio")
        models = get_local_models(api_url, api_type)
        if models and hasattr(self, "_local_model_combo"):
            current = self._local_model_combo.get()
            self._local_model_combo.configure(values=models)
            if current:
                self._local_model_combo.set(current)

    def _refresh_local_model_list_async(self):
        """Discover Local LLM models in background thread, update GUI when done."""
        if "local" in self._model_refresh_in_progress:
            return
        self._model_refresh_in_progress.add("local")

        def _worker():
            try:
                api_url = config.get("local_llm", "api_url", "http://localhost:1234")
                api_type = config.get("local_llm", "api_type", "lmstudio")
                models = get_local_models(api_url, api_type)
                self.after(0, lambda: self._apply_local_models(models))
            finally:
                self._model_refresh_in_progress.discard("local")

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_local_models(self, models: list):
        """Apply discovered Local LLM models to combobox (GUI thread)."""
        if models and hasattr(self, "_local_model_combo"):
            current = self._local_model_combo.get()
            self._local_model_combo.configure(values=models)
            if current:
                self._local_model_combo.set(current)

    def _update_backend_section_indicators(self, *args):
        """Update the 'Active' indicator on backend section headers."""
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
        """Sync settings dropdown (display names) to review tab radio buttons (internal values)."""
        if not hasattr(self, "_settings_backend_var") or not hasattr(self, "backend_var"):
            return
        display_val = self._settings_backend_var.get()
        internal_val = getattr(self, "_backend_reverse_map", {}).get(display_val, "bedrock")
        if self.backend_var.get() != internal_val:
            self.backend_var.set(internal_val)

    def _sync_review_to_menu(self, *args):
        """Sync review tab radio buttons (internal values) to settings dropdown (display names)."""
        if not hasattr(self, "_settings_backend_var") or not hasattr(self, "backend_var"):
            return
        internal_val = self.backend_var.get()
        display_val = getattr(self, "_backend_display_map", {}).get(internal_val, 
                                                                     t("gui.settings.backend_bedrock"))
        if self._settings_backend_var.get() != display_val:
            self._settings_backend_var.set(display_val)

    # ══════════════════════════════════════════════════════════════════════
    #  LOG handling
    # ══════════════════════════════════════════════════════════════════════

    def _install_log_handler(self):
        self._queue_handler = QueueLogHandler(self._log_queue)
        self._queue_handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(self._queue_handler)

    def destroy(self):
        """Clean up log handler and stop poll loop before destroying the window."""
        self._log_polling = False
        if hasattr(self, "_queue_handler"):
            logging.getLogger().removeHandler(self._queue_handler)
        super().destroy()

    def _poll_log_queue(self):
        """Drain the log queue into the log textbox."""
        if not getattr(self, "_log_polling", True):
            return
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
