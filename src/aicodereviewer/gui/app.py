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
* :class:`AddonReviewTabMixin` - Addon review tab and detached window
* :class:`ResultsTabMixin`  - Results tab, issue cards, AI Fix, sessions
* :class:`SettingsTabMixin`  - Settings tab, save / reset
* :class:`HealthMixin`       - Backend health checks, model refresh
"""
import logging
import platform
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.config import config
from aicodereviewer.execution import ReviewExecutionRuntime
from aicodereviewer.http_api import create_local_http_app, start_local_http_server
from aicodereviewer.i18n import t

from .addon_review_mixin import AddonReviewTabMixin
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


def _automatic_dpi_awareness_enabled() -> bool:
    if platform.system() != "Windows":
        return True
    raw = str(config.get("gui", "automatic_dpi_awareness", "false") or "false").strip().lower()
    return raw in ("true", "1", "yes", "on")


def _configure_customtkinter_dpi_awareness() -> None:
    if platform.system() != "Windows":
        return
    if _automatic_dpi_awareness_enabled():
        return
    try:
        ctk.deactivate_automatic_dpi_awareness()
    except Exception:
        logging.getLogger(__name__).debug("Unable to deactivate CustomTkinter DPI awareness", exc_info=True)


class App(
    ReviewTabMixin,
    AddonReviewTabMixin,
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
        _configure_customtkinter_dpi_awareness()
        super().__init__()
        self._startup_window_hidden = False
        if not testing_mode:
            try:
                self.withdraw()
                self._startup_window_hidden = True
            except Exception:
                self._startup_window_hidden = False
        self._configure_event_counts: dict[str, int] = {}
        self._configure_refresh_counts: dict[str, int] = {}
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

    def _schedule_debounced(self, attr: str, delay_ms: int, callback: Any) -> Any:
        previous = getattr(self, attr, None)
        if previous is not None:
            try:
                self.after_cancel(previous)
            except Exception:
                pass
        if delay_ms <= 0:
            callback()
            return None
        after_id = self._schedule_widget_after(self, delay_ms, callback)
        setattr(self, attr, after_id)
        return after_id

    def _increment_configure_event(self, event_name: str) -> None:
        self._configure_event_counts[event_name] = self._configure_event_counts.get(event_name, 0) + 1

    def _increment_configure_refresh(self, event_name: str) -> None:
        self._configure_refresh_counts[event_name] = self._configure_refresh_counts.get(event_name, 0) + 1

    def _wrap_configure_refresh(self, callback: Any, event_name: str) -> Any:
        def _wrapped() -> None:
            self._increment_configure_refresh(event_name)
            callback()

        return _wrapped

    def _schedule_configure_refresh(self, attr: str, delay_ms: int, callback: Any) -> Any:
        self._increment_configure_event(attr)
        return self._schedule_debounced(
            attr,
            delay_ms,
            self._wrap_configure_refresh(callback, attr),
        )

    def _current_tab_name(self) -> str | None:
        tabs = getattr(self, "tabs", None)
        if tabs is None or not hasattr(tabs, "get"):
            return None
        try:
            current_tab = tabs.get()
        except Exception:
            return None
        return str(current_tab) if current_tab else None

    def _detached_window_exists(self, attr_name: str | None) -> bool:
        if not attr_name:
            return False
        window = getattr(self, attr_name, None)
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except Exception:
            return False

    def _is_layout_surface_active(self, tab_name: str, *, detached_window_attr: str | None = None) -> bool:
        if self._detached_window_exists(detached_window_attr):
            return True
        return self._current_tab_name() == tab_name

    def _schedule_surface_layout_refresh(
        self,
        attr: str,
        callback: Any,
        *,
        tab_name: str,
        detached_window_attr: str | None = None,
    ) -> Any:
        if not self._is_layout_surface_active(tab_name, detached_window_attr=detached_window_attr):
            return None
        return self._schedule_configure_refresh(
            attr,
            self._gui_resize_debounce_ms(),
            callback,
        )

    def _configure_metrics_snapshot(self) -> dict[str, dict[str, int]]:
        return {
            "events": dict(self._configure_event_counts),
            "refreshes": dict(self._configure_refresh_counts),
        }

    def _schedule_popup_after(self, window: Any, delay_ms: int, callback: Any) -> Any:
        return schedule_popup_after(window, delay_ms, callback, host=self, skip_in_tests=True)

    def _finalize_startup_presentation(self) -> None:
        if not getattr(self, "_startup_window_hidden", False):
            return
        try:
            self._app_helpers().shell_layout().apply_geometry_refreshes(active_only=False)
        except Exception:
            logging.getLogger(__name__).debug("Startup geometry refresh failed", exc_info=True)
        try:
            self._refresh_detach_action_state()
        except Exception:
            logging.getLogger(__name__).debug("Startup detach refresh failed", exc_info=True)
        try:
            self.update_idletasks()
        except Exception:
            logging.getLogger(__name__).debug("Startup idle refresh failed", exc_info=True)
        try:
            self.deiconify()
            self.lift()
        except Exception:
            logging.getLogger(__name__).debug("Startup presentation failed", exc_info=True)
        self._startup_window_hidden = False

    def _ensure_tab(self, tab_name: str) -> Any:
        tabs = getattr(self, "tabs", None)
        if tabs is None:
            raise RuntimeError("Tabs widget is not initialized")
        # Use our own tracking dict first to avoid relying on private CTkTabview API
        own_dict = getattr(self, "_tab_name_to_frame", None)
        if own_dict is not None and tab_name in own_dict:
            return own_dict[tab_name]
        # Fallback: try CTkTabview's internal dict
        tab_dict = getattr(tabs, "_tab_dict", None)
        if tab_dict is not None and tab_name in tab_dict:
            frame = tab_dict[tab_name]
            if own_dict is not None:
                own_dict[tab_name] = frame
            return frame
        frame = tabs.add(tab_name)
        if own_dict is not None:
            own_dict[tab_name] = frame
        return frame

    def _build_tab_if_needed(self, tab_name: str) -> None:
        builder = getattr(self, "_lazy_tab_builders", {}).get(tab_name)
        if builder is None or tab_name in getattr(self, "_built_tabs", set()):
            return
        builder()
        self._built_tabs.add(tab_name)
        # After building, schedule a layout refresh for this tab
        self._schedule_app_after(0, lambda: self._refresh_tab_layout(tab_name))

    def _schedule_titlebar_fix(self, window: Any) -> None:
        schedule_titlebar_fix(window, host=self, testing_mode=self._testing_mode)

    def _visible_scroll_region_roots(self) -> list[Any]:
        roots: list[Any] = []
        seen: set[int] = set()

        def _append_root(candidate: Any) -> None:
            if candidate is None:
                return
            marker = id(candidate)
            if marker in seen:
                return
            try:
                if not candidate.winfo_exists():
                    return
            except Exception:
                return
            seen.add(marker)
            roots.append(candidate)

        current_tab = self._current_tab_name()
        tab_frames = getattr(self, "_tab_name_to_frame", {}) or {}
        if current_tab:
            _append_root(tab_frames.get(current_tab))

        for attr_name in (
            "_detached_settings_container",
            "_detached_benchmark_container",
            "_detached_addon_review_container",
            "_detached_log_window",
        ):
            _append_root(getattr(self, attr_name, None))

        return roots

    def _refresh_scroll_regions(self) -> None:
        def _walk(root: Any) -> list[Any]:
            widgets = [root]
            for child in getattr(root, "winfo_children", lambda: [])():
                widgets.extend(_walk(child))
            return widgets

        roots = self._visible_scroll_region_roots()
        if not roots:
            roots = [self]

        seen_widgets: set[int] = set()
        for root in roots:
            for widget in _walk(root):
                marker = id(widget)
                if marker in seen_widgets:
                    continue
                seen_widgets.add(marker)
                update_scroll = getattr(widget, "_acr_update_scroll_region", None)
                if callable(update_scroll):
                    try:
                        update_scroll()
                    except Exception:
                        pass

    def _gui_resize_debounce_ms(self) -> int:
        try:
            return max(100, int(config.get("gui", "resize_debounce_ms", 100) or 100))
        except Exception:
            return 100

    def _gui_toast_duration_ms(self) -> int:
        try:
            return max(1000, int(config.get("gui", "toast_duration_ms", 6000) or 6000))
        except Exception:
            return 6000

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
        self._schedule_surface_layout_refresh(
            "_log_layout_refresh_after_id",
            self._refresh_log_tab_layout,
            tab_name=t("gui.tab.log"),
            detached_window_attr="_detached_log_window",
        )

    def _schedule_status_bar_layout_refresh(self, *_args: Any) -> None:
        self._schedule_configure_refresh(
            "_status_bar_layout_refresh_after_id",
            self._gui_resize_debounce_ms(),
            self._refresh_status_bar_layout,
        )

    def _refresh_log_tab_layout(self) -> None:
        self._app_helpers().surfaces().refresh_log_tab_layout()

    def _refresh_status_bar_layout(self) -> None:
        self._app_helpers().surfaces().refresh_status_bar_layout()

    def _refresh_detach_action_state(self) -> None:
        self._app_helpers().surfaces().refresh_detach_action_state()

    # -- LOG handling --

    def _install_log_handler(self):
        self._app_helpers().bootstrap().install_log_handler()

    def geometry(self, geometry_string: str | None = None) -> Any:
        if geometry_string is None:
            return super().geometry()

        self._app_helpers().shell_layout().update_requested_geometry_width(geometry_string)
        result = super().geometry(geometry_string)
        # Removed update_idletasks() to prevent event loop blocking during resize
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

    def _open_detached_log_window(self) -> None:
        self._app_helpers().surfaces().open_detached_log_window()

    def _redock_detached_log_window(self) -> None:
        self._app_helpers().surfaces().redock_detached_log_window()

    def _restore_detached_windows(self) -> None:
        self._app_helpers().surfaces().restore_detached_windows()

    def _open_detached_settings_window(self, *, restoring: bool = False) -> None:
        self._settings_open_detached_window(restoring=restoring)

    def _redock_detached_settings_window(self) -> None:
        self._settings_redock_detached_window()

    def _open_detached_benchmark_window(self, *, restoring: bool = False) -> None:
        self._benchmark_open_detached_window(restoring=restoring)

    def _redock_detached_benchmark_window(self) -> None:
        self._benchmark_redock_detached_window()

    def _open_detached_addon_review_window(self, *, restoring: bool = False) -> None:
        self._addon_review_open_detached_window(restoring=restoring)

    def _redock_detached_addon_review_window(self) -> None:
        self._addon_review_redock_detached_window()

    def _detach_current_page_shortcut(self, event: Any = None) -> str | None:
        return self._app_helpers().surfaces().detach_current_page_into_window(event)

    # -- TOAST NOTIFICATIONS --

    _TOAST_SLOT_PX = 52

    def _restack_toasts(self) -> None:
        self._app_helpers().surfaces().restack_toasts()

    def _show_toast(self, message: str, *, duration: int = 6000,
                    error: bool = False):
        self._app_helpers().surfaces().show_toast(message, duration=duration, error=error)

    def _refresh_tab_layout(self, tab_name: str) -> None:
        """Refresh layout for a specific tab by name. Safe to call for any tab."""
        refreshers = self._app_helpers().shell_layout()._tab_refreshers(tab_name)
        for refresh in refreshers:
            try:
                refresh()
            except Exception:
                continue

    def _schedule_window_resize_refresh(self, event: Any = None) -> None:
        """Single coalesced handler for all Configure events (resize, move, etc.).

        Consolidates what was previously three separate refresh chains into one
        debounced call, preventing redundant layout recalculations.
        """
        delay_ms = self._gui_resize_debounce_ms()
        if event is not None and getattr(event, "widget", None) is not self:
            return
        if event is not None and getattr(event, "widget", None) is self:
            width = getattr(event, "width", None)
            height = getattr(event, "height", None)
            if isinstance(width, int) and isinstance(height, int) and width > 1 and height > 1:
                last_size = getattr(self, "_window_resize_last_size", None)
                if last_size == (width, height):
                    return
                self._window_resize_last_size = (width, height)
                if last_size is not None:
                    last_w, last_h = last_size
                    width_delta = abs(width - last_w)
                    height_delta = abs(height - last_h)
                    if width_delta < 5 and height_delta < 5:
                        return
                    if width_delta > max(48, int(last_w * 0.12)) or height_delta > max(32, int(last_h * 0.12)):
                        delay_ms = max(delay_ms, 150)
        self._schedule_configure_refresh(
            "_window_resize_refresh_after_id",
            delay_ms,
            self._apply_coalesced_resize_refresh,
        )

    def _apply_coalesced_resize_refresh(self) -> None:
        """Single refresh call that handles layout, toasts, and scroll regions."""
        try:
            self._app_helpers().shell_layout().apply_geometry_refreshes(active_only=True)
            self._restack_toasts()
        except Exception:
            logging.getLogger(__name__).exception("Coalesced resize refresh failed")


# -- public launcher --

def launch():
    """Create and run the application."""
    app = App()
    app.mainloop()