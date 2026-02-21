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
- Inline results with per-issue actions on the Results tab
- Connection testing & backend health checking
- Localised UI (English / Japanese) with theme support

The implementation is decomposed into mixins for maintainability:

* :class:`ReviewTabMixin`   - Review tab UI, validation, review execution
* :class:`ResultsTabMixin`  - Results tab, issue cards, AI Fix, sessions
* :class:`SettingsTabMixin`  - Settings tab, save / reset
* :class:`HealthMixin`       - Backend health checks, model refresh
"""
import logging
import queue
import time
from pathlib import Path
from tkinter import filedialog
from typing import Any, List, Optional

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.config import config
from aicodereviewer.auth import get_system_language
from aicodereviewer.i18n import t, set_locale
from aicodereviewer.models import ReviewIssue
from aicodereviewer.orchestration import AppRunner

from .widgets import QueueLogHandler, _Tooltip
from .review_mixin import ReviewTabMixin
from .results_mixin import ResultsTabMixin, IssueCard, _NUMERIC_SETTINGS
from .settings_mixin import SettingsTabMixin
from .health_mixin import HealthMixin

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (tests, tools, etc.)
from .widgets import _CancelledError, _fix_titlebar, InfoTooltip  # noqa: F401
from .dialogs import FileSelector, ConfirmDialog  # noqa: F401

__all__ = [
    "App",
    "launch",
    "IssueCard",
    "_NUMERIC_SETTINGS",
    "_CancelledError",
    "_fix_titlebar",
    "InfoTooltip",
    "FileSelector",
    "ConfirmDialog",
]


class App(
    ReviewTabMixin,
    ResultsTabMixin,
    SettingsTabMixin,
    HealthMixin,
    ctk.CTk,
):
    """Root window of the AICodeReviewer GUI."""

    WIDTH = 1100
    HEIGHT = 820

    def __init__(self, *, testing_mode: bool = False):
        super().__init__()
        self._testing_mode = testing_mode

        # -- Detect language & apply saved preferences --
        saved_lang = config.get("gui", "language", "").strip()
        if saved_lang and saved_lang != "system":
            self._ui_lang = saved_lang
        else:
            self._ui_lang = get_system_language()
        set_locale(self._ui_lang)

        # -- Apply saved theme --
        saved_theme = config.get("gui", "theme", "").strip() or "system"
        theme_map = {"system": "System", "dark": "Dark", "light": "Light"}
        ctk.set_appearance_mode(theme_map.get(saved_theme, "System"))
        ctk.set_default_color_theme("blue")

        self.title(t("common.app_title"))
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(900, 680)

        # Logging queue
        self._log_queue: queue.Queue = queue.Queue(maxsize=5000)
        self._log_lines: List[tuple] = []
        self._install_log_handler()

        # State
        self._issues: List[ReviewIssue] = []
        self._running = False
        self._review_client = None
        self._health_check_backend = None
        self._health_check_timer = None
        self._model_refresh_in_progress: set[str] = set()
        self._elapsed_start: Optional[float] = None
        self._elapsed_after_id: Optional[str] = None
        self._health_countdown_end: Optional[float] = None
        self._health_countdown_after_id: Optional[str] = None

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
            self.after(500, self._auto_health_check)

    # -- UI construction --

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
        ctk.CTkLabel(status_frame, textvariable=self.status_var,
                     anchor="w").grid(row=0, column=0, sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            status_frame, text=t("gui.cancel_btn"), width=80,
            fg_color="#dc2626", hover_color="#b91c1c",
            state="disabled", command=self._cancel_operation)
        self.cancel_btn.grid(row=0, column=1, padx=(8, 0))

        self._health_countdown_lbl = ctk.CTkLabel(
            status_frame, text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            width=56, anchor="e")
        self._health_countdown_lbl.grid(row=0, column=2, padx=(4, 0))

        self._bind_shortcuts()

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-Return>",
                      lambda e: self._start_review() if not self._running else None)
        self.bind_all("<Control-s>", self._on_ctrl_s)

    def _on_ctrl_s(self, event: Any) -> None:
        if self.tabs.get() == t("gui.tab.settings"):
            self._save_settings()

    # -- LOG TAB --

    def _build_log_tab(self):
        tab = self.tabs.add(t("gui.tab.log"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        filter_frame = ctk.CTkFrame(tab, fg_color="transparent")
        filter_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 0))

        ctk.CTkLabel(filter_frame, text="Level:").grid(row=0, column=0, padx=(0, 4))
        self._log_level_var = ctk.StringVar(value="All")
        _LOG_LEVELS = ["All", "DEBUG", "INFO", "WARNING", "ERROR"]
        self._log_level_menu = ctk.CTkOptionMenu(
            filter_frame,
            variable=self._log_level_var,
            values=_LOG_LEVELS,
            width=110,
            command=self._on_log_level_changed)
        self._log_level_menu.grid(row=0, column=1, padx=(0, 8))

        self.log_box = ctk.CTkTextbox(tab, state="disabled", wrap="word",
                                       font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)

        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=2, column=0, pady=4)

        ctk.CTkButton(btn_frame, text=t("gui.log.clear"), width=110,
                      command=self._clear_log).grid(row=0, column=0, padx=6)
        ctk.CTkButton(btn_frame, text=t("gui.log.save"), width=110,
                      command=self._save_log).grid(row=0, column=1, padx=6)

    # -- LOG handling --

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
        if not getattr(self, "_log_polling", True):
            return
        _LEVEL_MAP = {"All": 0, "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
        min_level = _LEVEL_MAP.get(
            getattr(self, "_log_level_var", None) and self._log_level_var.get(), 0)
        batch = []
        while True:
            try:
                batch.append(self._log_queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self._log_lines.extend(batch)
            visible = [text for lvl, text in batch if lvl >= min_level]
            if visible:
                self.log_box.configure(state="normal")
                self.log_box.insert("end", "\n".join(visible) + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        self.after(100, self._poll_log_queue)

    def _on_log_level_changed(self, _value: str = "") -> None:
        _LEVEL_MAP = {"All": 0, "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
        min_level = _LEVEL_MAP.get(self._log_level_var.get(), 0)
        visible = [text for lvl, text in self._log_lines if lvl >= min_level]
        self.log_box.configure(state="normal")
        self.log_box.delete("0.0", "end")
        if visible:
            self.log_box.insert("0.0", "\n".join(visible) + "\n")
            self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self._log_lines.clear()
        self.log_box.configure(state="normal")
        self.log_box.delete("0.0", "end")
        self.log_box.configure(state="disabled")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title=t("gui.log.save_dialog_title"),
        )
        if not path:
            return
        try:
            content = self.log_box.get("0.0", "end")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self._show_toast(t("gui.log.saved", path=Path(path).name))
        except Exception as exc:
            self._show_toast(str(exc), error=True)

    # -- TOAST NOTIFICATIONS --

    _TOAST_SLOT_PX = 52

    def _restack_toasts(self) -> None:
        win_h = self.winfo_height() or self.HEIGHT
        for i, frame in enumerate(self._active_toasts):
            offset_px = i * self._TOAST_SLOT_PX
            rely = 1.0 - (offset_px + 24) / win_h
            try:
                frame.place(relx=0.5, rely=rely, anchor="s")
                frame.lift()
            except Exception:
                pass

    def _show_toast(self, message: str, *, duration: int = 6000,
                    error: bool = False):
        bg = "#dc2626" if error else ("#1a7f37", "#2ea043")
        fg = "white"

        toast = ctk.CTkFrame(self, corner_radius=8,
                              fg_color=bg, border_width=0)
        self._active_toasts.append(toast)
        self._restack_toasts()

        lbl = ctk.CTkLabel(toast, text=message, text_color=fg,
                            font=ctk.CTkFont(size=12),
                            wraplength=600, anchor="center")
        lbl.pack(padx=16, pady=8)

        def _dismiss():
            try:
                toast.destroy()
            except Exception:
                pass
            try:
                self._active_toasts.remove(toast)
            except ValueError:
                pass
            self._restack_toasts()

        self.after(duration, _dismiss)


# -- public launcher --

def launch():
    """Create and run the application."""
    app = App()
    app.mainloop()