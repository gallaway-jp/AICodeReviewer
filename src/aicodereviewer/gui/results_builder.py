from __future__ import annotations

from typing import Any, Dict, List

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.i18n import t


class ResultsTabBuilder:
    def __init__(self, host: Any) -> None:
        self.host = host

    def build(self) -> None:
        tab = self.host.tabs.add(t("gui.tab.results"))
        self.host.results_root_tab = tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(6, weight=1)

        self._build_header(tab)
        self._build_overview_metrics(tab)
        self._build_quick_filter_bar(tab)
        self._build_severity_bar(tab)
        self._build_filter_bar(tab)
        self._build_results_frame(tab)
        self._build_bottom_actions(tab)
        self._finalize(tab)

    def _build_header(self, tab: Any) -> None:
        self.host.results_summary = ctk.CTkLabel(
            tab,
            text=t("gui.results.no_results"),
            anchor="w",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.host.results_summary.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        self.host.results_subsummary = ctk.CTkLabel(
            tab,
            text="",
            anchor="w",
            justify="left",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=12),
        )
        self.host.results_subsummary.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        self.host.results_subsummary.grid_remove()

    def _build_overview_metrics(self, tab: Any) -> None:
        self.host._overview_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.host._overview_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 6))
        for column in range(4):
            self.host._overview_frame.grid_columnconfigure(column, weight=1)

        self.host._overview_cards = {}
        self.host._overview_card_frames = []
        for column, (key, title) in enumerate(
            (
                ("issues", t("gui.results.metric_issues")),
                ("pending", t("gui.results.metric_pending")),
                ("attention", t("gui.results.metric_attention")),
                ("backend", t("gui.results.metric_backend")),
            )
        ):
            card = ctk.CTkFrame(
                self.host._overview_frame,
                fg_color=self.host._SECTION_SURFACE,
                border_width=1,
                border_color=self.host._SECTION_BORDER,
            )
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0), pady=0)
            self.host._overview_card_frames.append(card)
            value_lbl = ctk.CTkLabel(card, text="--", anchor="w", font=ctk.CTkFont(size=22, weight="bold"))
            value_lbl.pack(anchor="w", padx=12, pady=(10, 0))
            title_lbl = ctk.CTkLabel(
                card,
                text=title,
                anchor="w",
                text_color=self.host._MUTED_TEXT,
                font=ctk.CTkFont(size=11),
            )
            title_lbl.pack(anchor="w", padx=12, pady=(2, 10))
            self.host._overview_cards[key] = value_lbl
        self.host._overview_frame.grid_remove()

    def _build_quick_filter_bar(self, tab: Any) -> None:
        self.host._quick_filter_bar = ctk.CTkFrame(tab, fg_color="transparent")
        self.host._quick_filter_bar.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))
        self.host._quick_filter_bar.grid_columnconfigure(6, weight=1)
        self.host._quick_filter_label = ctk.CTkLabel(
            self.host._quick_filter_bar,
            text=t("gui.results.quick_filter_label"),
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.host._quick_filter_label.grid(row=0, column=0, padx=(0, 6), sticky="w")

        self.host._quick_filter_mode = "all"
        self.host._quick_filter_buttons = {}
        self.host._quick_filter_button_order = []
        quick_filters = (
            ("all", t("gui.results.quick_filter_all")),
            ("pending", t("gui.results.quick_filter_pending")),
            ("critical", t("gui.results.quick_filter_critical")),
            ("attention", t("gui.results.quick_filter_attention")),
            ("cross_file", t("gui.results.quick_filter_cross_file")),
            ("fix_failed", t("gui.results.quick_filter_fix_failed")),
        )
        for column, (mode, label) in enumerate(quick_filters, start=1):
            button = ctk.CTkButton(
                self.host._quick_filter_bar,
                text=label,
                width=96,
                height=28,
                font=ctk.CTkFont(size=11),
                fg_color=("#e5edf9", "#303744"),
                hover_color=("#d7e4f7", "#3a4352"),
                text_color=("gray15", "gray92"),
                command=lambda selected_mode=mode: self.host._set_quick_filter(selected_mode),
            )
            button.grid(row=0, column=column, padx=(0, 6), sticky="w")
            self.host._quick_filter_buttons[mode] = button
            self.host._quick_filter_button_order.append(button)
        self.host._quick_filter_bar.grid_remove()

    def _build_severity_bar(self, tab: Any) -> None:
        self.host.results_severity_bar = ctk.CTkLabel(
            tab,
            text="",
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.host.results_severity_bar.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 2))
        self.host.results_severity_bar.grid_remove()

    def _build_filter_bar(self, tab: Any) -> None:
        self.host._filter_bar = ctk.CTkFrame(tab, fg_color="transparent")
        self.host._filter_bar.grid(row=5, column=0, sticky="ew", padx=8, pady=(0, 2))
        self.host._filter_bar.grid_columnconfigure(7, weight=1)

        self.host._filter_severity_label = ctk.CTkLabel(self.host._filter_bar, text=t("gui.results.filter_severity"))
        self.host._filter_severity_label.grid(row=0, column=0, padx=(0, 2))
        self.host._filter_sev_var = ctk.StringVar(value=t("gui.results.filter_all"))
        self.host._filter_severity_menu = ctk.CTkOptionMenu(
            self.host._filter_bar,
            variable=self.host._filter_sev_var,
            width=110,
            values=[t("gui.results.filter_all"), "Critical", "High", "Medium", "Low", "Info"],
            command=lambda _value: self.host._on_filter_controls_changed(),
        )
        self.host._filter_severity_menu.grid(row=0, column=1, padx=(0, 8))

        self.host._filter_status_label = ctk.CTkLabel(self.host._filter_bar, text=t("gui.results.filter_status"))
        self.host._filter_status_label.grid(row=0, column=2, padx=(0, 2))
        self.host._filter_status_var = ctk.StringVar(value=t("gui.results.filter_all"))
        self.host._filter_status_menu = ctk.CTkOptionMenu(
            self.host._filter_bar,
            variable=self.host._filter_status_var,
            width=120,
            values=[
                t("gui.results.filter_all"),
                "Pending",
                "Resolved",
                "Ignored",
                "Skipped",
                "Fixed",
                "AI Fixed",
                "Fix Failed",
            ],
            command=lambda _value: self.host._on_filter_controls_changed(),
        )
        self.host._filter_status_menu.grid(row=0, column=3, padx=(0, 8))

        self.host._filter_type_label = ctk.CTkLabel(self.host._filter_bar, text=t("gui.results.filter_type"))
        self.host._filter_type_label.grid(row=0, column=4, padx=(0, 2))
        self.host._filter_type_var = ctk.StringVar(value=t("gui.results.filter_all_types"))
        self.host._filter_type_menu = ctk.CTkOptionMenu(
            self.host._filter_bar,
            variable=self.host._filter_type_var,
            width=150,
            values=[t("gui.results.filter_all_types")],
            command=lambda _value: self.host._on_filter_controls_changed(),
        )
        self.host._filter_type_menu.grid(row=0, column=5, padx=(0, 8))

        self.host._filter_clear_btn = ctk.CTkButton(
            self.host._filter_bar,
            text=t("gui.results.filter_clear"),
            width=80,
            fg_color="gray50",
            hover_color="gray40",
            command=self.host._clear_filters,
        )
        self.host._filter_clear_btn.grid(row=0, column=6, padx=(0, 8))

        self.host._filter_count_lbl = ctk.CTkLabel(
            self.host._filter_bar,
            text="",
            anchor="e",
            font=ctk.CTkFont(size=11),
        )
        self.host._filter_count_lbl.grid(row=0, column=7, padx=4, sticky="e")

        self.host._filter_bar.grid_remove()

    def _build_results_frame(self, tab: Any) -> None:
        self.host.results_frame = ctk.CTkFrame(tab) if self.host._testing_mode else ctk.CTkScrollableFrame(tab)
        self.host.results_frame.grid(row=6, column=0, sticky="nsew", padx=8, pady=(0, 4))
        self.host.results_frame.grid_columnconfigure(0, weight=1)

    def _build_bottom_actions(self, tab: Any) -> None:
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=7, column=0, sticky="ew", padx=8, pady=(0, 6))
        self.host._results_bottom_actions_frame = btn_frame

        self.host.results_action_hint = ctk.CTkLabel(
            btn_frame,
            text=t("gui.results.next_action_hint"),
            anchor="w",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        self.host.results_action_hint.grid(row=0, column=0, padx=(0, 12), sticky="w")

        self.host.ai_fix_mode_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.results.ai_fix_mode"),
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            state="disabled",
            command=self.host._enter_ai_fix_mode,
        )
        self.host.ai_fix_mode_btn.grid(row=0, column=1, padx=6)

        self.host.review_changes_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.results.review_changes"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            state="disabled",
            command=self.host._review_changes,
        )
        self.host.review_changes_btn.grid(row=0, column=2, padx=6)

        self.host.finalize_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.results.finalize"),
            fg_color="green",
            hover_color="#228B22",
            state="disabled",
            command=self.host._finalize_report,
        )
        self.host.finalize_btn.grid(row=0, column=3, padx=6)

        self.host.save_session_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.results.save_session"),
            fg_color="#0e7490",
            hover_color="#0c6983",
            width=110,
            state="disabled",
            command=self.host._save_session,
        )
        self.host.save_session_btn.grid(row=0, column=4, padx=(18, 6))

        self.host.load_session_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.results.load_session"),
            fg_color="#374151",
            hover_color="#1f2937",
            width=110,
            command=self.host._load_session,
        )
        self.host.load_session_btn.grid(row=0, column=5, padx=6)

        self.host.start_ai_fix_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.results.start_ai_fix"),
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            command=self.host._start_batch_ai_fix,
        )
        self.host.cancel_ai_fix_btn = ctk.CTkButton(
            btn_frame,
            text=t("gui.results.cancel_ai_fix"),
            fg_color="gray50",
            command=self.host._exit_ai_fix_mode,
        )

    def _finalize(self, tab: Any) -> None:
        self.host._ai_fix_mode = False
        self.host._results_action_buttons_order = [
            self.host.ai_fix_mode_btn,
            self.host.review_changes_btn,
            self.host.finalize_btn,
            self.host.save_session_btn,
            self.host.load_session_btn,
            self.host.start_ai_fix_btn,
            self.host.cancel_ai_fix_btn,
        ]
        self.host._issue_cards = []
        self.host._active_toasts = []

        tab.bind("<Configure>", self.host._schedule_results_layout_refresh, add="+")
        self.host._refresh_results_tab_layout()

        self.host._popup_recovery_restored = False
        self.host._ensure_popup_surface_controller()
        schedule_after = getattr(self.host, "_schedule_app_after", self.host.after)
        schedule_after(75, self.host._restore_popup_recovery_if_available)