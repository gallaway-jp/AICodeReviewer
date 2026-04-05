from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResultsLayoutState:
    overview_columns: int
    subsummary_wraplength: int
    action_hint_wraplength: int
    quick_filter_columns: int
    quick_filters_inline: bool
    filter_mode: str
    bottom_actions_inline: bool
    bottom_action_columns: int


class ResultsLayoutHelper:
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

    def build_state(self, logical_width: float, *, visible_buttons: int) -> ResultsLayoutState:
        if logical_width >= 1220:
            overview_columns = 4
        elif logical_width >= 760:
            overview_columns = 2
        else:
            overview_columns = 1

        return ResultsLayoutState(
            overview_columns=overview_columns,
            subsummary_wraplength=max(240, int(logical_width) - 56),
            action_hint_wraplength=max(240, int(logical_width * 0.45)),
            quick_filter_columns=3 if logical_width >= 900 else 2 if logical_width >= 640 else 1,
            quick_filters_inline=logical_width >= 1240,
            filter_mode=(
                "single_row"
                if logical_width >= 1220
                else "two_row"
                if logical_width >= 840
                else "stacked"
            ),
            bottom_actions_inline=logical_width >= 1320 and visible_buttons <= 5,
            bottom_action_columns=3 if logical_width >= 980 else 2 if logical_width >= 700 else 1,
        )

    def refresh_tab_layout(self) -> None:
        logical_width = float(self.host._results_logical_width(getattr(self.host, "results_root_tab", None), self.host))
        ordered_buttons = list(getattr(self.host, "_results_action_buttons_order", []))
        visible_buttons = [button for button in ordered_buttons if button.winfo_manager() != ""]
        state = self.build_state(logical_width, visible_buttons=len(visible_buttons))

        self._layout_overview_cards(state)

        results_subsummary = getattr(self.host, "results_subsummary", None)
        if results_subsummary is not None:
            results_subsummary.configure(wraplength=state.subsummary_wraplength)

        results_action_hint = getattr(self.host, "results_action_hint", None)
        if results_action_hint is not None:
            results_action_hint.configure(wraplength=state.action_hint_wraplength)

        self.layout_quick_filters(logical_width, state=state)
        self.layout_filter_bar(logical_width, state=state)
        self.layout_bottom_actions(logical_width, state=state)

    def _layout_overview_cards(self, state: ResultsLayoutState) -> None:
        overview_frame = getattr(self.host, "_overview_frame", None)
        overview_cards = list(getattr(self.host, "_overview_card_frames", []))
        if overview_frame is None or not overview_cards:
            return

        for column in range(4):
            overview_frame.grid_columnconfigure(column, weight=0, minsize=0)
        for column in range(state.overview_columns):
            overview_frame.grid_columnconfigure(column, weight=1, minsize=0)

        for index, card in enumerate(overview_cards):
            card.grid_forget()
            card.grid(
                row=index // state.overview_columns,
                column=index % state.overview_columns,
                sticky="ew",
                padx=(0 if index % state.overview_columns == 0 else 4, 0),
                pady=(0, 4 if state.overview_columns == 1 else 0),
            )

    def layout_quick_filters(
        self,
        logical_width: float,
        *,
        state: ResultsLayoutState | None = None,
    ) -> None:
        bar = getattr(self.host, "_quick_filter_bar", None)
        if bar is None:
            return

        label = getattr(self.host, "_quick_filter_label", None)
        buttons = list(getattr(self.host, "_quick_filter_button_order", []))
        if label is None or not buttons:
            return

        if state is None:
            ordered_buttons = list(getattr(self.host, "_results_action_buttons_order", []))
            visible_buttons = [button for button in ordered_buttons if button.winfo_manager() != ""]
            state = self.build_state(logical_width, visible_buttons=len(visible_buttons))

        for column in range(8):
            bar.grid_columnconfigure(column, weight=0, minsize=0)

        label.grid_forget()
        for button in buttons:
            button.grid_forget()

        if state.quick_filters_inline:
            label.grid(row=0, column=0, padx=(0, 6), pady=(0, 4), sticky="w")
            for index, button in enumerate(buttons, start=1):
                button.grid(row=0, column=index, padx=(0, 6), pady=(0, 4), sticky="w")
            return

        for column in range(state.quick_filter_columns):
            bar.grid_columnconfigure(column, weight=1, minsize=0)
        label.grid(row=0, column=0, columnspan=state.quick_filter_columns, padx=0, pady=(0, 6), sticky="w")
        for index, button in enumerate(buttons):
            button.grid(
                row=1 + index // state.quick_filter_columns,
                column=index % state.quick_filter_columns,
                padx=(0, 6),
                pady=(0, 6),
                sticky="ew",
            )

    def layout_filter_bar(
        self,
        logical_width: float,
        *,
        state: ResultsLayoutState | None = None,
    ) -> None:
        bar = getattr(self.host, "_filter_bar", None)
        if bar is None:
            return

        widgets = (
            self.host._filter_severity_label,
            self.host._filter_severity_menu,
            self.host._filter_status_label,
            self.host._filter_status_menu,
            self.host._filter_type_label,
            self.host._filter_type_menu,
            self.host._filter_clear_btn,
            self.host._filter_count_lbl,
        )
        for widget in widgets:
            widget.grid_forget()
        for column in range(8):
            bar.grid_columnconfigure(column, weight=0, minsize=0)

        if state is None:
            ordered_buttons = list(getattr(self.host, "_results_action_buttons_order", []))
            visible_buttons = [button for button in ordered_buttons if button.winfo_manager() != ""]
            state = self.build_state(logical_width, visible_buttons=len(visible_buttons))

        if state.filter_mode == "single_row":
            layout = (
                (self.host._filter_severity_label, 0, 0, "w"),
                (self.host._filter_severity_menu, 0, 1, "ew"),
                (self.host._filter_status_label, 0, 2, "w"),
                (self.host._filter_status_menu, 0, 3, "ew"),
                (self.host._filter_type_label, 0, 4, "w"),
                (self.host._filter_type_menu, 0, 5, "ew"),
                (self.host._filter_clear_btn, 0, 6, "w"),
                (self.host._filter_count_lbl, 0, 7, "e"),
            )
            for column in (1, 3, 5, 7):
                bar.grid_columnconfigure(column, weight=1, minsize=0)
        elif state.filter_mode == "two_row":
            layout = (
                (self.host._filter_severity_label, 0, 0, "w"),
                (self.host._filter_severity_menu, 0, 1, "ew"),
                (self.host._filter_status_label, 0, 2, "w"),
                (self.host._filter_status_menu, 0, 3, "ew"),
                (self.host._filter_type_label, 1, 0, "w"),
                (self.host._filter_type_menu, 1, 1, "ew"),
                (self.host._filter_clear_btn, 1, 2, "w"),
                (self.host._filter_count_lbl, 1, 3, "e"),
            )
            for column in (1, 3):
                bar.grid_columnconfigure(column, weight=1, minsize=0)
        else:
            layout = (
                (self.host._filter_severity_label, 0, 0, "w"),
                (self.host._filter_severity_menu, 0, 1, "ew"),
                (self.host._filter_status_label, 1, 0, "w"),
                (self.host._filter_status_menu, 1, 1, "ew"),
                (self.host._filter_type_label, 2, 0, "w"),
                (self.host._filter_type_menu, 2, 1, "ew"),
                (self.host._filter_clear_btn, 3, 0, "w"),
                (self.host._filter_count_lbl, 3, 1, "e"),
            )
            bar.grid_columnconfigure(1, weight=1, minsize=0)

        padx_map = {
            self.host._filter_severity_label: (0, 2),
            self.host._filter_status_label: (0, 2),
            self.host._filter_type_label: (0, 2),
            self.host._filter_severity_menu: (0, 8),
            self.host._filter_status_menu: (0, 8),
            self.host._filter_type_menu: (0, 8),
            self.host._filter_clear_btn: (0, 8),
            self.host._filter_count_lbl: (4, 0),
        }
        for widget, row, column, sticky in layout:
            widget.grid(row=row, column=column, padx=padx_map.get(widget, (0, 0)), pady=(0, 6), sticky=sticky)

    def layout_bottom_actions(
        self,
        logical_width: float,
        *,
        state: ResultsLayoutState | None = None,
    ) -> None:
        frame = getattr(self.host, "_results_bottom_actions_frame", None)
        if frame is None:
            return

        self.host.results_action_hint.grid_forget()
        ordered_buttons = list(getattr(self.host, "_results_action_buttons_order", []))
        visible_buttons = [button for button in ordered_buttons if button.winfo_manager() != ""]
        for button in visible_buttons:
            button.grid_forget()

        for column in range(6):
            frame.grid_columnconfigure(column, weight=0, minsize=0)

        if state is None:
            state = self.build_state(logical_width, visible_buttons=len(visible_buttons))

        if state.bottom_actions_inline:
            self.host.results_action_hint.grid(row=0, column=0, padx=(0, 12), pady=(0, 4), sticky="w")
            for index, button in enumerate(visible_buttons, start=1):
                frame.grid_columnconfigure(index, weight=0, minsize=0)
                button.grid(row=0, column=index, padx=(0, 8), pady=(0, 4), sticky="w")
            return

        for column in range(state.bottom_action_columns):
            frame.grid_columnconfigure(column, weight=1, minsize=0)
        self.host.results_action_hint.grid(
            row=0,
            column=0,
            columnspan=state.bottom_action_columns,
            padx=0,
            pady=(0, 6),
            sticky="w",
        )
        for index, button in enumerate(visible_buttons):
            button.grid(
                row=1 + index // state.bottom_action_columns,
                column=index % state.bottom_action_columns,
                padx=(0, 8),
                pady=(0, 6),
                sticky="ew",
            )