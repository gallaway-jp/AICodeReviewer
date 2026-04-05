"""Queue-panel coordination helpers for review submission UI state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .review_queue_actions import ReviewSubmissionQueueCancelEffect
from .review_queue_panel import ReviewSubmissionQueuePanelWidgets
from .review_queue_presenter import ReviewSubmissionQueuePresenter
from .review_execution_scheduler import ReviewExecutionScheduler
from .review_runtime import ReviewSubmissionSelectionController
from aicodereviewer.i18n import t


@dataclass
class ReviewSubmissionQueueCoordinator:
    """Coordinate queue selection and refresh timing above scheduler snapshots."""

    scheduler: ReviewExecutionScheduler
    presenter: ReviewSubmissionQueuePresenter
    selection: ReviewSubmissionSelectionController
    _widgets: ReviewSubmissionQueuePanelWidgets | None = field(default=None, init=False, repr=False)

    def bind_widgets(
        self,
        widgets: ReviewSubmissionQueuePanelWidgets,
    ) -> None:
        """Bind the queue-panel widgets used to render computed view state."""
        self._widgets = widgets

    def on_queue_panel_ready(self) -> None:
        """Build the initial queue-panel state once widgets exist."""
        self._refresh()

    def on_queue_selection_changed(
        self,
        selected_label: str,
    ) -> None:
        """Update selection from the queue panel and refresh the visible state."""
        self.selection.select_label(selected_label)
        self._refresh()

    def on_submission_sync_requested(self) -> None:
        """Refresh the queue panel after a submission lifecycle event."""
        self._refresh()

    def on_cancel_effect(self, effect: ReviewSubmissionQueueCancelEffect) -> None:
        """Refresh the queue panel when a queue cancellation effect requires it."""
        if effect.refresh_queue:
            self._refresh()

    def _refresh(self) -> None:
        """Recompute and apply queue-panel state from scheduler snapshots."""
        if self._widgets is None:
            return
        snapshots = list(
            self.presenter.order_snapshots(
                self.scheduler.list_submission_snapshots()
            )
        )
        selected_snapshot = self.selection.sync_snapshots(snapshots)
        view_state = self.presenter.build_view_state(
            snapshots,
            selected_submission_id=(selected_snapshot.submission_id if selected_snapshot else None),
        )
        self._apply_view_state(view_state)

    def _apply_view_state(self, view_state: Any | None) -> None:
        """Apply one computed queue-panel view state onto the bound widgets."""
        if self._widgets is None:
            return
        if view_state is None:
            self.selection.bind_labels({})
            empty_text = t("gui.review.queue_empty")
            self._widgets.menu.configure(values=[empty_text], state="disabled")
            self._widgets.variable.set(empty_text)
            self._widgets.summary_label.configure(text=empty_text)
            self._widgets.detail_label.configure(text=t("gui.review.queue_detail_idle"))
            self._widgets.cancel_button.configure(state="disabled")
            return

        self.selection.bind_labels(view_state.label_to_submission_id)
        self._widgets.menu.configure(values=list(view_state.labels), state="normal")
        self._widgets.variable.set(view_state.selected_label)
        self._widgets.summary_label.configure(text=view_state.summary_text)
        self._widgets.detail_label.configure(text=view_state.detail_text)
        self._widgets.cancel_button.configure(
            state="normal" if view_state.cancel_enabled else "disabled"
        )