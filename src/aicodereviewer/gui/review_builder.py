from __future__ import annotations

from typing import Any, List

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.config import config
from aicodereviewer.i18n import t
from aicodereviewer.registries import get_backend_registry, get_review_registry
from aicodereviewer.review_presets import (
    REVIEW_TYPE_PRESETS,
    format_review_preset_picker_label,
    infer_review_type_preset,
    get_review_type_label,
)

from .review_queue_panel import build_review_submission_queue_panel, make_review_submission_queue_callbacks
from .shared_ui import add_section_header, build_autohide_scroller
from .widgets import InfoTooltip, _Tooltip


class ReviewTabBuilder:
    def __init__(self, host: Any) -> None:
        self.host = host

    def build(self) -> None:
        tab = self.host.tabs.add(t("gui.tab.review"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        review_scroll_frame, review_content, review_scroll_canvas, review_scrollbar = build_autohide_scroller(
            self.host,
            tab,
        )
        review_scroll_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        review_content.grid_columnconfigure(0, weight=1)
        self.host.review_scroll_frame = review_scroll_frame
        self.host.review_scroll_canvas = review_scroll_canvas
        self.host.review_scrollbar = review_scrollbar
        review_scroll_frame.bind("<Map>", self.host._schedule_review_layout_refresh, add="+")

        row = 0
        row = self._build_intro(review_content, row)
        review_body = self._build_body(review_content, row)
        row = 0
        row = self._build_setup_panel(self.host.review_setup_panel, row)
        self._build_run_panel(self.host.review_run_panel)

        review_scroll_canvas.bind("<Configure>", self.host._schedule_review_layout_refresh, add="+")
        self.host._sync_review_submission_controls()
        self.host._refresh_review_tab_layout()

    def _build_intro(self, parent: Any, row: int) -> int:
        intro = ctk.CTkFrame(
            parent,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        intro.grid(row=row, column=0, sticky="ew", padx=6, pady=(0, 8))
        intro.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            intro,
            text=t("gui.review.header_title"),
            anchor="w",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(
            intro,
            text=t("gui.review.header_subtitle"),
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(2, 10))
        return row + 1

    def _build_body(self, parent: Any, row: int) -> Any:
        review_body = ctk.CTkFrame(parent, fg_color="transparent")
        review_body.grid(row=row, column=0, sticky="ew", padx=6, pady=0)
        review_body.grid_columnconfigure(0, weight=1)
        review_body.grid_rowconfigure(0, weight=0)

        review_setup_panel = ctk.CTkFrame(review_body, fg_color="transparent")
        review_setup_panel.grid_columnconfigure(0, weight=1)
        review_run_panel = ctk.CTkFrame(review_body, fg_color="transparent")
        review_run_panel.grid_columnconfigure(0, weight=1)
        review_layout_divider = ctk.CTkFrame(review_body, fg_color=("#d8e1ee", "#3a404b"))

        self.host.review_body_frame = review_body
        self.host.review_setup_panel = review_setup_panel
        self.host.review_run_panel = review_run_panel
        self.host.review_layout_divider = review_layout_divider
        self.host.review_layout_mode = "stacked"
        return review_body

    def _build_setup_panel(self, parent: Any, row: int) -> int:
        row = add_section_header(
            parent,
            row,
            t("gui.review.section_target_title"),
            t("gui.review.section_target_desc"),
            muted_text=self.host._MUTED_TEXT,
        )
        row = self._build_project_path_section(parent, row)
        row = self._build_scope_section(parent, row)

        row = add_section_header(
            parent,
            row,
            t("gui.review.section_analysis_title"),
            t("gui.review.section_analysis_desc"),
            muted_text=self.host._MUTED_TEXT,
        )
        row = self._build_review_types_section(parent, row)

        row = add_section_header(
            parent,
            row,
            t("gui.review.section_context_title"),
            t("gui.review.section_context_desc"),
            muted_text=self.host._MUTED_TEXT,
        )
        row = self._build_backend_section(parent, row)
        row = self._build_metadata_section(parent, row)
        return row

    def _build_project_path_section(self, parent: Any, row: int) -> int:
        path_frame = ctk.CTkFrame(
            parent,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        path_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=(0, 4))
        path_frame.grid_columnconfigure(2, weight=1)
        InfoTooltip.add(path_frame, t("gui.tip.project_path"), row=0, column=0)
        ctk.CTkLabel(path_frame, text=t("gui.review.project_path")).grid(row=0, column=1, padx=(0, 4))

        saved_path = config.get("gui", "project_path", "").strip()
        self.host.path_entry = ctk.CTkEntry(path_frame, placeholder_text=t("gui.review.placeholder_path"))
        if saved_path:
            self.host.path_entry.insert(0, saved_path)
        self.host.path_entry.grid(row=0, column=2, sticky="ew", padx=4)
        ctk.CTkButton(
            path_frame,
            text=t("common.browse"),
            width=80,
            command=self.host._browse_path,
        ).grid(row=0, column=3, padx=6)
        ctk.CTkLabel(
            path_frame,
            text=t("gui.review.project_path_hint"),
            anchor="w",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=1, columnspan=3, sticky="w", padx=(0, 4), pady=(1, 6))
        return row + 1

    def _build_scope_section(self, parent: Any, row: int) -> int:
        scope_frame = ctk.CTkFrame(
            parent,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        scope_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=3)
        scope_frame.grid_columnconfigure(4, weight=1)
        InfoTooltip.add(scope_frame, t("gui.tip.scope"), row=0, column=0)
        ctk.CTkLabel(scope_frame, text=t("gui.review.scope")).grid(row=0, column=1, padx=(0, 4))
        self.host.scope_var = ctk.StringVar(value="project")
        self.host.scope_var.trace_add("write", self.host._on_scope_changed)
        ctk.CTkRadioButton(
            scope_frame,
            text=t("gui.review.scope_project"),
            variable=self.host.scope_var,
            value="project",
        ).grid(row=0, column=2, padx=6)
        ctk.CTkRadioButton(
            scope_frame,
            text=t("gui.review.scope_diff"),
            variable=self.host.scope_var,
            value="diff",
        ).grid(row=0, column=3, padx=6)
        ctk.CTkLabel(
            scope_frame,
            text=t("gui.review.scope_hint"),
            anchor="e",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=4, padx=(12, 10), sticky="e")

        self.host.file_select_frame = ctk.CTkFrame(scope_frame)
        self.host.file_select_frame.grid(row=1, column=0, columnspan=5, sticky="ew", padx=6, pady=3)
        self.host.file_select_frame.grid_columnconfigure(4, weight=1)
        saved_file_mode = config.get("gui", "file_select_mode", "all")
        self.host.file_select_mode_var = ctk.StringVar(value=saved_file_mode)
        self.host.file_select_mode_var.trace_add("write", self.host._on_file_select_mode_changed)
        ctk.CTkRadioButton(
            self.host.file_select_frame,
            text=t("gui.review.file_mode_all"),
            variable=self.host.file_select_mode_var,
            value="all",
        ).grid(row=0, column=0, padx=6, sticky="w")
        ctk.CTkRadioButton(
            self.host.file_select_frame,
            text=t("gui.review.file_mode_selected"),
            variable=self.host.file_select_mode_var,
            value="selected",
        ).grid(row=0, column=1, padx=6, sticky="w")
        self.host.select_files_btn = ctk.CTkButton(
            self.host.file_select_frame,
            text=t("gui.review.select_files"),
            width=120,
            command=self.host._open_file_selector,
            state="normal" if saved_file_mode == "selected" else "disabled",
        )
        self.host.select_files_btn.grid(row=0, column=2, padx=6, sticky="w")

        saved_files_raw = config.get("gui", "selected_files", "").strip()
        self.host.selected_files = [path for path in saved_files_raw.split("|") if path]
        self.host._file_count_lbl = ctk.CTkLabel(
            self.host.file_select_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        self.host._file_count_lbl.grid(row=0, column=3, padx=(0, 6), sticky="w")
        ctk.CTkLabel(
            self.host.file_select_frame,
            text=t("gui.review.file_select_hint"),
            font=ctk.CTkFont(size=11),
            text_color=self.host._MUTED_TEXT,
            anchor="e",
        ).grid(row=0, column=4, padx=(8, 4), sticky="e")
        if self.host.selected_files:
            self.host._file_count_lbl.configure(
                text=self.host._selected_file_count_text(len(self.host.selected_files))
            )

        self.host.diff_filter_frame = ctk.CTkFrame(scope_frame)
        self.host.diff_filter_frame.grid(row=2, column=0, columnspan=5, sticky="ew", padx=6, pady=3)
        self.host.diff_filter_frame.grid_columnconfigure(3, weight=1)
        self.host.diff_filter_var = ctk.BooleanVar(value=False)
        self.host.diff_filter_var.trace_add("write", self.host._on_diff_filter_changed)
        self.host.diff_filter_cb = ctk.CTkCheckBox(
            self.host.diff_filter_frame,
            text=t("gui.review.diff_filter_toggle"),
            variable=self.host.diff_filter_var,
        )
        self.host.diff_filter_cb.grid(row=0, column=0, columnspan=4, padx=6, pady=(2, 0), sticky="w")
        InfoTooltip.add(self.host.diff_filter_frame, t("gui.tip.diff_file"), row=1, column=0)
        ctk.CTkLabel(self.host.diff_filter_frame, text=t("gui.review.diff_file")).grid(row=1, column=1, padx=4)
        self.host.diff_filter_file_entry = ctk.CTkEntry(
            self.host.diff_filter_frame,
            placeholder_text=t("gui.review.diff_placeholder"),
            state="disabled",
        )
        self.host.diff_filter_file_entry.grid(row=1, column=2, columnspan=2, sticky="ew", padx=4)
        self.host.diff_filter_browse_btn = ctk.CTkButton(
            self.host.diff_filter_frame,
            text="…",
            width=30,
            command=self.host._browse_diff_filter,
            state="disabled",
        )
        self.host.diff_filter_browse_btn.grid(row=1, column=4, padx=4)
        InfoTooltip.add(self.host.diff_filter_frame, t("gui.tip.commits"), row=2, column=0)
        ctk.CTkLabel(self.host.diff_filter_frame, text=t("gui.review.commits")).grid(
            row=2,
            column=1,
            padx=4,
            pady=(3, 0),
        )
        self.host.diff_filter_commits_entry = ctk.CTkEntry(
            self.host.diff_filter_frame,
            placeholder_text=t("gui.review.commits_placeholder"),
            state="disabled",
        )
        self.host.diff_filter_commits_entry.grid(row=2, column=2, columnspan=2, sticky="ew", padx=4, pady=(3, 0))

        self.host.diff_frame = ctk.CTkFrame(scope_frame)
        self.host.diff_frame.grid(row=3, column=0, columnspan=5, sticky="ew", padx=6, pady=3)
        self.host.diff_frame.grid_columnconfigure(2, weight=1)
        InfoTooltip.add(self.host.diff_frame, t("gui.tip.diff_file"), row=0, column=0)
        ctk.CTkLabel(self.host.diff_frame, text=t("gui.review.diff_file")).grid(row=0, column=1, padx=4)
        self.host.diff_file_entry = ctk.CTkEntry(self.host.diff_frame, placeholder_text=t("gui.review.diff_placeholder"))
        self.host.diff_file_entry.grid(row=0, column=2, sticky="ew", padx=4)
        ctk.CTkButton(self.host.diff_frame, text="…", width=30, command=self.host._browse_diff).grid(
            row=0,
            column=3,
            padx=4,
        )
        InfoTooltip.add(self.host.diff_frame, t("gui.tip.commits"), row=1, column=0)
        ctk.CTkLabel(self.host.diff_frame, text=t("gui.review.commits")).grid(
            row=1,
            column=1,
            padx=4,
            pady=(3, 0),
        )
        self.host.commits_entry = ctk.CTkEntry(self.host.diff_frame, placeholder_text=t("gui.review.commits_placeholder"))
        self.host.commits_entry.grid(row=1, column=2, sticky="ew", padx=4, pady=(3, 0))
        self.host.diff_frame.grid_remove()
        return row + 1

    def _build_review_types_section(self, parent: Any, row: int) -> int:
        types_hdr = ctk.CTkFrame(parent, fg_color="transparent")
        types_hdr.grid(row=row, column=0, sticky="w", padx=6, pady=(4, 1))
        InfoTooltip.add(types_hdr, t("gui.tip.review_types"), row=0, column=0)
        ctk.CTkLabel(types_hdr, text=t("gui.review.types_label"), anchor="w").grid(row=0, column=1)
        row += 1

        types_shell = ctk.CTkFrame(
            parent,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        types_shell.grid(row=row, column=0, sticky="ew", padx=6, pady=(0, 4))
        types_shell.grid_columnconfigure(0, weight=1)
        types_shell.grid_rowconfigure(0, weight=1)
        types_scroll_frame, types_frame, types_scroll_canvas, types_scrollbar = build_autohide_scroller(
            self.host,
            types_shell,
            content_fg_color="transparent",
            height=self.host._REVIEW_TYPES_SCROLL_HEIGHT,
        )
        types_scroll_frame.grid(row=0, column=0, sticky="nsew")
        self.host.review_types_shell = types_shell
        self.host.review_types_frame = types_frame
        self.host.review_types_scroll_frame = types_scroll_frame
        self.host.review_types_scroll_canvas = types_scroll_canvas
        self.host.review_types_scrollbar = types_scrollbar
        self.host.type_vars = {}
        self.host.type_checkboxes = {}
        self.host._review_type_depths = {}
        self.host._ordered_review_type_keys = []
        review_registry = get_review_registry()

        saved_types = config.get("gui", "review_types", "").strip()
        selected_types = set(self.host._parse_review_type_selection(saved_types))
        pinned_types, pinned_preset = self.host._load_pinned_review_selection()
        self.host._pinned_review_types = list(pinned_types)
        self.host._pinned_review_preset = pinned_preset
        if pinned_types:
            selected_types = set(pinned_types)
        if not selected_types:
            selected_types = {"best_practices"}
        selected_preset = pinned_preset or infer_review_type_preset(list(selected_types))

        self.host._review_preset_labels = {"custom": t("gui.review.preset_custom")}
        for preset_key in REVIEW_TYPE_PRESETS:
            self.host._review_preset_labels[preset_key] = format_review_preset_picker_label(preset_key)
        self.host._review_preset_reverse = {
            label: key for key, label in self.host._review_preset_labels.items()
        }

        for definition, depth in review_registry.iter_hierarchy(visible_only=True):
            key = definition.key
            label = get_review_type_label(key)
            if depth:
                label = f"> {label}"
            var = ctk.BooleanVar(value=(key in selected_types))
            checkbox = ctk.CTkCheckBox(
                types_frame,
                text=label,
                variable=var,
                width=220,
                command=self.host._on_review_types_changed,
            )
            self.host.type_vars[key] = var
            self.host.type_checkboxes[key] = checkbox
            self.host._review_type_depths[key] = depth
            self.host._ordered_review_type_keys.append(key)

        row += 1
        self._build_review_type_controls(parent, row, selected_preset)
        row += 1

        self.host.review_preset_summary_label = ctk.CTkLabel(
            parent,
            text="",
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        self.host.review_preset_summary_label.grid(row=row, column=0, sticky="w", padx=10, pady=(0, 2))
        self.host._sync_review_preset_ui(selected_preset)
        row += 1

        self.host.review_pin_status_label = ctk.CTkLabel(
            parent,
            text="",
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
            wraplength=920,
        )
        self.host.review_pin_status_label.grid(row=row, column=0, sticky="w", padx=10, pady=(0, 2))
        self.host._sync_review_pinning_controls()
        row += 1

        self.host.review_recommendation_label = ctk.CTkLabel(
            parent,
            text=t("gui.review.recommendation_hint"),
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
            wraplength=920,
        )
        self.host.review_recommendation_label.grid(row=row, column=0, sticky="w", padx=10, pady=(0, 2))
        row += 1

        self.host.review_types_hint_label = ctk.CTkLabel(
            parent,
            text=t("gui.review.types_hint"),
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        self.host.review_types_hint_label.grid(row=row, column=0, sticky="w", padx=10, pady=(0, 6))
        row += 1

        types_shell.bind("<Map>", self.host._schedule_review_type_layout_refresh, add="+")
        types_shell.bind("<Configure>", self.host._schedule_review_type_layout_refresh, add="+")
        types_scroll_canvas.bind("<Configure>", self.host._schedule_review_type_layout_refresh, add="+")
        self.host._refresh_review_type_layout()
        return row

    def _build_review_type_controls(self, parent: Any, row: int, selected_preset: str | None) -> None:
        sel_frame = ctk.CTkFrame(parent, fg_color="transparent")
        sel_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=2)
        self.host.review_type_controls_frame = sel_frame

        selection_frame = ctk.CTkFrame(sel_frame, fg_color="transparent")
        selection_frame.grid_columnconfigure(0, weight=0)
        selection_frame.grid_columnconfigure(1, weight=0)
        self.host.review_type_selection_actions_frame = selection_frame
        ctk.CTkButton(
            selection_frame,
            text=t("gui.review.select_all"),
            width=90,
            command=lambda: self.host._set_all_types(True),
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            selection_frame,
            text=t("gui.review.clear_all"),
            width=90,
            command=lambda: self.host._set_all_types(False),
        ).grid(row=0, column=1)

        preset_frame = ctk.CTkFrame(sel_frame, fg_color="transparent")
        self.host.review_type_preset_actions_frame = preset_frame
        self.host.review_preset_label = ctk.CTkLabel(preset_frame, text=t("gui.review.preset_label"))
        self.host.review_preset_var = ctk.StringVar(
            value=self.host._review_preset_labels.get(selected_preset or "custom", t("gui.review.preset_custom"))
        )
        self.host.review_preset_menu = ctk.CTkOptionMenu(
            preset_frame,
            variable=self.host.review_preset_var,
            values=list(self.host._review_preset_labels.values()),
            command=self.host._on_review_preset_selected,
            width=300,
        )
        self.host.recommend_btn = ctk.CTkButton(
            preset_frame,
            text=t("gui.review.recommend"),
            width=150,
            command=self.host._start_review_recommendation,
        )

        pin_frame = ctk.CTkFrame(sel_frame, fg_color="transparent")
        self.host.review_type_pin_actions_frame = pin_frame
        self.host.pin_review_set_btn = ctk.CTkButton(
            pin_frame,
            text=t("gui.review.pin_set"),
            width=120,
            command=self.host._pin_current_review_selection,
        )
        self.host.pin_review_set_btn.grid(row=0, column=0, padx=(0, 8))
        self.host.clear_pinned_review_set_btn = ctk.CTkButton(
            pin_frame,
            text=t("gui.review.clear_pin"),
            width=110,
            command=self.host._clear_pinned_review_selection,
        )
        self.host.clear_pinned_review_set_btn.grid(row=0, column=1)

    def _build_backend_section(self, parent: Any, row: int) -> int:
        be_frame = ctk.CTkFrame(
            parent,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        be_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=3)
        be_frame.grid_columnconfigure(2, weight=1)
        be_frame.grid_columnconfigure(3, weight=1)
        InfoTooltip.add(be_frame, t("gui.tip.backend_select"), row=0, column=0)
        ctk.CTkLabel(be_frame, text=t("gui.review.backend_label")).grid(row=0, column=1, padx=(0, 4))
        self.host.backend_var = ctk.StringVar(value=config.get("backend", "type", "bedrock"))
        self.host.backend_var.trace_add("write", self.host._on_backend_changed)
        self.host.backend_var.trace_add("write", self.host._sync_review_backend_menu)
        self.host._review_backend_display_map = {
            descriptor.key: self.host._backend_display_label(descriptor.key, descriptor.display_name)
            for descriptor in get_backend_registry().list_descriptors()
        }
        self.host._review_backend_reverse_map = {
            value: key for key, value in self.host._review_backend_display_map.items()
        }
        backend_display = self.host._review_backend_display_map.get(
            self.host.backend_var.get(),
            next(iter(self.host._review_backend_display_map.values()), self.host.backend_var.get()),
        )
        self.host.review_backend_display_var = ctk.StringVar(value=backend_display)
        self.host.review_backend_menu = ctk.CTkOptionMenu(
            be_frame,
            variable=self.host.review_backend_display_var,
            values=list(self.host._review_backend_display_map.values()),
            width=240,
            command=self.host._on_review_backend_selected,
        )
        self.host.review_backend_menu.grid(row=0, column=2, padx=(0, 8), pady=6, sticky="w")
        ctk.CTkLabel(
            be_frame,
            text=t("gui.review.backend_hint"),
            anchor="e",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=3, padx=(8, 10), sticky="e")
        return row + 1

    def _build_metadata_section(self, parent: Any, row: int) -> int:
        meta_frame = ctk.CTkFrame(
            parent,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        meta_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=3)
        meta_frame.grid_columnconfigure(2, weight=1)
        meta_frame.grid_columnconfigure(5, weight=1)

        InfoTooltip.add(meta_frame, t("gui.tip.programmers"), row=0, column=0)
        ctk.CTkLabel(meta_frame, text=t("gui.review.programmers")).grid(row=0, column=1, padx=(0, 4))
        saved_programmers = config.get("gui", "programmers", "").strip()
        self.host.programmers_entry = ctk.CTkEntry(meta_frame, placeholder_text=t("gui.review.programmers_ph"))
        if saved_programmers:
            self.host.programmers_entry.insert(0, saved_programmers)
        self.host.programmers_entry.grid(row=0, column=2, sticky="ew", padx=4)

        InfoTooltip.add(meta_frame, t("gui.tip.reviewers"), row=0, column=3)
        ctk.CTkLabel(meta_frame, text=t("gui.review.reviewers")).grid(row=0, column=4, padx=(0, 4))
        saved_reviewers = config.get("gui", "reviewers", "").strip()
        self.host.reviewers_entry = ctk.CTkEntry(meta_frame, placeholder_text=t("gui.review.reviewers_ph"))
        if saved_reviewers:
            self.host.reviewers_entry.insert(0, saved_reviewers)
        self.host.reviewers_entry.grid(row=0, column=5, sticky="ew", padx=4)

        InfoTooltip.add(meta_frame, t("gui.tip.language"), row=1, column=0)
        ctk.CTkLabel(meta_frame, text=t("gui.review.language")).grid(row=1, column=1, padx=(0, 4), pady=(3, 0))
        saved_review_lang = config.get("gui", "review_language", "").strip() or "system"
        self.host._review_lang_labels = {
            "system": t("gui.review.lang_system"),
            "en": t("gui.review.lang_en"),
            "ja": t("gui.review.lang_ja"),
        }
        self.host._review_lang_reverse = {value: key for key, value in self.host._review_lang_labels.items()}
        lang_display = self.host._review_lang_labels.get(saved_review_lang, t("gui.review.lang_system"))
        self.host.lang_var = ctk.StringVar(value=lang_display)
        ctk.CTkOptionMenu(
            meta_frame,
            variable=self.host.lang_var,
            values=list(self.host._review_lang_labels.values()),
            width=160,
        ).grid(row=1, column=2, sticky="w", padx=4, pady=(3, 0))

        InfoTooltip.add(meta_frame, t("gui.tip.spec_file"), row=1, column=3)
        ctk.CTkLabel(meta_frame, text=t("gui.review.spec_file")).grid(row=1, column=4, padx=(0, 4), pady=(3, 0))
        saved_spec = config.get("gui", "spec_file", "").strip()
        self.host.spec_entry = ctk.CTkEntry(meta_frame, placeholder_text=t("gui.review.spec_placeholder"))
        if saved_spec:
            self.host.spec_entry.insert(0, saved_spec)
        self.host.spec_entry.grid(row=1, column=5, sticky="ew", padx=4, pady=(3, 0))
        return row + 1

    def _build_run_panel(self, parent: Any) -> None:
        run_row = add_section_header(
            parent,
            0,
            t("gui.review.section_run_title"),
            t("gui.review.section_run_desc"),
            muted_text=self.host._MUTED_TEXT,
        )

        arch_frame = ctk.CTkFrame(
            parent,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        arch_frame.grid(row=run_row, column=0, sticky="ew", padx=6, pady=(2, 2))
        saved_arch = config.get("processing", "enable_architectural_review", "false")
        self.host.arch_analysis_var = ctk.BooleanVar(value=str(saved_arch).lower() in ("true", "1", "yes"))
        InfoTooltip.add(arch_frame, t("gui.tip.arch_analysis"), row=0, column=0)
        ctk.CTkCheckBox(
            arch_frame,
            text=t("gui.review.arch_analysis"),
            variable=self.host.arch_analysis_var,
        ).grid(row=0, column=1, padx=8, pady=6, sticky="w")
        run_row += 1

        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=run_row, column=0, sticky="ew", padx=6, pady=(6, 2))
        btn_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            btn_frame,
            text=t("gui.review.run_hint"),
            anchor="w",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.host.run_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.review.start"),
            fg_color="green",
            hover_color="#228B22",
            command=self.host._start_review,
        )
        self.host.run_btn.grid(row=0, column=1, padx=6)
        _Tooltip(self.host.run_btn, t("gui.shortcut.start_review"))
        self.host.dry_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.review.dry_run"),
            command=self.host._start_dry_run,
        )
        self.host.dry_btn.grid(row=0, column=2, padx=6)
        self.host.health_btn = ctk.CTkButton(
            btn_frame,
            text=t("health.check_btn"),
            command=self.host._check_backend_health,
        )
        self.host.health_btn.grid(row=0, column=3, padx=6)

        queue_callbacks = make_review_submission_queue_callbacks(
            on_selected=self.host._review_submission_queue.on_queue_selection_changed,
            scheduler=self.host._review_execution_scheduler_handle(),
            selection=self.host._selected_review_submission,
            set_status_text=lambda text: self.host.status_var.set(text),
            on_cancel_effect=self.host._review_submission_queue.on_cancel_effect,
            sync_global_cancel=self.host._sync_global_cancel_button,
        )
        queue_panel = build_review_submission_queue_panel(
            parent=parent,
            row=run_row + 1,
            section_surface=self.host._SECTION_SURFACE,
            section_border=self.host._SECTION_BORDER,
            muted_text=self.host._MUTED_TEXT,
            on_selected=queue_callbacks.on_selected,
            on_cancel_selected=queue_callbacks.on_cancel_selected,
        )
        self.host._review_submission_queue.bind_widgets(queue_panel)

        self.host.progress = ctk.CTkProgressBar(parent, width=400)
        self.host.progress.grid(row=run_row + 2, column=0, sticky="ew", padx=6, pady=(3, 0))
        self.host.progress.set(0)

        self.host._elapsed_lbl = ctk.CTkLabel(
            parent,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            anchor="e",
        )
        self.host._elapsed_lbl.grid(row=run_row + 3, column=0, sticky="e", padx=(0, 10), pady=(0, 4))
        self.host._review_submission_queue.on_queue_panel_ready()