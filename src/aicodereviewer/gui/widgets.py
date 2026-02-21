# src/aicodereviewer/gui/widgets.py
"""Reusable lightweight GUI utilities shared across the application.

Contains:
- ``_CancelledError`` – sentinel used to abort a running operation
- ``_fix_titlebar`` – force Windows DWM dark-mode title bar
- ``QueueLogHandler`` – send log records to a queue for the GUI
- ``InfoTooltip`` / ``_Tooltip`` – hover-tooltip helpers
"""
from __future__ import annotations

import ctypes
import logging
import queue
import sys
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

__all__ = [
    "_CancelledError",
    "_fix_titlebar",
    "QueueLogHandler",
    "InfoTooltip",
    "_Tooltip",
]

import tkinter as tk


class _CancelledError(Exception):
    """Raised when the user cancels a running operation."""


def _fix_titlebar(win: "tk.BaseWidget") -> None:
    """Force the Windows native title bar to honour the current CTk theme.

    CTkToplevel windows on Windows keep the OS-default (light) title bar even
    when the rest of the UI is in dark mode.  The DWM API attribute
    DWMWA_USE_IMMERSIVE_DARK_MODE (id 20) fixes this once the window handle
    is available.  Safe no-op on non-Windows platforms.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        dark = ctypes.c_int(1 if ctk.get_appearance_mode().lower() == "dark" else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
    except Exception:  # pragma: no cover
        pass


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
        widget.bind("<Destroy>", self._hide)

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
            try:
                self._tipwindow.destroy()
            except Exception:
                pass
            self._tipwindow = None
