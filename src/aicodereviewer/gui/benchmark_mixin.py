"""Benchmark browser tab mixin for :class:`App`."""

from __future__ import annotations

from copy import deepcopy
import json
import logging
import os
from pathlib import Path
from tkinter import filedialog
import difflib
from typing import Any
import webbrowser

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.benchmarking import describe_fixture_catalog_entry, discover_fixtures, load_report
from aicodereviewer.config import config
from aicodereviewer.i18n import t
from .benchmark_builder import BenchmarkTabBuilder
from .benchmark_layout import BenchmarkLayoutHelper
from .shared_ui import MUTED_TEXT, SECTION_BORDER, SECTION_SURFACE

logger = logging.getLogger(__name__)


class BenchmarkTabMixin:
    """Mixin supplying a lightweight in-app benchmark browser tab."""

    _SECTION_SURFACE = SECTION_SURFACE
    _SECTION_BORDER = SECTION_BORDER
    _MUTED_TEXT = MUTED_TEXT

    def _default_benchmark_fixtures_root(self) -> Path:
        return Path(__file__).resolve().parents[3] / "benchmarks" / "holistic_review" / "fixtures"

    def _default_benchmark_artifacts_root(self) -> Path:
        return Path(__file__).resolve().parents[3] / "artifacts"

    def _workspace_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    def _benchmark_layout_helper(self) -> BenchmarkLayoutHelper:
        helper = getattr(self, "_benchmark_layout_delegate", None)
        if helper is None:
            helper = BenchmarkLayoutHelper(self)
            self._benchmark_layout_delegate = helper
        return helper

    def _benchmark_logical_width(self, *candidates: Any) -> float:
        return self._benchmark_layout_helper().resolve_logical_width(*candidates)

    def _schedule_benchmark_layout_refresh(self, *_args: Any) -> None:
        self._refresh_benchmark_tab_layout()

    def _layout_benchmark_action_frame(
        self,
        frame: Any,
        buttons: list[Any],
        logical_width: float,
        *,
        max_columns: int,
    ) -> None:
        self._benchmark_layout_helper().layout_action_frame(
            frame,
            buttons,
            logical_width,
            max_columns=max_columns,
        )

    def _set_benchmark_advanced_sources_visible(self, visible: bool) -> None:
        self._benchmark_advanced_visible = visible
        advanced_frame = getattr(self, "benchmark_advanced_source_frame", None)
        toggle_btn = getattr(self, "benchmark_advanced_toggle_btn", None)
        if advanced_frame is not None:
            if visible:
                advanced_frame.grid()
            else:
                advanced_frame.grid_remove()
        if toggle_btn is not None:
            toggle_btn.configure(
                text=t("gui.benchmark.advanced_hide") if visible else t("gui.benchmark.advanced_show")
            )
        self._refresh_benchmark_tab_layout()

    def _toggle_benchmark_advanced_sources(self) -> None:
        self._set_benchmark_advanced_sources_visible(
            not bool(getattr(self, "_benchmark_advanced_visible", False))
        )

    def _refresh_benchmark_tab_layout(self) -> None:
        self._benchmark_layout_helper().refresh_tab_layout()

    def _build_benchmark_tab(self) -> None:
        BenchmarkTabBuilder(self).build()
        self._refresh_benchmark_tab_layout()

    def _clear_benchmark_container(self, container: Any) -> None:
        if container is None:
            return
        for child in container.winfo_children():
            child.destroy()

    def _is_benchmark_detached(self) -> bool:
        return bool(getattr(self, "_detached_benchmark_window", None)) and self._app_helpers().surfaces().is_page_detached("benchmark")

    def _capture_textbox_value(self, textbox: Any) -> str:
        if textbox is None:
            return ""
        return str(textbox.get("0.0", "end")).rstrip("\n")

    def _snapshot_benchmark_surface_state(self) -> dict[str, Any]:
        if getattr(self, "benchmark_source_value", None) is None:
            return {}
        summary_candidates = {
            label: str(path)
            for label, path in getattr(self, "_benchmark_summary_candidates", {}).items()
            if isinstance(label, str) and isinstance(path, Path)
        }
        return {
            "fixtures_root": self.benchmark_fixtures_root_entry.get().strip(),
            "artifacts_root": self.benchmark_artifacts_root_entry.get().strip(),
            "advanced_visible": bool(getattr(self, "_benchmark_advanced_visible", False)),
            "entries": deepcopy(getattr(self, "_benchmark_entries", [])),
            "source_text": str(self.benchmark_source_value.cget("text") or ""),
            "selected_fixture": self.benchmark_fixture_var.get(),
            "selected_summary": self.benchmark_summary_selector_var.get(),
            "summary_candidates": summary_candidates,
            "source_kind": getattr(self, "_benchmark_source_kind", None),
            "source_path": getattr(self, "_benchmark_source_path", None),
            "primary_summary_path": getattr(self, "_benchmark_primary_summary_path", None),
            "primary_summary_payload": deepcopy(getattr(self, "_benchmark_primary_summary_payload", None)),
            "compare_summary_path": getattr(self, "_benchmark_compare_summary_path", None),
            "compare_summary_payload": deepcopy(getattr(self, "_benchmark_compare_summary_payload", None)),
            "filter_label": self.benchmark_fixture_filter_var.get(),
            "sort_label": self.benchmark_fixture_sort_var.get(),
            "preview_primary_text": self._capture_textbox_value(getattr(self, "benchmark_preview_primary_box", None)),
            "preview_compare_text": self._capture_textbox_value(getattr(self, "benchmark_preview_compare_box", None)),
            "preview_diff_text": self._capture_textbox_value(getattr(self, "benchmark_preview_diff_box", None)),
        }

    def _restore_benchmark_surface_state(self, state: dict[str, Any] | None) -> None:
        if not state:
            return

        self.benchmark_fixtures_root_entry.delete(0, "end")
        self.benchmark_fixtures_root_entry.insert(0, str(state.get("fixtures_root") or ""))
        self.benchmark_artifacts_root_entry.delete(0, "end")
        self.benchmark_artifacts_root_entry.insert(0, str(state.get("artifacts_root") or ""))

        self._set_benchmark_advanced_sources_visible(bool(state.get("advanced_visible", False)))

        summary_candidates: dict[str, Path] = {}
        raw_summary_candidates = state.get("summary_candidates")
        if isinstance(raw_summary_candidates, dict):
            for label, raw_path in raw_summary_candidates.items():
                if isinstance(label, str) and isinstance(raw_path, str) and raw_path.strip():
                    summary_candidates[label] = Path(raw_path)
        self._benchmark_summary_candidates = summary_candidates
        if summary_candidates:
            labels = list(summary_candidates.keys())
            self.benchmark_summary_selector_menu.configure(values=labels, state="normal")
            selected_summary = str(state.get("selected_summary") or "")
            self.benchmark_summary_selector_var.set(selected_summary if selected_summary in summary_candidates else labels[0])
        else:
            empty_value = t("gui.benchmark.no_summaries")
            self.benchmark_summary_selector_menu.configure(values=[empty_value], state="disabled")
            self.benchmark_summary_selector_var.set(empty_value)

        self._benchmark_source_kind = state.get("source_kind")
        self._benchmark_source_path = state.get("source_path")
        self._benchmark_primary_summary_path = state.get("primary_summary_path") if isinstance(state.get("primary_summary_path"), str) else None
        self._benchmark_primary_summary_payload = deepcopy(state.get("primary_summary_payload")) if isinstance(state.get("primary_summary_payload"), dict) else None
        self._benchmark_compare_summary_path = state.get("compare_summary_path") if isinstance(state.get("compare_summary_path"), str) else None
        self._benchmark_compare_summary_payload = deepcopy(state.get("compare_summary_payload")) if isinstance(state.get("compare_summary_payload"), dict) else None

        entries = state.get("entries") if isinstance(state.get("entries"), list) else []
        self._set_benchmark_browser_entries(entries, source_text=str(state.get("source_text") or t("gui.benchmark.source_none")))

        if self._benchmark_primary_summary_payload is not None or self._benchmark_compare_summary_payload is not None:
            self._render_summary_overviews()

        filter_labels = {label for label, _filter_key, _allowed in self._benchmark_fixture_presence_filters}
        sort_labels = {label for label, _sort_key in self._benchmark_fixture_sort_options}
        filter_label = str(state.get("filter_label") or "")
        sort_label = str(state.get("sort_label") or "")
        if filter_label in filter_labels:
            self.benchmark_fixture_filter_var.set(filter_label)
        if sort_label in sort_labels:
            self.benchmark_fixture_sort_var.set(sort_label)
        if self._benchmark_primary_summary_payload is not None or self._benchmark_compare_summary_payload is not None:
            self._render_fixture_diff_table(self._benchmark_fixture_diff_records)

        selected_fixture = str(state.get("selected_fixture") or "")
        if selected_fixture in getattr(self, "_benchmark_entry_by_label", {}):
            self.benchmark_fixture_var.set(selected_fixture)
            self._on_benchmark_fixture_selected(selected_fixture)

        for attr_name, key in (
            ("benchmark_preview_primary_box", "preview_primary_text"),
            ("benchmark_preview_compare_box", "preview_compare_text"),
            ("benchmark_preview_diff_box", "preview_diff_text"),
        ):
            textbox = getattr(self, attr_name, None)
            if textbox is not None:
                self._set_textbox(textbox, str(state.get(key) or textbox.get("0.0", "end").rstrip("\n")))

    def _focus_detached_benchmark_window(self) -> None:
        window = getattr(self, "_detached_benchmark_window", None)
        if window is None or not window.winfo_exists():
            return
        window.deiconify()
        window.lift()
        window.focus_force()

    def _render_detached_benchmark_placeholder(self) -> None:
        root_tab = getattr(self, "benchmark_root_tab", None)
        if root_tab is None:
            return
        self._clear_benchmark_container(root_tab)
        root_tab.grid_columnconfigure(0, weight=1)
        root_tab.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(
            root_tab,
            fg_color=self._SECTION_SURFACE,
            border_width=1,
            border_color=self._SECTION_BORDER,
        )
        frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text=t("gui.benchmark.detached_title"),
            anchor="w",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))
        self.benchmark_detached_notice_label = ctk.CTkLabel(
            frame,
            text=t("gui.benchmark.detached_notice"),
            anchor="w",
            justify="left",
            text_color=self._MUTED_TEXT,
            font=ctk.CTkFont(size=12),
        )
        self.benchmark_detached_notice_label.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 16))

        ctk.CTkButton(
            actions,
            text=t("gui.benchmark.focus_window"),
            width=160,
            command=self._focus_detached_benchmark_window,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            actions,
            text=t("gui.benchmark.redock"),
            width=140,
            command=self._benchmark_redock_detached_window,
        ).grid(row=0, column=1)
        self._refresh_benchmark_tab_layout()

    def _rebuild_main_benchmark_surface(self, state: dict[str, Any] | None = None) -> None:
        root_tab = getattr(self, "benchmark_root_tab", None)
        if root_tab is None:
            return
        self.benchmark_detached_notice_label = None
        self._clear_benchmark_container(root_tab)
        BenchmarkTabBuilder(self, parent=root_tab).build()
        self._restore_benchmark_surface_state(state)
        self._refresh_benchmark_tab_layout()

    def _rebuild_detached_benchmark_surface(self, state: dict[str, Any] | None = None) -> None:
        container = getattr(self, "_detached_benchmark_container", None)
        if container is None:
            return
        self._clear_benchmark_container(container)
        BenchmarkTabBuilder(self, parent=container, detached=True).build()
        self._app_helpers().surfaces().bind_detached_redock_shortcuts(container, self._benchmark_redock_detached_window)
        self._restore_benchmark_surface_state(state)
        self._refresh_benchmark_tab_layout()

    def _destroy_detached_benchmark_window(self, *, persist_geometry: bool = True) -> None:
        window = getattr(self, "_detached_benchmark_window", None)
        if window is not None and window.winfo_exists():
            if persist_geometry:
                self._app_helpers().surfaces().save_detached_page_geometry("benchmark", window.geometry())
            window.destroy()
        self._detached_benchmark_window = None
        self._detached_benchmark_container = None
        self._detached_benchmark_redock_btn = None

    def _benchmark_open_detached_window(self, *, restoring: bool = False) -> None:
        existing_window = getattr(self, "_detached_benchmark_window", None)
        if existing_window is not None and existing_window.winfo_exists():
            self._focus_detached_benchmark_window()
            return

        benchmark_root_tab = getattr(self, "benchmark_root_tab", None)
        if benchmark_root_tab is None:
            return

        state = self._snapshot_benchmark_surface_state()
        detached_window = ctk.CTkToplevel(self)
        detached_window.title(t("gui.benchmark.detached_title"))
        saved_geometry = str(config.get("gui", "detached_benchmark_geometry", "") or "").strip()
        detached_window.geometry(saved_geometry or "1280x900")
        detached_window.minsize(960, 680)
        self._schedule_titlebar_fix(detached_window)

        container = ctk.CTkFrame(detached_window, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self._detached_benchmark_window = detached_window
        self._detached_benchmark_container = container
        self._app_helpers().surfaces().set_page_detached("benchmark", True)
        self._rebuild_detached_benchmark_surface(state)
        self._render_detached_benchmark_placeholder()

        def _persist_geometry(_event: Any = None) -> None:
            if not detached_window.winfo_exists() or getattr(self, "_app_destroying", False):
                return
            try:
                self._app_helpers().surfaces().save_detached_page_geometry("benchmark", detached_window.geometry())
            except Exception:
                pass

        def _on_close() -> None:
            if getattr(self, "_app_destroying", False):
                self._destroy_detached_benchmark_window(persist_geometry=False)
                return
            self._benchmark_redock_detached_window()

        detached_window.protocol("WM_DELETE_WINDOW", _on_close)
        detached_window.bind("<Configure>", _persist_geometry, add="+")

        if restoring:
            self.status_var.set(t("gui.benchmark.window_restored"))
        self._focus_detached_benchmark_window()

    def _benchmark_redock_detached_window(self) -> None:
        window = getattr(self, "_detached_benchmark_window", None)
        if window is None or not window.winfo_exists():
            self._app_helpers().surfaces().set_page_detached("benchmark", False)
            return

        state = self._snapshot_benchmark_surface_state()
        self._destroy_detached_benchmark_window()
        self._app_helpers().surfaces().set_page_detached("benchmark", False)
        self._rebuild_main_benchmark_surface(state)
        try:
            self.tabs.set(t("gui.tab.benchmarks"))
        except Exception:
            pass

    def _build_fixture_presence_filters(self) -> list[tuple[str, str, tuple[str, ...] | None]]:
        return [
            (t("gui.benchmark.fixture_filter_all"), "all", None),
            (t("gui.benchmark.fixture_filter_shared"), "shared", (t("gui.benchmark.fixture_presence_shared"),)),
            (t("gui.benchmark.fixture_filter_primary_only"), "primary_only", (t("gui.benchmark.fixture_presence_primary_only"),)),
            (t("gui.benchmark.fixture_filter_compare_only"), "compare_only", (t("gui.benchmark.fixture_presence_compare_only"),)),
        ]

    def _build_fixture_sort_options(self) -> list[tuple[str, str]]:
        return [
            (t("gui.benchmark.fixture_sort_default"), "default"),
            (t("gui.benchmark.fixture_sort_score_delta"), "score_delta"),
            (t("gui.benchmark.fixture_sort_status_churn"), "status_churn"),
        ]

    def _on_fixture_diff_filter_selected(self, _selected_label: str) -> None:
        self._render_fixture_diff_table(self._benchmark_fixture_diff_records)
        self._persist_benchmark_browser_state()

    def _on_fixture_diff_sort_selected(self, _selected_label: str) -> None:
        self._render_fixture_diff_table(self._benchmark_fixture_diff_records)
        self._persist_benchmark_browser_state()

    def _browse_benchmark_fixtures_root(self) -> None:
        if getattr(self, "_testing_mode", False):
            return
        selected = filedialog.askdirectory()
        if not selected:
            return
        self.benchmark_fixtures_root_entry.delete(0, "end")
        self.benchmark_fixtures_root_entry.insert(0, selected)
        self._persist_benchmark_browser_state()

    def _browse_benchmark_artifacts_root(self) -> None:
        if getattr(self, "_testing_mode", False):
            return
        selected = filedialog.askdirectory()
        if not selected:
            return
        self.benchmark_artifacts_root_entry.delete(0, "end")
        self.benchmark_artifacts_root_entry.insert(0, selected)
        self._refresh_benchmark_summary_selector(selected)
        self._persist_benchmark_browser_state()

    def _browse_benchmark_summary_artifact(self) -> None:
        if getattr(self, "_testing_mode", False):
            return
        initial_dir = self._current_benchmark_artifacts_root()
        path_str = filedialog.askopenfilename(
            initialdir=str(initial_dir) if initial_dir is not None else None,
            filetypes=[("JSON", "*.json"), (t("common.filetype_all"), "*.*")]
        )
        if not path_str:
            return
        try:
            self._load_benchmark_summary_artifact(self._validate_benchmark_summary_path(path_str))
        except Exception as exc:
            message = t("gui.benchmark.summary_outside_root", error=exc)
            self._show_toast(message, error=True)
            self.status_var.set(message)

    def _browse_benchmark_compare_artifact(self) -> None:
        if getattr(self, "_testing_mode", False):
            return
        initial_dir = self._current_benchmark_artifacts_root()
        path_str = filedialog.askopenfilename(
            initialdir=str(initial_dir) if initial_dir is not None else None,
            filetypes=[("JSON", "*.json"), (t("common.filetype_all"), "*.*")]
        )
        if not path_str:
            return
        try:
            self._load_benchmark_summary_artifact(
                self._validate_benchmark_summary_path(path_str),
                compare=True,
            )
        except Exception as exc:
            message = t("gui.benchmark.summary_outside_root", error=exc)
            self._show_toast(message, error=True)
            self.status_var.set(message)

    def _reload_benchmark_source(self) -> None:
        source_kind = getattr(self, "_benchmark_source_kind", None)
        source_path = getattr(self, "_benchmark_source_path", None)
        if source_kind == "summary" and source_path:
            self._load_benchmark_summary_artifact(source_path)
            return
        self._load_benchmark_fixture_catalog()

    def _load_benchmark_fixture_catalog(self, fixtures_root: str | Path | None = None) -> None:
        if fixtures_root is None:
            raw_root_text = self.benchmark_fixtures_root_entry.get().strip()
            if not raw_root_text:
                self._show_toast(t("gui.benchmark.invalid_fixtures_root"), error=True)
                self.status_var.set(t("gui.benchmark.invalid_fixtures_root"))
                return
            raw_root = Path(raw_root_text)
        else:
            raw_root = Path(fixtures_root)

        if not str(raw_root).strip():
            self._show_toast(t("gui.benchmark.invalid_fixtures_root"), error=True)
            self.status_var.set(t("gui.benchmark.invalid_fixtures_root"))
            return

        fixtures_root_path = raw_root.expanduser().resolve()
        if not fixtures_root_path.exists() or not fixtures_root_path.is_dir():
            self._show_toast(t("gui.benchmark.invalid_fixtures_root"), error=True)
            self.status_var.set(t("gui.benchmark.invalid_fixtures_root"))
            return

        try:
            entries = []
            for fixture in discover_fixtures(fixtures_root_path):
                entry = describe_fixture_catalog_entry(fixture)
                entry["fixture_dir"] = str(fixture.manifest_path.parent)
                if fixture.project_dir is not None:
                    entry["project_dir"] = str(fixture.project_dir)
                entry["manifest_path"] = str(fixture.manifest_path)
                entries.append(entry)
        except Exception as exc:
            logger.exception("Failed to load benchmark fixture catalog")
            message = t("gui.benchmark.catalog_load_error", error=exc)
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return

        self.benchmark_fixtures_root_entry.delete(0, "end")
        self.benchmark_fixtures_root_entry.insert(0, str(fixtures_root_path))
        self._benchmark_source_kind = "catalog"
        self._benchmark_source_path = str(fixtures_root_path)
        self._set_benchmark_browser_entries(entries, source_text=t("gui.benchmark.source_catalog", path=fixtures_root_path))
        self._persist_benchmark_browser_state()
        self.status_var.set(t("gui.benchmark.catalog_loaded_status", count=len(entries)))

    def _load_benchmark_summary_artifact(
        self,
        path_str: str | Path,
        *,
        compare: bool = False,
        persist_state: bool = True,
    ) -> None:
        summary_path = Path(path_str).expanduser().resolve()
        try:
            payload = self._read_benchmark_summary_payload(summary_path)
        except Exception as exc:
            logger.exception("Failed to load benchmark summary artifact")
            message = t("gui.benchmark.summary_load_error", error=exc)
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return

        if compare:
            self._benchmark_compare_summary_path = str(summary_path)
            self._benchmark_compare_summary_payload = payload
            self._render_summary_overviews()
            self._restore_benchmark_comparison_view_state()
            if persist_state:
                self._persist_benchmark_browser_state()
            self.status_var.set(
                t(
                    "gui.benchmark.compare_loaded_status",
                    count=len(self._representative_fixture_ids(payload)),
                )
            )
            return

        raw_entries = payload.get("representative_fixtures")
        if not isinstance(raw_entries, list):
            message = t("gui.benchmark.summary_missing_fixtures")
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return

        entries = [entry for entry in (self._normalize_benchmark_entry(item) for item in raw_entries) if entry]
        self._benchmark_source_kind = "summary"
        self._benchmark_source_path = str(summary_path)
        self._benchmark_primary_summary_path = str(summary_path)
        self._benchmark_primary_summary_payload = payload
        self._set_benchmark_browser_entries(entries, source_text=t("gui.benchmark.source_summary", path=summary_path.name))
        self._render_summary_overviews()
        self._restore_benchmark_comparison_view_state()
        if persist_state:
            self._persist_benchmark_browser_state()
        self.status_var.set(t("gui.benchmark.summary_loaded_status", count=len(entries)))

    def _load_selected_benchmark_summary(self) -> None:
        selected_path = self._selected_benchmark_summary_path()
        if selected_path is None:
            message = t("gui.benchmark.no_summary_selected")
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        self._load_benchmark_summary_artifact(self._validate_benchmark_summary_path(selected_path))

    def _compare_selected_benchmark_summary(self) -> None:
        selected_path = self._selected_benchmark_summary_path()
        if selected_path is None:
            message = t("gui.benchmark.no_summary_selected")
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        self._load_benchmark_summary_artifact(
            self._validate_benchmark_summary_path(selected_path),
            compare=True,
        )

    def _refresh_benchmark_summary_selector(self, artifacts_root: str | Path | None = None) -> None:
        if artifacts_root is None:
            raw_root_text = self.benchmark_artifacts_root_entry.get().strip()
            if not raw_root_text:
                self._set_benchmark_summary_selector([])
                return
            raw_root = Path(raw_root_text)
        else:
            raw_root = Path(artifacts_root)

        artifacts_root_path = raw_root.expanduser().resolve()
        if not artifacts_root_path.exists() or not artifacts_root_path.is_dir():
            self._set_benchmark_summary_selector([])
            return

        self.benchmark_artifacts_root_entry.delete(0, "end")
        self.benchmark_artifacts_root_entry.insert(0, str(artifacts_root_path))
        candidates = self._discover_benchmark_summary_artifacts(artifacts_root_path)
        self._set_benchmark_summary_selector(candidates, root=artifacts_root_path)
        self._persist_benchmark_browser_state()

    def _set_benchmark_summary_selector(self, paths: list[Path], *, root: Path | None = None) -> None:
        self._benchmark_summary_candidates = {}
        if root is None and paths:
            root = paths[0].parent

        for path in paths:
            label = self._benchmark_summary_label(path, root)
            self._benchmark_summary_candidates[label] = path

        if self._benchmark_summary_candidates:
            labels = list(self._benchmark_summary_candidates.keys())
            self.benchmark_summary_selector_menu.configure(values=labels, state="normal")
            self.benchmark_summary_selector_var.set(labels[0])
            return

        empty_value = t("gui.benchmark.no_summaries")
        self.benchmark_summary_selector_menu.configure(values=[empty_value], state="disabled")
        self.benchmark_summary_selector_var.set(empty_value)

    def _selected_benchmark_summary_path(self) -> Path | None:
        return self._benchmark_summary_candidates.get(self.benchmark_summary_selector_var.get())

    def _current_benchmark_artifacts_root(self) -> Path | None:
        entry = getattr(self, "benchmark_artifacts_root_entry", None)
        if entry is None:
            return None
        raw_root = str(entry.get() or "").strip()
        if not raw_root:
            return None
        return Path(raw_root).expanduser().resolve()

    def _current_benchmark_fixtures_root(self) -> Path | None:
        entry = getattr(self, "benchmark_fixtures_root_entry", None)
        if entry is None:
            return None
        raw_root = str(entry.get() or "").strip()
        if not raw_root:
            return None
        return Path(raw_root).expanduser().resolve()

    def _resolve_benchmark_source_entry_path(self, raw_path: str) -> Path | None:
        fixtures_root = self._current_benchmark_fixtures_root()
        if fixtures_root is None:
            return None
        candidate = Path(raw_path).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (fixtures_root / candidate).resolve()
        if resolved == fixtures_root or resolved.is_relative_to(fixtures_root):
            return resolved
        logger.warning("Skipping out-of-scope benchmark source path: %s", raw_path)
        return None

    def _validate_benchmark_summary_path(self, path: str | Path) -> Path:
        summary_path = Path(path).expanduser().resolve()
        artifacts_root = self._current_benchmark_artifacts_root()
        if artifacts_root is None:
            return summary_path
        if summary_path == artifacts_root or summary_path.is_relative_to(artifacts_root):
            return summary_path
        raise ValueError("Benchmark summary must stay within the configured saved runs folder")

    def _allowed_benchmark_artifact_root(self, summary_path: Path) -> Path:
        artifacts_root = self._current_benchmark_artifacts_root()
        if artifacts_root is not None and (
            summary_path == artifacts_root or summary_path.is_relative_to(artifacts_root)
        ):
            return artifacts_root
        return summary_path.parent.resolve()

    def _discover_benchmark_summary_artifacts(self, artifacts_root: Path) -> list[Path]:
        candidates: list[Path] = []
        for path in sorted(artifacts_root.rglob("*.json")):
            try:
                payload = self._read_benchmark_summary_payload(path)
            except Exception:
                continue
            if self._is_benchmark_summary_payload(payload):
                candidates.append(path)
        return candidates

    def _read_benchmark_summary_payload(self, path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Benchmark summary payload must be a JSON object")
        return payload

    def _is_benchmark_summary_payload(self, payload: dict[str, Any]) -> bool:
        return any(
            key in payload
            for key in (
                "representative_fixtures",
                "representative_fixture_ids",
                "score_summary",
                "generated_reports",
                "pair_summaries",
                "baseline_results",
                "fixtures_evaluated",
            )
        )

    def _benchmark_summary_label(self, path: Path, root: Path | None) -> str:
        if root is not None:
            try:
                return str(path.relative_to(root))
            except ValueError:
                return path.name
        return path.name

    def _set_benchmark_browser_entries(self, entries: list[dict[str, Any]], *, source_text: str) -> None:
        normalized_entries = [entry for entry in (self._normalize_benchmark_entry(item) for item in entries) if entry]
        normalized_entries.sort(key=lambda entry: (str(entry["id"]).lower(), str(entry["title"]).lower()))
        self._benchmark_entries = normalized_entries
        self._benchmark_entry_by_label = {
            self._benchmark_entry_label(entry): entry for entry in normalized_entries
        }

        labels = list(self._benchmark_entry_by_label.keys())
        if labels:
            self.benchmark_fixture_menu.configure(values=labels, state="normal")
            self.benchmark_fixture_var.set(labels[0])
            selected_entry = self._benchmark_entry_by_label[labels[0]]
        else:
            empty_value = t("gui.benchmark.none_available")
            self.benchmark_fixture_menu.configure(values=[empty_value], state="disabled")
            self.benchmark_fixture_var.set(empty_value)
            selected_entry = None

        self.benchmark_source_value.configure(text=source_text)
        self.benchmark_count_value.configure(text=t("gui.benchmark.count_value", count=len(normalized_entries)))
        self._set_textbox(self.benchmark_catalog_box, self._format_benchmark_catalog(normalized_entries))
        self._render_benchmark_details(selected_entry)

    def _on_benchmark_fixture_selected(self, label: str) -> None:
        entry = self._benchmark_entry_by_label.get(label)
        self._render_benchmark_details(entry)

    def _render_benchmark_details(self, entry: dict[str, Any] | None) -> None:
        if not entry:
            self._set_textbox(self.benchmark_detail_box, t("gui.benchmark.detail_empty"))
            return

        benchmark_metadata = entry.get("benchmark_metadata")
        metadata_review_types = []
        if isinstance(benchmark_metadata, dict):
            metadata_review_types = benchmark_metadata.get("review_types") if isinstance(benchmark_metadata.get("review_types"), list) else []

        lines = [
            f"{t('gui.benchmark.detail_id')} {entry['id']}",
            f"{t('gui.benchmark.detail_title')} {entry['title']}",
            f"{t('gui.benchmark.detail_scope')} {entry['scope']}",
            f"{t('gui.benchmark.detail_review_types')} {', '.join(entry['review_types']) or '-'}",
            f"{t('gui.benchmark.detail_fixture_tags')} {', '.join(self._metadata_string_list(benchmark_metadata, 'fixture_tags')) or '-'}",
            f"{t('gui.benchmark.detail_expected_focus')} {', '.join(self._metadata_string_list(benchmark_metadata, 'expected_focus')) or '-'}",
        ]

        if metadata_review_types:
            lines.append("")
            lines.append(t("gui.benchmark.detail_registry_title"))
            for item in metadata_review_types:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or "").strip()
                label = str(item.get("label") or key).strip() or key
                group = str(item.get("group") or "").strip()
                tags = ", ".join(self._metadata_string_list(item.get("metadata"), "fixture_tags")) or "-"
                focus = ", ".join(self._metadata_string_list(item.get("metadata"), "expected_focus")) or "-"
                lines.append(f"- {label} [{key}]")
                lines.append(f"  {t('gui.benchmark.detail_registry_group')} {group or '-'}")
                lines.append(f"  {t('gui.benchmark.detail_fixture_tags')} {tags}")
                lines.append(f"  {t('gui.benchmark.detail_expected_focus')} {focus}")

        self._set_textbox(self.benchmark_detail_box, "\n".join(lines))

    def _format_benchmark_catalog(self, entries: list[dict[str, Any]]) -> str:
        if not entries:
            return t("gui.benchmark.catalog_empty")

        lines: list[str] = []
        for entry in entries:
            benchmark_metadata = entry.get("benchmark_metadata")
            tags = ", ".join(self._metadata_string_list(benchmark_metadata, "fixture_tags")) or "-"
            focus = ", ".join(self._metadata_string_list(benchmark_metadata, "expected_focus")) or "-"
            lines.append(f"{entry['id']} | {entry['title']}")
            lines.append(f"  {t('gui.benchmark.detail_scope')} {entry['scope']}")
            lines.append(f"  {t('gui.benchmark.detail_review_types')} {', '.join(entry['review_types']) or '-'}")
            lines.append(f"  {t('gui.benchmark.detail_fixture_tags')} {tags}")
            lines.append(f"  {t('gui.benchmark.detail_expected_focus')} {focus}")
            lines.append("")
        return "\n".join(lines).rstrip()

    def _benchmark_entry_label(self, entry: dict[str, Any]) -> str:
        return f"{entry['id']} - {entry['title']}"

    def _normalize_benchmark_entry(self, entry: Any) -> dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None
        fixture_id = str(entry.get("id") or "").strip()
        title = str(entry.get("title") or fixture_id).strip()
        if not fixture_id:
            return None

        raw_review_types = entry.get("review_types")
        review_types = [
            str(item).strip()
            for item in raw_review_types
            if isinstance(item, str) and str(item).strip()
        ] if isinstance(raw_review_types, list) else []

        benchmark_metadata = entry.get("benchmark_metadata") if isinstance(entry.get("benchmark_metadata"), dict) else {}
        normalized_entry = {
            "id": fixture_id,
            "title": title,
            "scope": str(entry.get("scope") or "project"),
            "review_types": review_types,
            "benchmark_metadata": benchmark_metadata,
        }
        for key in ("fixture_dir", "project_dir", "manifest_path"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                normalized_entry[key] = value.strip()
        return normalized_entry

    def _open_benchmark_source_folder(self) -> None:
        path = self._current_benchmark_open_path()
        if path is None:
            message = t("gui.benchmark.no_openable_source")
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        try:
            self._open_directory_path(path)
        except Exception as exc:
            logger.exception("Failed to open benchmark source folder")
            message = t("gui.benchmark.open_source_error", error=exc)
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        self.status_var.set(t("gui.benchmark.open_source_status", path=path.name))

    def _open_selected_benchmark_summary_json(self) -> None:
        path = self._selected_benchmark_summary_path() or self._current_primary_summary_path()
        if path is None:
            message = t("gui.benchmark.no_summary_json")
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        try:
            self._open_path(self._validate_benchmark_summary_path(path))
        except Exception as exc:
            logger.exception("Failed to open benchmark summary JSON")
            message = t("gui.benchmark.open_summary_json_error", error=exc)
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        self.status_var.set(t("gui.benchmark.open_summary_json_status", path=path.name))

    def _open_selected_benchmark_report_directory(self) -> None:
        path = self._selected_benchmark_report_directory()
        if path is None:
            message = t("gui.benchmark.no_report_dir")
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        try:
            self._open_directory_path(path)
        except Exception as exc:
            logger.exception("Failed to open benchmark report directory")
            message = t("gui.benchmark.open_report_dir_error", error=exc)
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        self.status_var.set(t("gui.benchmark.open_report_dir_status", path=path.name))

    def _open_fixture_diff_report(self, fixture_id: str, side: str) -> None:
        row = self._benchmark_fixture_diff_rows.get(fixture_id)
        report_path = None if row is None else row.get(f"{side}_report_path")
        if not isinstance(report_path, Path):
            message = t("gui.benchmark.no_fixture_report", fixture_id=fixture_id)
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        try:
            self._open_path(report_path)
        except Exception as exc:
            logger.exception("Failed to open fixture diff report")
            message = t("gui.benchmark.open_fixture_report_error", error=exc)
            self._show_toast(message, error=True)
            self.status_var.set(message)
            return
        self.status_var.set(
            t(
                "gui.benchmark.open_fixture_report_status",
                fixture_id=fixture_id,
                side=t("gui.benchmark.fixture_side_primary") if side == "primary" else t("gui.benchmark.fixture_side_compare"),
            )
        )

    def _preview_fixture_diff_reports(self, fixture_id: str) -> None:
        row = self._benchmark_fixture_diff_rows.get(fixture_id)
        if row is None:
            return
        primary_text = self._format_report_preview(
            row.get("primary_report_path"),
            empty_text=t("gui.benchmark.preview_primary_missing"),
        )
        compare_text = self._format_report_preview(
            row.get("compare_report_path"),
            empty_text=t("gui.benchmark.preview_compare_missing"),
        )
        self._set_textbox(self.benchmark_preview_primary_box, primary_text)
        self._set_textbox(self.benchmark_preview_compare_box, compare_text)
        self._set_textbox(
            self.benchmark_preview_diff_box,
            self._build_report_diff_text(
                row.get("primary_report_path"),
                row.get("compare_report_path"),
                primary_text,
                compare_text,
            ),
        )
        self.status_var.set(t("gui.benchmark.preview_loaded_status", fixture_id=fixture_id))

    def _show_fixture_diff_only(self, fixture_id: str) -> None:
        self._preview_fixture_diff_reports(fixture_id)
        self.status_var.set(t("gui.benchmark.preview_diff_loaded_status", fixture_id=fixture_id))

    def _current_benchmark_open_path(self) -> Path | None:
        selected_entry = self._benchmark_entry_by_label.get(self.benchmark_fixture_var.get())
        if selected_entry is not None:
            for key in ("project_dir", "fixture_dir"):
                raw_path = selected_entry.get(key)
                if isinstance(raw_path, str) and raw_path.strip():
                    resolved = self._resolve_benchmark_source_entry_path(raw_path)
                    if resolved is not None:
                        return resolved

        source_kind = getattr(self, "_benchmark_source_kind", None)
        source_path = getattr(self, "_benchmark_source_path", None)
        if source_kind == "summary" and source_path:
            return Path(source_path).parent
        if source_kind == "catalog" and source_path:
            return Path(source_path)
        return None

    def _open_directory_path(self, path: Path) -> None:
        self._open_path(path)

    def _open_path(self, path: Path) -> None:
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]
            return
        webbrowser.open(path.resolve().as_uri())

    def _render_summary_overviews(self) -> None:
        self._set_textbox(
            self.benchmark_primary_summary_box,
            self._format_summary_overview(
                self._benchmark_primary_summary_path,
                self._benchmark_primary_summary_payload,
                empty_text=t("gui.benchmark.primary_summary_empty"),
            ),
        )
        self._set_textbox(
            self.benchmark_compare_summary_box,
            self._format_summary_overview(
                self._benchmark_compare_summary_path,
                self._benchmark_compare_summary_payload,
                empty_text=t("gui.benchmark.compare_summary_empty"),
                compare_to=self._benchmark_primary_summary_payload,
            ),
        )
        self.benchmark_takeaways_label.configure(text=self._format_benchmark_takeaways())
        self._render_fixture_diff_table(
            self._build_fixture_diff_records(
                self._benchmark_primary_summary_payload,
                self._benchmark_compare_summary_payload,
                primary_summary_path=self._current_primary_summary_path(),
                compare_summary_path=Path(self._benchmark_compare_summary_path) if self._benchmark_compare_summary_path else None,
            )
        )

    def _format_benchmark_takeaways(self) -> str:
        primary = self._benchmark_primary_summary_payload
        compare = self._benchmark_compare_summary_payload
        if not isinstance(primary, dict):
            return t("gui.benchmark.takeaways_empty")

        primary_summary = primary.get("score_summary") if isinstance(primary.get("score_summary"), dict) else {}
        primary_score = primary.get("overall_score")
        if primary_score is None:
            primary_score = primary_summary.get("overall_score")
        primary_fixtures = primary.get("fixtures_evaluated") or primary_summary.get("fixtures_evaluated") or len(self._representative_fixture_ids(primary))
        primary_passed = primary.get("fixtures_passed") or primary_summary.get("fixtures_passed") or 0
        primary_failed = primary.get("fixtures_failed") or primary_summary.get("fixtures_failed") or 0

        if not isinstance(compare, dict):
            return t(
                "gui.benchmark.takeaways_single",
                backend=primary.get("backend") or "-",
                score=self._format_score_value(primary_score),
                fixtures=primary_fixtures,
                passed=primary_passed,
                failed=primary_failed,
            )

        compare_summary = compare.get("score_summary") if isinstance(compare.get("score_summary"), dict) else {}
        compare_score = compare.get("overall_score")
        if compare_score is None:
            compare_score = compare_summary.get("overall_score")
        compare_passed = compare.get("fixtures_passed") or compare_summary.get("fixtures_passed") or 0

        primary_score_value = float(primary_score or 0)
        compare_score_value = float(compare_score or 0)
        if compare_score_value > primary_score_value:
            winner = str(compare.get("backend") or "-")
        elif compare_score_value < primary_score_value:
            winner = str(primary.get("backend") or "-")
        else:
            winner = t("gui.benchmark.takeaways_tie")

        return t(
            "gui.benchmark.takeaways_compare",
            winner=winner,
            primary_backend=primary.get("backend") or "-",
            compare_backend=compare.get("backend") or "-",
            score_delta=f"{compare_score_value - primary_score_value:+.4f}",
            pass_delta=f"{int(compare_passed) - int(primary_passed):+d}",
        )

    def _format_summary_overview(
        self,
        path_str: str | None,
        payload: dict[str, Any] | None,
        *,
        empty_text: str,
        compare_to: dict[str, Any] | None = None,
    ) -> str:
        if not path_str or not isinstance(payload, dict):
            return empty_text

        summary = payload.get("score_summary") if isinstance(payload.get("score_summary"), dict) else {}
        representative_ids = self._representative_fixture_ids(payload)
        fixtures_evaluated = payload.get("fixtures_evaluated") or summary.get("fixtures_evaluated") or len(representative_ids)
        fixtures_passed = payload.get("fixtures_passed") or summary.get("fixtures_passed")
        fixtures_failed = payload.get("fixtures_failed") or summary.get("fixtures_failed")
        overall_score = payload.get("overall_score")
        if overall_score is None:
            overall_score = summary.get("overall_score")

        lines = [
            f"{t('gui.benchmark.summary_path')} {Path(path_str).name}",
            f"{t('gui.benchmark.summary_backend')} {payload.get('backend') or '-'}",
            f"{t('gui.benchmark.summary_status')} {payload.get('status') or '-'}",
            f"{t('gui.benchmark.summary_fixtures')} {fixtures_evaluated}",
            f"{t('gui.benchmark.summary_passed')} {fixtures_passed if fixtures_passed is not None else '-'}",
            f"{t('gui.benchmark.summary_failed')} {fixtures_failed if fixtures_failed is not None else '-'}",
            f"{t('gui.benchmark.summary_score')} {self._format_score_value(overall_score)}",
            f"{t('gui.benchmark.summary_representative_count')} {len(representative_ids)}",
        ]
        if representative_ids:
            lines.append(f"{t('gui.benchmark.summary_representative_ids')} {', '.join(representative_ids[:8])}")

        if isinstance(compare_to, dict):
            comparison_lines = self._format_summary_comparison(compare_to, payload)
            if comparison_lines:
                lines.append("")
                lines.extend(comparison_lines)

        return "\n".join(lines)

    def _format_summary_comparison(self, primary_payload: dict[str, Any], compare_payload: dict[str, Any]) -> list[str]:
        primary_score = primary_payload.get("overall_score")
        if primary_score is None and isinstance(primary_payload.get("score_summary"), dict):
            primary_score = primary_payload["score_summary"].get("overall_score")
        compare_score = compare_payload.get("overall_score")
        if compare_score is None and isinstance(compare_payload.get("score_summary"), dict):
            compare_score = compare_payload["score_summary"].get("overall_score")

        primary_ids = set(self._representative_fixture_ids(primary_payload))
        compare_ids = set(self._representative_fixture_ids(compare_payload))
        lines = [t("gui.benchmark.summary_compare_title")]
        if primary_score is not None and compare_score is not None:
            lines.append(
                f"{t('gui.benchmark.summary_score_delta')} {round(float(compare_score) - float(primary_score), 4):+.4f}"
            )
        lines.append(f"{t('gui.benchmark.summary_shared_ids')} {', '.join(sorted(primary_ids & compare_ids)) or '-'}")
        lines.append(f"{t('gui.benchmark.summary_only_primary_ids')} {', '.join(sorted(primary_ids - compare_ids)) or '-'}")
        lines.append(f"{t('gui.benchmark.summary_only_compare_ids')} {', '.join(sorted(compare_ids - primary_ids)) or '-'}")
        fixture_delta_lines = self._format_fixture_level_deltas(primary_payload, compare_payload)
        if fixture_delta_lines:
            lines.append("")
            lines.extend(fixture_delta_lines)
        return lines

    def _format_fixture_level_deltas(self, primary_payload: dict[str, Any], compare_payload: dict[str, Any]) -> list[str]:
        diff_records = self._build_fixture_diff_records(
            primary_payload,
            compare_payload,
            primary_summary_path=self._current_primary_summary_path(),
            compare_summary_path=Path(self._benchmark_compare_summary_path) if self._benchmark_compare_summary_path else None,
        )
        lines: list[str] = [t("gui.benchmark.fixture_compare_title")]
        changed_lines = [f"- {record['fixture_id']}: {record['summary']}" for record in diff_records]

        if changed_lines:
            lines.extend(changed_lines)
        else:
            lines.append(t("gui.benchmark.fixture_compare_none"))
        return lines

    def _build_fixture_diff_records(
        self,
        primary_payload: dict[str, Any] | None,
        compare_payload: dict[str, Any] | None,
        *,
        primary_summary_path: Path | None,
        compare_summary_path: Path | None,
    ) -> list[dict[str, Any]]:
        if not isinstance(primary_payload, dict) or not isinstance(compare_payload, dict):
            return []

        primary_snapshots = self._collect_fixture_snapshots(primary_payload, summary_path=primary_summary_path)
        compare_snapshots = self._collect_fixture_snapshots(compare_payload, summary_path=compare_summary_path)
        shared_ids = sorted(set(primary_snapshots) & set(compare_snapshots))
        primary_only_ids = sorted(set(primary_snapshots) - set(compare_snapshots))
        compare_only_ids = sorted(set(compare_snapshots) - set(primary_snapshots))
        records: list[dict[str, Any]] = []

        for fixture_id in shared_ids:
            primary = primary_snapshots[fixture_id]
            compare = compare_snapshots[fixture_id]
            deltas: list[str] = []

            primary_score = primary.get("score")
            compare_score = compare.get("score")
            score_delta_text = "-"
            if isinstance(primary_score, (int, float)) and isinstance(compare_score, (int, float)):
                score_delta = round(float(compare_score) - float(primary_score), 4)
                score_delta_text = f"{score_delta:+.4f}"
                if score_delta != 0:
                    deltas.append(f"{t('gui.benchmark.fixture_compare_score_delta')} {score_delta_text}")

            primary_status = str(primary.get("status") or "").strip() or "-"
            compare_status = str(compare.get("status") or "").strip() or "-"
            if primary_status != "-" and compare_status != "-" and primary_status != compare_status:
                deltas.append(
                    t(
                        "gui.benchmark.fixture_compare_status_delta",
                        primary=primary_status,
                        compare=compare_status,
                    )
                )

            primary_types = set(primary.get("review_types") or [])
            compare_types = set(compare.get("review_types") or [])
            added_types = sorted(compare_types - primary_types)
            removed_types = sorted(primary_types - compare_types)
            type_deltas: list[str] = []
            if added_types:
                added_text = ", ".join(added_types)
                deltas.append(t("gui.benchmark.fixture_compare_added_types", types=added_text))
                type_deltas.append(f"+ {added_text}")
            if removed_types:
                removed_text = ", ".join(removed_types)
                deltas.append(t("gui.benchmark.fixture_compare_removed_types", types=removed_text))
                type_deltas.append(f"- {removed_text}")

            if not deltas:
                continue

            records.append(
                {
                    "fixture_id": fixture_id,
                    "title": str(compare.get("title") or primary.get("title") or fixture_id),
                    "presence": t("gui.benchmark.fixture_presence_shared"),
                    "presence_rank": 0,
                    "primary_score": self._format_score_value(primary_score),
                    "compare_score": self._format_score_value(compare_score),
                    "score_delta": score_delta_text,
                    "score_delta_value": score_delta if isinstance(primary_score, (int, float)) and isinstance(compare_score, (int, float)) else None,
                    "primary_status": primary_status,
                    "compare_status": compare_status,
                    "status_changed": primary_status != "-" and compare_status != "-" and primary_status != compare_status,
                    "type_delta": " | ".join(type_deltas) if type_deltas else "-",
                    "summary": "; ".join(deltas),
                    "primary_report_path": primary.get("report_path"),
                    "compare_report_path": compare.get("report_path"),
                }
            )

        for fixture_id in primary_only_ids:
            primary = primary_snapshots[fixture_id]
            primary_types = ", ".join(primary.get("review_types") or []) or "-"
            records.append(
                {
                    "fixture_id": fixture_id,
                    "title": str(primary.get("title") or fixture_id),
                    "presence": t("gui.benchmark.fixture_presence_primary_only"),
                    "presence_rank": 1,
                    "primary_score": self._format_score_value(primary.get("score")),
                    "compare_score": "-",
                    "score_delta": "-",
                    "score_delta_value": None,
                    "primary_status": str(primary.get("status") or "-").strip() or "-",
                    "compare_status": "-",
                    "status_changed": False,
                    "type_delta": t("gui.benchmark.fixture_only_primary_types", types=primary_types),
                    "summary": t("gui.benchmark.fixture_only_primary_summary"),
                    "primary_report_path": primary.get("report_path"),
                    "compare_report_path": None,
                }
            )

        for fixture_id in compare_only_ids:
            compare = compare_snapshots[fixture_id]
            compare_types = ", ".join(compare.get("review_types") or []) or "-"
            records.append(
                {
                    "fixture_id": fixture_id,
                    "title": str(compare.get("title") or fixture_id),
                    "presence": t("gui.benchmark.fixture_presence_compare_only"),
                    "presence_rank": 2,
                    "primary_score": "-",
                    "compare_score": self._format_score_value(compare.get("score")),
                    "score_delta": "-",
                    "score_delta_value": None,
                    "primary_status": "-",
                    "compare_status": str(compare.get("status") or "-").strip() or "-",
                    "status_changed": False,
                    "type_delta": t("gui.benchmark.fixture_only_compare_types", types=compare_types),
                    "summary": t("gui.benchmark.fixture_only_compare_summary"),
                    "primary_report_path": None,
                    "compare_report_path": compare.get("report_path"),
                }
            )

        presence_rank = {
            t("gui.benchmark.fixture_presence_shared"): 0,
            t("gui.benchmark.fixture_presence_primary_only"): 1,
            t("gui.benchmark.fixture_presence_compare_only"): 2,
        }
        records.sort(key=lambda record: (presence_rank.get(str(record.get("presence")), 9), str(record["fixture_id"])))

        return records

    def _render_fixture_diff_table(self, records: list[dict[str, Any]]) -> None:
        self._benchmark_fixture_diff_records = records
        self._benchmark_fixture_diff_rows = {}
        filtered_records = self._sorted_fixture_diff_records(self._filtered_fixture_diff_records(records))

        for child in self.benchmark_fixture_diff_scroll.winfo_children():
            child.destroy()

        if not records:
            self.benchmark_fixture_diff_empty_label.configure(text=t("gui.benchmark.fixture_table_empty"))
            self.benchmark_fixture_diff_empty_label.grid()
            self.benchmark_fixture_diff_scroll.grid_remove()
            return

        if not filtered_records:
            self.benchmark_fixture_diff_empty_label.configure(text=t("gui.benchmark.fixture_table_filter_empty"))
            self.benchmark_fixture_diff_empty_label.grid()
            self.benchmark_fixture_diff_scroll.grid_remove()
            return

        self.benchmark_fixture_diff_empty_label.grid_remove()
        self.benchmark_fixture_diff_scroll.grid()

        for row_index, record in enumerate(filtered_records):
            row_frame = ctk.CTkFrame(self.benchmark_fixture_diff_scroll, fg_color="transparent")
            row_frame.grid(row=row_index, column=0, sticky="ew", pady=(0, 4))
            for column, weight in ((0, 2), (1, 1), (2, 1), (3, 1), (4, 1), (5, 2), (6, 0), (7, 0), (8, 0), (9, 0)):
                row_frame.grid_columnconfigure(column, weight=weight)

            cells = (
                record["fixture_id"],
                record["presence"],
                f"{record['primary_score']} / {record['primary_status']}",
                f"{record['compare_score']} / {record['compare_status']}",
                record["score_delta"],
                record["type_delta"],
            )
            labels: list[Any] = []
            for column, text in enumerate(cells):
                label = ctk.CTkLabel(row_frame, text=text, anchor="w", justify="left")
                label.grid(row=0, column=column, sticky="w", padx=(0, 8))
                labels.append(label)

            primary_button = ctk.CTkButton(
                row_frame,
                text=t("gui.benchmark.fixture_table_open_primary_short"),
                width=72,
                height=28,
                state="normal" if isinstance(record.get("primary_report_path"), Path) else "disabled",
                command=lambda fixture_id=record["fixture_id"]: self._open_fixture_diff_report(fixture_id, "primary"),
            )
            primary_button.grid(row=0, column=5, padx=(0, 8), sticky="w")

            compare_button = ctk.CTkButton(
                row_frame,
                text=t("gui.benchmark.fixture_table_open_compare_short"),
                width=72,
                height=28,
                state="normal" if isinstance(record.get("compare_report_path"), Path) else "disabled",
                command=lambda fixture_id=record["fixture_id"]: self._open_fixture_diff_report(fixture_id, "compare"),
            )
            compare_button.grid(row=0, column=7, padx=(0, 8), sticky="w")

            preview_button = ctk.CTkButton(
                row_frame,
                text=t("gui.benchmark.fixture_table_preview_short"),
                width=72,
                height=28,
                state="normal" if isinstance(record.get("primary_report_path"), Path) or isinstance(record.get("compare_report_path"), Path) else "disabled",
                command=lambda fixture_id=record["fixture_id"]: self._preview_fixture_diff_reports(fixture_id),
            )
            preview_button.grid(row=0, column=8, padx=(0, 8), sticky="w")

            diff_button = ctk.CTkButton(
                row_frame,
                text=t("gui.benchmark.fixture_table_diff_short"),
                width=72,
                height=28,
                state="normal" if isinstance(record.get("primary_report_path"), Path) or isinstance(record.get("compare_report_path"), Path) else "disabled",
                command=lambda fixture_id=record["fixture_id"]: self._show_fixture_diff_only(fixture_id),
            )
            diff_button.grid(row=0, column=9, sticky="w")

            self._benchmark_fixture_diff_rows[record["fixture_id"]] = {
                "frame": row_frame,
                "labels": labels,
                "primary_button": primary_button,
                "compare_button": compare_button,
                "preview_button": preview_button,
                "diff_button": diff_button,
                "primary_report_path": record.get("primary_report_path"),
                "compare_report_path": record.get("compare_report_path"),
                "record": record,
            }

    def _filtered_fixture_diff_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected_label = self.benchmark_fixture_filter_var.get()
        for label, _filter_key, allowed_presences in self._benchmark_fixture_presence_filters:
            if label != selected_label:
                continue
            if allowed_presences is None:
                return list(records)
            return [record for record in records if str(record.get("presence")) in allowed_presences]
        return list(records)

    def _sorted_fixture_diff_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected_label = self.benchmark_fixture_sort_var.get()
        selected_mode = "default"
        for label, sort_mode in self._benchmark_fixture_sort_options:
            if label == selected_label:
                selected_mode = sort_mode
                break

        if selected_mode == "score_delta":
            return sorted(records, key=self._fixture_diff_score_delta_sort_key)
        if selected_mode == "status_churn":
            return sorted(records, key=self._fixture_diff_status_churn_sort_key)
        return sorted(records, key=self._fixture_diff_default_sort_key)

    def _fixture_diff_default_sort_key(self, record: dict[str, Any]) -> tuple[int, str]:
        return (int(record.get("presence_rank", 9)), str(record.get("fixture_id") or ""))

    def _fixture_diff_score_delta_sort_key(self, record: dict[str, Any]) -> tuple[int, float, int, str]:
        score_delta_value = record.get("score_delta_value")
        has_delta = 0 if isinstance(score_delta_value, (int, float)) else 1
        delta_rank = -abs(float(score_delta_value)) if isinstance(score_delta_value, (int, float)) else 0.0
        return (has_delta, delta_rank, int(record.get("presence_rank", 9)), str(record.get("fixture_id") or ""))

    def _fixture_diff_status_churn_sort_key(self, record: dict[str, Any]) -> tuple[int, int, float, int, str]:
        score_delta_value = record.get("score_delta_value")
        has_delta = 0 if isinstance(score_delta_value, (int, float)) else 1
        delta_rank = -abs(float(score_delta_value)) if isinstance(score_delta_value, (int, float)) else 0.0
        status_rank = 0 if bool(record.get("status_changed")) else 1
        return (status_rank, has_delta, delta_rank, int(record.get("presence_rank", 9)), str(record.get("fixture_id") or ""))

    def _collect_fixture_snapshots(self, payload: dict[str, Any], *, summary_path: Path | None) -> dict[str, dict[str, Any]]:
        snapshots: dict[str, dict[str, Any]] = {}

        raw_entries = payload.get("representative_fixtures")
        if isinstance(raw_entries, list):
            for entry in raw_entries:
                if not isinstance(entry, dict):
                    continue
                fixture_id = str(entry.get("id") or "").strip()
                if not fixture_id:
                    continue
                snapshots.setdefault(fixture_id, {})
                snapshots[fixture_id].update(
                    {
                        "title": str(entry.get("title") or fixture_id).strip(),
                        "review_types": [
                            str(item).strip()
                            for item in entry.get("review_types", [])
                            if isinstance(item, str) and str(item).strip()
                        ],
                        "scope": str(entry.get("scope") or "project").strip(),
                    }
                )

        result_groups = []
        score_summary = payload.get("score_summary")
        if isinstance(score_summary, dict) and isinstance(score_summary.get("results"), list):
            result_groups.append(score_summary["results"])
        for key in ("baseline_results", "pair_results", "generated_reports"):
            value = payload.get(key)
            if isinstance(value, list):
                result_groups.append(value)

        for group in result_groups:
            for entry in group:
                if not isinstance(entry, dict):
                    continue
                fixture_id = str(entry.get("fixture_id") or entry.get("id") or "").strip()
                if not fixture_id:
                    continue
                snapshots.setdefault(fixture_id, {})
                for source_key, target_key in (
                    ("fixture_title", "title"),
                    ("title", "title"),
                    ("status", "status"),
                    ("score", "score"),
                    ("passed", "passed"),
                    ("report_path", "report_path"),
                    ("output_path", "report_path"),
                ):
                    if source_key in entry and entry[source_key] is not None:
                        value = entry[source_key]
                        if target_key == "report_path" and isinstance(value, str) and value.strip():
                            base_dir = summary_path.parent if summary_path is not None else self._workspace_root()
                            try:
                                snapshots[fixture_id][target_key] = self._resolve_artifact_path(value, base_dir)
                            except ValueError:
                                logger.warning(
                                    "Skipping out-of-scope benchmark report path for fixture %s: %s",
                                    fixture_id,
                                    value,
                                )
                        else:
                            snapshots[fixture_id][target_key] = value
                if isinstance(entry.get("selected_review_types"), list):
                    snapshots[fixture_id]["review_types"] = [
                        str(item).strip()
                        for item in entry["selected_review_types"]
                        if isinstance(item, str) and str(item).strip()
                    ]
        return snapshots

    def _representative_fixture_ids(self, payload: dict[str, Any]) -> list[str]:
        if isinstance(payload.get("representative_fixture_ids"), list):
            return [str(item).strip() for item in payload["representative_fixture_ids"] if str(item).strip()]
        raw_entries = payload.get("representative_fixtures")
        if isinstance(raw_entries, list):
            return [
                str(item.get("id") or "").strip()
                for item in raw_entries
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            ]
        return []

    def _current_primary_summary_path(self) -> Path | None:
        if self._benchmark_primary_summary_path:
            return Path(self._benchmark_primary_summary_path)
        return None

    def _selected_benchmark_report_directory(self) -> Path | None:
        selected_path = self._selected_benchmark_summary_path() or self._current_primary_summary_path()
        if selected_path is None:
            return None
        try:
            payload = self._read_benchmark_summary_payload(selected_path)
        except Exception:
            payload = self._benchmark_primary_summary_payload if self._benchmark_primary_summary_path == str(selected_path) else None
        if not isinstance(payload, dict):
            return None
        return self._report_directory_for_summary(selected_path, payload)

    def _report_directory_for_summary(self, summary_path: Path, payload: dict[str, Any]) -> Path | None:
        generated_reports = payload.get("generated_reports")
        if not isinstance(generated_reports, list):
            return None
        resolved_dirs: list[Path] = []
        for entry in generated_reports:
            if not isinstance(entry, dict):
                continue
            output_path = entry.get("output_path")
            if not isinstance(output_path, str) or not output_path.strip():
                continue
            try:
                resolved_path = self._resolve_artifact_path(output_path, summary_path.parent)
            except ValueError:
                logger.warning("Skipping out-of-scope benchmark generated report path: %s", output_path)
                continue
            resolved_dirs.append(resolved_path.parent)
        if not resolved_dirs:
            return None
        unique_dirs = {path.resolve() for path in resolved_dirs}
        if len(unique_dirs) == 1:
            return next(iter(unique_dirs))
        common_dir = Path(os.path.commonpath([str(path) for path in unique_dirs]))
        return common_dir

    def _resolve_artifact_path(self, raw_path: str, summary_parent: Path) -> Path:
        candidate = Path(raw_path)
        resolved = candidate.resolve() if candidate.is_absolute() else (summary_parent / candidate).resolve()
        allowed_root = self._allowed_benchmark_artifact_root(summary_parent)
        if resolved == allowed_root or resolved.is_relative_to(allowed_root):
            return resolved
        raise ValueError(f"Benchmark artifact path escapes the allowed saved runs root: {raw_path}")

    def _format_report_preview(self, report_path: Any, *, empty_text: str) -> str:
        if not isinstance(report_path, Path):
            return empty_text
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            try:
                return report_path.read_text(encoding="utf-8")
            except Exception as exc:
                return t("gui.benchmark.preview_load_error", error=exc)
        try:
            return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        except Exception:
            return str(payload)

    def _build_report_diff_text(
        self,
        primary_report_path: Any,
        compare_report_path: Any,
        primary_text: str,
        compare_text: str,
    ) -> str:
        semantic_summary = self._build_issue_level_diff_summary(primary_report_path, compare_report_path)
        diff_lines = list(
            difflib.unified_diff(
                primary_text.splitlines(),
                compare_text.splitlines(),
                fromfile=t("gui.benchmark.fixture_side_primary"),
                tofile=t("gui.benchmark.fixture_side_compare"),
                lineterm="",
            )
        )
        raw_diff_text = "\n".join(diff_lines) if diff_lines else t("gui.benchmark.preview_diff_none")
        if not semantic_summary:
            return raw_diff_text
        return "\n\n".join((semantic_summary, t("gui.benchmark.preview_diff_raw_title"), raw_diff_text))

    def _saved_benchmark_root_value(self, key: str, default: str) -> str:
        raw_value = config.get("gui", key, default)
        value = str(raw_value or "").strip()
        return value or default

    def _restore_benchmark_browser_state(self) -> None:
        self._restore_fixture_filter_selection(config.get("gui", "benchmark_fixture_filter_key", "all"))
        self._restore_fixture_sort_selection(config.get("gui", "benchmark_fixture_sort_key", "default"))
        self._refresh_benchmark_summary_selector()

    def _persist_benchmark_browser_state(self) -> None:
        try:
            config.set_value("gui", "benchmark_fixtures_root", self.benchmark_fixtures_root_entry.get().strip())
            config.set_value("gui", "benchmark_artifacts_root", self.benchmark_artifacts_root_entry.get().strip())
            config.set_value("gui", "benchmark_fixture_filter_key", self._selected_fixture_filter_key())
            config.set_value("gui", "benchmark_fixture_sort_key", self._selected_fixture_sort_key())
            config.set_value(
                "gui",
                "benchmark_compare_views",
                json.dumps(self._updated_benchmark_comparison_views(), sort_keys=True, ensure_ascii=False),
            )
            config.save()
        except Exception:
            logger.exception("Failed to persist benchmark browser state")

    def _selected_fixture_filter_key(self) -> str:
        selected_label = self.benchmark_fixture_filter_var.get()
        for label, filter_key, _allowed_presences in self._benchmark_fixture_presence_filters:
            if label == selected_label:
                return filter_key
        return "all"

    def _selected_fixture_sort_key(self) -> str:
        selected_label = self.benchmark_fixture_sort_var.get()
        for label, sort_key in self._benchmark_fixture_sort_options:
            if label == selected_label:
                return sort_key
        return "default"

    def _restore_fixture_filter_selection(self, filter_key: Any) -> None:
        normalized_key = str(filter_key or "all").strip() or "all"
        for label, current_key, _allowed_presences in self._benchmark_fixture_presence_filters:
            if current_key == normalized_key:
                self.benchmark_fixture_filter_var.set(label)
                return
        self.benchmark_fixture_filter_var.set(self._benchmark_fixture_presence_filters[0][0])

    def _restore_fixture_sort_selection(self, sort_key: Any) -> None:
        normalized_key = str(sort_key or "default").strip() or "default"
        for label, current_key in self._benchmark_fixture_sort_options:
            if current_key == normalized_key:
                self.benchmark_fixture_sort_var.set(label)
                return
        self.benchmark_fixture_sort_var.set(self._benchmark_fixture_sort_options[0][0])

    def _restore_benchmark_comparison_view_state(self) -> None:
        current_view = self._load_benchmark_comparison_views().get(self._benchmark_comparison_state_key(), {})
        if not isinstance(current_view, dict):
            return

        filter_key = current_view.get("filter_key")
        sort_key = current_view.get("sort_key")
        current_filter_key = self._selected_fixture_filter_key()
        current_sort_key = self._selected_fixture_sort_key()
        self._restore_fixture_filter_selection(filter_key if filter_key is not None else current_filter_key)
        self._restore_fixture_sort_selection(sort_key if sort_key is not None else current_sort_key)

        if filter_key is not None or sort_key is not None:
            self._render_fixture_diff_table(self._benchmark_fixture_diff_records)

    def _benchmark_comparison_state_key(self) -> str:
        primary_path = self._benchmark_primary_summary_path
        compare_path = self._benchmark_compare_summary_path
        if not primary_path or not compare_path:
            return ""
        return "::".join(
            (
                str(Path(primary_path).expanduser().resolve()),
                str(Path(compare_path).expanduser().resolve()),
            )
        )

    def _load_benchmark_comparison_views(self) -> dict[str, dict[str, str]]:
        raw_value = str(config.get("gui", "benchmark_compare_views", "") or "").strip()
        if not raw_value:
            return {}
        try:
            payload = json.loads(raw_value)
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        normalized: dict[str, dict[str, str]] = {}
        for comparison_key, view_state in payload.items():
            if not isinstance(comparison_key, str) or not isinstance(view_state, dict):
                continue
            normalized[comparison_key] = {
                key: str(value).strip()
                for key, value in view_state.items()
                if key in {"filter_key", "sort_key"} and str(value).strip()
            }
        return normalized

    def _updated_benchmark_comparison_views(self) -> dict[str, dict[str, str]]:
        views = self._load_benchmark_comparison_views()
        comparison_key = self._benchmark_comparison_state_key()
        if comparison_key:
            views[comparison_key] = {
                "filter_key": self._selected_fixture_filter_key(),
                "sort_key": self._selected_fixture_sort_key(),
            }
        return views

    def _build_issue_level_diff_summary(self, primary_report_path: Any, compare_report_path: Any) -> str:
        primary_issues = self._load_report_issues(primary_report_path)
        compare_issues = self._load_report_issues(compare_report_path)
        if not primary_issues and not compare_issues:
            return ""

        primary_groups = self._group_report_issues(primary_issues)
        compare_groups = self._group_report_issues(compare_issues)
        unchanged_count = 0
        changed_lines: list[str] = []
        added_issues: list[dict[str, Any]] = []
        removed_issues: list[dict[str, Any]] = []

        for group_key in sorted(set(primary_groups) | set(compare_groups), key=str):
            before_group = primary_groups.get(group_key, [])
            after_group = compare_groups.get(group_key, [])
            shared_count = min(len(before_group), len(after_group))

            for index in range(shared_count):
                field_changes = self._issue_field_changes(before_group[index], after_group[index])
                if field_changes:
                    changed_lines.append(
                        f"- {self._format_issue_reference(after_group[index])} | {'; '.join(field_changes)}"
                    )
                else:
                    unchanged_count += 1

            added_issues.extend(after_group[shared_count:])
            removed_issues.extend(before_group[shared_count:])

        lines = [
            t("gui.benchmark.preview_diff_issue_summary_title"),
            t(
                "gui.benchmark.preview_diff_issue_count",
                primary=len(primary_issues),
                compare=len(compare_issues),
                delta=self._format_signed_count(len(compare_issues) - len(primary_issues)),
            ),
            t("gui.benchmark.preview_diff_unchanged_count", count=unchanged_count),
        ]

        if changed_lines:
            lines.append("")
            lines.append(t("gui.benchmark.preview_diff_changed_issues_title"))
            lines.extend(changed_lines)

        if added_issues:
            lines.append("")
            lines.append(t("gui.benchmark.preview_diff_added_issues_title"))
            lines.extend(f"- {self._format_issue_reference(issue)}" for issue in self._sorted_issue_items(added_issues))

        if removed_issues:
            lines.append("")
            lines.append(t("gui.benchmark.preview_diff_removed_issues_title"))
            lines.extend(f"- {self._format_issue_reference(issue)}" for issue in self._sorted_issue_items(removed_issues))

        return "\n".join(lines)

    def _load_report_issues(self, report_path: Any) -> list[dict[str, Any]]:
        if not isinstance(report_path, Path):
            return []
        try:
            report = load_report(report_path)
        except Exception:
            return []
        raw_issues = report.get("issues_found", [])
        if not isinstance(raw_issues, list):
            return []
        return [issue for issue in raw_issues if isinstance(issue, dict)]

    def _group_report_issues(self, issues: list[dict[str, Any]]) -> dict[tuple[str, ...], list[dict[str, Any]]]:
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for issue in issues:
            grouped.setdefault(self._issue_group_key(issue), []).append(issue)
        for entries in grouped.values():
            entries.sort(key=self._issue_sort_key)
        return grouped

    def _issue_group_key(self, issue: dict[str, Any]) -> tuple[str, ...]:
        issue_id = str(issue.get("issue_id") or "").strip()
        if issue_id:
            return ("issue_id", issue_id)
        related_files = tuple(
            sorted(Path(str(path)).name.lower() for path in issue.get("related_files", []) if path)
        )
        return (
            "fingerprint",
            Path(str(issue.get("file_path") or "")).name.lower(),
            self._normalize_issue_token(issue.get("issue_type")),
            self._normalize_issue_token(issue.get("context_scope")),
            *related_files,
        )

    def _issue_sort_key(self, issue: dict[str, Any]) -> tuple[int, str, str, int, str]:
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        severity = str(issue.get("severity") or "").strip().lower()
        file_name = Path(str(issue.get("file_path") or "")).name.lower()
        issue_type = self._normalize_issue_token(issue.get("issue_type"))
        line_number = issue.get("line_number")
        line_value = int(line_number) if isinstance(line_number, int) else 0
        issue_id = str(issue.get("issue_id") or "").strip().lower()
        return (severity_order.get(severity, 9), file_name, issue_type, line_value, issue_id)

    def _sorted_issue_items(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(issues, key=self._issue_sort_key)

    def _format_issue_reference(self, issue: dict[str, Any]) -> str:
        issue_id = str(issue.get("issue_id") or "").strip()
        issue_type = str(issue.get("issue_type") or "-").strip() or "-"
        severity = str(issue.get("severity") or "-").strip() or "-"
        file_name = Path(str(issue.get("file_path") or "")).name
        line_number = issue.get("line_number")
        location = file_name or "-"
        if isinstance(line_number, int):
            location = f"{location}:{line_number}"
        descriptor = issue_id or location
        return f"{descriptor} | {issue_type} | {severity} | {location}"

    def _issue_field_changes(self, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
        changes: list[str] = []
        for field_name, label_key in (
            ("severity", "gui.benchmark.preview_diff_field_severity"),
            ("issue_type", "gui.benchmark.preview_diff_field_issue_type"),
            ("file_path", "gui.benchmark.preview_diff_field_file"),
            ("line_number", "gui.benchmark.preview_diff_field_line"),
        ):
            before_value = before.get(field_name)
            after_value = after.get(field_name)
            if field_name == "file_path":
                before_value = Path(str(before_value or "")).name if before_value else "-"
                after_value = Path(str(after_value or "")).name if after_value else "-"
            if before_value == after_value:
                continue
            changes.append(f"{t(label_key)} {before_value or '-'} -> {after_value or '-'}")
        return changes

    def _normalize_issue_token(self, value: Any) -> str:
        raw_value = str(value or "").strip().lower()
        return "_".join(raw_value.replace("/", " ").replace("-", " ").split())

    def _format_signed_count(self, value: int) -> str:
        return f"{value:+d}"

    def _format_score_value(self, value: Any) -> str:
        if isinstance(value, int | float):
            return f"{float(value):.4f}"
        return "-"

    def _metadata_string_list(self, container: Any, key: str) -> list[str]:
        if not isinstance(container, dict):
            return []
        value = container.get(key)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        return []

    def _set_textbox(self, textbox: Any, value: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("0.0", "end")
        textbox.insert("0.0", value)
        textbox.configure(state="disabled")