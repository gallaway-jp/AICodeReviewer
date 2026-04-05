from __future__ import annotations

from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.i18n import t

from .shared_ui import add_section_header, build_autohide_scroller


class BenchmarkTabBuilder:
    def __init__(self, host: Any) -> None:
        self.host = host

    def build(self) -> None:
        root_tab = self.host.tabs.add(t("gui.tab.benchmarks"))
        root_tab.grid_columnconfigure(0, weight=1)
        root_tab.grid_rowconfigure(0, weight=1)

        benchmark_scroll_frame, benchmark_content, benchmark_scroll_canvas, benchmark_scrollbar = build_autohide_scroller(
            self.host,
            root_tab,
        )
        benchmark_scroll_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        benchmark_content.grid_columnconfigure(0, weight=1)
        self.host.benchmark_scroll_frame = benchmark_scroll_frame
        self.host.benchmark_scroll_canvas = benchmark_scroll_canvas
        self.host.benchmark_scrollbar = benchmark_scrollbar
        tab = benchmark_content

        self.host._benchmark_entries = []
        self.host._benchmark_entry_by_label = {}
        self.host._benchmark_summary_candidates = {}
        self.host._benchmark_primary_summary_path = None
        self.host._benchmark_primary_summary_payload = None
        self.host._benchmark_compare_summary_path = None
        self.host._benchmark_compare_summary_payload = None
        self.host._benchmark_fixture_diff_records = []
        self.host._benchmark_fixture_diff_rows = {}
        self.host._benchmark_fixture_presence_filters = self.host._build_fixture_presence_filters()
        self.host._benchmark_fixture_sort_options = self.host._build_fixture_sort_options()
        self.host._benchmark_advanced_visible = False

        intro = ctk.CTkFrame(
            tab,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        intro.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 8))
        intro.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            intro,
            text=t("gui.benchmark.header_title"),
            anchor="w",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        self.host.benchmark_intro_subtitle_label = ctk.CTkLabel(
            intro,
            text=t("gui.benchmark.header_subtitle"),
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=12),
        )
        self.host.benchmark_intro_subtitle_label.grid(row=1, column=0, sticky="w", padx=12, pady=(2, 10))
        self.host.benchmark_quickstart_label = ctk.CTkLabel(
            intro,
            text=t("gui.benchmark.quickstart"),
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        self.host.benchmark_quickstart_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        row = 1
        row = add_section_header(
            tab,
            row,
            t("gui.benchmark.section_source_title"),
            t("gui.benchmark.section_source_desc"),
            muted_text=self.host._MUTED_TEXT,
        )

        source_frame = ctk.CTkFrame(
            tab,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        source_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=(0, 8))
        source_frame.grid_columnconfigure(1, weight=1)
        source_frame.grid_columnconfigure(2, weight=0)

        self.host.benchmark_advanced_hint_label = ctk.CTkLabel(
            source_frame,
            text=t("gui.benchmark.advanced_hint"),
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        self.host.benchmark_advanced_hint_label.grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(12, 8))

        ctk.CTkLabel(source_frame, text=t("gui.benchmark.summary_selector"), anchor="w").grid(
            row=1, column=0, sticky="w", padx=(12, 8), pady=(0, 6)
        )
        self.host.benchmark_summary_selector_var = ctk.StringVar(value=t("gui.benchmark.no_summaries"))
        self.host.benchmark_summary_selector_menu = ctk.CTkOptionMenu(
            source_frame,
            variable=self.host.benchmark_summary_selector_var,
            values=[t("gui.benchmark.no_summaries")],
        )
        self.host.benchmark_summary_selector_menu.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 6))

        self.host.benchmark_refresh_summaries_btn = ctk.CTkButton(
            source_frame,
            text=t("gui.benchmark.refresh_summaries"),
            width=96,
            command=self.host._refresh_benchmark_summary_selector,
        )
        self.host.benchmark_refresh_summaries_btn.grid(row=1, column=2, padx=(0, 12), pady=(0, 6))

        action_frame = ctk.CTkFrame(source_frame, fg_color="transparent")
        action_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 8))
        self.host.benchmark_source_actions_frame = action_frame

        self.host.benchmark_load_catalog_btn = ctk.CTkButton(
            action_frame,
            text=t("gui.benchmark.load_catalog"),
            width=150,
            command=self.host._load_benchmark_fixture_catalog,
        )
        self.host.benchmark_load_catalog_btn.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.host.benchmark_load_summary_btn = ctk.CTkButton(
            action_frame,
            text=t("gui.benchmark.load_summary"),
            width=170,
            command=self.host._browse_benchmark_summary_artifact,
        )
        self.host.benchmark_load_summary_btn.grid(row=0, column=1, padx=(0, 8), sticky="w")

        self.host.benchmark_compare_summary_btn = ctk.CTkButton(
            action_frame,
            text=t("gui.benchmark.compare_summary"),
            width=170,
            command=self.host._browse_benchmark_compare_artifact,
        )
        self.host.benchmark_compare_summary_btn.grid(row=0, column=2, padx=(0, 8), sticky="w")

        self.host.benchmark_load_selected_summary_btn = ctk.CTkButton(
            action_frame,
            text=t("gui.benchmark.load_selected_summary"),
            width=170,
            command=self.host._load_selected_benchmark_summary,
        )
        self.host.benchmark_load_selected_summary_btn.grid(row=0, column=3, padx=(0, 8), sticky="w")

        self.host.benchmark_compare_selected_summary_btn = ctk.CTkButton(
            action_frame,
            text=t("gui.benchmark.compare_selected_summary"),
            width=190,
            command=self.host._compare_selected_benchmark_summary,
        )
        self.host.benchmark_compare_selected_summary_btn.grid(row=0, column=4, padx=(0, 8), sticky="w")

        self.host.benchmark_advanced_toggle_btn = ctk.CTkButton(
            source_frame,
            text=t("gui.benchmark.advanced_show"),
            width=180,
            fg_color=("#dbe7f6", "#334155"),
            hover_color=("#c8dbf1", "#3f4d61"),
            text_color=("gray15", "gray92"),
            command=self.host._toggle_benchmark_advanced_sources,
        )
        self.host.benchmark_advanced_toggle_btn.grid(row=3, column=0, padx=12, pady=(0, 10), sticky="w")

        advanced_frame = ctk.CTkFrame(source_frame, fg_color="transparent")
        advanced_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))
        advanced_frame.grid_columnconfigure(1, weight=1)
        advanced_frame.grid_columnconfigure(2, weight=0)
        self.host.benchmark_advanced_source_frame = advanced_frame

        ctk.CTkLabel(advanced_frame, text=t("gui.benchmark.fixtures_root"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6)
        )
        self.host.benchmark_fixtures_root_entry = ctk.CTkEntry(advanced_frame)
        self.host.benchmark_fixtures_root_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(0, 6))
        self.host.benchmark_fixtures_root_entry.insert(
            0,
            self.host._saved_benchmark_root_value(
                "benchmark_fixtures_root",
                str(self.host._default_benchmark_fixtures_root()),
            ),
        )

        self.host.benchmark_fixtures_browse_btn = ctk.CTkButton(
            advanced_frame,
            text=t("common.browse"),
            width=96,
            command=self.host._browse_benchmark_fixtures_root,
        )
        self.host.benchmark_fixtures_browse_btn.grid(row=0, column=2, padx=(0, 0), pady=(0, 6))

        ctk.CTkLabel(advanced_frame, text=t("gui.benchmark.artifacts_root"), anchor="w").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 6)
        )
        self.host.benchmark_artifacts_root_entry = ctk.CTkEntry(advanced_frame)
        self.host.benchmark_artifacts_root_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 6))
        self.host.benchmark_artifacts_root_entry.insert(
            0,
            self.host._saved_benchmark_root_value(
                "benchmark_artifacts_root",
                str(self.host._default_benchmark_artifacts_root()),
            ),
        )

        self.host.benchmark_artifacts_browse_btn = ctk.CTkButton(
            advanced_frame,
            text=t("common.browse"),
            width=96,
            command=self.host._browse_benchmark_artifacts_root,
        )
        self.host.benchmark_artifacts_browse_btn.grid(row=1, column=2, padx=(0, 0), pady=(0, 6))

        self.host.benchmark_source_hint_label = ctk.CTkLabel(
            advanced_frame,
            text=t("gui.benchmark.source_hint"),
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        self.host.benchmark_source_hint_label.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        secondary_action_frame = ctk.CTkFrame(advanced_frame, fg_color="transparent")
        secondary_action_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.host.benchmark_source_secondary_actions_frame = secondary_action_frame

        self.host.benchmark_open_source_btn = ctk.CTkButton(
            secondary_action_frame,
            text=t("gui.benchmark.open_source_folder"),
            width=170,
            fg_color=("#dbe7f6", "#334155"),
            hover_color=("#c8dbf1", "#3f4d61"),
            text_color=("gray15", "gray92"),
            command=self.host._open_benchmark_source_folder,
        )
        self.host.benchmark_open_source_btn.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.host.benchmark_open_summary_json_btn = ctk.CTkButton(
            secondary_action_frame,
            text=t("gui.benchmark.open_summary_json"),
            width=160,
            fg_color=("#dbe7f6", "#334155"),
            hover_color=("#c8dbf1", "#3f4d61"),
            text_color=("gray15", "gray92"),
            command=self.host._open_selected_benchmark_summary_json,
        )
        self.host.benchmark_open_summary_json_btn.grid(row=0, column=1, padx=(0, 8), sticky="w")

        self.host.benchmark_open_report_dir_btn = ctk.CTkButton(
            secondary_action_frame,
            text=t("gui.benchmark.open_report_dir"),
            width=170,
            fg_color=("#dbe7f6", "#334155"),
            hover_color=("#c8dbf1", "#3f4d61"),
            text_color=("gray15", "gray92"),
            command=self.host._open_selected_benchmark_report_directory,
        )
        self.host.benchmark_open_report_dir_btn.grid(row=0, column=2, padx=(0, 8), sticky="w")

        self.host.benchmark_reload_btn = ctk.CTkButton(
            secondary_action_frame,
            text=t("gui.benchmark.reload"),
            width=110,
            fg_color=("#dbe7f6", "#334155"),
            hover_color=("#c8dbf1", "#3f4d61"),
            text_color=("gray15", "gray92"),
            command=self.host._reload_benchmark_source,
        )
        self.host.benchmark_reload_btn.grid(row=0, column=3, padx=(0, 8), sticky="w")

        self.host._benchmark_action_buttons = [
            self.host.benchmark_load_catalog_btn,
            self.host.benchmark_load_summary_btn,
            self.host.benchmark_compare_summary_btn,
            self.host.benchmark_load_selected_summary_btn,
            self.host.benchmark_compare_selected_summary_btn,
        ]
        self.host._benchmark_secondary_action_buttons = [
            self.host.benchmark_open_source_btn,
            self.host.benchmark_open_summary_json_btn,
            self.host.benchmark_open_report_dir_btn,
            self.host.benchmark_reload_btn,
        ]
        self.host._set_benchmark_advanced_sources_visible(False)

        row += 1
        row = add_section_header(
            tab,
            row,
            t("gui.benchmark.section_browser_title"),
            t("gui.benchmark.section_browser_desc"),
            muted_text=self.host._MUTED_TEXT,
        )

        browser_frame = ctk.CTkFrame(tab, fg_color="transparent")
        browser_frame.grid(row=row, column=0, sticky="nsew", padx=6, pady=(0, 6))
        browser_frame.grid_columnconfigure(0, weight=1)
        browser_frame.grid_columnconfigure(1, weight=1)
        browser_frame.grid_rowconfigure(2, weight=1)
        browser_frame.grid_rowconfigure(3, weight=1)
        self.host.benchmark_browser_frame = browser_frame

        metrics_frame = ctk.CTkFrame(browser_frame, fg_color="transparent")
        metrics_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        metrics_frame.grid_columnconfigure(1, weight=1)
        metrics_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            metrics_frame,
            text=t("gui.benchmark.source_label"),
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.host.benchmark_source_value = ctk.CTkLabel(metrics_frame, text=t("gui.benchmark.source_none"), anchor="w")
        self.host.benchmark_source_value.grid(row=0, column=1, sticky="ew", padx=(0, 16))

        ctk.CTkLabel(
            metrics_frame,
            text=t("gui.benchmark.count_label"),
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.host.benchmark_count_value = ctk.CTkLabel(metrics_frame, text=t("gui.benchmark.count_value", count=0), anchor="w")
        self.host.benchmark_count_value.grid(row=0, column=3, sticky="ew")

        ctk.CTkLabel(browser_frame, text=t("gui.benchmark.fixture_selector"), anchor="w").grid(
            row=1, column=0, sticky="w", pady=(0, 4)
        )
        self.host.benchmark_fixture_var = ctk.StringVar(value=t("gui.benchmark.none_available"))
        self.host.benchmark_fixture_menu = ctk.CTkOptionMenu(
            browser_frame,
            variable=self.host.benchmark_fixture_var,
            values=[t("gui.benchmark.none_available")],
            command=self.host._on_benchmark_fixture_selected,
        )
        self.host.benchmark_fixture_menu.grid(row=1, column=1, sticky="ew", pady=(0, 4))

        self.host.benchmark_catalog_box = ctk.CTkTextbox(
            browser_frame,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.host.benchmark_catalog_box.grid(row=2, column=0, sticky="nsew", padx=(0, 4))

        self.host.benchmark_detail_box = ctk.CTkTextbox(
            browser_frame,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.host.benchmark_detail_box.grid(row=2, column=1, sticky="nsew", padx=(4, 0))

        self.host._set_textbox(self.host.benchmark_catalog_box, t("gui.benchmark.catalog_empty"))
        self.host._set_textbox(self.host.benchmark_detail_box, t("gui.benchmark.detail_empty"))

        row += 1
        row = add_section_header(
            tab,
            row,
            t("gui.benchmark.section_compare_title"),
            t("gui.benchmark.section_compare_desc"),
            muted_text=self.host._MUTED_TEXT,
        )

        compare_frame = ctk.CTkFrame(tab, fg_color="transparent")
        compare_frame.grid(row=row, column=0, sticky="nsew", padx=6, pady=(0, 6))
        compare_frame.grid_columnconfigure(0, weight=1)
        compare_frame.grid_columnconfigure(1, weight=1)
        compare_frame.grid_rowconfigure(1, weight=1)
        compare_frame.grid_rowconfigure(2, weight=1)
        compare_frame.grid_rowconfigure(3, weight=1)
        compare_frame.grid_rowconfigure(4, weight=1)
        self.host.benchmark_compare_frame = compare_frame

        self.host.benchmark_takeaways_label = ctk.CTkLabel(
            compare_frame,
            text=t("gui.benchmark.takeaways_empty"),
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        self.host.benchmark_takeaways_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        self.host.benchmark_primary_summary_label = ctk.CTkLabel(
            compare_frame,
            text=t("gui.benchmark.primary_summary_label"),
            anchor="w",
        )
        self.host.benchmark_primary_summary_label.grid(row=1, column=0, sticky="w", pady=(0, 4))
        self.host.benchmark_compare_summary_label = ctk.CTkLabel(
            compare_frame,
            text=t("gui.benchmark.compare_summary_label"),
            anchor="w",
        )
        self.host.benchmark_compare_summary_label.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(0, 4))

        self.host.benchmark_primary_summary_box = ctk.CTkTextbox(
            compare_frame,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.host.benchmark_primary_summary_box.grid(row=2, column=0, sticky="nsew", padx=(0, 4))

        self.host.benchmark_compare_summary_box = ctk.CTkTextbox(
            compare_frame,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.host.benchmark_compare_summary_box.grid(row=2, column=1, sticky="nsew", padx=(4, 0))

        table_frame = ctk.CTkFrame(
            compare_frame,
            fg_color=self.host._SECTION_SURFACE,
            border_width=1,
            border_color=self.host._SECTION_BORDER,
        )
        table_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_columnconfigure(1, weight=0)
        table_frame.grid_rowconfigure(2, weight=1)
        table_frame.grid_rowconfigure(4, weight=1)
        table_frame.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(
            table_frame,
            text=t("gui.benchmark.fixture_table_title"),
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        controls_frame = ctk.CTkFrame(table_frame, fg_color="transparent")
        controls_frame.grid(row=0, column=1, sticky="e", padx=12, pady=(8, 4))
        controls_frame.grid_columnconfigure(1, weight=0)
        controls_frame.grid_columnconfigure(3, weight=0)

        ctk.CTkLabel(
            controls_frame,
            text=t("gui.benchmark.fixture_table_filter_label"),
            anchor="e",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, sticky="e", padx=(0, 8))
        self.host.benchmark_fixture_filter_var = ctk.StringVar(value=self.host._benchmark_fixture_presence_filters[0][0])
        self.host.benchmark_fixture_filter_menu = ctk.CTkOptionMenu(
            controls_frame,
            variable=self.host.benchmark_fixture_filter_var,
            values=[label for label, _filter_key, _predicate in self.host._benchmark_fixture_presence_filters],
            command=self.host._on_fixture_diff_filter_selected,
            width=170,
        )
        self.host.benchmark_fixture_filter_menu.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            controls_frame,
            text=t("gui.benchmark.fixture_table_sort_label"),
            anchor="e",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=2, sticky="e", padx=(12, 8))
        self.host.benchmark_fixture_sort_var = ctk.StringVar(value=self.host._benchmark_fixture_sort_options[0][0])
        self.host.benchmark_fixture_sort_menu = ctk.CTkOptionMenu(
            controls_frame,
            variable=self.host.benchmark_fixture_sort_var,
            values=[label for label, _sort_key in self.host._benchmark_fixture_sort_options],
            command=self.host._on_fixture_diff_sort_selected,
            width=210,
        )
        self.host.benchmark_fixture_sort_menu.grid(row=0, column=3, sticky="e")

        self.host.benchmark_fixture_diff_header = ctk.CTkFrame(table_frame, fg_color="transparent")
        self.host.benchmark_fixture_diff_header.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        for column, weight in ((0, 2), (1, 1), (2, 1), (3, 1), (4, 1), (5, 2), (6, 0), (7, 0), (8, 0), (9, 0)):
            self.host.benchmark_fixture_diff_header.grid_columnconfigure(column, weight=weight)

        header_keys = (
            "gui.benchmark.fixture_table_fixture",
            "gui.benchmark.fixture_table_presence",
            "gui.benchmark.fixture_table_primary",
            "gui.benchmark.fixture_table_compare",
            "gui.benchmark.fixture_table_delta",
            "gui.benchmark.fixture_table_types",
            "gui.benchmark.fixture_table_open_primary",
            "gui.benchmark.fixture_table_open_compare",
            "gui.benchmark.fixture_table_preview",
            "gui.benchmark.fixture_table_diff",
        )
        for column, key in enumerate(header_keys):
            ctk.CTkLabel(
                self.host.benchmark_fixture_diff_header,
                text=t(key),
                anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=self.host._MUTED_TEXT,
            ).grid(row=0, column=column, sticky="w", padx=(0, 8))

        self.host.benchmark_fixture_diff_empty_label = ctk.CTkLabel(
            table_frame,
            text=t("gui.benchmark.fixture_table_empty"),
            anchor="w",
            justify="left",
            text_color=self.host._MUTED_TEXT,
        )
        self.host.benchmark_fixture_diff_empty_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        self.host.benchmark_fixture_diff_scroll = (
            ctk.CTkFrame(table_frame, fg_color="transparent")
            if self.host._testing_mode
            else ctk.CTkScrollableFrame(table_frame, fg_color="transparent")
        )
        self.host.benchmark_fixture_diff_scroll.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 10))
        self.host.benchmark_fixture_diff_scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            table_frame,
            text=t("gui.benchmark.preview_title"),
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=3, column=0, sticky="w", padx=12, pady=(2, 4))

        preview_frame = ctk.CTkFrame(table_frame, fg_color="transparent")
        preview_frame.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 8))
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(1, weight=1)
        preview_frame.grid_rowconfigure(1, weight=1)

        self.host.benchmark_preview_frame = preview_frame
        self.host.benchmark_preview_primary_label = ctk.CTkLabel(
            preview_frame,
            text=t("gui.benchmark.preview_primary_label"),
            anchor="w",
        )
        self.host.benchmark_preview_compare_label = ctk.CTkLabel(
            preview_frame,
            text=t("gui.benchmark.preview_compare_label"),
            anchor="w",
        )

        self.host.benchmark_preview_primary_box = ctk.CTkTextbox(
            preview_frame,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.host.benchmark_preview_primary_box.grid(row=1, column=0, sticky="nsew", padx=(0, 4))

        self.host.benchmark_preview_compare_box = ctk.CTkTextbox(
            preview_frame,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.host.benchmark_preview_compare_box.grid(row=1, column=1, sticky="nsew", padx=(4, 0))

        ctk.CTkLabel(
            table_frame,
            text=t("gui.benchmark.preview_diff_title"),
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=5, column=0, sticky="w", padx=12, pady=(0, 4))

        self.host.benchmark_preview_diff_box = ctk.CTkTextbox(
            table_frame,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.host.benchmark_preview_diff_box.grid(row=6, column=0, sticky="nsew", padx=12, pady=(0, 10))

        self.host._set_textbox(self.host.benchmark_primary_summary_box, t("gui.benchmark.primary_summary_empty"))
        self.host._set_textbox(self.host.benchmark_compare_summary_box, t("gui.benchmark.compare_summary_empty"))
        self.host._render_fixture_diff_table([])
        self.host._set_textbox(self.host.benchmark_preview_primary_box, t("gui.benchmark.preview_primary_empty"))
        self.host._set_textbox(self.host.benchmark_preview_compare_box, t("gui.benchmark.preview_compare_empty"))
        self.host._set_textbox(self.host.benchmark_preview_diff_box, t("gui.benchmark.preview_diff_empty"))
        self.host.benchmark_takeaways_label.configure(text=t("gui.benchmark.takeaways_empty"))
        self.host._restore_benchmark_browser_state()
        benchmark_scroll_canvas.bind("<Configure>", self.host._schedule_benchmark_layout_refresh, add="+")
        self.host._refresh_benchmark_tab_layout()