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

        def _set_with_layout_refresh(name: str) -> None:
            original_set(name)
            self.schedule_tab_selection_refresh(name)

        tabs.set = _set_with_layout_refresh

    def schedule_tab_selection_refresh(self, tab_name: str) -> None:
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

    def schedule_geometry_refreshes(self) -> None:
        for refresh in self._all_layout_refreshers():
            self.host._schedule_app_after(0, refresh)
            self.host._schedule_app_after(40, refresh)

    def _tab_refreshers(self, tab_name: str) -> tuple[Callable[[], Any], ...]:
        refreshers: dict[str, tuple[Callable[[], Any], ...]] = {
            t("gui.tab.review"): self._callable_refreshers(
                getattr(self.host, "_refresh_review_tab_layout", None),
                getattr(self.host, "_refresh_review_type_layout", None),
            ),
            t("gui.tab.results"): self._callable_refreshers(
                getattr(self.host, "_refresh_results_layout", None),
            ),
            t("gui.tab.benchmarks"): self._callable_refreshers(
                getattr(self.host, "_refresh_benchmark_tab_layout", None),
            ),
            t("gui.tab.settings"): self._callable_refreshers(
                getattr(self.host, "_refresh_settings_layout", None),
            ),
            t("gui.tab.log"): self._callable_refreshers(
                getattr(self.host, "_refresh_log_tab_layout", None),
            ),
        }
        return refreshers.get(tab_name, ())

    def _all_layout_refreshers(self) -> tuple[Callable[[], Any], ...]:
        return self._callable_refreshers(
            getattr(self.host, "_refresh_review_tab_layout", None),
            getattr(self.host, "_refresh_review_type_layout", None),
            getattr(self.host, "_refresh_results_layout", None),
            getattr(self.host, "_refresh_settings_layout", None),
            getattr(self.host, "_refresh_benchmark_tab_layout", None),
            getattr(self.host, "_refresh_log_tab_layout", None),
        )

    @staticmethod
    def _callable_refreshers(*refreshers: Any) -> tuple[Callable[[], Any], ...]:
        return tuple(refresh for refresh in refreshers if callable(refresh))