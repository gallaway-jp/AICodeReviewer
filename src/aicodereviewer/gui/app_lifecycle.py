from __future__ import annotations

import logging
from typing import Any


class AppLifecycleHelper:
    def __init__(self, host: Any) -> None:
        self.host = host

    def run_startup(self) -> None:
        self.host._build_ui()
        self.host._start_local_http_server_from_settings()
        self.host._poll_log_queue()
        if not self.host._testing_mode:
            self.host._schedule_app_after(100, self.host._refresh_current_backend_models_async)
            self.host._schedule_app_after(500, self.host._auto_health_check)

    def prepare_for_destroy(self) -> None:
        self.host._log_polling = False
        self.host._cancel_widget_after_callbacks(self.host)
        self.host._stop_local_http_server()
        if hasattr(self.host, "_queue_handler"):
            logging.getLogger().removeHandler(self.host._queue_handler)
        self._release_active_ai_fix_client()
        self._finish_active_health_check()
        if hasattr(self.host, "_release_review_client"):
            self.host._release_review_client()
        self.host._app_helpers().runtime().clear_ui_call_queue()

    def _release_active_ai_fix_client(self) -> None:
        active_ai_fix = getattr(self.host, "_active_ai_fix", None)
        if active_ai_fix is None or getattr(active_ai_fix, "client", None) is None:
            return
        if hasattr(self.host, "_release_ai_fix_client"):
            self.host._release_ai_fix_client()

    def _finish_active_health_check(self) -> None:
        active_health_check = getattr(self.host, "_active_health_check", None)
        if active_health_check is None or not getattr(active_health_check, "running", False):
            return
        if hasattr(self.host, "_cancel_active_health_check_timer"):
            self.host._cancel_active_health_check_timer()
        if hasattr(self.host, "_finish_active_health_check"):
            self.host._finish_active_health_check()