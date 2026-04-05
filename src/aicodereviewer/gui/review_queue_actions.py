"""Queue-oriented GUI action helpers for review submissions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from aicodereviewer.i18n import t

from .review_execution_scheduler import ReviewExecutionScheduler
from .review_runtime import ReviewSubmissionSelectionController


@dataclass(frozen=True)
class ReviewSubmissionQueueCancelEffect:
    """Side effects to apply after attempting queue-targeted cancellation."""

    status_text: str | None = None
    refresh_queue: bool = False
    sync_global_cancel: bool = False


def apply_review_submission_cancel_effect(
    *,
    effect: ReviewSubmissionQueueCancelEffect,
    set_status_text: Callable[[str], None],
    on_cancel_effect: Callable[[ReviewSubmissionQueueCancelEffect], None],
    sync_global_cancel: Callable[[], None],
) -> None:
    """Apply the UI work implied by a queue-targeted cancellation effect."""
    if effect.status_text is not None:
        set_status_text(effect.status_text)
    on_cancel_effect(effect)
    if effect.sync_global_cancel:
        sync_global_cancel()


def cancel_selected_review_submission_and_apply(
    *,
    scheduler: ReviewExecutionScheduler,
    selection: ReviewSubmissionSelectionController,
    set_status_text: Callable[[str], None],
    on_cancel_effect: Callable[[ReviewSubmissionQueueCancelEffect], None],
    sync_global_cancel: Callable[[], None],
) -> None:
    """Cancel the selected submission and apply the resulting queue UI effects."""
    effect = cancel_selected_review_submission(
        scheduler=scheduler,
        selection=selection,
    )
    apply_review_submission_cancel_effect(
        effect=effect,
        set_status_text=set_status_text,
        on_cancel_effect=on_cancel_effect,
        sync_global_cancel=sync_global_cancel,
    )


def make_cancel_selected_review_submission_callback(
    *,
    scheduler: ReviewExecutionScheduler,
    selection: ReviewSubmissionSelectionController,
    set_status_text: Callable[[str], None],
    on_cancel_effect: Callable[[ReviewSubmissionQueueCancelEffect], None],
    sync_global_cancel: Callable[[], None],
) -> Callable[[], None]:
    """Return a zero-argument callback that cancels the selected queue item."""

    def _callback() -> None:
        cancel_selected_review_submission_and_apply(
            scheduler=scheduler,
            selection=selection,
            set_status_text=set_status_text,
            on_cancel_effect=on_cancel_effect,
            sync_global_cancel=sync_global_cancel,
        )

    return _callback


def cancel_selected_review_submission(
    *,
    scheduler: ReviewExecutionScheduler,
    selection: ReviewSubmissionSelectionController,
) -> ReviewSubmissionQueueCancelEffect:
    """Cancel the currently selected submission and describe the resulting UI effects."""
    submission_id = selection.submission_id
    if submission_id is None:
        return ReviewSubmissionQueueCancelEffect()

    snapshot = scheduler.get_submission_snapshot(submission_id)
    if snapshot is None:
        return ReviewSubmissionQueueCancelEffect(refresh_queue=True)

    if not scheduler.cancel_submission(submission_id):
        return ReviewSubmissionQueueCancelEffect(refresh_queue=True)

    if snapshot.is_active:
        status_text = t("gui.val.cancellation_requested")
    else:
        status_text = t("gui.review.queue_cancelled", submission_id=submission_id)

    return ReviewSubmissionQueueCancelEffect(
        status_text=status_text,
        refresh_queue=True,
        sync_global_cancel=True,
    )