from __future__ import annotations

import queue
import threading
import tkinter as tk
from types import SimpleNamespace
from typing import Any

from aicodereviewer.gui.app_runtime import AppRuntimeHelper


class _DummyTk:
    def __init__(self, *, pending_after: tuple[Any, ...] = (), raise_on_call: bool = False) -> None:
        self.pending_after = pending_after
        self.raise_on_call = raise_on_call

    def call(self, *args: Any) -> Any:
        if args != ("after", "info"):
            raise AssertionError(f"Unexpected tk.call invocation: {args!r}")
        if self.raise_on_call:
            raise tk.TclError("interpreter is gone")
        return self.pending_after


class _DummyWidget:
    def __init__(
        self,
        *,
        tracked_after: tuple[str, ...] = (),
        pending_after: tuple[Any, ...] = (),
        raise_on_call: bool = False,
        raise_on_cancel: tuple[Any, ...] = (),
    ) -> None:
        self._acr_after_ids = set(tracked_after)
        self.tk = _DummyTk(pending_after=pending_after, raise_on_call=raise_on_call)
        self.raise_on_cancel = set(raise_on_cancel)
        self.cancelled: list[Any] = []

    def after_cancel(self, after_id: Any) -> None:
        self.cancelled.append(after_id)
        if after_id in self.raise_on_cancel:
            raise tk.TclError("no such callback")


def _helper() -> AppRuntimeHelper:
    host = SimpleNamespace(
        _ui_thread_id=threading.get_ident(),
        _log_polling=True,
        _ui_call_queue=queue.Queue(),
    )
    return AppRuntimeHelper(host)


def test_cancel_widget_after_callbacks_cancels_tracked_and_tk_pending_callbacks() -> None:
    helper = _helper()
    widget = _DummyWidget(
        tracked_after=("tracked-1",),
        pending_after=("tk-1", "tk-2"),
    )

    helper.cancel_widget_after_callbacks(widget)

    assert widget._acr_after_ids == set()
    assert widget.cancelled == ["tracked-1", "tk-1", "tk-2"]


def test_cancel_widget_after_callbacks_ignores_tcl_errors_and_continues() -> None:
    helper = _helper()
    widget = _DummyWidget(
        tracked_after=("tracked-1",),
        pending_after=("tk-1", "tk-2"),
        raise_on_cancel=("tracked-1", "tk-1"),
    )

    helper.cancel_widget_after_callbacks(widget)

    assert widget._acr_after_ids == set()
    assert widget.cancelled == ["tracked-1", "tk-1", "tk-2"]


def test_cancel_widget_after_callbacks_returns_when_tk_call_unavailable() -> None:
    helper = _helper()
    widget = _DummyWidget(
        tracked_after=("tracked-1",),
        raise_on_call=True,
    )

    helper.cancel_widget_after_callbacks(widget)

    assert widget._acr_after_ids == set()
    assert widget.cancelled == ["tracked-1"]
