from __future__ import annotations

import logging
import queue
import threading
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.addons import install_addon_runtime
from aicodereviewer.auth import get_system_language
from aicodereviewer.config import config
from aicodereviewer.execution import ReviewExecutionRuntime, get_shared_review_execution_runtime
from aicodereviewer.i18n import set_locale, t
from aicodereviewer.models import ReviewIssue
from aicodereviewer.review_definitions import get_active_review_pack_paths, install_review_registry, merge_review_pack_paths

from .review_execution_coordinator import ReviewExecutionCoordinator
from .review_execution_facade import ReviewExecutionFacade
from .review_execution_scheduler import ReviewExecutionScheduler
from .review_queue_coordinator import ReviewSubmissionQueueCoordinator
from .review_queue_presenter import ReviewSubmissionQueuePresenter
from .review_runtime import (
    ActiveAIFixController,
    ActiveHealthCheckController,
    ActiveModelRefreshController,
    ActiveReviewChangesController,
    ActiveReviewController,
    ReviewSubmissionSelectionController,
)
from .widgets import QueueLogHandler


class AppBootstrapHelper:
    def __init__(self, host: Any) -> None:
        self.host = host

    def initialize(
        self,
        *,
        testing_mode: bool,
        review_runtime: ReviewExecutionRuntime | None,
    ) -> None:
        install_addon_runtime()
        install_review_registry(merge_review_pack_paths(get_active_review_pack_paths()))
        self.host._testing_mode = testing_mode
        self._apply_saved_language()
        self._apply_saved_theme()
        self._configure_window()
        self._initialize_log_state()
        self._initialize_review_state(review_runtime)
        self._initialize_dynamic_attrs()

    def build_ui(self) -> None:
        self.host.grid_columnconfigure(0, weight=1)
        self.host.grid_rowconfigure(0, weight=1)

        self.host.tabs = ctk.CTkTabview(self.host, anchor="nw")
        self.host.tabs.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self.host._build_review_tab()
        self.host._build_results_tab()
        self.host._build_benchmark_tab()
        self.host._build_addon_review_tab()
        self.host._build_settings_tab()
        self.host._build_log_tab()
        self.host._app_helpers().shell_layout().install_tab_selection_layout_hooks()
        self.host._app_helpers().surfaces().build_status_bar()

        self.bind_shortcuts()

    def bind_shortcuts(self) -> None:
        self.host.bind_all(
            "<Control-Return>",
            lambda e: self.host._start_review() if self.host._can_submit_review() else None,
        )
        self.host.bind_all("<Control-s>", self.host._on_ctrl_s)
        self.host.bind_all("<Control-Shift-o>", self.host._detach_current_page_shortcut)
        self.host.bind_all("<Control-Shift-O>", self.host._detach_current_page_shortcut)

    def install_log_handler(self) -> None:
        level_name = (config.get("logging", "log_level", "INFO") or "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        root_logger = logging.getLogger()
        if root_logger.level == logging.NOTSET or root_logger.level > level:
            root_logger.setLevel(level)
        self.host._queue_handler = QueueLogHandler(self.host._log_queue)
        self.host._queue_handler.setFormatter(logging.Formatter("%(message)s"))
        self.host._queue_handler.setLevel(level)
        root_logger.addHandler(self.host._queue_handler)

    def _apply_saved_language(self) -> None:
        saved_lang = config.get("gui", "language", "").strip()
        if saved_lang and saved_lang != "system":
            self.host._ui_lang = saved_lang
        else:
            self.host._ui_lang = get_system_language()
        set_locale(self.host._ui_lang)

    def _apply_saved_theme(self) -> None:
        saved_theme = config.get("gui", "theme", "").strip() or "system"
        theme_map = {"system": "System", "dark": "Dark", "light": "Light"}
        ctk.set_appearance_mode(theme_map.get(saved_theme, "System"))
        ctk.set_default_color_theme("blue")

    def _configure_window(self) -> None:
        self.host.title(t("common.app_title"))
        self.host.geometry(f"{self.host.WIDTH}x{self.host.HEIGHT}")
        self.host.minsize(860, 540)

    def _initialize_log_state(self) -> None:
        self.host._log_queue: queue.Queue[tuple[int, str]] = queue.Queue(maxsize=5000)
        self.host._log_lines: list[tuple[int, str]] = []
        self.host._log_polling = True
        self.host._ui_thread_id = threading.get_ident()
        self.host._ui_call_queue: queue.Queue[tuple[Any, tuple[Any, ...], dict[str, Any]]] = queue.Queue()
        self.install_log_handler()

    def _initialize_review_state(self, review_runtime: ReviewExecutionRuntime | None) -> None:
        self.host._issues: list[ReviewIssue] = []
        self.host._review_runtime = review_runtime or (
            ReviewExecutionRuntime()
            if self.host._testing_mode
            else get_shared_review_execution_runtime()
        )
        self.host._active_review = ActiveReviewController()
        self.host._review_execution = ReviewExecutionCoordinator(self.host._active_review)
        self.host._review_execution_facade = ReviewExecutionFacade(self.host._review_execution)
        self.host._review_execution_scheduler = ReviewExecutionScheduler(
            self.host._review_execution_facade,
            self.host._review_runtime,
        )
        self.host._review_submission_queue_presenter = ReviewSubmissionQueuePresenter()
        self.host._selected_review_submission = ReviewSubmissionSelectionController()
        self.host._review_submission_queue = ReviewSubmissionQueueCoordinator(
            self.host._review_execution_scheduler,
            self.host._review_submission_queue_presenter,
            self.host._selected_review_submission,
        )
        self.host._active_review_changes = ActiveReviewChangesController()
        self.host._active_ai_fix = ActiveAIFixController()
        self.host._active_health_check = ActiveHealthCheckController()
        self.host._active_model_refresh = ActiveModelRefreshController()

    def _initialize_dynamic_attrs(self) -> None:
        self.host._settings_backend_var = None
        self.host._copilot_model_combo = None
        self.host._bedrock_model_combo = None
        self.host._local_model_combo = None
        self.host._local_http_server_handle = None
        self.host._app_destroying = False
        self.host._detached_log_window = None
        self.host._detached_log_box = None
        self.host._detached_log_level_var = None
        self.host._detached_log_level_menu = None
        self.host._detached_log_clear_btn = None
        self.host._detached_log_save_btn = None
        self.host._detached_log_redock_btn = None
        self.host._detached_settings_window = None
        self.host._detached_settings_container = None
        self.host._detached_settings_redock_btn = None
        self.host._detached_benchmark_window = None
        self.host._detached_benchmark_container = None
        self.host._detached_benchmark_redock_btn = None
        self.host._detached_addon_review_window = None
        self.host._detached_addon_review_container = None
        self.host._detached_addon_review_redock_btn = None
        self.host._current_addon_review_surface = None
        self.host._current_addon_review_diffs = {}