from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class SettingsLayoutState:
    wraplength: int
    local_http_status_wraplength: int
    local_http_copy_button_width: int
    local_http_docs_height: int
    addon_summary_height: int
    addon_diagnostics_height: int
    output_format_columns: int
    stack_settings_buttons: bool
    refresh_addons_sticky: str
    contribution_wraplength: int


class SettingsLayoutHelper:
    @staticmethod
    def resolve_logical_width(host: Any, *candidates: Any) -> float:
        review_width = getattr(host, "_review_logical_width", None)
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
            available_width = int(getattr(host, "winfo_width", lambda: 0)())
        return float(available_width)

    @staticmethod
    def build_state(logical_width: float) -> SettingsLayoutState:
        width = int(logical_width)
        return SettingsLayoutState(
            wraplength=max(320, width - 120),
            local_http_status_wraplength=max(280, width - 280),
            local_http_copy_button_width=96 if logical_width >= 1080 else 80,
            local_http_docs_height=126 if logical_width >= 1080 else 164,
            addon_summary_height=110 if logical_width >= 1080 else 136,
            addon_diagnostics_height=120 if logical_width >= 1080 else 146,
            output_format_columns=3 if logical_width >= 1180 else 2 if logical_width >= 900 else 1,
            stack_settings_buttons=logical_width < 960,
            refresh_addons_sticky="w" if logical_width >= 960 else "ew",
            contribution_wraplength=max(320, width - 180),
        )

    @staticmethod
    def apply_output_format_layout(frame: Any, checkboxes: Iterable[Any], columns: int) -> None:
        checkbox_list = list(checkboxes)
        for checkbox in checkbox_list:
            checkbox.grid_forget()
        for column in range(3):
            frame.grid_columnconfigure(column, weight=0, minsize=0)
        for column in range(columns):
            frame.grid_columnconfigure(column, weight=1, minsize=0)
        for index, checkbox in enumerate(checkbox_list):
            checkbox.grid(
                row=index // columns,
                column=index % columns,
                padx=(0, 15),
                pady=(0, 4),
                sticky="w",
            )

    @staticmethod
    def apply_button_layout(save_button: Any, reset_button: Any, *, stacked: bool) -> None:
        save_button.grid_forget()
        reset_button.grid_forget()
        if stacked:
            save_button.grid(row=0, column=0, pady=(0, 6), sticky="ew")
            reset_button.grid(row=1, column=0, pady=0, sticky="ew")
            return
        save_button.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="w")
        reset_button.grid(row=0, column=1, pady=0, sticky="w")

    @staticmethod
    def apply_contribution_wraplength(frame: Any, *, wraplength: int) -> None:
        for widget in frame.winfo_children():
            for child in widget.winfo_children():
                try:
                    if str(child.cget("justify")) == "left":
                        child.configure(wraplength=wraplength)
                except Exception:
                    continue