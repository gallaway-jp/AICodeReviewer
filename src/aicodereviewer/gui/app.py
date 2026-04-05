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
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.execution import ReviewExecutionRuntime
from aicodereviewer.http_api import create_local_http_app, start_local_http_server
from aicodereviewer.i18n import t

from .app_composition import AppCompositionHelper
from .benchmark_mixin import BenchmarkTabMixin
from .review_mixin import ReviewTabMixin
from .popup_utils import schedule_popup_after, schedule_titlebar_fix
from .results_mixin import ResultsTabMixin, IssueCard, _NUMERIC_SETTINGS
from .settings_mixin import SettingsTabMixin
from .health_mixin import HealthMixin

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
    BenchmarkTabMixin,
    ResultsTabMixin,
    SettingsTabMixin,
    HealthMixin,
    ctk.CTk,
):
    """Root window of the AICodeReviewer GUI."""

    WIDTH = 1100
    HEIGHT = 820
    _testing_mode: bool
    tabs: Any

    def __init__(self, *, testing_mode: bool = False, review_runtime: ReviewExecutionRuntime | None = None):
        super().__init__()
        self._app_helpers().bootstrap().initialize(
            testing_mode=testing_mode,
            review_runtime=review_runtime,
        )

        self._app_helpers().lifecycle().run_startup()

    def _app_helpers(self) -> AppCompositionHelper:
        helper = getattr(self, "_app_composition_delegate", None)
        if helper is None:
            helper = AppCompositionHelper(self)
            self._app_composition_delegate = helper
        return helper

    def _cancel_widget_after_callbacks(self, widget: Any) -> None:
        self._app_helpers().runtime().cancel_widget_after_callbacks(widget)

    def _ensure_widget_after_cleanup(self, widget: Any) -> None:
        self._app_helpers().runtime().ensure_widget_after_cleanup(widget)

    def _schedule_widget_after(
        self,
        widget: Any,
        delay_ms: int,
        callback: Any,
        *,
        skip_in_tests: bool = False,
    ) -> Any:
        return self._app_helpers().runtime().schedule_widget_after(
            widget,
            delay_ms,
            callback,
            skip_in_tests=skip_in_tests,
        )

    def _schedule_app_after(self, delay_ms: int, callback: Any) -> Any:
        return self._app_helpers().runtime().schedule_app_after(delay_ms, callback)

    def _schedule_popup_after(self, window: Any, delay_ms: int, callback: Any) -> Any:
        return schedule_popup_after(window, delay_ms, callback, host=self, skip_in_tests=True)

    def _schedule_titlebar_fix(self, window: Any) -> None:
        schedule_titlebar_fix(window, host=self, testing_mode=self._testing_mode)

    # -- UI construction --

    def _build_ui(self):
        self._app_helpers().bootstrap().build_ui()

    def _bind_shortcuts(self) -> None:
        self._app_helpers().bootstrap().bind_shortcuts()

    def _install_tab_selection_layout_hooks(self) -> None:
        self._app_helpers().shell_layout().install_tab_selection_layout_hooks()

    def _on_ctrl_s(self, event: Any) -> None:
        if self.tabs.get() == t("gui.tab.settings"):
            self._save_settings()

    # -- LOG TAB --

    def _build_log_tab(self):
        self._app_helpers().surfaces().build_log_tab()

    def _log_logical_width(self, *candidates: Any) -> float:
        return self._app_helpers().surfaces().resolve_logical_width(*candidates)

    def _schedule_log_layout_refresh(self, *_args: Any) -> None:
        self._refresh_log_tab_layout()

    def _refresh_log_tab_layout(self) -> None:
        self._app_helpers().surfaces().refresh_log_tab_layout()

    # -- LOG handling --

    def _install_log_handler(self):
        self._app_helpers().bootstrap().install_log_handler()

    def geometry(self, geometry_string: str | None = None) -> Any:
        if geometry_string is None:
            return super().geometry()

        self._app_helpers().shell_layout().update_requested_geometry_width(geometry_string)
        result = super().geometry(geometry_string)
        if hasattr(self, "tabs"):
            self._app_helpers().shell_layout().schedule_geometry_refreshes()
        return result

    def destroy(self):
        """Clean up log handler and stop poll loop before destroying the window."""
        self._app_helpers().lifecycle().prepare_for_destroy()
        super().destroy()

    def _run_on_ui_thread(self, callback: Any, *args: Any, **kwargs: Any) -> bool:
        """Run the callback on the UI thread or enqueue it for the next poll tick."""
        return self._app_helpers().runtime().run_on_ui_thread(callback, *args, **kwargs)

    def _drain_ui_call_queue(self) -> None:
        """Execute any pending worker-thread UI callbacks on the main loop."""
        self._app_helpers().runtime().drain_ui_call_queue()

    def _start_local_http_server_from_settings(self) -> None:
        self._app_helpers().local_http().start_from_settings()

    def _create_local_http_app(self, *, runtime: Any = None) -> Any:
        return create_local_http_app(runtime=runtime)

    def _start_local_http_server(self, app: Any, *, host: str, port: int) -> Any:
        return start_local_http_server(app, host=host, port=port)

    def _stop_local_http_server(self) -> None:
        self._app_helpers().local_http().stop()

    def _local_http_runtime_status_snapshot(self) -> tuple[str, str]:
        return self._app_helpers().local_http().runtime_status_snapshot()

    def _poll_log_queue(self):
        self._app_helpers().surfaces().poll_log_queue()

    def _on_log_level_changed(self, _value: str = "") -> None:
        self._app_helpers().surfaces().on_log_level_changed()

    def _clear_log(self):
        self._app_helpers().surfaces().clear_log()

    def _save_log(self):
        self._app_helpers().surfaces().save_log()

    # -- TOAST NOTIFICATIONS --

    _TOAST_SLOT_PX = 52

    def _restack_toasts(self) -> None:
        self._app_helpers().surfaces().restack_toasts()

    def _show_toast(self, message: str, *, duration: int = 6000,
                    error: bool = False):
        self._app_helpers().surfaces().show_toast(message, duration=duration, error=error)


# -- public launcher --

def launch():
    """Create and run the application."""
    app = App()
    app.mainloop()