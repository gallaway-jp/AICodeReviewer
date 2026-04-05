"""Widget-construction helpers for the Review tab's queue panel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.i18n import t

from .review_execution_scheduler import ReviewExecutionScheduler
from .review_queue_actions import (
    ReviewSubmissionQueueCancelEffect,
    make_cancel_selected_review_submission_callback,
)
from .review_runtime import ReviewSubmissionSelectionController


@dataclass(frozen=True)
class ReviewSubmissionQueuePanelWidgets:
    """Bundle of widgets owned by the Review tab queue panel."""

    frame: Any
    summary_label: Any
    variable: Any
    menu: Any
    detail_label: Any
    cancel_button: Any


@dataclass(frozen=True)
class ReviewSubmissionQueueCallbacks:
    """Queue panel callbacks bound by the Review tab builder."""

    on_selected: Callable[[str], None]
    on_cancel_selected: Callable[[], None]


def make_review_submission_queue_callbacks(
    *,
    on_selected: Callable[[str], None],
    scheduler: ReviewExecutionScheduler,
    selection: ReviewSubmissionSelectionController,
    set_status_text: Callable[[str], None],
    on_cancel_effect: Callable[[ReviewSubmissionQueueCancelEffect], None],
    sync_global_cancel: Callable[[], None],
) -> ReviewSubmissionQueueCallbacks:
    """Bundle queue selection and cancellation callbacks for the queue panel."""
    return ReviewSubmissionQueueCallbacks(
        on_selected=on_selected,
        on_cancel_selected=make_cancel_selected_review_submission_callback(
            scheduler=scheduler,
            selection=selection,
            set_status_text=set_status_text,
            on_cancel_effect=on_cancel_effect,
            sync_global_cancel=sync_global_cancel,
        ),
    )

def build_review_submission_queue_panel(
    *,
    parent: Any,
    row: int,
    section_surface: Any,
    section_border: Any,
    muted_text: Any,
    on_selected: Callable[[str], None],
    on_cancel_selected: Callable[[], None],
) -> ReviewSubmissionQueuePanelWidgets:
    """Create and lay out the Review tab queue panel widgets."""
    queue_frame = ctk.CTkFrame(parent, fg_color=section_surface, border_width=1, border_color=section_border)
    queue_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=(6, 0))
    queue_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(
        queue_frame,
        text=t("gui.review.queue_title"),
        font=ctk.CTkFont(size=14, weight="bold"),
        anchor="w",
    ).grid(row=0, column=0, padx=10, pady=(8, 0), sticky="w")
    summary_label = ctk.CTkLabel(
        queue_frame,
        text=t("gui.review.queue_empty"),
        anchor="e",
        text_color=muted_text,
        font=ctk.CTkFont(size=11),
    )
    summary_label.grid(row=0, column=1, padx=(8, 10), pady=(8, 0), sticky="e")
    variable = ctk.StringVar(value=t("gui.review.queue_empty"))
    menu = ctk.CTkOptionMenu(
        queue_frame,
        variable=variable,
        values=[t("gui.review.queue_empty")],
        command=on_selected,
        state="disabled",
        width=260,
    )
    menu.grid(row=1, column=0, padx=10, pady=8, sticky="w")
    detail_label = ctk.CTkLabel(
        queue_frame,
        text=t("gui.review.queue_detail_idle"),
        anchor="w",
        justify="left",
        text_color=muted_text,
        font=ctk.CTkFont(size=11),
    )
    detail_label.grid(row=1, column=1, padx=(4, 10), pady=8, sticky="ew")
    cancel_button = ctk.CTkButton(
        queue_frame,
        text=t("gui.review.queue_cancel_selected"),
        width=130,
        state="disabled",
        command=on_cancel_selected,
    )
    cancel_button.grid(row=1, column=2, padx=(0, 10), pady=8)
    return ReviewSubmissionQueuePanelWidgets(
        frame=queue_frame,
        summary_label=summary_label,
        variable=variable,
        menu=menu,
        detail_label=detail_label,
        cancel_button=cancel_button,
    )