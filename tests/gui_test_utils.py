from __future__ import annotations

import time
from pathlib import Path
from typing import Any


class GuiTestHarness:
    """Drive the GUI in tests using the same controls a user would touch."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.toasts: list[tuple[str, bool]] = []
        self._scheduled_callbacks: dict[str, tuple[float, Any, tuple[Any, ...]]] = {}
        self._after_counter = 0

        def _capture_toast(
            message: str,
            *,
            duration: int = 6000,
            error: bool = False,
        ) -> None:
            self.toasts.append((message, error))

        def _after(delay_ms: int, callback: Any = None, *args: Any) -> str:
            self._after_counter += 1
            token = f"gui-harness-after-{self._after_counter}"
            if callback is None:
                callback = lambda: None
            due = time.monotonic() + max(delay_ms, 0) / 1000.0
            self._scheduled_callbacks[token] = (due, callback, args)
            return token

        def _after_cancel(token: str) -> None:
            self._scheduled_callbacks.pop(token, None)

        self.app._show_toast = _capture_toast
        self.app.after = _after
        self.app.after_cancel = _after_cancel

    def pump(self, cycles: int = 1) -> None:
        for _ in range(cycles):
            self.app.update_idletasks()
            self.app.update()
            now = time.monotonic()
            ready = [
                token
                for token, (due, _callback, _args) in self._scheduled_callbacks.items()
                if due <= now
            ]
            for token in ready:
                _due, callback, args = self._scheduled_callbacks.pop(token)
                callback(*args)

    def wait_until(
        self,
        predicate: Any,
        *,
        timeout: float = 5.0,
        interval: float = 0.01,
        message: str | None = None,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            if predicate():
                return
            time.sleep(interval)
        raise AssertionError(message or "Condition not met before timeout")

    def enable_runtime_actions(self) -> None:
        self.app._testing_mode = False

    def set_entry(self, entry: Any, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)

    def select_review_types(self, *review_types: str) -> None:
        selected = set(review_types)
        for key, var in self.app.type_vars.items():
            var.set(key in selected)

    def fill_valid_review_form(
        self,
        project_path: Path,
        *,
        review_types: tuple[str, ...] = ("security",),
        programmers: str = "Alice",
        reviewers: str = "Bob",
    ) -> None:
        self.app.scope_var.set("project")
        self.pump()
        self.set_entry(self.app.path_entry, str(project_path))
        self.set_entry(self.app.programmers_entry, programmers)
        self.set_entry(self.app.reviewers_entry, reviewers)
        self.app.file_select_mode_var.set("all")
        self.select_review_types(*review_types)
        self.pump()

    def start_review(self) -> None:
        self.app.run_btn.invoke()
        self.pump()

    def start_dry_run(self) -> None:
        self.app.dry_btn.invoke()
        self.pump()

    def start_health_check(self) -> None:
        self.app.health_btn.invoke()
        self.pump()

    def log_text(self) -> str:
        return self.app.log_box.get("0.0", "end").strip()
