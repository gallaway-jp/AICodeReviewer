from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aicodereviewer.i18n import t
from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionSubmissionSnapshot
from aicodereviewer.gui.review_queue_actions import ReviewSubmissionQueueCancelEffect
from aicodereviewer.gui.review_queue_coordinator import ReviewSubmissionQueueCoordinator
from aicodereviewer.gui.review_queue_panel import ReviewSubmissionQueuePanelWidgets
from aicodereviewer.gui.review_queue_presenter import ReviewSubmissionQueuePresenter
from aicodereviewer.gui.review_runtime import ReviewSubmissionSelectionController


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


class _FakeVariable:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class _FakeWidget:
    def __init__(self) -> None:
        self.config: dict[str, object] = {}

    def configure(self, **kwargs: object) -> None:
        self.config.update(kwargs)


def _build_widgets() -> ReviewSubmissionQueuePanelWidgets:
    return ReviewSubmissionQueuePanelWidgets(
        frame=SimpleNamespace(),
        summary_label=_FakeWidget(),
        variable=_FakeVariable(),
        menu=_FakeWidget(),
        detail_label=_FakeWidget(),
        cancel_button=_FakeWidget(),
    )


def test_review_submission_queue_coordinator_applies_selection_change_refresh() -> None:
    scheduler = SimpleNamespace(
        list_submission_snapshots=lambda: (
            _snapshot(1, status="running", is_active=True, thread_attached=True),
            _snapshot(2, status="queued"),
        )
    )
    selection = ReviewSubmissionSelectionController()
    presenter = ReviewSubmissionQueuePresenter()
    coordinator = ReviewSubmissionQueueCoordinator(scheduler, presenter, selection)
    widgets = _build_widgets()

    coordinator.bind_widgets(widgets)

    coordinator.on_queue_panel_ready()
    queued_label = next(
        label for label, submission_id in selection.label_to_submission_id.items() if submission_id == 2
    )

    coordinator.on_queue_selection_changed(queued_label)

    assert selection.submission_id == 2
    assert widgets.variable.value == queued_label
    assert widgets.detail_label.config["text"] == t(
        "gui.review.queue_detail_selected_queued",
        submission_id=2,
        kind=t("gui.review.queue_kind_review"),
        status=t("gui.review.queue_status_queued"),
        cancel_state=t("gui.review.queue_cancel_available"),
    )
    assert widgets.cancel_button.config["state"] == "normal"


def test_review_submission_queue_coordinator_disables_cancel_for_recent_terminal_selection() -> None:
    scheduler = SimpleNamespace(
        list_submission_snapshots=lambda: (
            _snapshot(1, status="completed", completed_at=datetime.now()),
        )
    )
    selection = ReviewSubmissionSelectionController()
    presenter = ReviewSubmissionQueuePresenter()
    coordinator = ReviewSubmissionQueueCoordinator(scheduler, presenter, selection)
    widgets = _build_widgets()

    coordinator.bind_widgets(widgets)
    coordinator.on_queue_panel_ready()

    assert widgets.summary_label.config["text"] == t("gui.review.queue_summary", active=0, queued=0, recent=1)
    assert widgets.detail_label.config["text"] == t(
        "gui.review.queue_detail_selected_recent",
        submission_id=1,
        kind=t("gui.review.queue_kind_review"),
        status=t("gui.review.queue_status_completed"),
        cancel_state=t("gui.review.queue_cancel_available"),
    )
    assert widgets.cancel_button.config["state"] == "disabled"


def test_review_submission_queue_coordinator_refreshes_widgets_only_when_cancel_effect_requires_it() -> None:
    snapshots: list[ReviewExecutionSubmissionSnapshot] = [
        _snapshot(1, status="running", is_active=True, thread_attached=True),
    ]
    scheduler = SimpleNamespace(list_submission_snapshots=lambda: tuple(snapshots))
    selection = ReviewSubmissionSelectionController()
    presenter = ReviewSubmissionQueuePresenter()
    coordinator = ReviewSubmissionQueueCoordinator(scheduler, presenter, selection)
    widgets = _build_widgets()

    coordinator.bind_widgets(widgets)
    coordinator.on_queue_panel_ready()

    running_summary = widgets.summary_label.config["text"]
    snapshots.clear()

    coordinator.on_cancel_effect(ReviewSubmissionQueueCancelEffect(refresh_queue=False))

    assert widgets.summary_label.config["text"] == running_summary
    assert selection.label_to_submission_id

    coordinator.on_cancel_effect(ReviewSubmissionQueueCancelEffect(refresh_queue=True))

    assert widgets.summary_label.config["text"] == t("gui.review.queue_empty")
    assert widgets.variable.value == t("gui.review.queue_empty")
    assert widgets.menu.config["state"] == "disabled"
    assert widgets.detail_label.config["text"] == t("gui.review.queue_detail_idle")
    assert widgets.cancel_button.config["state"] == "disabled"
    assert selection.label_to_submission_id == {}