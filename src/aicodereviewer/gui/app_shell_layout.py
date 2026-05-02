from __future__ import annotations

from typing import Any, Callable

from aicodereviewer.i18n import t


class AppShellLayoutHelper:
    def __init__(self, host: Any) -> None:
        self.host = host

    def install_tab_selection_layout_hooks(self) -> None:
        tabs = getattr(self.host, "tabs", None)
        if tabs is None:
            return
        original_set = tabs.set

        # Guard to prevent re-entrant calls
        self._tab_selection_in_progress = False

        def _on_tab_selected(tab_name: str) -> None:
            """Called whenever a tab is selected — by click or programmatic set()."""
            if getattr(self, "_tab_selection_in_progress", False):
                return
            self._tab_selection_in_progress = True
            try:
                self.schedule_tab_selection_refresh(tab_name)
            finally:
                self._tab_selection_in_progress = False

        # Hook 1: Intercept programmatic tabs.set() calls
        def _set_with_layout_refresh(name: str) -> None:
            self.host._build_tab_if_needed(name)
            original_set(name)
            _on_tab_selected(name)

        # Hook 2: Intercept mouse clicks on tabs via CTkTabview's command callback.
        # CTkTabview._segmented_button_callback calls self._command() with NO
        # arguments (unlike CTkSegmentedButton which passes the value).
        try:
            original_command = tabs._command
        except AttributeError:
            original_command = None

        def _tabview_command() -> None:
            if callable(original_command):
                original_command()
            # Get the currently selected tab name after the switch
            try:
                tab_name = tabs.get()
            except Exception:
                tab_name = None
            if tab_name:
                _on_tab_selected(tab_name)

        tabs.set = _set_with_layout_refresh
        try:
            tabs.configure(command=_tabview_command)
        except Exception:
            pass

    def schedule_tab_selection_refresh(self, tab_name: str) -> None:
        self.host._build_tab_if_needed(tab_name)
        refresh_detach_action = getattr(self.host, "_refresh_detach_action_state", None)
        if callable(refresh_detach_action):
            refresh_detach_action()
        for refresh in self._tab_refreshers(tab_name):
            self.host._schedule_app_after(0, refresh)

    def update_requested_geometry_width(self, geometry_string: str) -> None:
        geometry_text = str(geometry_string).strip()
        geometry_size = geometry_text.split("+", 1)[0]
        if "x" not in geometry_size:
            return
        width_text, _height_text = geometry_size.split("x", 1)
        if width_text.isdigit():
            self.host._requested_geometry_width = int(width_text)

    def schedule_geometry_refreshes(self, active_only: bool = True) -> None:
        self.host._schedule_debounced(
            "_geometry_refresh_after_id",
            self.host._gui_resize_debounce_ms(),
            lambda: self._perform_geometry_refreshes(active_only),
        )

    def apply_geometry_refreshes(self, active_only: bool = True) -> None:
        after_id = getattr(self.host, "_geometry_refresh_after_id", None)
        if after_id is not None:
            try:
                self.host.after_cancel(after_id)
            except Exception:
                pass
            self.host._geometry_refresh_after_id = None
        self._perform_geometry_refreshes(active_only)

    def _perform_geometry_refreshes(self, active_only: bool = True) -> None:
        if not getattr(self.host, "winfo_exists", lambda: False)():
            return
        refreshers = self._active_tab_refreshers() if active_only else self._all_layout_refreshers()
        for refresh in refreshers:
            try:
                refresh()
            except Exception:
                continue
        try:
            self.host._refresh_status_bar_layout()
        except Exception:
            pass
        self.host._refresh_scroll_regions()
        # Removed update_idletasks() to prevent event loop blocking

    def _tab_refreshers(self, tab_name: str) -> tuple[Callable[[], Any], ...]:
        built_tabs = getattr(self.host, "_built_tabs", set())
        if tab_name not in built_tabs:
            return ()
        refreshers: dict[str, tuple[Callable[[], Any], ...]] = {
            t("gui.tab.review"): self._callable_refreshers(
                getattr(self.host, "_refresh_review_tab_layout", None),
                getattr(self.host, "_refresh_review_type_layout", None),
            ),
            t("gui.tab.results"): self._callable_refreshers(
                getattr(self.host, "_refresh_results_tab_layout", None),
            ),
            t("gui.tab.benchmarks"): self._callable_refreshers(
                getattr(self.host, "_refresh_benchmark_tab_layout", None),
            ),
            t("gui.tab.addon_review"): self._callable_refreshers(
                getattr(self.host, "_refresh_addon_review_tab_layout", None),
            ),
            t("gui.tab.settings"): self._callable_refreshers(
                getattr(self.host, "_refresh_settings_tab_layout", None),
            ),
            t("gui.tab.log"): self._callable_refreshers(
                getattr(self.host, "_refresh_log_tab_layout", None),
            ),
        }
        return refreshers.get(tab_name, ())

    def _active_tab_refreshers(self) -> tuple[Callable[[], Any], ...]:
        current_tab = None
        tabs = getattr(self.host, "tabs", None)
        if tabs is not None and hasattr(tabs, "get"):
            try:
                current_tab = tabs.get()
            except Exception:
                current_tab = None
        if not current_tab:
            return self._all_layout_refreshers()
        return self._tab_refreshers(current_tab)

    def _all_layout_refreshers(self) -> tuple[Callable[[], Any], ...]:
        built_tabs = getattr(self.host, "_built_tabs", set())
        refresher_map = {
            t("gui.tab.review"): (
                getattr(self.host, "_refresh_review_tab_layout", None),
                getattr(self.host, "_refresh_review_type_layout", None),
            ),
            t("gui.tab.results"): (getattr(self.host, "_refresh_results_tab_layout", None),),
            t("gui.tab.settings"): (getattr(self.host, "_refresh_settings_tab_layout", None),),
            t("gui.tab.benchmarks"): (getattr(self.host, "_refresh_benchmark_tab_layout", None),),
            t("gui.tab.addon_review"): (getattr(self.host, "_refresh_addon_review_tab_layout", None),),
            t("gui.tab.log"): (getattr(self.host, "_refresh_log_tab_layout", None),),
        }
        result = []
        for tab_name, refreshers in refresher_map.items():
            if tab_name not in built_tabs:
                continue
            for r in refreshers:
                if callable(r):
                    result.append(r)
        return tuple(result)

    @staticmethod
    def _callable_refreshers(*refreshers: Any) -> tuple[Callable[[], Any], ...]:
        return tuple(refresh for refresh in refreshers if callable(refresh))