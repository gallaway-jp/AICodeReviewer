from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aicodereviewer.i18n import t
from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionSubmissionSnapshot
from aicodereviewer.gui.review_queue_presenter import ReviewSubmissionQueuePresenter


def _snapshot(
    submission_id: int,
    *,
    submission_kind: str = "review",
    status: str = "queued",
    cancel_requested: bool = False,
    is_active: bool = False,
    thread_attached: bool = False,
    completed_at: datetime | None = None,
) -> ReviewExecutionSubmissionSnapshot:
    return ReviewExecutionSubmissionSnapshot(
        submission_id=submission_id,
        submission_kind=submission_kind,
        status=status,
        cancel_requested=cancel_requested,
        is_active=is_active,
        thread_attached=thread_attached,
        completed_at=completed_at,
    )


def test_review_submission_queue_presenter_returns_none_for_empty_snapshots() -> None:
    presenter = ReviewSubmissionQueuePresenter()

    assert presenter.build_view_state((), selected_submission_id=None) is None


def test_review_submission_queue_presenter_falls_back_to_first_ordered_snapshot_for_stale_selection() -> None:
    presenter = ReviewSubmissionQueuePresenter()
    active_review = _snapshot(2, status="running", is_active=True, thread_attached=True)
    queued_dry_run = _snapshot(3, submission_kind="dry_run")

    view_state = presenter.build_view_state(
        (queued_dry_run, active_review),
        selected_submission_id=999,
    )

    assert view_state is not None
    assert tuple(snapshot.submission_id for snapshot in view_state.ordered_snapshots) == (2, 3)
    assert view_state.label_to_submission_id[view_state.selected_label] == 2
    assert view_state.summary_text == t("gui.review.queue_summary", active=1, queued=1, recent=0)
    assert view_state.detail_text == t(
        "gui.review.queue_detail_selected_active",
        submission_id=2,
        kind=t("gui.review.queue_kind_review"),
        status=t("gui.review.queue_status_running"),
        cancel_state=t("gui.review.queue_cancel_available"),
    )
    assert view_state.cancel_enabled is True


def test_review_submission_queue_presenter_orders_recent_terminal_snapshots_after_active_and_queued() -> None:
    presenter = ReviewSubmissionQueuePresenter()
    now = datetime.now()
    active_review = _snapshot(2, status="running", is_active=True, thread_attached=True)
    queued_review = _snapshot(3, status="queued")
    recent_failed = _snapshot(4, status="failed", completed_at=now - timedelta(minutes=1))
    recent_completed = _snapshot(5, status="completed", completed_at=now)

    view_state = presenter.build_view_state(
        (recent_failed, queued_review, recent_completed, active_review),
        selected_submission_id=5,
    )

    assert view_state is not None
    assert tuple(snapshot.submission_id for snapshot in view_state.ordered_snapshots) == (2, 3, 5, 4)
    assert view_state.summary_text == t("gui.review.queue_summary", active=1, queued=1, recent=2)
    assert view_state.detail_text == t(
        "gui.review.queue_detail_selected_recent",
        submission_id=5,
        kind=t("gui.review.queue_kind_review"),
        status=t("gui.review.queue_status_completed"),
        cancel_state=t("gui.review.queue_cancel_unavailable"),
    )
    assert view_state.cancel_enabled is False