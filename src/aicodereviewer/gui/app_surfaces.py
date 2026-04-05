from __future__ import annotations

import logging
import queue
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.i18n import t

logger = logging.getLogger(__name__)


class AppSurfaceHelper:
    LOG_LEVELS = ["All", "DEBUG", "INFO", "WARNING", "ERROR"]
    LEVEL_MAP = {"All": 0, "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}

    def __init__(self, host: Any) -> None:
        self.host = host

    def build_status_bar(self) -> None:
        status_frame = ctk.CTkFrame(self.host, fg_color="transparent")
        status_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 6))
        status_frame.grid_columnconfigure(0, weight=1)

        self.host.status_var = ctk.StringVar(value=t("common.ready"))
        ctk.CTkLabel(status_frame, textvariable=self.host.status_var, anchor="w").grid(
            row=0,
            column=0,
            sticky="ew",
        )

        self.host.cancel_btn = ctk.CTkButton(
            status_frame,
            text=t("gui.cancel_btn"),
            width=80,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            state="disabled",
            command=self.host._cancel_operation,
        )
        self.host.cancel_btn.grid(row=0, column=1, padx=(8, 0))

        self.host._health_countdown_lbl = ctk.CTkLabel(
            status_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            width=56,
            anchor="e",
        )
        self.host._health_countdown_lbl.grid(row=0, column=2, padx=(4, 0))

    def build_log_tab(self) -> None:
        tab = self.host.tabs.add(t("gui.tab.log"))
        self.host.log_root_tab = tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        self.host.log_intro_label = ctk.CTkLabel(
            tab,
            text=t("gui.log.intro"),
            anchor="w",
            justify="left",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=11),
        )
        self.host.log_intro_label.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 0))

        filter_frame = ctk.CTkFrame(tab, fg_color="transparent")
        filter_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=(4, 0))
        self.host._log_filter_frame = filter_frame

        self.host._log_level_label = ctk.CTkLabel(filter_frame, text=t("gui.log.level"))
        self.host._log_level_label.grid(row=0, column=0, padx=(0, 4))
        self.host._log_level_var = ctk.StringVar(value="All")
        self.host._log_level_menu = ctk.CTkOptionMenu(
            filter_frame,
            variable=self.host._log_level_var,
            values=self.LOG_LEVELS,
            width=110,
            command=self.host._on_log_level_changed,
        )
        self.host._log_level_menu.grid(row=0, column=1, padx=(0, 8))

        self.host.log_box = ctk.CTkTextbox(
            tab,
            state="disabled",
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.host.log_box.grid(row=2, column=0, sticky="nsew", padx=6, pady=6)

        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=3, column=0, pady=4, padx=6, sticky="ew")
        self.host._log_button_frame = btn_frame

        self.host.clear_log_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.log.clear"),
            width=110,
            command=self.host._clear_log,
        )
        self.host.clear_log_btn.grid(row=0, column=0, padx=6)
        self.host.save_log_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.log.save"),
            width=110,
            command=self.host._save_log,
        )
        self.host.save_log_btn.grid(row=0, column=1, padx=6)
        tab.bind("<Configure>", self.host._schedule_log_layout_refresh, add="+")
        self.refresh_log_tab_layout()

    def resolve_logical_width(self, *candidates: Any) -> float:
        review_width = getattr(self.host, "_review_logical_width", None)
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
            available_width = int(getattr(self.host, "winfo_width", lambda: 0)())
        return float(available_width)

    def refresh_log_tab_layout(self) -> None:
        logical_width = float(self.host._log_logical_width(getattr(self.host, "log_root_tab", None), self.host))
        self.host.log_intro_label.configure(wraplength=max(320, int(logical_width) - 48))

        self.host._log_level_label.grid_forget()
        self.host._log_level_menu.grid_forget()
        if logical_width >= 860:
            self.host._log_level_label.grid(row=0, column=0, padx=(0, 4), pady=(0, 2), sticky="w")
            self.host._log_level_menu.grid(row=0, column=1, padx=(0, 8), pady=(0, 2), sticky="w")
        else:
            self.host._log_level_label.grid(row=0, column=0, padx=0, pady=(0, 4), sticky="w")
            self.host._log_level_menu.grid(row=1, column=0, padx=0, pady=(0, 2), sticky="w")

        self.host.clear_log_btn.grid_forget()
        self.host.save_log_btn.grid_forget()
        if logical_width >= 860:
            self.host.clear_log_btn.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="w")
            self.host.save_log_btn.grid(row=0, column=1, padx=0, pady=0, sticky="w")
        else:
            self.host.clear_log_btn.grid(row=0, column=0, padx=0, pady=(0, 6), sticky="ew")
            self.host.save_log_btn.grid(row=1, column=0, padx=0, pady=0, sticky="ew")

    def poll_log_queue(self) -> None:
        if not getattr(self.host, "_log_polling", True):
            return
        self.host._drain_ui_call_queue()
        min_level = self.LEVEL_MAP.get(
            getattr(self.host, "_log_level_var", None) and self.host._log_level_var.get(),
            0,
        )
        batch = []
        while True:
            try:
                batch.append(self.host._log_queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self.host._log_lines.extend(batch)
            visible = [text for lvl, text in batch if lvl >= min_level]
            if visible:
                self.host.log_box.configure(state="normal")
                self.host.log_box.insert("end", "\n".join(visible) + "\n")
                self.host.log_box.see("end")
                self.host.log_box.configure(state="disabled")
        self.host._schedule_app_after(100, self.host._poll_log_queue)

    def on_log_level_changed(self) -> None:
        min_level = self.LEVEL_MAP.get(self.host._log_level_var.get(), 0)
        visible = [text for lvl, text in self.host._log_lines if lvl >= min_level]
        self.host.log_box.configure(state="normal")
        self.host.log_box.delete("0.0", "end")
        if visible:
            self.host.log_box.insert("0.0", "\n".join(visible) + "\n")
            self.host.log_box.see("end")
        self.host.log_box.configure(state="disabled")

    def clear_log(self) -> None:
        self.host._log_lines.clear()
        self.host.log_box.configure(state="normal")
        self.host.log_box.delete("0.0", "end")
        self.host.log_box.configure(state="disabled")

    def save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title=t("gui.log.save_dialog_title"),
        )
        if not path:
            return
        try:
            content = self.host.log_box.get("0.0", "end")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self.show_toast(t("gui.log.saved", path=Path(path).name))
        except Exception as exc:
            self.show_toast(str(exc), error=True)

    def restack_toasts(self) -> None:
        win_h = self.host.winfo_height() or self.host.HEIGHT
        toast_slot_px = int(getattr(self.host, "_TOAST_SLOT_PX", 52))
        for index, frame in enumerate(self.host._active_toasts):
            offset_px = index * toast_slot_px
            rely = 1.0 - (offset_px + 24) / win_h
            try:
                frame.place(relx=0.5, rely=rely, anchor="s")
                frame.lift()
            except Exception:
                pass

    def show_toast(self, message: str, *, duration: int = 6000, error: bool = False) -> None:
        if error:
            logger.warning("UI toast: %s", message)
        else:
            logger.info("UI toast: %s", message)
        bg = "#dc2626" if error else ("#1a7f37", "#2ea043")
        fg = "white"

        toast = ctk.CTkFrame(self.host, corner_radius=8, fg_color=bg, border_width=0)
        self.host._active_toasts.append(toast)
        self.restack_toasts()

        lbl = ctk.CTkLabel(
            toast,
            text=message,
            text_color=fg,
            font=ctk.CTkFont(size=12),
            wraplength=600,
            anchor="center",
        )
        lbl.pack(padx=16, pady=8)

        def _dismiss() -> None:
            try:
                toast.destroy()
            except Exception:
                pass
            try:
                self.host._active_toasts.remove(toast)
            except ValueError:
                pass
            self.restack_toasts()

        self.host._schedule_app_after(duration, _dismiss)