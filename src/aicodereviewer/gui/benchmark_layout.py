from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BenchmarkLayoutState:
    action_columns: int
    secondary_action_columns: int
    browser_split: bool
    compare_split: bool
    preview_split: bool
    wraplength: int
    action_button_keys: tuple[str, ...]
    secondary_action_button_keys: tuple[str, ...]


class BenchmarkLayoutHelper:
    def __init__(self, host: Any) -> None:
        self.host = host

    @staticmethod
    def resolve_base_logical_width(host: Any, *candidates: Any) -> float:
        review_width = getattr(host, "_review_logical_width", None)
        if callable(review_width):
            delegated_width = review_width(*candidates)
            if isinstance(delegated_width, (int, float, str)):
                return float(delegated_width)
        available_width = 0
        for candidate in candidates:
            if candidate is None:
                continue
            width = int(getattr(candidate, "winfo_width", lambda: 0)())
            if width > 1:
                available_width = width
                break
        if available_width <= 1:
            available_width = int(getattr(host, "winfo_width", lambda: 0)())
        return float(available_width)

    def resolve_logical_width(self, *candidates: Any) -> float:
        return self.resolve_base_logical_width(self.host, *candidates)

    @staticmethod
    def resolve_action_columns(logical_width: float, *, max_columns: int) -> int:
        if logical_width >= 1300:
            return min(max_columns, 4)
        if logical_width >= 1060:
            return min(max_columns, 3)
        if logical_width >= 760:
            return min(max_columns, 2)
        return 1

    def build_state(
        self,
        logical_width: float,
        *,
        action_buttons: list[Any],
        secondary_action_buttons: list[Any],
    ) -> BenchmarkLayoutState:
        return BenchmarkLayoutState(
            action_columns=self.resolve_action_columns(logical_width, max_columns=3),
            secondary_action_columns=self.resolve_action_columns(logical_width, max_columns=2),
            browser_split=logical_width >= 1060,
            compare_split=logical_width >= 1060,
            preview_split=logical_width >= 1000,
            wraplength=max(360, int(logical_width) - 60),
            action_button_keys=tuple(str(button) for button in action_buttons),
            secondary_action_button_keys=tuple(str(button) for button in secondary_action_buttons),
        )

    def layout_action_frame(
        self,
        frame: Any,
        buttons: list[Any],
        *,
        columns: int,
    ) -> None:
        if frame is None or not buttons:
            return
        for column in range(len(buttons)):
            frame.grid_columnconfigure(column, weight=0, minsize=0)
        for column in range(columns):
            frame.grid_columnconfigure(column, weight=1, minsize=0)
        for index, button in enumerate(buttons):
            button.grid_forget()
            button.grid(
                row=index // columns,
                column=index % columns,
                padx=(0, 8) if index % columns != columns - 1 else 0,
                pady=(0, 8),
                sticky="ew",
            )

    def refresh_tab_layout(self) -> None:
        logical_width = self.resolve_logical_width(
            getattr(self.host, "benchmark_scroll_canvas", None),
            getattr(self.host, "benchmark_scroll_frame", None),
            getattr(self.host, "benchmark_source_actions_frame", None),
            self.host,
        )
        action_buttons = list(getattr(self.host, "_benchmark_action_buttons", []))
        secondary_action_buttons = list(getattr(self.host, "_benchmark_secondary_action_buttons", []))
        state = self.build_state(
            logical_width,
            action_buttons=action_buttons,
            secondary_action_buttons=secondary_action_buttons,
        )
        previous_state = getattr(self.host, "_benchmark_layout_state", None)

        if previous_state is None or (
            previous_state.action_columns != state.action_columns
            or previous_state.action_button_keys != state.action_button_keys
        ):
            self.layout_action_frame(
                getattr(self.host, "benchmark_source_actions_frame", None),
                action_buttons,
                columns=state.action_columns,
            )
        if previous_state is None or (
            previous_state.secondary_action_columns != state.secondary_action_columns
            or previous_state.secondary_action_button_keys != state.secondary_action_button_keys
        ):
            self.layout_action_frame(
                getattr(self.host, "benchmark_source_secondary_actions_frame", None),
                secondary_action_buttons,
                columns=state.secondary_action_columns,
            )

        browser_frame = getattr(self.host, "benchmark_browser_frame", None)
        if browser_frame is not None and (
            previous_state is None or previous_state.browser_split != state.browser_split
        ):
            self.host.benchmark_catalog_box.grid_forget()
            self.host.benchmark_detail_box.grid_forget()
            if state.browser_split:
                browser_frame.grid_columnconfigure(0, weight=1, minsize=0)
                browser_frame.grid_columnconfigure(1, weight=1, minsize=0)
                self.host.benchmark_catalog_box.grid(row=2, column=0, sticky="nsew", padx=(0, 4))
                self.host.benchmark_detail_box.grid(row=2, column=1, sticky="nsew", padx=(4, 0))
            else:
                browser_frame.grid_columnconfigure(0, weight=1, minsize=0)
                browser_frame.grid_columnconfigure(1, weight=0, minsize=0)
                self.host.benchmark_catalog_box.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=0, pady=(0, 8))
                self.host.benchmark_detail_box.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=0)

        compare_frame = getattr(self.host, "benchmark_compare_frame", None)
        if compare_frame is not None and (
            previous_state is None or previous_state.compare_split != state.compare_split
        ):
            self.host.benchmark_takeaways_label.grid_forget()
            self.host.benchmark_primary_summary_label.grid_forget()
            self.host.benchmark_compare_summary_label.grid_forget()
            self.host.benchmark_primary_summary_box.grid_forget()
            self.host.benchmark_compare_summary_box.grid_forget()
            self.host.benchmark_takeaways_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
            if state.compare_split:
                compare_frame.grid_columnconfigure(0, weight=1, minsize=0)
                compare_frame.grid_columnconfigure(1, weight=1, minsize=0)
                self.host.benchmark_primary_summary_label.grid(row=1, column=0, sticky="w", pady=(0, 4))
                self.host.benchmark_compare_summary_label.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(0, 4))
                self.host.benchmark_primary_summary_box.grid(row=2, column=0, sticky="nsew", padx=(0, 4))
                self.host.benchmark_compare_summary_box.grid(row=2, column=1, sticky="nsew", padx=(4, 0))
            else:
                compare_frame.grid_columnconfigure(0, weight=1, minsize=0)
                compare_frame.grid_columnconfigure(1, weight=0, minsize=0)
                self.host.benchmark_primary_summary_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))
                self.host.benchmark_primary_summary_box.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=0, pady=(0, 8))
                self.host.benchmark_compare_summary_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 4))
                self.host.benchmark_compare_summary_box.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=0)

        preview_frame = getattr(self.host, "benchmark_preview_frame", None)
        if preview_frame is not None and (
            previous_state is None or previous_state.preview_split != state.preview_split
        ):
            self.host.benchmark_preview_primary_label.grid_forget()
            self.host.benchmark_preview_compare_label.grid_forget()
            self.host.benchmark_preview_primary_box.grid_forget()
            self.host.benchmark_preview_compare_box.grid_forget()
            if state.preview_split:
                preview_frame.grid_columnconfigure(0, weight=1, minsize=0)
                preview_frame.grid_columnconfigure(1, weight=1, minsize=0)
                self.host.benchmark_preview_primary_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
                self.host.benchmark_preview_compare_label.grid(row=0, column=1, sticky="w", padx=(4, 0), pady=(0, 4))
                self.host.benchmark_preview_primary_box.grid(row=1, column=0, sticky="nsew", padx=(0, 4))
                self.host.benchmark_preview_compare_box.grid(row=1, column=1, sticky="nsew", padx=(4, 0))
            else:
                preview_frame.grid_columnconfigure(0, weight=1, minsize=0)
                preview_frame.grid_columnconfigure(1, weight=0, minsize=0)
                self.host.benchmark_preview_primary_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
                self.host.benchmark_preview_primary_box.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=0, pady=(0, 8))
                self.host.benchmark_preview_compare_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 4))
                self.host.benchmark_preview_compare_box.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=0)

        if previous_state is None or previous_state.wraplength != state.wraplength:
            for label_name in (
                "benchmark_intro_subtitle_label",
                "benchmark_quickstart_label",
                "benchmark_takeaways_label",
                "benchmark_advanced_hint_label",
                "benchmark_source_hint_label",
                "benchmark_fixture_diff_empty_label",
                "benchmark_detached_notice_label",
            ):
                label = getattr(self.host, label_name, None)
                if label is not None:
                    label.configure(wraplength=state.wraplength)
        self.host._benchmark_layout_state = state