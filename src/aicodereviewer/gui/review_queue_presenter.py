"""Presentation helpers for the Review tab's queue panel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from aicodereviewer.i18n import t

from .review_execution_scheduler import ReviewExecutionSubmissionSnapshot


@dataclass(frozen=True)
class ReviewSubmissionQueueViewState:
    """Computed queue-panel presentation state for one scheduler snapshot set."""

    ordered_snapshots: tuple[ReviewExecutionSubmissionSnapshot, ...]
    labels: tuple[str, ...]
    label_to_submission_id: dict[str, str]
    selected_label: str
    summary_text: str
    detail_text: str
    cancel_enabled: bool


class ReviewSubmissionQueuePresenter:
    """Build localized queue-panel presentation from scheduler snapshots."""

    def order_snapshots(
        self,
        snapshots: Iterable[ReviewExecutionSubmissionSnapshot],
    ) -> tuple[ReviewExecutionSubmissionSnapshot, ...]:
        """Return queue snapshots in UI display order."""
        return tuple(sorted(snapshots, key=self._sort_key))

    def build_view_state(
        self,
        snapshots: Iterable[ReviewExecutionSubmissionSnapshot],
        *,
        selected_submission_id: str | None,
    ) -> ReviewSubmissionQueueViewState | None:
        """Build the queue-panel view state for the given snapshots and selection."""
        ordered_snapshots = self.order_snapshots(snapshots)
        if not ordered_snapshots:
            return None

        labels = tuple(self._format_label(snapshot) for snapshot in ordered_snapshots)
        label_to_submission_id = {
            label: snapshot.submission_id for label, snapshot in zip(labels, ordered_snapshots)
        }
        selected_snapshot = next(
            (
                snapshot
                for snapshot in ordered_snapshots
                if snapshot.submission_id == selected_submission_id
            ),
            ordered_snapshots[0],
        )
        selected_label = next(
            label
            for label, snapshot in zip(labels, ordered_snapshots)
            if snapshot.submission_id == selected_snapshot.submission_id
        )
        active_count = sum(1 for snapshot in ordered_snapshots if snapshot.is_active)
        queued_count = sum(1 for snapshot in ordered_snapshots if snapshot.status == "queued")
        recent_count = sum(1 for snapshot in ordered_snapshots if self._is_terminal(snapshot))
        if self._is_terminal(selected_snapshot):
            cancel_state = t("gui.review.queue_cancel_unavailable")
        else:
            cancel_state = t(
                "gui.review.queue_cancel_requested"
                if selected_snapshot.cancel_requested
                else "gui.review.queue_cancel_available"
            )
        if selected_snapshot.is_active:
            detail_key = "gui.review.queue_detail_selected_active"
        elif self._is_terminal(selected_snapshot):
            detail_key = "gui.review.queue_detail_selected_recent"
        else:
            detail_key = "gui.review.queue_detail_selected_queued"
        detail_text = t(
            detail_key,
            submission_id=selected_snapshot.submission_id,
            kind=self._localized_kind(selected_snapshot.submission_kind),
            status=self._localized_status(selected_snapshot.status),
            cancel_state=cancel_state,
        )
        return ReviewSubmissionQueueViewState(
            ordered_snapshots=ordered_snapshots,
            labels=labels,
            label_to_submission_id=label_to_submission_id,
            selected_label=selected_label,
            summary_text=t("gui.review.queue_summary", active=active_count, queued=queued_count, recent=recent_count),
            detail_text=detail_text,
            cancel_enabled=selected_snapshot.status in {"queued", "running"},
        )

    def _sort_key(self, snapshot: ReviewExecutionSubmissionSnapshot) -> tuple[int, int, str]:
        """Return the queue-panel display ordering key for one snapshot."""
        completed_at = snapshot.completed_at or datetime.min
        return (
            0 if snapshot.is_active else (2 if self._is_terminal(snapshot) else 1),
            0 if snapshot.submission_kind == "review" else 1,
            -int(completed_at.timestamp()) if self._is_terminal(snapshot) else 0,
            str(snapshot.submission_id),
        )

    def _format_label(self, snapshot: ReviewExecutionSubmissionSnapshot) -> str:
        """Return the localized option-menu label for one queue snapshot."""
        return t(
            "gui.review.queue_entry_label",
            badge=self._localized_badge(snapshot.submission_kind),
            submission_id=snapshot.submission_id,
            status=self._localized_status(snapshot.status),
            role=self._localized_role(snapshot),
        )

    def _localized_status(self, status: str) -> str:
        return t(f"gui.review.queue_status_{status}")

    def _localized_kind(self, submission_kind: str) -> str:
        return t(f"gui.review.queue_kind_{submission_kind}")

    def _localized_badge(self, submission_kind: str) -> str:
        return t(f"gui.review.queue_badge_{submission_kind}")

    def _localized_role(self, snapshot: ReviewExecutionSubmissionSnapshot) -> str:
        if snapshot.is_active:
            return t("gui.review.queue_role_active")
        if self._is_terminal(snapshot):
            return t("gui.review.queue_role_recent")
        return t("gui.review.queue_role_queued")

    @staticmethod
    def _is_terminal(snapshot: ReviewExecutionSubmissionSnapshot) -> bool:
        return snapshot.status in {"completed", "cancelled", "failed"}