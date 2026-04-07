# src/aicodereviewer/gui/health_mixin.py
"""Backend health-check and model-refresh mixin for :class:`App`."""
from __future__ import annotations

import logging
import re
import threading
import webbrowser
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.backends.health import (
    check_backend,
    get_copilot_models,
    get_kiro_models,
    get_bedrock_models,
    get_local_models,
)
from aicodereviewer.config import config
from aicodereviewer.i18n import t

from .popup_utils import schedule_titlebar_fix

logger = logging.getLogger(__name__)

__all__ = ["HealthMixin"]


class HealthMixin:
    """Mixin supplying backend health checking and model list refresh."""

    def _dispatch_health_ui(self, callback: Any, *args: Any, **kwargs: Any) -> bool:
        """Marshal worker-thread callbacks onto the main UI loop when available."""
        dispatcher = getattr(self, "_run_on_ui_thread", None)
        if callable(dispatcher):
            return bool(dispatcher(callback, *args, **kwargs))
        schedule_after = getattr(self, "_schedule_app_after", self.after)
        schedule_after(0, lambda: callback(*args, **kwargs))
        return True

    def _model_refresh_controller(self) -> Any:
        """Return the runtime owner for backend model-refresh state."""
        return getattr(self, "_active_model_refresh")

    def _schedule_titlebar_fix(self, window: Any) -> None:
        """Defer titlebar tweaks for popup windows without leaking fragile Tk callbacks in tests."""
        schedule_titlebar_fix(window, host=self)

    # ══════════════════════════════════════════════════════════════════════
    #  BACKEND HEALTH CHECK
    # ══════════════════════════════════════════════════════════════════════

    def _on_backend_changed(self, *_args: object):
        backend_name = self.backend_var.get()
        config.set_value("backend", "type", backend_name)
        self._sync_review_to_menu()
        logger.info("Backend changed to %s", backend_name)
        if not self._testing_mode:
            self._auto_health_check()

    def _auto_health_check(self):
        self._run_health_check(self.backend_var.get(), always_show_dialog=False)

    def _check_backend_health(self):
        if self._testing_mode:
            if self._is_health_check_running():
                return
            logger.info("Simulating health check for backend %s", self.backend_var.get())
            self._begin_active_health_check("simulated")
            self._set_action_buttons_state("disabled")
            self._sync_global_cancel_button()
            self.status_var.set("Simulating health check…")
            self._start_health_countdown()

            def _sim_complete():
                self._finish_active_health_check()
                self._stop_health_countdown()
                self._set_action_buttons_state("normal")
                self._sync_global_cancel_button()
                self.status_var.set(t("common.ready"))
                self._show_toast(
                    "Check Setup is simulated in testing mode — "
                    "backend connectivity is not tested", error=False)

            schedule_after = getattr(self, "_schedule_app_after", self.after)
            schedule_after(10_000, _sim_complete)
            return
        self._run_health_check(self.backend_var.get(), always_show_dialog=True)

    def _run_health_check(self, backend_name: str, *, always_show_dialog: bool):
        if self._is_busy() and not self._is_health_check_running():
            return
        if self._active_health_check_matches(backend_name):
            return

        self._cancel_active_health_check_timer()

        self._begin_active_health_check(backend_name)
        self._set_action_buttons_state("disabled")
        self._sync_global_cancel_button()
        self.status_var.set(t("health.checking", backend=backend_name))

        def _on_timeout():
            if self._active_health_check_matches(backend_name):
                self._finish_active_health_check()
                self._dispatch_health_ui(self._stop_health_countdown)
                self._dispatch_health_ui(
                    self._show_health_error,
                    t("health.timeout", backend=backend_name),
                )
                self._dispatch_health_ui(self._set_action_buttons_state, "normal")
                self._dispatch_health_ui(self._sync_global_cancel_button)
                self._dispatch_health_ui(self.status_var.set, t("common.ready"))

        timeout_timer = threading.Timer(60, _on_timeout)
        timeout_timer.daemon = True
        self._bind_active_health_check_timer(timeout_timer)
        timeout_timer.start()
        self._start_health_countdown()

        def _worker():
            try:
                report = check_backend(backend_name)
                if self._active_health_check_matches(backend_name):
                    self._cancel_active_health_check_timer()
                    self._finish_active_health_check()
                    self._dispatch_health_ui(self._stop_health_countdown)

                    if always_show_dialog:
                        self._dispatch_health_ui(self._show_health_dialog, report)
                        self._dispatch_health_ui(self.status_var.set, t("common.ready"))
                    else:
                        if report.ready:
                            self._dispatch_health_ui(
                                self.status_var.set,
                                t("health.auto_ok", backend=backend_name),
                            )
                            if backend_name == "copilot":
                                self._dispatch_health_ui(self._refresh_copilot_model_list)
                            elif backend_name == "bedrock":
                                self._dispatch_health_ui(self._refresh_bedrock_model_list)
                            elif backend_name == "local":
                                self._dispatch_health_ui(self._refresh_local_model_list)
                        else:
                            self._dispatch_health_ui(self._show_health_dialog, report)
                            self._dispatch_health_ui(self.status_var.set, t("common.ready"))

                    self._dispatch_health_ui(self._set_action_buttons_state, "normal")
                    self._dispatch_health_ui(self._sync_global_cancel_button)
            except Exception as exc:
                if self._active_health_check_matches(backend_name):
                    logger.error("Health check failed: %s", exc)
                    self._cancel_active_health_check_timer()
                    self._finish_active_health_check()
                    self._dispatch_health_ui(self._show_health_error, str(exc))
                    self._dispatch_health_ui(self._stop_health_countdown)
                    self._dispatch_health_ui(self._set_action_buttons_state, "normal")
                    self._dispatch_health_ui(self._sync_global_cancel_button)
                    self._dispatch_health_ui(self.status_var.set, t("common.ready"))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_health_dialog(self, report):
        if self._testing_mode:
            logger.info("Health dialog suppressed in testing: %s", report.summary)
            return

        win = ctk.CTkToplevel(self)
        win.title(t("health.dialog_title"))
        win.geometry("600x450")
        win.grab_set()
        self._schedule_titlebar_fix(win)
        win.bind("<Control-w>", lambda e: win.destroy())

        if report.backend == "copilot" and report.ready:
            self._refresh_copilot_model_list()
        elif report.backend == "bedrock" and report.ready:
            self._refresh_bedrock_model_list()
        elif report.backend == "local" and report.ready:
            self._refresh_local_model_list()

        summary_color = "green" if report.ready else "#dc2626"
        ctk.CTkLabel(win, text=report.summary,
                      text_color=summary_color,
                      font=ctk.CTkFont(size=14, weight="bold")).pack(
            padx=10, pady=(10, 6))

        scroll = ctk.CTkFrame(win) if self._testing_mode else ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=10, pady=4)
        scroll.grid_columnconfigure(1, weight=1)

        for i, check in enumerate(report.checks):
            icon = "✅" if check.passed else "❌"
            color = "green" if check.passed else "#dc2626"

            ctk.CTkLabel(scroll, text=icon, width=24).grid(
                row=i * 3, column=0, sticky="nw", padx=(4, 2), pady=(4, 0))
            ctk.CTkLabel(scroll, text=check.name,
                          font=ctk.CTkFont(weight="bold"),
                          text_color=color).grid(
                row=i * 3, column=1, sticky="w", padx=4, pady=(4, 0))
            ctk.CTkLabel(scroll, text=check.detail, anchor="w",
                          wraplength=450,
                          text_color=("gray30", "gray70")).grid(
                row=i * 3 + 1, column=1, sticky="w", padx=4)

            meta_parts: list[str] = []
            category = getattr(check, "category", "none")
            origin = getattr(check, "origin", "prerequisite")
            if not check.passed and category and category != "none":
                meta_parts.append(f"{t('health.meta_category')}: {category.replace('_', ' ')}")
            if origin:
                meta_parts.append(f"{t('health.meta_origin')}: {origin.replace('_', ' ')}")
            if meta_parts:
                ctk.CTkLabel(
                    scroll,
                    text=" | ".join(meta_parts),
                    anchor="w",
                    wraplength=450,
                    text_color=("gray45", "gray60"),
                    font=ctk.CTkFont(size=11),
                ).grid(row=i * 3 + 2, column=1, sticky="w", padx=4)

            if check.fix_hint and not check.passed:
                url_match = re.search(r'https?://[^\s]+', check.fix_hint)
                if url_match:
                    url = url_match.group(0)
                    text_before = check.fix_hint[:url_match.start()].rstrip(': ')

                    hint_frame = ctk.CTkFrame(scroll, fg_color="transparent")
                    hint_frame.grid(row=i * 3 + 3, column=1, sticky="w",
                                    padx=4, pady=(0, 4))

                    if text_before:
                        ctk.CTkLabel(hint_frame, text=f"💡 {text_before}: ",
                                      anchor="w",
                                      text_color="#2563eb",
                                      font=ctk.CTkFont(size=11)).pack(
                            side="left", padx=(0, 2))
                    else:
                        ctk.CTkLabel(hint_frame, text="💡 ",
                                      text_color="#2563eb",
                                      font=ctk.CTkFont(size=11)).pack(
                            side="left")

                    link_label = ctk.CTkLabel(hint_frame, text=url,
                                               anchor="w",
                                               text_color="#0066cc",
                                               font=ctk.CTkFont(size=11, underline=True),
                                               cursor="hand2")
                    link_label.pack(side="left")
                    link_label.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                else:
                    ctk.CTkLabel(scroll, text=f"💡 {check.fix_hint}",
                                  anchor="w", wraplength=450,
                                  text_color="#2563eb",
                                  font=ctk.CTkFont(size=11)).grid(
                        row=i * 3 + 3, column=1, sticky="w", padx=4,
                        pady=(0, 4))

        ctk.CTkButton(win, text=t("common.close"),
                       command=win.destroy).pack(pady=8)

    def _show_health_error(self, error_msg: str):
        if self._testing_mode:
            logger.warning("Health check error (suppressed in testing): %s",
                           error_msg)
            return
        from tkinter import messagebox
        messagebox.showerror(t("health.dialog_title"), error_msg)

    # ══════════════════════════════════════════════════════════════════════
    #  MODEL REFRESH
    # ══════════════════════════════════════════════════════════════════════

    def _refresh_current_backend_models_async(self):
        backend = self.backend_var.get()
        if backend == "copilot":
            self._refresh_copilot_model_list_async()
        elif backend == "bedrock":
            self._refresh_bedrock_model_list_async()
        elif backend == "local":
            self._refresh_local_model_list_async()

    # ── Copilot ────────────────────────────────────────────────────────────

    def _refresh_copilot_model_list(self):
        models = get_copilot_models()
        if models and hasattr(self, "_copilot_model_combo"):
            current = self._copilot_model_combo.get()
            self._copilot_model_combo.configure(values=["auto"] + models)
            self._copilot_model_combo.set(current)

    def _refresh_copilot_model_list_async(self):
        controller = self._model_refresh_controller()
        if not controller.begin("copilot"):
            return

        def _worker():
            try:
                models = get_copilot_models()
                self._dispatch_health_ui(self._apply_copilot_models, models)
            finally:
                controller.finish("copilot")

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_copilot_models(self, models: list):
        if models and hasattr(self, "_copilot_model_combo"):
            current = self._copilot_model_combo.get()
            self._copilot_model_combo.configure(values=["auto"] + models)
            self._copilot_model_combo.set(current)

    # ── Kiro CLI ────────────────────────────────────────────────────────────

    def _refresh_kiro_model_list_async(self):
        controller = self._model_refresh_controller()
        if not controller.begin("kiro"):
            return

        def _worker():
            try:
                kiro_path = config.get("kiro", "cli_command", "kiro")
                wsl_distro = config.get("kiro", "wsl_distro", "")
                models = get_kiro_models(kiro_path, wsl_distro)
                self._dispatch_health_ui(self._apply_kiro_models, models)
            finally:
                controller.finish("kiro")

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_kiro_models(self, models: list):
        if hasattr(self, "_kiro_model_combo"):
            current = self._kiro_model_combo.get()
            self._kiro_model_combo.configure(values=models)
            if current and current in models:
                self._kiro_model_combo.set(current)

    # ── Bedrock ────────────────────────────────────────────────────────────

    def _refresh_bedrock_model_list(self):
        models = get_bedrock_models()
        if models and hasattr(self, "_bedrock_model_combo"):
            current = self._bedrock_model_combo.get()
            self._bedrock_model_combo.configure(values=models)
            if current:
                self._bedrock_model_combo.set(current)

    def _refresh_bedrock_model_list_async(self):
        controller = self._model_refresh_controller()
        if not controller.begin("bedrock"):
            return

        def _worker():
            try:
                models = get_bedrock_models()
                self._dispatch_health_ui(self._apply_bedrock_models, models)
            finally:
                controller.finish("bedrock")

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_bedrock_models(self, models: list):
        if models and hasattr(self, "_bedrock_model_combo"):
            current = self._bedrock_model_combo.get()
            self._bedrock_model_combo.configure(values=models)
            if current:
                self._bedrock_model_combo.set(current)

    # ── Local LLM ──────────────────────────────────────────────────────────

    def _refresh_local_model_list(self):
        api_url = config.get("local_llm", "api_url", "http://localhost:1234")
        api_type = config.get("local_llm", "api_type", "lmstudio")
        models = get_local_models(api_url, api_type)
        if models and hasattr(self, "_local_model_combo"):
            current = self._local_model_combo.get()
            self._local_model_combo.configure(values=models)
            if current:
                self._local_model_combo.set(current)

    def _refresh_local_model_list_async(self):
        controller = self._model_refresh_controller()
        if not controller.begin("local"):
            return

        def _worker():
            try:
                api_url = config.get("local_llm", "api_url", "http://localhost:1234")
                api_type = config.get("local_llm", "api_type", "lmstudio")
                models = get_local_models(api_url, api_type)
                self._dispatch_health_ui(self._apply_local_models, models)
            finally:
                controller.finish("local")

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_local_models(self, models: list):
        if models and hasattr(self, "_local_model_combo"):
            current = self._local_model_combo.get()
            self._local_model_combo.configure(values=models)
            if current:
                self._local_model_combo.set(current)
