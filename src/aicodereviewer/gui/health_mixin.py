# src/aicodereviewer/gui/health_mixin.py
"""Backend health-check and model-refresh mixin for :class:`App`."""
from __future__ import annotations

import logging
import re
import threading
import webbrowser

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.backends.health import (
    check_backend,
    get_copilot_models,
    get_bedrock_models,
    get_local_models,
)
from aicodereviewer.config import config
from aicodereviewer.i18n import t

from .widgets import _fix_titlebar

logger = logging.getLogger(__name__)

__all__ = ["HealthMixin"]


class HealthMixin:
    """Mixin supplying backend health checking and model list refresh."""

    # ══════════════════════════════════════════════════════════════════════
    #  BACKEND HEALTH CHECK
    # ══════════════════════════════════════════════════════════════════════

    def _on_backend_changed(self, *_args: object):
        backend_name = self.backend_var.get()
        config.set_value("backend", "type", backend_name)
        self._sync_review_to_menu()
        if not self._testing_mode:
            self._auto_health_check()

    def _auto_health_check(self):
        self._run_health_check(self.backend_var.get(), always_show_dialog=False)

    def _check_backend_health(self):
        if self._testing_mode:
            if self._health_check_backend:
                return
            self._health_check_backend = "simulated"
            self._set_action_buttons_state("disabled")
            self.cancel_btn.configure(state="normal")
            self.status_var.set("Simulating health check…")
            self._start_health_countdown()

            def _sim_complete():
                self._health_check_backend = None
                self._stop_health_countdown()
                self._set_action_buttons_state("normal")
                self.cancel_btn.configure(state="disabled")
                self.status_var.set(t("common.ready"))
                self._show_toast(
                    "Check Setup is simulated in testing mode — "
                    "backend connectivity is not tested", error=False)

            self.after(10_000, _sim_complete)
            return
        self._run_health_check(self.backend_var.get(), always_show_dialog=True)

    def _run_health_check(self, backend_name: str, *, always_show_dialog: bool):
        if self._running:
            return
        if self._health_check_backend == backend_name:
            return

        if self._health_check_timer:
            self._health_check_timer.cancel()
            self._health_check_timer = None

        self._health_check_backend = backend_name
        self._set_action_buttons_state("disabled")
        self.cancel_btn.configure(state="normal")
        self.status_var.set(t("health.checking", backend=backend_name))

        def _on_timeout():
            if self._health_check_backend == backend_name:
                self._health_check_backend = None
                self._health_check_timer = None
                self.after(0, self._stop_health_countdown)
                self.after(0, lambda: self._show_health_error(
                    t("health.timeout", backend=backend_name)))
                self.after(0, lambda: self._set_action_buttons_state("normal"))
                self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
                self.after(0, lambda: self.status_var.set(t("common.ready")))

        self._health_check_timer = threading.Timer(60, _on_timeout)
        self._health_check_timer.daemon = True
        self._health_check_timer.start()
        self._start_health_countdown()

        def _worker():
            try:
                report = check_backend(backend_name)
                if self._health_check_backend == backend_name:
                    if self._health_check_timer:
                        self._health_check_timer.cancel()
                        self._health_check_timer = None

                    self._health_check_backend = None
                    self.after(0, self._stop_health_countdown)

                    if always_show_dialog:
                        self.after(0, lambda: self._show_health_dialog(report))
                        self.after(0, lambda: self.status_var.set(t("common.ready")))
                    else:
                        if report.ready:
                            self.after(0, lambda: self.status_var.set(
                                t("health.auto_ok", backend=backend_name)))
                            if backend_name == "copilot":
                                self.after(0, self._refresh_copilot_model_list)
                            elif backend_name == "bedrock":
                                self.after(0, self._refresh_bedrock_model_list)
                            elif backend_name == "local":
                                self.after(0, self._refresh_local_model_list)
                        else:
                            self.after(0, lambda: self._show_health_dialog(report))
                            self.after(0, lambda: self.status_var.set(t("common.ready")))

                    self.after(0, lambda: self._set_action_buttons_state("normal"))
                    self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
            except Exception as exc:
                if self._health_check_backend == backend_name:
                    logger.error("Health check failed: %s", exc)
                    if self._health_check_timer:
                        self._health_check_timer.cancel()
                        self._health_check_timer = None
                    self._health_check_backend = None
                    self.after(0, lambda: self._show_health_error(str(exc)))
                    self.after(0, self._stop_health_countdown)
                    self.after(0, lambda: self._set_action_buttons_state("normal"))
                    self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
                    self.after(0, lambda: self.status_var.set(t("common.ready")))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_health_dialog(self, report):
        if self._testing_mode:
            logger.info("Health dialog suppressed in testing: %s", report.summary)
            return

        win = ctk.CTkToplevel(self)
        win.title(t("health.dialog_title"))
        win.geometry("600x450")
        win.grab_set()
        win.after(10, lambda w=win: _fix_titlebar(w))
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

        scroll = ctk.CTkScrollableFrame(win)
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

            if check.fix_hint and not check.passed:
                url_match = re.search(r'https?://[^\s]+', check.fix_hint)
                if url_match:
                    url = url_match.group(0)
                    text_before = check.fix_hint[:url_match.start()].rstrip(': ')

                    hint_frame = ctk.CTkFrame(scroll, fg_color="transparent")
                    hint_frame.grid(row=i * 3 + 2, column=1, sticky="w",
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
                        row=i * 3 + 2, column=1, sticky="w", padx=4,
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
        if "copilot" in self._model_refresh_in_progress:
            return
        self._model_refresh_in_progress.add("copilot")

        def _worker():
            try:
                models = get_copilot_models()
                self.after(0, lambda: self._apply_copilot_models(models))
            finally:
                self._model_refresh_in_progress.discard("copilot")

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_copilot_models(self, models: list):
        if models and hasattr(self, "_copilot_model_combo"):
            current = self._copilot_model_combo.get()
            self._copilot_model_combo.configure(values=["auto"] + models)
            self._copilot_model_combo.set(current)

    # ── Bedrock ────────────────────────────────────────────────────────────

    def _refresh_bedrock_model_list(self):
        models = get_bedrock_models()
        if models and hasattr(self, "_bedrock_model_combo"):
            current = self._bedrock_model_combo.get()
            self._bedrock_model_combo.configure(values=models)
            if current:
                self._bedrock_model_combo.set(current)

    def _refresh_bedrock_model_list_async(self):
        if "bedrock" in self._model_refresh_in_progress:
            return
        self._model_refresh_in_progress.add("bedrock")

        def _worker():
            try:
                models = get_bedrock_models()
                self.after(0, lambda: self._apply_bedrock_models(models))
            finally:
                self._model_refresh_in_progress.discard("bedrock")

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
        if "local" in self._model_refresh_in_progress:
            return
        self._model_refresh_in_progress.add("local")

        def _worker():
            try:
                api_url = config.get("local_llm", "api_url", "http://localhost:1234")
                api_type = config.get("local_llm", "api_type", "lmstudio")
                models = get_local_models(api_url, api_type)
                self.after(0, lambda: self._apply_local_models(models))
            finally:
                self._model_refresh_in_progress.discard("local")

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_local_models(self, models: list):
        if models and hasattr(self, "_local_model_combo"):
            current = self._local_model_combo.get()
            self._local_model_combo.configure(values=models)
            if current:
                self._local_model_combo.set(current)
