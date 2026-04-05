# src/aicodereviewer/gui/review_mixin.py
"""Review-tab builder and execution logic mixin for :class:`App`.

Provides ``_build_review_tab`` plus input validation, dry-run / full review
execution, file browsing helpers and the elapsed-time / health-countdown
tickers.
"""
from __future__ import annotations

import inspect
import logging
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional, cast

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.backends import create_backend
from aicodereviewer.config import config
from aicodereviewer.execution import CallbackEventSink, ReviewExecutionService, ReviewJob, ReviewRequest
from aicodereviewer.i18n import t
from aicodereviewer.orchestration import AppRunner
from aicodereviewer.recommendations import (
    ReviewRecommendationCancelledError,
    ReviewRecommendationResult,
    recommend_review_types,
)
from aicodereviewer.registries import get_review_registry
from aicodereviewer.review_presets import (
    REVIEW_TYPE_PRESETS,
    format_review_preset_picker_label,
    get_review_preset_label,
    get_review_type_label,
    infer_review_type_preset,
    resolve_review_preset_key,
)
from aicodereviewer.scanner import (
    scan_project_with_scope,
    parse_diff_file,
    get_diff_from_commits,
)

from .dialogs import FileSelector
from .review_builder import ReviewTabBuilder
from .review_execution_coordinator import ReviewExecutionCoordinator
from .review_execution_facade import ReviewExecutionFacade
from .review_layout import ReviewLayoutHelper
from .review_execution_scheduler import ReviewExecutionScheduler, ReviewExecutionSubmissionSnapshot
from .review_runtime import (
    ActiveAIFixController,
    ActiveHealthCheckController,
    ActiveReviewChangesController,
    ActiveReviewController,
)
from .shared_ui import (
    MUTED_TEXT,
    SECTION_BORDER,
    SECTION_SURFACE,
    add_section_header,
    build_autohide_scroller,
    ensure_autohide_scroll_bindings,
    on_scroll_mousewheel,
    resolve_scroll_background,
    scroll_canvas_for_widget,
)
from .widgets import _CancelledError

logger = logging.getLogger(__name__)

__all__ = ["ReviewTabMixin"]


class ReviewTabMixin:
    """Mixin supplying Review-tab construction and review execution."""

    _SECTION_SURFACE = SECTION_SURFACE
    _SECTION_BORDER = SECTION_BORDER
    _MUTED_TEXT = MUTED_TEXT
    _REVIEW_TYPES_SCROLL_HEIGHT = 260
    _REVIEW_SPLIT_LAYOUT_MIN_WIDTH = 1120
    _REVIEW_TYPES_TWO_COLUMN_MIN_WIDTH = 620
    _REVIEW_TYPES_THREE_COLUMN_MIN_WIDTH = 860
    _REVIEW_TYPE_ACTIONS_INLINE_MIN_WIDTH = 1180
    _REVIEW_TYPE_ACTIONS_TWO_ROW_MIN_WIDTH = 760

    def _review_logical_width(self, *candidates: Any) -> float:
        available_width = 0
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                width = int(getattr(candidate, "winfo_width", lambda: 0)())
            except Exception:
                continue
            if width > 1:
                available_width = width
                break
        if available_width <= 1:
            try:
                available_width = int(getattr(self, "winfo_width", lambda: 0)())
            except Exception:
                available_width = 0

        try:
            window_scaling = float(ctk.ScalingTracker.get_window_scaling(self))
        except Exception:
            window_scaling = 1.0
        if window_scaling <= 0:
            window_scaling = 1.0
        logical_width = available_width / window_scaling
        requested_width = float(getattr(self, "_requested_geometry_width", 0) or 0)
        if requested_width > 0:
            logical_width = max(logical_width, requested_width)
        return logical_width

    def _review_scroll_background(self) -> str:
        return resolve_scroll_background()

    def _review_scroll_canvas_for_widget(self, widget: Any) -> Any | None:
        return scroll_canvas_for_widget(widget)

    def _on_review_scroll_mousewheel(self, event: Any) -> str | None:
        return on_scroll_mousewheel(event)

    def _ensure_review_scroll_bindings(self) -> None:
        ensure_autohide_scroll_bindings(self)
        self._review_scroll_bindings_ready = getattr(self, "_acr_scroll_bindings_ready", False)

    def _build_autohide_scroller(
        self,
        parent: Any,
        *,
        content_fg_color: Any = "transparent",
        height: int | None = None,
    ) -> tuple[Any, Any, Any, Any]:
        return build_autohide_scroller(
            self,
            parent,
            content_fg_color=content_fg_color,
            height=height,
        )

    def _build_review_autohide_scroller(
        self,
        parent: Any,
        *,
        content_fg_color: Any = "transparent",
        height: int | None = None,
    ) -> tuple[Any, Any, Any, Any]:
        return self._build_autohide_scroller(
            parent,
            content_fg_color=content_fg_color,
            height=height,
        )

    def _schedule_review_layout_refresh(self, *_args: Any) -> None:
        self._refresh_review_tab_layout()

    def _schedule_review_type_layout_refresh(self, *_args: Any) -> None:
        self._refresh_review_type_layout()

    def _review_layout_helper(self) -> ReviewLayoutHelper:
        return ReviewLayoutHelper(self)

    def _refresh_review_tab_layout(self) -> None:
        self._review_layout_helper().refresh_tab_layout()

    def _refresh_review_type_layout(self) -> None:
        self._review_layout_helper().refresh_type_layout()

    def _refresh_review_type_checkbox_layout(self) -> None:
        self._review_layout_helper().refresh_type_checkbox_layout()

    def _refresh_review_type_controls_layout(self) -> None:
        self._review_layout_helper().refresh_type_controls_layout()

    def _backend_display_label(self, backend_key: str, fallback: str) -> str:
        translated = t(f"gui.review.backend_{backend_key}")
        if translated != f"gui.review.backend_{backend_key}":
            return translated
        return fallback

    def _on_review_backend_selected(self, selected_display: str) -> None:
        internal_value = getattr(self, "_review_backend_reverse_map", {}).get(selected_display, "bedrock")
        if self.backend_var.get() != internal_value:
            self.backend_var.set(internal_value)

    def _sync_review_backend_menu(self, *_args: Any) -> None:
        if not hasattr(self, "review_backend_display_var"):
            return
        internal_value = self.backend_var.get()
        display_value = getattr(self, "_review_backend_display_map", {}).get(internal_value, internal_value)
        if self.review_backend_display_var.get() != display_value:
            self.review_backend_display_var.set(display_value)

    def _review_controller(self) -> ActiveReviewController:
        """Return the runtime owner for the app's active review state."""
        return cast(ActiveReviewController, getattr(self, "_active_review"))

    def _review_execution_coordinator(self) -> ReviewExecutionCoordinator:
        """Return the coordinator for review execution behavior."""
        return cast(ReviewExecutionCoordinator, getattr(self, "_review_execution"))

    def _review_execution_facade_handle(self) -> ReviewExecutionFacade:
        """Return the higher-level facade for review execution setup."""
        return cast(ReviewExecutionFacade, getattr(self, "_review_execution_facade"))

    def _review_execution_scheduler_handle(self) -> ReviewExecutionScheduler:
        """Return the scheduler-facing boundary for review execution."""
        return cast(ReviewExecutionScheduler, getattr(self, "_review_execution_scheduler"))

    def _ai_fix_controller(self) -> ActiveAIFixController:
        """Return the runtime owner for the app's active AI Fix state."""
        return cast(ActiveAIFixController, getattr(self, "_active_ai_fix"))

    def _health_check_controller(self) -> ActiveHealthCheckController:
        """Return the runtime owner for the app's active health-check state."""
        return cast(ActiveHealthCheckController, getattr(self, "_active_health_check"))

    def _review_changes_controller(self) -> ActiveReviewChangesController:
        """Return the runtime owner for Review Changes verification state."""
        return cast(ActiveReviewChangesController, getattr(self, "_active_review_changes"))

    def _add_review_section_header(self, parent: Any, row: int, title: str, description: str) -> int:
        return add_section_header(parent, row, title, description, muted_text=self._MUTED_TEXT)

    def _add_section_header(self, parent: Any, row: int, title: str, description: str) -> int:
        return add_section_header(parent, row, title, description, muted_text=self._MUTED_TEXT)

    def _is_review_execution_running(self) -> bool:
        """Return True when a review execution is currently active."""
        return bool(self._review_controller().running)

    def _is_review_changes_running(self) -> bool:
        """Return True when Review Changes verification is currently active."""
        return bool(self._review_changes_controller().running)

    def _is_health_check_running(self) -> bool:
        """Return True when a backend health check is currently active."""
        return bool(self._health_check_controller().running)

    def _is_ai_fix_running(self) -> bool:
        """Return True when AI Fix generation is currently active."""
        return bool(self._ai_fix_controller().running)

    def _is_busy(self) -> bool:
        """Return True when any blocking GUI background workflow is active."""
        return (
            self._is_review_execution_running()
            or self._is_review_changes_running()
            or self._is_health_check_running()
            or self._is_ai_fix_running()
            or self._is_review_recommendation_running()
        )

    def _can_submit_review(self) -> bool:
        """Return True when the GUI may accept another review submission."""
        return not (
            self._is_review_changes_running()
            or self._is_health_check_running()
            or self._is_ai_fix_running()
            or self._is_review_recommendation_running()
        )

    def _is_global_cancel_available(self) -> bool:
        """Return True when the shared cancel button should be enabled."""
        if self._is_health_check_running():
            return True

        recommendation_cancel_event = self._active_review_recommendation_cancel_event()
        if (
            self._is_review_recommendation_running()
            and recommendation_cancel_event is not None
            and not recommendation_cancel_event.is_set()
        ):
            return True

        cancel_event = self._active_review_cancel_event()
        return bool(cancel_event is not None and not cancel_event.is_set() and self._is_review_execution_running())

    def _is_review_recommendation_running(self) -> bool:
        """Return True when a recommendation lookup is active."""
        return bool(getattr(self, "_review_recommendation_running", False))

    def _sync_global_cancel_button(self) -> None:
        """Keep the shared cancel button aligned with the active cancel-capable workflow."""
        if not hasattr(self, "cancel_btn"):
            return
        self.cancel_btn.configure(
            state="normal" if self._is_global_cancel_available() else "disabled"
        )

    def _sync_review_submission_controls(self) -> None:
        """Keep review action buttons aligned with queue-capable review submission rules."""
        if not hasattr(self, "run_btn"):
            return
        submit_state = "normal" if self._can_submit_review() else "disabled"
        health_state = "normal" if not self._is_busy() else "disabled"
        self.run_btn.configure(state=submit_state)
        self.dry_btn.configure(state=submit_state)
        self.health_btn.configure(state=health_state)
        if hasattr(self, "recommend_btn"):
            self.recommend_btn.configure(state=submit_state)
        self._sync_review_pinning_controls()

    def _has_pinned_review_selection(self) -> bool:
        """Return True when a pinned default review-type set is configured."""
        return bool(getattr(self, "_pinned_review_types", []))

    def _current_selection_matches_pinned(self) -> bool:
        """Return True when the active checkbox selection matches the pinned default."""
        if not self._has_pinned_review_selection():
            return False
        return set(self._get_selected_types()) == set(getattr(self, "_pinned_review_types", []))

    def _sync_review_pinning_controls(self) -> None:
        """Keep pinned-review controls aligned with the current selection and busy state."""
        if not hasattr(self, "pin_review_set_btn"):
            return

        busy = self._is_busy()
        pin_state = "normal" if self._get_selected_types() and not busy else "disabled"
        clear_state = "normal" if self._has_pinned_review_selection() and not busy else "disabled"

        self.pin_review_set_btn.configure(state=pin_state)
        self.clear_pinned_review_set_btn.configure(state=clear_state)

        if not hasattr(self, "review_pin_status_label"):
            return

        if not self._has_pinned_review_selection():
            summary = t("gui.review.pin_hint")
        else:
            pinned_types = list(getattr(self, "_pinned_review_types", []))
            pinned_preset = cast(Optional[str], getattr(self, "_pinned_review_preset", None))
            type_labels = ", ".join(get_review_type_label(review_type) for review_type in pinned_types)
            if pinned_preset:
                summary_key = (
                    "gui.review.pin_active_preset_summary"
                    if self._current_selection_matches_pinned()
                    else "gui.review.pin_summary_preset"
                )
                summary = t(
                    summary_key,
                    preset=get_review_preset_label(pinned_preset),
                    types=type_labels,
                )
            else:
                summary_key = (
                    "gui.review.pin_active_summary"
                    if self._current_selection_matches_pinned()
                    else "gui.review.pin_summary"
                )
                summary = t(summary_key, types=type_labels)
        self.review_pin_status_label.configure(text=summary)

    def _parse_review_type_selection(self, raw_types: str) -> List[str]:
        """Resolve a stored comma-separated review-type list to canonical keys."""
        review_registry = get_review_registry()
        selected_types: list[str] = []
        seen: set[str] = set()
        for raw_type in raw_types.split(","):
            normalized = raw_type.strip()
            if not normalized:
                continue
            try:
                canonical = review_registry.resolve_key(normalized)
            except KeyError:
                canonical = normalized
            if canonical not in seen:
                selected_types.append(canonical)
                seen.add(canonical)
        return selected_types

    def _load_pinned_review_selection(self) -> tuple[List[str], Optional[str]]:
        """Load the pinned default review-type set from config."""
        raw_pinned_types = config.get("gui", "pinned_review_types", "").strip()
        if not raw_pinned_types:
            return [], None

        pinned_types = self._parse_review_type_selection(raw_pinned_types)
        if not pinned_types:
            return [], None

        raw_pinned_preset = config.get("gui", "pinned_review_preset", "").strip()
        pinned_preset: Optional[str] = None
        if raw_pinned_preset:
            try:
                pinned_preset = resolve_review_preset_key(raw_pinned_preset)
            except KeyError:
                pinned_preset = None
        if pinned_preset is None:
            pinned_preset = infer_review_type_preset(pinned_types)

        return pinned_types, pinned_preset

    def _store_pinned_review_selection(self, selected_types: List[str]) -> None:
        """Persist the pinned default review-type set."""
        pinned_preset = infer_review_type_preset(selected_types)
        config.set_value("gui", "pinned_review_types", ",".join(selected_types))
        config.set_value("gui", "pinned_review_preset", pinned_preset or "")
        config.save()
        self._pinned_review_types = list(selected_types)
        self._pinned_review_preset = pinned_preset
        self._sync_review_pinning_controls()

    def _clear_pinned_review_selection(self) -> None:
        """Remove the pinned default review-type set from config."""
        if not self._has_pinned_review_selection():
            return
        try:
            config.set_value("gui", "pinned_review_types", "")
            config.set_value("gui", "pinned_review_preset", "")
            config.save()
        except Exception as exc:
            logger.warning("Failed to clear pinned review set: %s", exc)
            self._show_toast(t("gui.review.pin_clear_failed", error=exc), error=True)
            return
        self._pinned_review_types = []
        self._pinned_review_preset = None
        self._sync_review_pinning_controls()
        self.status_var.set(t("gui.review.pin_cleared"))
        self._show_toast(t("gui.review.pin_cleared"), error=False)

    def _pin_current_review_selection(self) -> None:
        """Pin the active checkbox selection as the default recommendation set."""
        selected_types = self._get_selected_types()
        if not selected_types:
            self._show_toast(t("gui.val.type_required"), error=True)
            return
        try:
            self._store_pinned_review_selection(selected_types)
        except Exception as exc:
            logger.warning("Failed to persist pinned review set: %s", exc)
            self._show_toast(t("gui.review.pin_save_failed", error=exc), error=True)
            return
        self.status_var.set(t("gui.review.pin_saved"))
        self._show_toast(t("gui.review.pin_saved"), error=False)

    def _attach_active_review_client(self, client: Any | None) -> None:
        """Attach a backend client to the active review controller."""
        self._review_controller().bind_client(client)

    def _active_review_client(self) -> Any | None:
        """Return the backend client currently owned by review-related flows."""
        return self._review_controller().client

    def _bind_active_review_client(self, client: Any | None) -> None:
        """Bind a transient review-side backend client onto the active review controller."""
        self._review_controller().bind_client(client)

    def _active_review_cancel_event(self) -> threading.Event | None:
        """Return the cancel event currently owned by review execution."""
        return self._review_controller().cancel_event

    def _bind_session_runner(self, runner: AppRunner | None) -> None:
        """Attach the current finalize-capable session runner to the active review controller."""
        self._review_controller().bind_runner(runner)

    def _clear_session_runner(self) -> None:
        """Clear the current finalize-capable session runner binding."""
        self._bind_session_runner(None)

    def _current_session_runner(self) -> AppRunner | None:
        """Return the runner currently bound for finalize or session restore flows."""
        return self._review_controller().runner

    def _build_review_runner(
        self,
        client: Any | None,
        *,
        scan_fn: Any,
        backend_name: str,
    ) -> Any:
        """Create an AppRunner while preserving compatibility with older test doubles."""
        runner_kwargs: dict[str, Any] = {
            "scan_fn": scan_fn,
            "backend_name": backend_name,
        }
        try:
            signature = inspect.signature(AppRunner)
        except (TypeError, ValueError):
            signature = None
        accepts_execution_service = signature is None or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD or name == "execution_service"
            for name, parameter in (signature.parameters.items() if signature is not None else ())
        )
        if accepts_execution_service:
            runner_kwargs["execution_service"] = ReviewExecutionService(scan_fn=scan_fn)
        return AppRunner(client, **runner_kwargs)

    @staticmethod
    def _runner_uses_execution_service(runner: Any) -> bool:
        """Return True when the runner exposes the typed execution-service boundary."""
        return hasattr(runner, "execution_service") and hasattr(runner, "_set_execution_result")

    def _begin_active_ai_fix(self) -> threading.Event:
        """Start a tracked active AI Fix execution and return its cancel event."""
        return self._ai_fix_controller().begin()

    def _attach_active_ai_fix_client(self, client: Any | None) -> None:
        """Attach a backend client to the active AI Fix controller."""
        self._ai_fix_controller().bind_client(client)

    def _current_ai_fix_client(self) -> Any | None:
        """Return the backend client currently owned by the AI Fix workflow."""
        return self._ai_fix_controller().client

    def _active_ai_fix_cancel_event(self) -> threading.Event | None:
        """Return the cancel event currently owned by the AI Fix workflow."""
        return self._ai_fix_controller().cancel_event

    def _active_review_recommendation_cancel_event(self) -> threading.Event | None:
        """Return the cancel event currently owned by the review recommendation flow."""
        return cast(Optional[threading.Event], getattr(self, "_review_recommendation_cancel_event", None))

    def _bind_active_review_recommendation_client(self, client: Any | None) -> None:
        """Track the transient backend client used by review recommendations."""
        self._review_recommendation_client = client

    def _active_review_recommendation_client(self) -> Any | None:
        """Return the transient backend client currently used by review recommendations."""
        return getattr(self, "_review_recommendation_client", None)

    def _begin_review_recommendation_cancel(self) -> threading.Event:
        """Start a cancellable review recommendation run and return its cancel event."""
        cancel_event = threading.Event()
        self._review_recommendation_cancel_event = cancel_event
        self._bind_active_review_recommendation_client(None)
        return cancel_event

    def _request_active_review_recommendation_cancel(self) -> None:
        """Signal cancellation for the active review recommendation flow when possible."""
        cancel_event = self._active_review_recommendation_cancel_event()
        if cancel_event is not None:
            cancel_event.set()
        client = self._active_review_recommendation_client()
        if client is not None and hasattr(client, "cancel"):
            try:
                client.cancel()
            except Exception as exc:
                logger.warning("Failed to cancel recommendation backend: %s", exc)

    def _clear_active_review_recommendation_tracking(self, cancel_event: threading.Event | None = None) -> None:
        """Drop the tracked cancel state and client for the completed recommendation run."""
        active_cancel_event = self._active_review_recommendation_cancel_event()
        if cancel_event is not None and active_cancel_event is not cancel_event:
            return
        self._review_recommendation_cancel_event = None
        self._bind_active_review_recommendation_client(None)

    def _dispatch_review_ui(self, callback: Any, *args: Any, **kwargs: Any) -> bool:
        """Marshal worker-thread review UI updates onto the main loop when available."""
        dispatcher = getattr(self, "_run_on_ui_thread", None)
        if callable(dispatcher):
            return bool(dispatcher(callback, *args, **kwargs))
        schedule_after = getattr(self, "_schedule_app_after", self.after)
        schedule_after(0, lambda: callback(*args, **kwargs))
        return True

    def _has_backend_context_for_ai_fix(self) -> bool:
        """Return True when AI Fix has enough backend context to run."""
        return bool(
            self._current_ai_fix_client()
            or self._current_session_runner() is not None
            or getattr(self, "_testing_mode", False)
        )

    def _request_active_ai_fix_cancel(self) -> None:
        """Signal cancellation for the active AI Fix workflow when possible."""
        self._ai_fix_controller().request_cancel()

    def _finish_active_ai_fix(self) -> None:
        """Mark the active AI Fix workflow as finished."""
        self._ai_fix_controller().finish()

    def _release_ai_fix_client(self) -> None:
        """Release the backend client owned by the active AI Fix workflow."""
        self._ai_fix_controller().release_client()

    def _begin_active_health_check(self, backend_name: str) -> None:
        """Start tracking an active health check for the given backend."""
        self._health_check_controller().begin(backend_name)

    def _bind_active_health_check_timer(self, timer: threading.Timer | None) -> None:
        """Attach the timeout timer used by the active health check."""
        self._health_check_controller().bind_timer(timer)

    def _cancel_active_health_check_timer(self) -> None:
        """Cancel the timeout timer used by the active health check."""
        self._health_check_controller().cancel_timer()

    def _active_health_check_matches(self, backend_name: str) -> bool:
        """Return True when the active health check targets the given backend."""
        return self._health_check_controller().matches(backend_name)

    def _finish_active_health_check(self) -> None:
        """Mark the active health check as finished and clear its timer."""
        self._health_check_controller().finish()

    # ══════════════════════════════════════════════════════════════════════
    #  REVIEW TAB  – includes inline results panel
    # ══════════════════════════════════════════════════════════════════════

    def _build_review_tab(self):
        ReviewTabBuilder(self).build()

    # ══════════════════════════════════════════════════════════════════════
    #  ACTIONS – file browsing, validation, review execution
    # ══════════════════════════════════════════════════════════════════════

    def _browse_path(self):
        if self._testing_mode:
            return
        d = filedialog.askdirectory()
        if d:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, d)

    def _browse_diff(self):
        f = filedialog.askopenfilename(
            filetypes=[
                (t("common.filetype_diff_patch"), "*.diff *.patch"),
                (t("common.filetype_all"), "*.*"),
            ])
        if f:
            self.diff_file_entry.delete(0, "end")
            self.diff_file_entry.insert(0, f)

    def _set_all_types(self, value: bool):
        for var in self.type_vars.values():
            var.set(value)
        self._sync_review_preset_ui()
        self._sync_review_pinning_controls()

    def _on_review_types_changed(self) -> None:
        self._sync_review_preset_ui()
        self._sync_review_pinning_controls()

    def _on_review_preset_selected(self, selected_label: str) -> None:
        preset_key = self._review_preset_reverse.get(selected_label, "custom")
        if preset_key == "custom":
            self._sync_review_preset_ui()
            self._sync_review_pinning_controls()
            return
        selected_types = set(REVIEW_TYPE_PRESETS[preset_key])
        for key, var in self.type_vars.items():
            var.set(key in selected_types)
        self._sync_review_preset_ui(preset_key)
        self._sync_review_pinning_controls()

    def _sync_review_preset_ui(self, preset_key: Optional[str] = None) -> None:
        current_preset = preset_key or infer_review_type_preset(self._get_selected_types())
        display_key = current_preset or "custom"
        if hasattr(self, "review_preset_var"):
            self.review_preset_var.set(self._review_preset_labels[display_key])
        if not hasattr(self, "review_preset_summary_label"):
            return
        if current_preset:
            included = ", ".join(
                get_review_type_label(review_type)
                for review_type in REVIEW_TYPE_PRESETS[current_preset]
            )
            summary = t(
                "gui.review.preset_summary",
                preset=get_review_preset_label(current_preset),
                types=included,
            )
        else:
            summary = t("gui.review.preset_custom_summary")
        self.review_preset_summary_label.configure(text=summary)

    def _on_scope_changed(self, *_args: object) -> None:
        scope = self.scope_var.get()
        if scope == "project":
            self.file_select_frame.grid()
            self.diff_filter_frame.grid()
            self.diff_frame.grid_remove()
        else:
            self.file_select_frame.grid_remove()
            self.diff_filter_frame.grid_remove()
            self.diff_frame.grid()

    def _on_diff_filter_changed(self, *_args: object) -> None:
        enabled = self.diff_filter_var.get()
        state = "normal" if enabled else "disabled"
        self.diff_filter_file_entry.configure(state=state)
        self.diff_filter_browse_btn.configure(state=state)
        self.diff_filter_commits_entry.configure(state=state)

    def _browse_diff_filter(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                (t("common.filetype_diff_patch"), "*.diff *.patch"),
                (t("common.filetype_all"), "*.*"),
            ])
        if path:
            self.diff_filter_file_entry.delete(0, "end")
            self.diff_filter_file_entry.insert(0, path)

    def _on_file_select_mode_changed(self, *_args: object):
        mode = self.file_select_mode_var.get()
        if mode == "selected":
            self.select_files_btn.configure(state="normal")
        else:
            self.select_files_btn.configure(state="disabled")

    def _open_file_selector(self):
        path = self.path_entry.get().strip()
        if not path:
            self._show_toast(t("gui.val.path_required"), error=True)
            return
        if not Path(path).is_dir():
            if self._testing_mode:
                path = str(Path(__file__).resolve().parent.parent.parent.parent)
            else:
                self._show_toast(t("gui.review.invalid_project_path"), error=True)
                return
        selector = FileSelector(self, path, self.selected_files)
        self.wait_window(selector)
        if hasattr(selector, 'result') and selector.result:
            self.selected_files = list(selector.result)
            self._file_count_lbl.configure(
                text=self._selected_file_count_text(len(self.selected_files)))
            self._show_toast(t("gui.review.selected_file_count", count=len(self.selected_files)))
            try:
                config.set_value("gui", "selected_files",
                                 "|".join(self.selected_files))
                config.save()
            except Exception as exc:
                logger.warning("Could not save selected files: %s", exc)

    def _get_selected_types(self) -> List[str]:
        return [k for k, v in self.type_vars.items() if v.get()]

    def _save_form_values(self):
        try:
            config.set_value("gui", "project_path", self.path_entry.get().strip())
            config.set_value("gui", "programmers", self.programmers_entry.get().strip())
            config.set_value("gui", "reviewers", self.reviewers_entry.get().strip())
            config.set_value("gui", "spec_file", self.spec_entry.get().strip())
            selected_types = self._get_selected_types()
            config.set_value("gui", "review_types", ",".join(selected_types))
            config.set_value("gui", "file_select_mode",
                             self.file_select_mode_var.get())
            config.set_value("gui", "selected_files",
                             "|".join(self.selected_files))
            config.set_value("processing", "enable_architectural_review",
                             str(self.arch_analysis_var.get()).lower())
            config.save()
        except Exception as exc:
            logger.warning("Failed to save form values: %s", exc)

    def _validate_inputs(self, dry_run: bool = False) -> Optional[Dict[str, Any]]:
        """Validate form and return a params dict, or None on failure."""
        path = self.path_entry.get().strip()
        scope = self.scope_var.get()
        diff_file: Optional[str] = None
        commits: Optional[str] = None
        diff_filter_file: Optional[str] = None
        diff_filter_commits: Optional[str] = None

        if scope == "diff":
            diff_file = self.diff_file_entry.get().strip() or None
            commits = self.commits_entry.get().strip() or None
        elif scope == "project" and self.diff_filter_var.get():
            diff_filter_file = self.diff_filter_file_entry.get().strip() or None
            diff_filter_commits = self.diff_filter_commits_entry.get().strip() or None

        if scope == "project" and not path:
            self._show_toast(t("gui.val.path_required"), error=True)
            return None

        selected_files: Optional[List[str]] = None
        if scope == "project":
            file_mode = self.file_select_mode_var.get()
            if file_mode == "selected":
                if not self.selected_files:
                    self._show_toast(t("gui.review.select_files_required"), error=True)
                    return None
                selected_files = self.selected_files

        if scope == "project" and self.diff_filter_var.get():
            if not diff_filter_file and not diff_filter_commits:
                self._show_toast(t("gui.review.diff_filter_required"), error=True)
                return None

        if scope == "diff" and not diff_file and not commits:
            self._show_toast(t("gui.val.diff_required"), error=True)
            return None

        review_types = self._get_selected_types()
        if not review_types:
            self._show_toast(t("gui.val.type_required"), error=True)
            return None

        programmers = [n.strip() for n in self.programmers_entry.get().split(",") if n.strip()] if not dry_run else []
        reviewers = [n.strip() for n in self.reviewers_entry.get().split(",") if n.strip()] if not dry_run else []

        if not dry_run and (not programmers or not reviewers):
            self._show_toast(t("gui.val.meta_required"), error=True)
            return None

        spec_content = None
        spec_path = self.spec_entry.get().strip()
        if "specification" in review_types and spec_path:
            try:
                with open(spec_path, "r", encoding="utf-8") as fh:
                    spec_content = fh.read()
            except Exception as exc:
                self._show_toast(t("gui.val.spec_read_error", error=exc), error=True)
                return None

        lang_display = self.lang_var.get()
        review_lang = self._review_lang_reverse.get(lang_display, "system")
        if review_lang == "system":
            review_lang = self._ui_lang
        config.set_value("gui", "review_language",
                         self._review_lang_reverse.get(lang_display, "system"))
        try:
            config.save()
        except Exception:
            pass

        return dict(
            path=path or None,
            scope=scope,
            diff_file=diff_file,
            commits=commits,
            review_types=review_types,
            spec_content=spec_content,
            target_lang=review_lang,
            programmers=programmers,
            reviewers=reviewers,
            backend=self.backend_var.get(),
            selected_files=selected_files,
            diff_filter_file=diff_filter_file,
            diff_filter_commits=diff_filter_commits,
        )

    def _start_review(self):
        if not self._can_submit_review():
            return
        if self._testing_mode:
            self._show_toast(
                t("gui.review.testing_mode_start"), error=False)
            return
        params = self._validate_inputs()
        if not params:
            return
        self._save_form_values()
        self._run_review(params, dry_run=False)

    def _start_dry_run(self):
        if not self._can_submit_review():
            return
        params = self._validate_inputs(dry_run=True)
        if not params:
            return
        if not self._testing_mode:
            self._save_form_values()
        self._run_review(params, dry_run=True)

    def _set_action_buttons_state(self, state: str):
        self.run_btn.configure(state=state)
        self.dry_btn.configure(state=state)
        self.health_btn.configure(state=state)
        if hasattr(self, "recommend_btn"):
            self.recommend_btn.configure(state=state)
        self._sync_review_pinning_controls()

    def _validate_recommendation_inputs(self) -> Optional[Dict[str, Any]]:
        path = self.path_entry.get().strip()
        scope = self.scope_var.get()
        diff_file: Optional[str] = None
        commits: Optional[str] = None
        diff_filter_file: Optional[str] = None
        diff_filter_commits: Optional[str] = None

        if scope == "diff":
            diff_file = self.diff_file_entry.get().strip() or None
            commits = self.commits_entry.get().strip() or None
        elif scope == "project" and self.diff_filter_var.get():
            diff_filter_file = self.diff_filter_file_entry.get().strip() or None
            diff_filter_commits = self.diff_filter_commits_entry.get().strip() or None

        if scope == "project" and not path:
            self._show_toast(t("gui.val.path_required"), error=True)
            return None
        if scope == "diff" and not diff_file and not commits:
            self._show_toast(t("gui.val.diff_required"), error=True)
            return None
        if scope == "project" and self.file_select_mode_var.get() == "selected" and not self.selected_files:
            self._show_toast(t("gui.review.select_files_required"), error=True)
            return None
        if scope == "project" and self.diff_filter_var.get() and not diff_filter_file and not diff_filter_commits:
            self._show_toast(t("gui.review.diff_filter_required"), error=True)
            return None

        lang_display = self.lang_var.get()
        review_lang = self._review_lang_reverse.get(lang_display, "system")
        if review_lang == "system":
            review_lang = self._ui_lang

        return {
            "path": path or None,
            "scope": scope,
            "diff_file": diff_file,
            "commits": commits,
            "target_lang": review_lang,
            "backend": self.backend_var.get(),
            "selected_files": list(self.selected_files) if self.file_select_mode_var.get() == "selected" else None,
            "diff_filter_file": diff_filter_file,
            "diff_filter_commits": diff_filter_commits,
        }

    def _set_review_recommendation_running(self, running: bool) -> None:
        self._review_recommendation_running = running
        self._sync_review_submission_controls()
        self._sync_global_cancel_button()

    def _start_review_recommendation(self) -> None:
        if not self._can_submit_review():
            return
        params = self._validate_recommendation_inputs()
        if not params:
            return
        cancel_event = self._begin_review_recommendation_cancel()
        if not self._testing_mode:
            self._save_form_values()
        self.review_recommendation_label.configure(text=t("gui.review.recommendation_running"))
        self.status_var.set(t("gui.review.recommendation_running"))
        self._set_review_recommendation_running(True)
        if self._testing_mode:
            self._run_review_recommendation_worker(params, cancel_event)
            return
        threading.Thread(
            target=self._run_review_recommendation_worker,
            args=(params, cancel_event),
            daemon=True,
            name="review-recommendation",
        ).start()

    def _run_review_recommendation_worker(self, params: Dict[str, Any], cancel_event: threading.Event) -> None:
        client = None
        try:
            if cancel_event.is_set():
                raise ReviewRecommendationCancelledError("Recommendation cancelled")
            client = create_backend(params["backend"])
            self._bind_active_review_recommendation_client(client)
            if cancel_event.is_set():
                self._request_active_review_recommendation_cancel()
                raise ReviewRecommendationCancelledError("Recommendation cancelled")
            result = recommend_review_types(
                path=params["path"],
                scope=params["scope"],
                diff_file=params["diff_file"],
                commits=params["commits"],
                target_lang=params["target_lang"],
                client=client,
                selected_files=params.get("selected_files"),
                diff_filter_file=params.get("diff_filter_file"),
                diff_filter_commits=params.get("diff_filter_commits"),
                cancel_check=cancel_event.is_set,
            )
            if cancel_event.is_set():
                raise ReviewRecommendationCancelledError("Recommendation cancelled")
            if self._testing_mode:
                self._apply_review_recommendation(result)
            else:
                self._dispatch_review_ui(self._apply_review_recommendation, result)
        except ReviewRecommendationCancelledError:
            logger.info("Review type recommendation cancelled")
            if self._testing_mode:
                self._handle_review_recommendation_cancelled()
            else:
                self._dispatch_review_ui(self._handle_review_recommendation_cancelled)
        except Exception as exc:
            if cancel_event.is_set():
                logger.info("Review type recommendation cancelled during backend shutdown")
                if self._testing_mode:
                    self._handle_review_recommendation_cancelled()
                else:
                    self._dispatch_review_ui(self._handle_review_recommendation_cancelled)
                return
            logger.warning("Failed to generate review recommendation: %s", exc)
            if self._testing_mode:
                self._handle_review_recommendation_failure(exc)
            else:
                self._dispatch_review_ui(self._handle_review_recommendation_failure, exc)
        finally:
            if client is not None and hasattr(client, "close"):
                try:
                    client.close()
                except Exception:
                    pass
            self._clear_active_review_recommendation_tracking(cancel_event)

    def _handle_review_recommendation_cancelled(self) -> None:
        self.review_recommendation_label.configure(text=t("gui.review.recommendation_cancelled"))
        self.status_var.set(t("gui.val.cancelled"))
        self._show_toast(t("gui.review.recommendation_cancelled_short"), error=False)
        self._set_review_recommendation_running(False)

    def _handle_review_recommendation_failure(self, exc: Exception) -> None:
        self._set_review_recommendation_running(False)
        self.review_recommendation_label.configure(
            text=t("gui.review.recommendation_failed", error=exc)
        )
        self.status_var.set(t("gui.review.recommendation_failed_short"))
        self._show_toast(t("gui.review.recommendation_failed_short"), error=True)

    def _apply_review_recommendation(self, result: ReviewRecommendationResult) -> None:
        selected_types = set(result.review_types)
        for key, var in self.type_vars.items():
            var.set(key in selected_types)
        self._sync_review_preset_ui(result.recommended_preset)
        self._sync_review_pinning_controls()

        summary_lines = []
        if result.recommended_preset:
            summary_lines.append(
                t(
                    "gui.review.recommendation_summary_preset",
                    preset=result.recommended_preset,
                    types=", ".join(result.review_types),
                )
            )
        else:
            summary_lines.append(
                t("gui.review.recommendation_summary", types=", ".join(result.review_types))
            )
        if result.project_signals:
            summary_lines.append(
                t("gui.review.recommendation_signals", signals="; ".join(result.project_signals))
            )
        for item in result.rationale:
            summary_lines.append(f"- {item.review_type}: {item.reason}")
        self.review_recommendation_label.configure(text="\n".join(summary_lines))
        self.status_var.set(t("gui.review.recommendation_applied"))
        self._show_toast(t("gui.review.recommendation_applied"), error=False)
        self._set_review_recommendation_running(False)

    def _cancel_operation(self):
        if self._is_health_check_running():
            self._cancel_active_health_check_timer()
            self._finish_active_health_check()
            self._stop_health_countdown()
            self._set_action_buttons_state("normal")
            self.status_var.set(t("gui.val.cancelled"))
        elif self._is_review_recommendation_running():
            self._request_active_review_recommendation_cancel()
            self.review_recommendation_label.configure(text=t("gui.review.recommendation_cancelling"))
            self.status_var.set(t("gui.review.recommendation_cancelling"))
        elif self._is_review_execution_running():
            active_snapshot = self._review_execution_scheduler_handle().get_active_submission_snapshot()
            cancelled = False
            if active_snapshot is not None:
                try:
                    cancelled = self._review_execution_scheduler_handle().cancel_submission(active_snapshot.submission_id)
                except Exception as exc:
                    logger.warning("Failed to cancel active review submission %s: %s", active_snapshot.submission_id, exc)
            elif active_snapshot is None:
                try:
                    self._review_controller().request_cancel()
                    cancelled = True
                except Exception as exc:
                    logger.warning("Failed to cancel backend: %s", exc)
            if cancelled:
                self.status_var.set(t("gui.val.cancellation_requested"))
            self._review_submission_queue.on_submission_sync_requested()
        self._sync_global_cancel_button()

    def _selected_file_count_text(self, count: int) -> str:
        """Return the localized selected-file count summary."""
        return t("gui.review.selected_file_count", count=count)

    def _release_review_client(self) -> None:
        self._review_controller().release_client()

    # ── Health-check countdown ticker ─────────────────────────────────────

    _HEALTH_TIMEOUT_SECS = 60

    def _start_health_countdown(self) -> None:
        controller = self._health_check_controller()
        if controller.countdown_after_id is not None:
            self.after_cancel(controller.countdown_after_id)
            controller.bind_countdown_after(None)
        controller.start_countdown(ends_at=time.monotonic() + self._HEALTH_TIMEOUT_SECS)
        self._tick_health_countdown()

    def _tick_health_countdown(self) -> None:
        controller = self._health_check_controller()
        if controller.countdown_ends_at is None:
            return
        remaining = max(0, int(controller.countdown_ends_at - time.monotonic()))
        self._health_countdown_lbl.configure(text=f"⏱ {remaining}s")
        if remaining > 0:
            schedule_after = getattr(self, "_schedule_app_after", self.after)
            controller.bind_countdown_after(schedule_after(1000, self._tick_health_countdown))
        else:
            controller.bind_countdown_after(None)

    def _stop_health_countdown(self) -> None:
        controller = self._health_check_controller()
        if controller.countdown_after_id is not None:
            self.after_cancel(controller.countdown_after_id)
        controller.clear_countdown()
        self._health_countdown_lbl.configure(text="")

    # ── Elapsed-time ticker ────────────────────────────────────────────────

    def _start_elapsed_timer(self) -> None:
        controller = self._review_controller()
        if controller.elapsed_after_id is not None:
            self.after_cancel(controller.elapsed_after_id)
            controller.bind_elapsed_after(None)
        controller.start_elapsed(time.monotonic())
        self._elapsed_lbl.configure(text="0:00")
        self._tick_elapsed()

    def _tick_elapsed(self) -> None:
        controller = self._review_controller()
        if not self._is_review_execution_running() or controller.elapsed_started_at is None:
            return
        elapsed = int(time.monotonic() - controller.elapsed_started_at)
        m, s = divmod(elapsed, 60)
        self._elapsed_lbl.configure(text=f"{m}:{s:02d}")
        schedule_after = getattr(self, "_schedule_app_after", self.after)
        controller.bind_elapsed_after(schedule_after(1000, self._tick_elapsed))

    def _stop_elapsed_timer(self) -> None:
        controller = self._review_controller()
        if controller.elapsed_after_id is not None:
            self.after_cancel(controller.elapsed_after_id)
        controller.clear_elapsed()
        self._elapsed_lbl.configure(text="")

    def _make_gui_review_event_sink(self) -> CallbackEventSink:
        """Return a Tk-safe execution event sink for review progress."""
        facade = self._review_execution_facade_handle()
        schedule_after = getattr(self, "_schedule_app_after", self.after)
        return facade.build_event_sink(
            lambda fraction, status_text: schedule_after(
                0,
                lambda f=fraction, s=status_text: (
                    self.progress.set(f) if f > 0 else None,
                    self.status_var.set(s),
                ),
            )
        )

    def _run_review(self, params: Dict[str, Any], dry_run: bool):
        """Execute the review in a background thread."""
        self._review_submission_queue.on_submission_sync_requested()
        self._sync_review_submission_controls()
        started_submission_id: dict[str, str | None] = {"value": None}

        request = ReviewRequest(
            path=params.get("path"),
            scope=str(params.get("scope") or "project"),
            diff_file=params.get("diff_file"),
            commits=params.get("commits"),
            review_types=list(params.get("review_types") or []),
            spec_content=params.get("spec_content"),
            target_lang=str(params.get("target_lang") or "en"),
            backend_name=str(params.get("backend") or "bedrock"),
            programmers=list(params.get("programmers") or []),
            reviewers=list(params.get("reviewers") or []),
            dry_run=dry_run,
        )

        def _execute_run(job: ReviewJob, cancel_event: threading.Event, event_sink: CallbackEventSink) -> Any:
            facade = self._review_execution_facade_handle()
            coordinator = self._review_execution_coordinator()
            run_params = dict(params)
            backend_name = str(run_params.get("backend") or "bedrock")
            selected_files = cast(Optional[list[str]], run_params.get("selected_files"))
            diff_filter_file = cast(Optional[str], run_params.get("diff_filter_file"))
            diff_filter_commits = cast(Optional[str], run_params.get("diff_filter_commits"))
            schedule_after = getattr(self, "_schedule_app_after", self.after)
            publish_status = lambda status_text: schedule_after(0, lambda s=status_text: self.status_var.set(s))

            client = None
            if not dry_run:
                client = coordinator.activate_client(backend_name, create_backend, publish_status)

            scan_fn = facade.build_scan_function(
                directory=cast(Optional[str], run_params.get("path")),
                selected_files=selected_files,
                diff_filter_file=diff_filter_file,
                diff_filter_commits=diff_filter_commits,
                scan_project_with_scope_fn=scan_project_with_scope,
                get_diff_from_commits_fn=get_diff_from_commits,
                parse_diff_file_fn=parse_diff_file,
            )
            runner = self._build_review_runner(
                client,
                scan_fn=scan_fn,
                backend_name=backend_name,
            )
            if self._runner_uses_execution_service(runner):
                result = runner.execution_service.execute_job(
                    job,
                    client,
                    sink=event_sink,
                    cancel_check=cancel_event.is_set,
                )
                runner._set_execution_result(result, job=job)
                if result.status == "issues_found":
                    return coordinator.classify_run_result(
                        dry_run=dry_run,
                        result=list(result.issues),
                        runner=runner,
                        cancel_requested=False,
                    )
                return coordinator.classify_run_result(
                    dry_run=dry_run,
                    result=None,
                    runner=runner,
                    cancel_requested=False,
                )
            result = runner.run(
                **run_params,
                dry_run=dry_run,
                event_sink=event_sink,
                interactive=False,
                cancel_check=cancel_event.is_set,
            )
            return coordinator.classify_run_result(
                dry_run=dry_run,
                result=result,
                runner=runner,
                cancel_requested=cancel_event.is_set(),
            )

        def _handle_outcome(outcome: Any) -> None:
            schedule_after = getattr(self, "_schedule_app_after", self.after)
            if started_submission_id["value"] is None and outcome.kind == "cancelled":
                return
            if outcome.kind == "cancelled":
                logger.info(t("gui.val.cancelled"))
                schedule_after(0, lambda: self.status_var.set(t("gui.val.cancelled")))
            elif outcome.kind == "dry_run_complete":
                schedule_after(0, lambda: self._show_dry_run_complete())
            elif outcome.kind == "issues_found":
                issues = outcome.issues or []
                self._issues = issues
                self._bind_session_runner(outcome.runner)
                schedule_after(0, lambda result_issues=issues: self._show_issues(result_issues))
            elif outcome.kind == "no_report":
                schedule_after(0, lambda: self.status_var.set(t("gui.val.no_report")))

        def _handle_error(exc: Exception) -> None:
            logger.error("Review failed: %s", exc)
            if not self._testing_mode:
                error_text = str(exc)
                schedule_after = getattr(self, "_schedule_app_after", self.after)
                schedule_after(0, lambda e=error_text: messagebox.showerror(t("common.error"), e))

        def _handle_started(submission: Any) -> None:
            started_submission_id["value"] = getattr(submission, "submission_id", None)
            schedule_after = getattr(self, "_schedule_app_after", self.after)
            schedule_after(0, lambda: self.progress.set(0))
            schedule_after(0, lambda: self.status_var.set(t("common.running")))
            schedule_after(0, self._start_elapsed_timer)
            schedule_after(0, self._sync_global_cancel_button)
            schedule_after(
                0,
                self._review_submission_queue.on_submission_sync_requested,
            )
            schedule_after(0, self._sync_review_submission_controls)

        def _handle_finished() -> None:
            schedule_after = getattr(self, "_schedule_app_after", self.after)
            if started_submission_id["value"] is not None:
                schedule_after(0, self._stop_elapsed_timer)
                schedule_after(0, lambda: self.progress.set(1.0))
            schedule_after(0, self._sync_global_cancel_button)
            schedule_after(
                0,
                self._review_submission_queue.on_submission_sync_requested,
            )
            schedule_after(0, self._sync_review_submission_controls)

        submission = self._review_execution_scheduler_handle().submit_run(
            request=request,
            submission_kind="dry_run" if dry_run else "review",
            execute_run=_execute_run,
            on_started=_handle_started,
            on_outcome=_handle_outcome,
            on_error=_handle_error,
            on_finished=_handle_finished,
        )
        if submission.status == "queued":
            self.status_var.set(
                t(
                    "gui.review.queue_submitted",
                    kind=t(f"gui.review.queue_kind_{submission.submission_kind}"),
                    submission_id=submission.submission_id,
                )
            )
        self._review_submission_queue.on_submission_sync_requested()
        self._sync_review_submission_controls()

    def _show_dry_run_complete(self):
        self.status_var.set(t("gui.val.dry_run_done"))
        self.tabs.set(t("gui.tab.log"))
