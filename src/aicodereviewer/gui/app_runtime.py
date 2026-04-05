from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from typing import Any

logger = logging.getLogger(__name__)


class AppRuntimeHelper:
    def __init__(self, host: Any) -> None:
        self.host = host

    def cancel_widget_after_callbacks(self, widget: Any) -> None:
        after_ids = getattr(widget, "_acr_after_ids", None)
        if not after_ids:
            return
        pending_after_ids = tuple(after_ids)
        after_ids.clear()
        for after_id in pending_after_ids:
            try:
                widget.after_cancel(after_id)
            except tk.TclError:
                continue

    def ensure_widget_after_cleanup(self, widget: Any) -> None:
        if widget is None or getattr(widget, "_acr_after_cleanup_bound", False):
            return
        if not hasattr(widget, "_acr_after_ids"):
            setattr(widget, "_acr_after_ids", set())

        def _cleanup(_event: Any | None = None, target: Any = widget) -> None:
            self.cancel_widget_after_callbacks(target)

        try:
            widget.bind("<Destroy>", _cleanup, add="+")
        except Exception:
            return
        setattr(widget, "_acr_after_cleanup_bound", True)

    def schedule_widget_after(
        self,
        widget: Any,
        delay_ms: int,
        callback: Any,
        *,
        skip_in_tests: bool = False,
    ) -> Any:
        if threading.get_ident() != getattr(self.host, "_ui_thread_id", None):
            self.host._run_on_ui_thread(
                self.schedule_widget_after,
                widget,
                delay_ms,
                callback,
                skip_in_tests=skip_in_tests,
            )
            return None
        if widget is None or (skip_in_tests and self.host._testing_mode):
            return None
        try:
            if not widget.winfo_exists():
                return None
        except Exception:
            return None

        self.ensure_widget_after_cleanup(widget)
        after_ids = getattr(widget, "_acr_after_ids", None)
        if after_ids is None:
            after_ids = set()
            setattr(widget, "_acr_after_ids", after_ids)

        callback_id: dict[str, Any] = {"value": None}

        def _wrapped() -> None:
            after_id = callback_id["value"]
            if after_id is not None:
                after_ids.discard(after_id)
            try:
                if widget.winfo_exists():
                    callback()
            except tk.TclError:
                return

        try:
            after_id = widget.after(delay_ms, _wrapped)
        except tk.TclError:
            return None
        callback_id["value"] = after_id
        after_ids.add(after_id)
        return after_id

    def schedule_app_after(self, delay_ms: int, callback: Any) -> Any:
        return self.schedule_widget_after(self.host, delay_ms, callback)

    def run_on_ui_thread(self, callback: Any, *args: Any, **kwargs: Any) -> bool:
        if threading.get_ident() == getattr(self.host, "_ui_thread_id", None):
            callback(*args, **kwargs)
            return True
        if not getattr(self.host, "_log_polling", True):
            return False
        self.host._ui_call_queue.put((callback, args, kwargs))
        return True

    def drain_ui_call_queue(self) -> None:
        while True:
            try:
                callback, args, kwargs = self.host._ui_call_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args, **kwargs)
            except Exception:
                logger.exception("Queued UI callback failed")

    def clear_ui_call_queue(self) -> None:
        while not self.host._ui_call_queue.empty():
            try:
                self.host._ui_call_queue.get_nowait()
            except queue.Empty:
                break