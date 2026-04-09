from __future__ import annotations

from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.i18n import t

from .shared_ui import SECTION_BORDER, SECTION_SURFACE, MUTED_TEXT, add_section_header, build_autohide_scroller


class AddonReviewTabBuilder:
    def __init__(self, host: Any, parent: Any | None = None, *, detached: bool = False) -> None:
        self.host = host
        self.parent = parent
        self.detached = detached

    def build(self) -> None:
        root_tab = self.parent if self.parent is not None else self.host.tabs.add(t("gui.tab.addon_review"))
        root_tab.grid_columnconfigure(0, weight=1)
        root_tab.grid_rowconfigure(0, weight=1)
        if not self.detached:
            self.host.addon_review_root_tab = root_tab

        scroll_frame, content, scroll_canvas, scrollbar = build_autohide_scroller(self.host, root_tab)
        scroll_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        content.grid_columnconfigure(0, weight=1)
        self.host.addon_review_scroll_frame = scroll_frame
        self.host.addon_review_scroll_canvas = scroll_canvas
        self.host.addon_review_scrollbar = scrollbar
        tab = content

        intro = ctk.CTkFrame(tab, fg_color=SECTION_SURFACE, border_width=1, border_color=SECTION_BORDER)
        intro.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 8))
        intro.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            intro,
            text=t("gui.addon_review.header_title"),
            anchor="w",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        self.host.addon_review_intro_subtitle_label = ctk.CTkLabel(
            intro,
            text=t("gui.addon_review.header_subtitle"),
            anchor="w",
            justify="left",
            text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=12),
        )
        self.host.addon_review_intro_subtitle_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 10))
        self.host.addon_review_quickstart_label = ctk.CTkLabel(
            intro,
            text=t("gui.addon_review.quickstart"),
            anchor="w",
            justify="left",
            text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        self.host.addon_review_quickstart_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        row = 1
        row = add_section_header(
            tab,
            row,
            t("gui.addon_review.section_source_title"),
            t("gui.addon_review.section_source_desc"),
            muted_text=MUTED_TEXT,
        )

        source_frame = ctk.CTkFrame(tab, fg_color=SECTION_SURFACE, border_width=1, border_color=SECTION_BORDER)
        source_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=(0, 8))
        source_frame.grid_columnconfigure(1, weight=1)
        source_frame.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(source_frame, text=t("gui.settings.addons_preview_dir"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=(12, 8), pady=(12, 6)
        )
        self.host.addon_review_preview_entry = ctk.CTkEntry(source_frame)
        self.host.addon_review_preview_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(12, 6))

        preview_actions = ctk.CTkFrame(source_frame, fg_color="transparent")
        preview_actions.grid(row=0, column=2, sticky="e", padx=(0, 12), pady=(12, 6))
        self.host.addon_review_browse_btn = ctk.CTkButton(
            preview_actions,
            text=t("common.browse"),
            width=86,
            command=self.host._browse_addon_review_preview_dir,
            fg_color=("#dbe7f6", "#334155"),
            hover_color=("#c8dbf1", "#3f4d61"),
            text_color=("gray15", "gray92"),
        )
        self.host.addon_review_browse_btn.grid(row=0, column=0, padx=(0, 8))
        self.host.addon_review_load_btn = ctk.CTkButton(
            preview_actions,
            text=t("gui.settings.addons_preview_load"),
            width=110,
            command=self.host._load_addon_review_surface,
        )
        self.host.addon_review_load_btn.grid(row=0, column=1)

        ctk.CTkLabel(source_frame, text=t("gui.settings.addons_preview_reviewer"), anchor="w").grid(
            row=1, column=0, sticky="w", padx=(12, 8), pady=(0, 6)
        )
        self.host.addon_review_reviewer_entry = ctk.CTkEntry(source_frame)
        self.host.addon_review_reviewer_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 6))
        self.host.addon_review_reviewer_entry.insert(0, self.host._default_addon_review_reviewer_name())

        ctk.CTkLabel(source_frame, text=t("gui.settings.addons_preview_install_dir"), anchor="w").grid(
            row=2, column=0, sticky="w", padx=(12, 8), pady=(0, 6)
        )
        self.host.addon_review_install_dir_entry = ctk.CTkEntry(source_frame)
        self.host.addon_review_install_dir_entry.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(0, 6))
        self.host.addon_review_install_dir_browse_btn = ctk.CTkButton(
            source_frame,
            text=t("common.browse"),
            width=86,
            command=self.host._browse_addon_review_install_dir,
            fg_color=("#dbe7f6", "#334155"),
            hover_color=("#c8dbf1", "#3f4d61"),
            text_color=("gray15", "gray92"),
        )
        self.host.addon_review_install_dir_browse_btn.grid(row=2, column=2, sticky="w", padx=(0, 12), pady=(0, 6))

        source_actions = ctk.CTkFrame(source_frame, fg_color="transparent")
        source_actions.grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 12))
        if self.detached:
            self.host.detach_addon_review_btn = None
            self.host._detached_addon_review_redock_btn = ctk.CTkButton(
                source_actions,
                text=t("gui.addon_review.redock"),
                width=150,
                fg_color=("#dbe7f6", "#334155"),
                hover_color=("#c8dbf1", "#3f4d61"),
                text_color=("gray15", "gray92"),
                command=self.host._redock_detached_addon_review_window,
            )
            self.host._detached_addon_review_redock_btn.grid(row=0, column=0, sticky="w")
        else:
            self.host._detached_addon_review_redock_btn = None
            self.host.detach_addon_review_btn = ctk.CTkButton(
                source_actions,
                text=t("gui.addon_review.open_window"),
                width=160,
                fg_color=("#dbe7f6", "#334155"),
                hover_color=("#c8dbf1", "#3f4d61"),
                text_color=("gray15", "gray92"),
                command=self.host._open_detached_addon_review_window,
            )
            self.host.detach_addon_review_btn.grid(row=0, column=0, sticky="w")

        row += 1
        row = add_section_header(
            tab,
            row,
            t("gui.addon_review.section_review_title"),
            t("gui.addon_review.section_review_desc"),
            muted_text=MUTED_TEXT,
        )

        review_frame = ctk.CTkFrame(tab, fg_color=SECTION_SURFACE, border_width=1, border_color=SECTION_BORDER)
        review_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=(0, 6))
        review_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(review_frame, text=t("gui.settings.addons_preview_status"), anchor="w").grid(
            row=0, column=0, sticky="nw", padx=(12, 8), pady=(12, 6)
        )
        self.host.addon_review_status_box = ctk.CTkTextbox(review_frame, height=88, wrap="word")
        self.host.addon_review_status_box.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 6))

        ctk.CTkLabel(review_frame, text=t("gui.settings.addons_preview_metadata"), anchor="w").grid(
            row=1, column=0, sticky="nw", padx=(12, 8), pady=(0, 6)
        )
        self.host.addon_review_metadata_box = ctk.CTkTextbox(review_frame, height=110, wrap="word")
        self.host.addon_review_metadata_box.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 6))

        ctk.CTkLabel(review_frame, text=t("gui.settings.addons_preview_checklist"), anchor="w").grid(
            row=2, column=0, sticky="nw", padx=(12, 8), pady=(0, 6)
        )
        self.host.addon_review_checklist_box = ctk.CTkTextbox(review_frame, height=126, wrap="word")
        self.host.addon_review_checklist_box.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=(0, 6))

        ctk.CTkLabel(review_frame, text=t("gui.settings.addons_preview_notes"), anchor="w").grid(
            row=3, column=0, sticky="nw", padx=(12, 8), pady=(0, 6)
        )
        self.host.addon_review_notes_box = ctk.CTkTextbox(review_frame, height=84, wrap="word")
        self.host.addon_review_notes_box.grid(row=3, column=1, sticky="ew", padx=(0, 12), pady=(0, 6))

        ctk.CTkLabel(review_frame, text=t("gui.settings.addons_preview_diff"), anchor="w").grid(
            row=4, column=0, sticky="w", padx=(12, 8), pady=(0, 6)
        )
        self.host.addon_review_diff_var = ctk.StringVar(value=t("gui.settings.addons_preview_diff_placeholder"))
        self.host.addon_review_diff_menu = ctk.CTkOptionMenu(
            review_frame,
            variable=self.host.addon_review_diff_var,
            values=[t("gui.settings.addons_preview_diff_placeholder")],
            command=self.host._on_addon_review_diff_selected,
        )
        self.host.addon_review_diff_menu.grid(row=4, column=1, sticky="w", padx=(0, 12), pady=(0, 6))

        self.host.addon_review_diff_box = ctk.CTkTextbox(review_frame, height=260, wrap="none")
        self.host.addon_review_diff_box.grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))

        action_frame = ctk.CTkFrame(review_frame, fg_color="transparent")
        action_frame.grid(row=6, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 12))
        self.host.addon_review_approve_btn = ctk.CTkButton(
            action_frame,
            text=t("gui.settings.addons_preview_approve"),
            width=130,
            command=self.host._approve_loaded_addon_review_preview,
        )
        self.host.addon_review_approve_btn.grid(row=0, column=0, padx=(0, 8))
        self.host.addon_review_reject_btn = ctk.CTkButton(
            action_frame,
            text=t("gui.settings.addons_preview_reject"),
            width=130,
            fg_color="gray40",
            hover_color="gray30",
            command=self.host._reject_loaded_addon_review_preview,
        )
        self.host.addon_review_reject_btn.grid(row=0, column=1)

        self.host._initialize_addon_review_surface_widgets()
        root_tab.bind("<Configure>", self.host._schedule_addon_review_layout_refresh, add="+")
        self.host._refresh_addon_review_tab_layout()