from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

SECTION_SURFACE = ("#f5f7fb", "#262a31")
SECTION_BORDER = ("#d8e1ee", "#3a404b")
MUTED_TEXT = ("gray40", "gray65")


def add_section_header(
    parent: Any,
    row: int,
    title: str,
    description: str,
    *,
    muted_text: Any = MUTED_TEXT,
) -> int:
    header = ctk.CTkFrame(parent, fg_color="transparent")
    header.grid(row=row, column=0, sticky="ew", padx=6, pady=(10, 4))
    header.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        header,
        text=title,
        anchor="w",
        font=ctk.CTkFont(size=16, weight="bold"),
    ).grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(
        header,
        text=description,
        anchor="w",
        justify="left",
        text_color=muted_text,
        font=ctk.CTkFont(size=11),
    ).grid(row=1, column=0, sticky="w", pady=(1, 0))
    return row + 1


def resolve_scroll_background() -> str:
    return "#f3f4f6" if ctk.get_appearance_mode().lower() != "dark" else "#1f2937"


def scroll_canvas_for_widget(widget: Any) -> Any | None:
    current = widget
    while current is not None:
        canvas = getattr(current, "_acr_scroll_canvas", None)
        if canvas is not None:
            return canvas
        current = getattr(current, "master", None)
    return None


def on_scroll_mousewheel(event: Any) -> str | None:
    canvas = scroll_canvas_for_widget(getattr(event, "widget", None))
    if canvas is None:
        return None
    delta = getattr(event, "delta", 0)
    if delta == 0:
        return None
    step = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
    canvas.yview_scroll(step, "units")
    return "break"


def ensure_autohide_scroll_bindings(host: Any) -> None:
    if getattr(host, "_acr_scroll_bindings_ready", False):
        return

    def _handler(event: Any) -> str | None:
        return on_scroll_mousewheel(event)

    host.bind_all("<MouseWheel>", _handler, add="+")
    host._acr_shared_scroll_mousewheel_handler = _handler
    host._acr_scroll_bindings_ready = True


def build_autohide_scroller(
    host: Any,
    parent: Any,
    *,
    content_fg_color: Any = "transparent",
    height: int | None = None,
) -> tuple[Any, Any, Any, Any]:
    ensure_autohide_scroll_bindings(host)

    outer = ctk.CTkFrame(parent, fg_color="transparent")
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(0, weight=1)

    canvas = tk.Canvas(
        outer,
        highlightthickness=0,
        bd=0,
        relief="flat",
        background=resolve_scroll_background(),
    )
    if height is not None:
        canvas.configure(height=height)
    canvas.grid(row=0, column=0, sticky="nsew")

    scrollbar = ctk.CTkScrollbar(outer, orientation="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")

    content = ctk.CTkFrame(canvas, fg_color=content_fg_color)
    window_id = canvas.create_window((0, 0), window=content, anchor="nw")

    for widget in (outer, canvas, content):
        setattr(widget, "_acr_scroll_canvas", canvas)

    def sync_scrollbar(first: str, last: str) -> None:
        scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            scrollbar.grid_remove()
            canvas.yview_moveto(0)
        else:
            scrollbar.grid()

    def update_scroll_region(_event: Any | None = None) -> None:
        bbox = canvas.bbox("all")
        if bbox is not None:
            canvas.configure(scrollregion=bbox)
        first, last = canvas.yview()
        sync_scrollbar(str(first), str(last))

    def sync_content_width(event: Any) -> None:
        canvas.itemconfigure(window_id, width=event.width)
        update_scroll_region()

    canvas.configure(yscrollcommand=sync_scrollbar)
    canvas.bind("<Configure>", sync_content_width, add="+")
    content.bind("<Configure>", update_scroll_region, add="+")
    setattr(outer, "_acr_update_scroll_region", update_scroll_region)
    setattr(outer, "_acr_sync_scrollbar", sync_scrollbar)
    setattr(canvas, "_acr_update_scroll_region", update_scroll_region)
    setattr(canvas, "_acr_sync_scrollbar", sync_scrollbar)
    schedule_after = getattr(host, "_schedule_app_after", host.after)
    schedule_after(0, update_scroll_region)
    return outer, content, canvas, scrollbar