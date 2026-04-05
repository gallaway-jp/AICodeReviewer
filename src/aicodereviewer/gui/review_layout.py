from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReviewTabLayoutState:
    split_mode: bool


@dataclass(frozen=True)
class ReviewTypeLayoutState:
    wraplength: int
    checkbox_columns: int
    checkbox_rows_per_column: int
    checkbox_width: int
    controls_mode: str
    preset_inline: bool


class ReviewLayoutHelper:
    def __init__(self, host: Any) -> None:
        self.host = host

    def resolve_logical_width(self, *candidates: Any) -> float:
        review_width = getattr(self.host, "_review_logical_width", None)
        if callable(review_width):
            return float(review_width(*candidates))
        available_width = 0
        for candidate in candidates:
            if candidate is None:
                continue
            width = int(getattr(candidate, "winfo_width", lambda: 0)())
            if width > 1:
                available_width = width
                break
        if available_width <= 1:
            available_width = int(getattr(self.host, "winfo_width", lambda: 0)())
        return float(available_width)

    def build_tab_state(self, logical_width: float) -> ReviewTabLayoutState:
        split_min_width = float(getattr(self.host, "_REVIEW_SPLIT_LAYOUT_MIN_WIDTH", 1120))
        return ReviewTabLayoutState(split_mode=logical_width >= split_min_width)

    def build_type_state(self, logical_width: float, review_type_count: int) -> ReviewTypeLayoutState:
        two_column_min_width = float(getattr(self.host, "_REVIEW_TYPES_TWO_COLUMN_MIN_WIDTH", 620))
        three_column_min_width = float(getattr(self.host, "_REVIEW_TYPES_THREE_COLUMN_MIN_WIDTH", 860))
        actions_inline_min_width = float(getattr(self.host, "_REVIEW_TYPE_ACTIONS_INLINE_MIN_WIDTH", 1180))
        actions_two_row_min_width = float(getattr(self.host, "_REVIEW_TYPE_ACTIONS_TWO_ROW_MIN_WIDTH", 760))

        checkbox_columns = 1
        if logical_width >= three_column_min_width:
            checkbox_columns = 3
        elif logical_width >= two_column_min_width:
            checkbox_columns = 2
        checkbox_columns = max(1, min(checkbox_columns, max(review_type_count, 1)))
        checkbox_rows_per_column = max(1, (max(review_type_count, 1) + checkbox_columns - 1) // checkbox_columns)
        checkbox_width = max(220, int(logical_width / max(checkbox_columns, 1)) - 28)

        if logical_width >= actions_inline_min_width:
            controls_mode = "inline"
        elif logical_width >= actions_two_row_min_width:
            controls_mode = "two_row"
        else:
            controls_mode = "stacked"

        return ReviewTypeLayoutState(
            wraplength=max(320, int(logical_width) - 56),
            checkbox_columns=checkbox_columns,
            checkbox_rows_per_column=checkbox_rows_per_column,
            checkbox_width=checkbox_width,
            controls_mode=controls_mode,
            preset_inline=logical_width >= 820,
        )

    def refresh_tab_layout(self) -> None:
        body = getattr(self.host, "review_body_frame", None)
        setup_panel = getattr(self.host, "review_setup_panel", None)
        run_panel = getattr(self.host, "review_run_panel", None)
        divider = getattr(self.host, "review_layout_divider", None)
        scroll_frame = getattr(self.host, "review_scroll_frame", None)
        scroll_canvas = getattr(self.host, "review_scroll_canvas", None)
        if body is None or setup_panel is None or run_panel is None or divider is None:
            return

        logical_width = self.resolve_logical_width(
            scroll_frame,
            scroll_canvas,
            getattr(body, "master", None),
            getattr(self.host, "tabs", None),
            self.host,
            body,
        )
        state = self.build_tab_state(logical_width)
        self.host.review_layout_mode = "split" if state.split_mode else "stacked"

        for child in (setup_panel, run_panel, divider):
            try:
                child.grid_forget()
            except Exception:
                pass

        if state.split_mode:
            body.grid_columnconfigure(0, weight=5, minsize=0)
            body.grid_columnconfigure(1, weight=0, minsize=0)
            body.grid_columnconfigure(2, weight=3, minsize=320)
            body.grid_rowconfigure(0, weight=1)
            body.grid_rowconfigure(1, weight=0)
            body.grid_rowconfigure(2, weight=0)
            setup_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=0)
            divider.configure(width=2, height=0)
            divider.grid(row=0, column=1, sticky="ns", padx=0, pady=4)
            run_panel.grid(row=0, column=2, sticky="nsew", padx=(12, 0), pady=0)
        else:
            body.grid_columnconfigure(0, weight=1, minsize=0)
            body.grid_columnconfigure(1, weight=0, minsize=0)
            body.grid_columnconfigure(2, weight=0, minsize=0)
            body.grid_rowconfigure(0, weight=0)
            body.grid_rowconfigure(1, weight=0)
            body.grid_rowconfigure(2, weight=0)
            setup_panel.grid(row=0, column=0, columnspan=3, sticky="ew", padx=0, pady=0)
            divider.configure(width=0, height=2)
            divider.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6, pady=(10, 10))
            run_panel.grid(row=2, column=0, columnspan=3, sticky="ew", padx=0, pady=0)

        self.refresh_type_layout()

    def refresh_type_layout(self) -> None:
        try:
            if not self.host.winfo_exists():
                return
        except Exception:
            return

        logical_width = self.resolve_logical_width(
            getattr(self.host, "review_setup_panel", None),
            getattr(self.host, "review_body_frame", None),
            getattr(self.host, "review_scroll_canvas", None),
            self.host,
        )
        state = self.build_type_state(
            logical_width,
            len(list(getattr(self.host, "_ordered_review_type_keys", []))),
        )

        self.refresh_type_checkbox_layout(state)
        self.refresh_type_controls_layout(state)

        for label_name in (
            "review_preset_summary_label",
            "review_pin_status_label",
            "review_recommendation_label",
            "review_types_hint_label",
        ):
            label = getattr(self.host, label_name, None)
            if label is not None:
                label.configure(wraplength=state.wraplength)

        for widget_name in ("review_types_scroll_canvas", "review_scroll_canvas"):
            widget = getattr(self.host, widget_name, None)
            update_scroll_region = getattr(widget, "_acr_update_scroll_region", None)
            if callable(update_scroll_region):
                update_scroll_region()

    def refresh_type_checkbox_layout(self, state: ReviewTypeLayoutState | None = None) -> None:
        types_frame = getattr(self.host, "review_types_frame", None)
        ordered_keys = list(getattr(self.host, "_ordered_review_type_keys", []))
        if types_frame is None or not ordered_keys:
            return
        try:
            if not types_frame.winfo_exists():
                return
        except Exception:
            return

        if state is None:
            logical_width = self.resolve_logical_width(
                getattr(self.host, "review_types_scroll_canvas", None),
                getattr(self.host, "review_types_shell", None),
                getattr(self.host, "review_setup_panel", None),
            )
            state = self.build_type_state(logical_width, len(ordered_keys))

        for column in range(3):
            types_frame.grid_columnconfigure(column, weight=0, minsize=0)
        for column in range(state.checkbox_columns):
            types_frame.grid_columnconfigure(column, weight=1, minsize=0)

        for checkbox in getattr(self.host, "type_checkboxes", {}).values():
            checkbox.grid_forget()

        review_type_depths = getattr(self.host, "_review_type_depths", {})
        type_checkboxes = getattr(self.host, "type_checkboxes", {})
        for index, key in enumerate(ordered_keys):
            checkbox = type_checkboxes[key]
            depth = int(review_type_depths.get(key, 0))
            column = index // state.checkbox_rows_per_column
            row = index % state.checkbox_rows_per_column
            checkbox.configure(width=state.checkbox_width)
            checkbox.grid(
                row=row,
                column=column,
                sticky="w",
                padx=(8 + depth * 18, 12),
                pady=2,
            )

    def refresh_type_controls_layout(self, state: ReviewTypeLayoutState | None = None) -> None:
        container = getattr(self.host, "review_type_controls_frame", None)
        selection_frame = getattr(self.host, "review_type_selection_actions_frame", None)
        preset_frame = getattr(self.host, "review_type_preset_actions_frame", None)
        pin_frame = getattr(self.host, "review_type_pin_actions_frame", None)
        if container is None or selection_frame is None or preset_frame is None or pin_frame is None:
            return
        try:
            if not container.winfo_exists():
                return
        except Exception:
            return

        if state is None:
            logical_width = self.resolve_logical_width(
                container,
                getattr(self.host, "review_types_shell", None),
                getattr(self.host, "review_setup_panel", None),
            )
            state = self.build_type_state(
                logical_width,
                len(list(getattr(self.host, "_ordered_review_type_keys", []))),
            )

        for child in (selection_frame, preset_frame, pin_frame):
            child.grid_forget()

        for column in range(3):
            container.grid_columnconfigure(column, weight=0, minsize=0)

        if state.controls_mode == "inline":
            container.grid_columnconfigure(1, weight=1, minsize=0)
            selection_frame.grid(row=0, column=0, sticky="w", padx=(0, 12), pady=2)
            preset_frame.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=2)
            pin_frame.grid(row=0, column=2, sticky="e", pady=2)
        elif state.controls_mode == "two_row":
            container.grid_columnconfigure(0, weight=1, minsize=0)
            container.grid_columnconfigure(1, weight=0, minsize=0)
            selection_frame.grid(row=0, column=0, sticky="w", padx=(0, 12), pady=2)
            pin_frame.grid(row=0, column=1, sticky="e", pady=2)
            preset_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        else:
            container.grid_columnconfigure(0, weight=1, minsize=0)
            selection_frame.grid(row=0, column=0, sticky="w", pady=2)
            preset_frame.grid(row=1, column=0, sticky="ew", pady=(6, 2))
            pin_frame.grid(row=2, column=0, sticky="w", pady=(6, 2))

        preset_frame.grid_columnconfigure(0, weight=0, minsize=0)
        preset_frame.grid_columnconfigure(1, weight=1, minsize=0)
        preset_frame.grid_columnconfigure(2, weight=0, minsize=0)
        self.host.review_preset_label.grid_forget()
        self.host.review_preset_menu.grid_forget()
        self.host.recommend_btn.grid_forget()
        if state.preset_inline:
            self.host.review_preset_label.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="w")
            self.host.review_preset_menu.grid(row=0, column=1, padx=(0, 8), pady=0, sticky="ew")
            self.host.recommend_btn.grid(row=0, column=2, padx=0, pady=0, sticky="e")
        else:
            self.host.review_preset_label.grid(row=0, column=0, padx=(0, 8), pady=(0, 4), sticky="w")
            self.host.review_preset_menu.grid(row=0, column=1, padx=0, pady=(0, 4), sticky="ew")
            self.host.recommend_btn.grid(row=1, column=0, columnspan=3, padx=0, pady=(2, 0), sticky="w")