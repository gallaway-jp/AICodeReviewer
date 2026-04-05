from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aicodereviewer.i18n import t
from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionSubmissionSnapshot
from aicodereviewer.gui.review_queue_actions import (
    ReviewSubmissionQueueCancelEffect,
    apply_review_submission_cancel_effect,
    cancel_selected_review_submission,
    cancel_selected_review_submission_and_apply,
    make_cancel_selected_review_submission_callback,
)
from aicodereviewer.gui.review_queue_panel import (
    ReviewSubmissionQueueCallbacks,
    make_review_submission_queue_callbacks,
)
from aicodereviewer.gui.review_runtime import ReviewSubmissionSelectionController


def _snapshot(
    submission_id: int,
    *,
    submission_kind: str = "review",
    status: str = "queued",
    cancel_requested: bool = False,
    is_active: bool = False,
    thread_attached: bool = False,
) -> ReviewExecutionSubmissionSnapshot:
    return ReviewExecutionSubmissionSnapshot(
        submission_id=submission_id,
        submission_kind=submission_kind,
        status=status,
        cancel_requested=cancel_requested,
        is_active=is_active,
        thread_attached=thread_attached,
    )


def test_cancel_selected_review_submission_returns_no_effect_without_selection() -> None:
    scheduler = SimpleNamespace(
        get_submission_snapshot=lambda _submission_id: None,
        cancel_submission=lambda _submission_id: False,
    )
    selection = ReviewSubmissionSelectionController(submission_id=None)

    effect = cancel_selected_review_submission(
        scheduler=scheduler,
        selection=selection,
    )

    assert effect == ReviewSubmissionQueueCancelEffect()


def test_cancel_selected_review_submission_requests_refresh_for_stale_selection() -> None:
    scheduler = SimpleNamespace(
        get_submission_snapshot=lambda _submission_id: None,
        cancel_submission=lambda _submission_id: False,
    )
    selection = ReviewSubmissionSelectionController(submission_id=7)

    effect = cancel_selected_review_submission(
        scheduler=scheduler,
        selection=selection,
    )

    assert effect == ReviewSubmissionQueueCancelEffect(refresh_queue=True)


def test_cancel_selected_review_submission_requests_refresh_when_cancel_is_rejected() -> None:
    scheduler = SimpleNamespace(
        get_submission_snapshot=lambda submission_id: _snapshot(submission_id, status="queued"),
        cancel_submission=lambda _submission_id: False,
    )
    selection = ReviewSubmissionSelectionController(submission_id=5)

    effect = cancel_selected_review_submission(
        scheduler=scheduler,
        selection=selection,
    )

    assert effect == ReviewSubmissionQueueCancelEffect(refresh_queue=True)


def test_cancel_selected_review_submission_returns_active_cancel_effect() -> None:
    scheduler = SimpleNamespace(
        get_submission_snapshot=lambda submission_id: _snapshot(
            submission_id,
            status="running",
            is_active=True,
            thread_attached=True,
        ),
        cancel_submission=lambda _submission_id: True,
    )
    selection = ReviewSubmissionSelectionController(submission_id=3)

    effect = cancel_selected_review_submission(
        scheduler=scheduler,
        selection=selection,
    )

    assert effect == ReviewSubmissionQueueCancelEffect(
        status_text=t("gui.val.cancellation_requested"),
        refresh_queue=True,
        sync_global_cancel=True,
    )


def test_cancel_selected_review_submission_returns_queued_cancel_effect() -> None:
    scheduler = SimpleNamespace(
        get_submission_snapshot=lambda submission_id: _snapshot(submission_id, status="queued", is_active=False),
        cancel_submission=lambda _submission_id: True,
    )
    selection = ReviewSubmissionSelectionController(submission_id=9)

    effect = cancel_selected_review_submission(
        scheduler=scheduler,
        selection=selection,
    )

    assert effect == ReviewSubmissionQueueCancelEffect(
        status_text=t("gui.review.queue_cancelled", submission_id=9),
        refresh_queue=True,
        sync_global_cancel=True,
    )


def test_apply_review_submission_cancel_effect_updates_status_refresh_and_cancel_sync() -> None:
    status_updates: list[str] = []
    received_effects: list[ReviewSubmissionQueueCancelEffect] = []
    sync_calls: list[str] = []
    effect = ReviewSubmissionQueueCancelEffect(
        status_text="queued cancelled",
        refresh_queue=True,
        sync_global_cancel=True,
    )

    apply_review_submission_cancel_effect(
        effect=effect,
        set_status_text=status_updates.append,
        on_cancel_effect=received_effects.append,
        sync_global_cancel=lambda: sync_calls.append("sync"),
    )

    assert status_updates == ["queued cancelled"]
    assert received_effects == [effect]
    assert sync_calls == ["sync"]


def test_cancel_selected_review_submission_and_apply_delegates_effect_application() -> None:
    scheduler = SimpleNamespace(
        get_submission_snapshot=lambda submission_id: _snapshot(submission_id, status="queued", is_active=False),
        cancel_submission=lambda _submission_id: True,
    )
    selection = ReviewSubmissionSelectionController(submission_id=11)
    status_updates: list[str] = []
    received_effects: list[ReviewSubmissionQueueCancelEffect] = []
    sync_calls: list[str] = []

    cancel_selected_review_submission_and_apply(
        scheduler=scheduler,
        selection=selection,
        set_status_text=status_updates.append,
        on_cancel_effect=received_effects.append,
        sync_global_cancel=lambda: sync_calls.append("sync"),
    )

    assert status_updates == [t("gui.review.queue_cancelled", submission_id=11)]
    assert received_effects == [
        ReviewSubmissionQueueCancelEffect(
            status_text=t("gui.review.queue_cancelled", submission_id=11),
            refresh_queue=True,
            sync_global_cancel=True,
        )
    ]
    assert sync_calls == ["sync"]


def test_make_cancel_selected_review_submission_callback_returns_invokable_callback() -> None:
    scheduler = SimpleNamespace(
        get_submission_snapshot=lambda submission_id: _snapshot(submission_id, status="queued", is_active=False),
        cancel_submission=lambda _submission_id: True,
    )
    selection = ReviewSubmissionSelectionController(submission_id=13)
    status_updates: list[str] = []
    received_effects: list[ReviewSubmissionQueueCancelEffect] = []
    sync_calls: list[str] = []

    callback = make_cancel_selected_review_submission_callback(
        scheduler=scheduler,
        selection=selection,
        set_status_text=status_updates.append,
        on_cancel_effect=received_effects.append,
        sync_global_cancel=lambda: sync_calls.append("sync"),
    )

    callback()

    expected_effect = ReviewSubmissionQueueCancelEffect(
        status_text=t("gui.review.queue_cancelled", submission_id=13),
        refresh_queue=True,
        sync_global_cancel=True,
    )
    assert status_updates == [t("gui.review.queue_cancelled", submission_id=13)]
    assert received_effects == [expected_effect]
    assert sync_calls == ["sync"]


def test_make_review_submission_queue_callbacks_bundles_selection_and_cancel_callbacks() -> None:
    scheduler = SimpleNamespace(
        get_submission_snapshot=lambda submission_id: _snapshot(submission_id, status="queued", is_active=False),
        cancel_submission=lambda _submission_id: True,
    )
    selection = ReviewSubmissionSelectionController(submission_id=17)
    selected_labels: list[str] = []
    status_updates: list[str] = []
    received_effects: list[ReviewSubmissionQueueCancelEffect] = []
    sync_calls: list[str] = []

    callbacks = make_review_submission_queue_callbacks(
        on_selected=selected_labels.append,
        scheduler=scheduler,
        selection=selection,
        set_status_text=status_updates.append,
        on_cancel_effect=received_effects.append,
        sync_global_cancel=lambda: sync_calls.append("sync"),
    )

    assert isinstance(callbacks, ReviewSubmissionQueueCallbacks)

    callbacks.on_selected("Submission 17")
    callbacks.on_cancel_selected()

    expected_effect = ReviewSubmissionQueueCancelEffect(
        status_text=t("gui.review.queue_cancelled", submission_id=17),
        refresh_queue=True,
        sync_global_cancel=True,
    )
    assert selected_labels == ["Submission 17"]
    assert status_updates == [t("gui.review.queue_cancelled", submission_id=17)]
    assert received_effects == [expected_effect]
    assert sync_calls == ["sync"]