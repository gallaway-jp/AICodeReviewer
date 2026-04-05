from __future__ import annotations

import logging
from typing import Any

from aicodereviewer.config import config
from aicodereviewer.http_api import create_local_http_app, start_local_http_server
from aicodereviewer.i18n import t

logger = logging.getLogger(__name__)


class AppLocalHttpHelper:
    def __init__(self, host: Any) -> None:
        self.host = host

    def start_from_settings(self) -> None:
        if self.host._local_http_server_handle is not None:
            return
        enabled = config.get("local_http", "enabled", False)
        if enabled is not True:
            if hasattr(self.host, "_refresh_local_http_discovery_ui"):
                self.host._refresh_local_http_discovery_ui()
            return
        try:
            port = int(config.get("local_http", "port", 8765))
            create_app = getattr(self.host, "_create_local_http_app", create_local_http_app)
            start_server = getattr(self.host, "_start_local_http_server", start_local_http_server)
            api_app = create_app(runtime=self.host._review_runtime)
            self.host._local_http_server_handle = start_server(
                api_app,
                host="127.0.0.1",
                port=port,
            )
            logger.info(
                "Local HTTP server listening on %s",
                self.host._local_http_server_handle.base_url,
            )
            if hasattr(self.host, "_refresh_local_http_discovery_ui"):
                self.host._refresh_local_http_discovery_ui()
        except Exception as exc:
            logger.warning("Failed to start local HTTP server: %s", exc)
            if hasattr(self.host, "_refresh_local_http_discovery_ui"):
                self.host._refresh_local_http_discovery_ui()
            self.host._run_on_ui_thread(
                self.host._show_toast,
                f"Local HTTP server failed to start: {exc}",
                error=True,
            )

    def stop(self) -> None:
        handle = self.host._local_http_server_handle
        self.host._local_http_server_handle = None
        if handle is None:
            return
        try:
            handle.close(wait=True, timeout=1.0)
        except Exception as exc:
            logger.warning("Failed to stop local HTTP server cleanly: %s", exc)
        finally:
            if hasattr(self.host, "_refresh_local_http_discovery_ui"):
                self.host._refresh_local_http_discovery_ui()

    def runtime_status_snapshot(self) -> tuple[str, str]:
        configured_port = int(config.get("local_http", "port", 8765))
        handle = self.host._local_http_server_handle
        if handle is not None:
            runtime_port = getattr(handle, "port", configured_port)
            return (
                t("gui.settings.local_http_status_running", port=runtime_port),
                handle.base_url,
            )
        if config.get("local_http", "enabled", False) is True:
            return (
                t("gui.settings.local_http_status_not_running", port=configured_port),
                f"http://127.0.0.1:{configured_port}",
            )
        return (
            t("gui.settings.local_http_status_disabled", port=configured_port),
            f"http://127.0.0.1:{configured_port}",
        )