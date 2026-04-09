from __future__ import annotations

import logging
import queue
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.config import config
from aicodereviewer.i18n import t

logger = logging.getLogger(__name__)


class AppSurfaceHelper:
    LOG_LEVELS = ["All", "DEBUG", "INFO", "WARNING", "ERROR"]
    LEVEL_MAP = {"All": 0, "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
    DETACHED_GEOMETRY_KEYS = {
        "log": "detached_log_geometry",
        "settings": "detached_settings_geometry",
        "benchmark": "detached_benchmark_geometry",
        "addon_review": "detached_addon_review_geometry",
    }

    def __init__(self, host: Any) -> None:
        self.host = host

    @staticmethod
    def _walk_widgets(root: Any) -> list[Any]:
        widgets = [root]
        for child in root.winfo_children():
            widgets.extend(AppSurfaceHelper._walk_widgets(child))
        return widgets

    def bind_detached_redock_shortcuts(self, root: Any, callback: Any) -> None:
        def _handler(_event: Any = None) -> str:
            callback()
            return "break"

        for widget in self._walk_widgets(root):
            widget.bind("<Control-w>", _handler, add="+")
            widget.bind("<Control-W>", _handler, add="+")
            widget.bind("<Control-Shift-w>", _handler, add="+")
            widget.bind("<Control-Shift-W>", _handler, add="+")

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
        self.host.detach_log_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.log.open_window"),
            width=140,
            command=self.host._open_detached_log_window,
        )
        self.host.detach_log_btn.grid(row=0, column=2, padx=6)
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
        self.host.detach_log_btn.grid_forget()
        if logical_width >= 860:
            self.host.clear_log_btn.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="w")
            self.host.save_log_btn.grid(row=0, column=1, padx=0, pady=0, sticky="w")
            self.host.detach_log_btn.grid(row=0, column=2, padx=(6, 0), pady=0, sticky="w")
        else:
            self.host.clear_log_btn.grid(row=0, column=0, padx=0, pady=(0, 6), sticky="ew")
            self.host.save_log_btn.grid(row=1, column=0, padx=0, pady=0, sticky="ew")
            self.host.detach_log_btn.grid(row=2, column=0, padx=0, pady=(6, 0), sticky="ew")

    @staticmethod
    def _detached_pages() -> set[str]:
        raw = str(config.get("gui", "detached_pages", "") or "").strip()
        return {token.strip().lower() for token in raw.split(",") if token.strip()}

    @staticmethod
    def _persist_detached_pages(pages: set[str]) -> None:
        config.set_value("gui", "detached_pages", ",".join(sorted(pages)))
        config.save()

    def set_page_detached(self, page_key: str, detached: bool) -> None:
        pages = self._detached_pages()
        normalized = page_key.strip().lower()
        if detached:
            pages.add(normalized)
        else:
            pages.discard(normalized)
        self._persist_detached_pages(pages)

    def is_page_detached(self, page_key: str) -> bool:
        return page_key.strip().lower() in self._detached_pages()

    def save_detached_page_geometry(self, page_key: str, geometry: str | None) -> None:
        config_key = self.DETACHED_GEOMETRY_KEYS.get(page_key.strip().lower())
        if not config_key:
            return
        config.set_value("gui", config_key, str(geometry or ""))
        config.save()

    @staticmethod
    def _current_log_lines(min_level: int, log_lines: list[tuple[int, str]]) -> str:
        visible = [text for lvl, text in log_lines if lvl >= min_level]
        return "\n".join(visible) + ("\n" if visible else "")

    def _render_log_textbox(self, textbox: Any, *, min_level: int) -> None:
        if textbox is None:
            return
        textbox.configure(state="normal")
        textbox.delete("0.0", "end")
        content = self._current_log_lines(min_level, self.host._log_lines)
        if content:
            textbox.insert("0.0", content)
            textbox.see("end")
        textbox.configure(state="disabled")

    def _sync_log_views(self) -> None:
        self._render_log_textbox(
            self.host.log_box,
            min_level=self.LEVEL_MAP.get(self.host._log_level_var.get(), 0),
        )
        detached_level_var = getattr(self.host, "_detached_log_level_var", None)
        if detached_level_var is not None and self.host._detached_log_box is not None:
            self._render_log_textbox(
                self.host._detached_log_box,
                min_level=self.LEVEL_MAP.get(detached_level_var.get(), 0),
            )

    def _destroy_detached_log_window(self, *, persist_detached_state: bool) -> None:
        window = getattr(self.host, "_detached_log_window", None)
        if window is not None and window.winfo_exists():
            try:
                self.save_detached_page_geometry("log", window.geometry())
            except Exception:
                pass
            try:
                window.destroy()
            except Exception:
                pass
        self.host._detached_log_window = None
        self.host._detached_log_box = None
        self.host._detached_log_level_var = None
        self.host._detached_log_level_menu = None
        self.host._detached_log_clear_btn = None
        self.host._detached_log_save_btn = None
        self.host._detached_log_redock_btn = None
        if persist_detached_state:
            self.set_page_detached("log", False)

    def redock_detached_log_window(self) -> None:
        self._destroy_detached_log_window(persist_detached_state=True)
        self.host.tabs.set(t("gui.tab.log"))

    def prepare_detached_windows_for_shutdown(self) -> None:
        for page_key, attr_name in (
            ("log", "_detached_log_window"),
            ("settings", "_detached_settings_window"),
            ("benchmark", "_detached_benchmark_window"),
            ("addon_review", "_detached_addon_review_window"),
        ):
            window = getattr(self.host, attr_name, None)
            if window is None or not window.winfo_exists():
                continue
            try:
                self.save_detached_page_geometry(page_key, window.geometry())
            except Exception:
                pass

    def restore_detached_windows(self) -> None:
        if "settings" in self._detached_pages():
            self.host._open_detached_settings_window(restoring=True)
        if "benchmark" in self._detached_pages():
            self.host._open_detached_benchmark_window(restoring=True)
        if "addon_review" in self._detached_pages():
            self.host._open_detached_addon_review_window(restoring=True)
        if "log" in self._detached_pages():
            self.open_detached_log_window(restoring=True)

    def detach_current_page_into_window(self, event: Any = None) -> str | None:
        if event is not None:
            try:
                toplevel = event.widget.winfo_toplevel()
            except Exception:
                return None
            if toplevel is not self.host:
                return None

        current_tab = str(self.host.tabs.get())
        if current_tab == t("gui.tab.log"):
            self.host._open_detached_log_window()
            return "break"
        if current_tab == t("gui.tab.settings"):
            self.host._open_detached_settings_window()
            return "break"
        if current_tab == t("gui.tab.benchmarks"):
            self.host._open_detached_benchmark_window()
            return "break"
        if current_tab == t("gui.tab.addon_review"):
            self.host._open_detached_addon_review_window()
            return "break"
        return None

    def open_detached_log_window(self, *, restoring: bool = False) -> None:
        existing = getattr(self.host, "_detached_log_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return

        win = ctk.CTkToplevel(self.host)
        win.title(t("gui.log.detached_title"))
        saved_geometry = str(config.get("gui", "detached_log_geometry", "") or "").strip()
        win.geometry(saved_geometry or "900x540")
        win.minsize(560, 360)
        self.host._schedule_titlebar_fix(win)
        self.host._detached_log_window = win

        container = ctk.CTkFrame(win, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(2, weight=1)

        intro = ctk.CTkLabel(
            container,
            text=t("gui.log.intro"),
            anchor="w",
            justify="left",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=11),
        )
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        filter_frame = ctk.CTkFrame(container, fg_color="transparent")
        filter_frame.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(filter_frame, text=t("gui.log.level")).grid(row=0, column=0, padx=(0, 4), sticky="w")
        self.host._detached_log_level_var = ctk.StringVar(value=self.host._log_level_var.get())
        self.host._detached_log_level_menu = ctk.CTkOptionMenu(
            filter_frame,
            variable=self.host._detached_log_level_var,
            values=self.LOG_LEVELS,
            width=110,
            command=lambda _value: self._sync_log_views(),
        )
        self.host._detached_log_level_menu.grid(row=0, column=1, padx=(0, 8), sticky="w")

        self.host._detached_log_box = ctk.CTkTextbox(
            container,
            state="disabled",
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.host._detached_log_box.grid(row=2, column=0, sticky="nsew", pady=(0, 6))

        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.grid(row=3, column=0, sticky="ew")
        self.host._detached_log_clear_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.log.clear"),
            width=110,
            command=self.host._clear_log,
        )
        self.host._detached_log_clear_btn.grid(row=0, column=0, padx=(0, 6), sticky="w")
        self.host._detached_log_save_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.log.save"),
            width=110,
            command=lambda: self.save_log(source="detached"),
        )
        self.host._detached_log_save_btn.grid(row=0, column=1, padx=(0, 6), sticky="w")
        self.host._detached_log_redock_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.log.redock"),
            width=110,
            command=self.host._redock_detached_log_window,
        )
        self.host._detached_log_redock_btn.grid(row=0, column=2, sticky="w")

        def _on_close() -> None:
            if getattr(self.host, "_app_destroying", False):
                self._destroy_detached_log_window(persist_detached_state=False)
                return
            self.redock_detached_log_window()

        def _persist_geometry(_event: Any = None) -> None:
            if not win.winfo_exists() or getattr(self.host, "_app_destroying", False):
                return
            try:
                self.save_detached_page_geometry("log", win.geometry())
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", _on_close)
        win.bind("<Configure>", _persist_geometry, add="+")
        self.bind_detached_redock_shortcuts(win, self.redock_detached_log_window)

        self.set_page_detached("log", True)
        self._sync_log_views()
        if restoring:
            self.show_toast(t("gui.log.window_restored"))

    def poll_log_queue(self) -> None:
        if not getattr(self.host, "_log_polling", True):
            return
        self.host._drain_ui_call_queue()
        batch = []
        while True:
            try:
                batch.append(self.host._log_queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self.host._log_lines.extend(batch)
            self._sync_log_views()
        self.host._schedule_app_after(100, self.host._poll_log_queue)

    def on_log_level_changed(self) -> None:
        self._sync_log_views()

    def clear_log(self) -> None:
        self.host._log_lines.clear()
        self._sync_log_views()

    def save_log(self, *, source: str = "main") -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title=t("gui.log.save_dialog_title"),
        )
        if not path:
            return
        try:
            textbox = self.host.log_box
            if source == "detached" and self.host._detached_log_box is not None:
                textbox = self.host._detached_log_box
            content = textbox.get("0.0", "end")
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