from __future__ import annotations

import tkinter as tk
from typing import Any

from .widgets import _fix_titlebar

__all__ = [
    "resolve_popup_host",
    "resolve_popup_testing_mode",
    "schedule_popup_after",
    "schedule_titlebar_fix",
]


def resolve_popup_host(widget: Any) -> Any | None:
    current = widget
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if callable(getattr(current, "_schedule_widget_after", None)):
            return current
        current = getattr(current, "_ui_parent", None) or getattr(current, "master", None)
    return None


def resolve_popup_testing_mode(widget: Any) -> bool:
    current = widget
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if hasattr(current, "_testing_mode"):
            return bool(getattr(current, "_testing_mode", False))
        current = getattr(current, "_ui_parent", None) or getattr(current, "master", None)
    return False


def _ensure_window_after_cleanup(window: Any) -> bool:
    if hasattr(window, "_acr_after_ids") is False:
        setattr(window, "_acr_after_ids", set())
    if getattr(window, "_acr_after_cleanup_bound", False):
        return True

    def _cleanup(_event: Any | None = None, target: Any = window) -> None:
        after_ids = getattr(target, "_acr_after_ids", None)
        if not after_ids:
            return
        pending_after_ids = tuple(after_ids)
        after_ids.clear()
        for after_id in pending_after_ids:
            try:
                target.after_cancel(after_id)
            except tk.TclError:
                continue

    try:
        window.bind("<Destroy>", _cleanup, add="+")
        setattr(window, "_acr_after_cleanup_bound", True)
    except Exception:
        return False
    return True


def schedule_popup_after(
    window: Any,
    delay_ms: int,
    callback: Any,
    *,
    host: Any | None = None,
    skip_in_tests: bool = False,
) -> Any:
    resolved_host = host or resolve_popup_host(window)
    schedule_widget_after = getattr(resolved_host, "_schedule_widget_after", None)
    if callable(schedule_widget_after):
        return schedule_widget_after(window, delay_ms, callback, skip_in_tests=skip_in_tests)

    testing_mode = resolve_popup_testing_mode(resolved_host or window)
    if skip_in_tests and testing_mode:
        return None
    if window is None:
        return None
    try:
        if not window.winfo_exists():
            return None
    except Exception:
        return None
    if not _ensure_window_after_cleanup(window):
        return None

    try:
        after_id = window.after(delay_ms, callback)
    except tk.TclError:
        return None

    getattr(window, "_acr_after_ids").add(after_id)
    return after_id


def schedule_titlebar_fix(
    window: Any,
    *,
    host: Any | None = None,
    testing_mode: bool | None = None,
) -> None:
    if testing_mode is None:
        testing_mode = resolve_popup_testing_mode(host or window)
    if testing_mode:
        return

    def _apply() -> None:
        try:
            if window.winfo_exists():
                _fix_titlebar(window)
        except tk.TclError:
            return

    schedule_popup_after(window, 10, _apply, host=host, skip_in_tests=True)