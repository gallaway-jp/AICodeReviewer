from __future__ import annotations

from typing import Any


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

    def layout_action_frame(
        self,
        frame: Any,
        buttons: list[Any],
        logical_width: float,
        *,
        max_columns: int,
    ) -> None:
        if frame is None or not buttons:
            return
        if logical_width >= 1300:
            columns = min(max_columns, 4)
        elif logical_width >= 1060:
            columns = min(max_columns, 3)
        elif logical_width >= 760:
            columns = min(max_columns, 2)
        else:
            columns = 1
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

        self.layout_action_frame(
            getattr(self.host, "benchmark_source_actions_frame", None),
            list(getattr(self.host, "_benchmark_action_buttons", [])),
            logical_width,
            max_columns=3,
        )
        self.layout_action_frame(
            getattr(self.host, "benchmark_source_secondary_actions_frame", None),
            list(getattr(self.host, "_benchmark_secondary_action_buttons", [])),
            logical_width,
            max_columns=2,
        )

        browser_split = logical_width >= 1060
        browser_frame = getattr(self.host, "benchmark_browser_frame", None)
        if browser_frame is not None:
            self.host.benchmark_catalog_box.grid_forget()
            self.host.benchmark_detail_box.grid_forget()
            if browser_split:
                browser_frame.grid_columnconfigure(0, weight=1, minsize=0)
                browser_frame.grid_columnconfigure(1, weight=1, minsize=0)
                self.host.benchmark_catalog_box.grid(row=2, column=0, sticky="nsew", padx=(0, 4))
                self.host.benchmark_detail_box.grid(row=2, column=1, sticky="nsew", padx=(4, 0))
            else:
                browser_frame.grid_columnconfigure(0, weight=1, minsize=0)
                browser_frame.grid_columnconfigure(1, weight=0, minsize=0)
                self.host.benchmark_catalog_box.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=0, pady=(0, 8))
                self.host.benchmark_detail_box.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=0)

        compare_split = logical_width >= 1060
        compare_frame = getattr(self.host, "benchmark_compare_frame", None)
        if compare_frame is not None:
            self.host.benchmark_takeaways_label.grid_forget()
            self.host.benchmark_primary_summary_label.grid_forget()
            self.host.benchmark_compare_summary_label.grid_forget()
            self.host.benchmark_primary_summary_box.grid_forget()
            self.host.benchmark_compare_summary_box.grid_forget()
            self.host.benchmark_takeaways_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
            if compare_split:
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

        preview_split = logical_width >= 1000
        preview_frame = getattr(self.host, "benchmark_preview_frame", None)
        if preview_frame is not None:
            self.host.benchmark_preview_primary_label.grid_forget()
            self.host.benchmark_preview_compare_label.grid_forget()
            self.host.benchmark_preview_primary_box.grid_forget()
            self.host.benchmark_preview_compare_box.grid_forget()
            if preview_split:
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

        wraplength = max(360, int(logical_width) - 60)
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
                label.configure(wraplength=wraplength)