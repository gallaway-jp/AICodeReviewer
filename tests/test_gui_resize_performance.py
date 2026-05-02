# tests/test_gui_resize_performance.py
"""Performance-oriented regression tests for GUI resize handling."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk
import aicodereviewer.gui.app as app_module
from aicodereviewer.config import config
from aicodereviewer.gui.app import App
from aicodereviewer.gui.test_fixtures import create_sample_issues
from aicodereviewer.i18n import t

try:
    _root = tk.Tk()
    _root.destroy()
    HAS_DISPLAY = True
except (tk.TclError, RuntimeError):
    HAS_DISPLAY = False

pytestmark = pytest.mark.skipif(not HAS_DISPLAY, reason="No display available")


def test_gui_resize_debounce_minimum_default() -> None:
    original_value = str(config.get("gui", "resize_debounce_ms", "100"))
    config.set_value("gui", "resize_debounce_ms", "20")
    app = App(testing_mode=True)
    try:
        assert app._gui_resize_debounce_ms() >= 100
    finally:
        app.destroy()
        config.set_value("gui", "resize_debounce_ms", original_value)


def test_customtkinter_dpi_awareness_disabled_by_default_on_windows(monkeypatch: Any) -> None:
    original_value = str(config.get("gui", "automatic_dpi_awareness", "false"))
    config.set_value("gui", "automatic_dpi_awareness", "false")
    calls = {"count": 0}

    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        app_module.ctk,
        "deactivate_automatic_dpi_awareness",
        lambda: calls.__setitem__("count", calls["count"] + 1),
    )

    try:
        app_module._configure_customtkinter_dpi_awareness()
        assert calls["count"] == 1
    finally:
        config.set_value("gui", "automatic_dpi_awareness", original_value)


def test_customtkinter_dpi_awareness_can_remain_enabled(monkeypatch: Any) -> None:
    original_value = str(config.get("gui", "automatic_dpi_awareness", "false"))
    config.set_value("gui", "automatic_dpi_awareness", "true")
    calls = {"count": 0}

    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        app_module.ctk,
        "deactivate_automatic_dpi_awareness",
        lambda: calls.__setitem__("count", calls["count"] + 1),
    )

    try:
        app_module._configure_customtkinter_dpi_awareness()
        assert calls["count"] == 0
    finally:
        config.set_value("gui", "automatic_dpi_awareness", original_value)


def test_configure_refresh_instrumentation_counts() -> None:
    app = App(testing_mode=True)
    try:
        app._schedule_configure_refresh("_test_refresh_after_id", 0, lambda: None)
        assert app._configure_event_counts["_test_refresh_after_id"] == 1
        assert app._configure_refresh_counts["_test_refresh_after_id"] == 1

        app._schedule_review_layout_refresh()
        assert app._configure_event_counts["_review_layout_refresh_after_id"] == 1
    finally:
        app.destroy()


def test_lazy_startup_poll_log_queue_and_restack_toasts_safe() -> None:
    app = App(testing_mode=True)
    try:
        app._poll_log_queue()
        app._restack_toasts()
    finally:
        app.destroy()


def test_lazy_tab_selection_builds_tab_widgets() -> None:
    app = App(testing_mode=True)
    try:
        assert getattr(app, "results_summary", None) is None
        app.tabs.set(t("gui.tab.results"))
        app.update_idletasks()
        app.update()
        if getattr(app, "results_summary", None) is None:
            app.tabs.event_generate("<<NotebookTabChanged>>")
            app.update_idletasks()
            app.update()
        assert getattr(app, "results_summary", None) is not None
    finally:
        app.destroy()


def test_window_resize_refresh_skips_redundant_events(monkeypatch: Any) -> None:
    app = App(testing_mode=True)
    try:
        scheduled: list[tuple[str, int, Any]] = []

        def fake_schedule(attr: str, delay_ms: int, callback: Any) -> None:
            scheduled.append((attr, delay_ms, callback))

        monkeypatch.setattr(app, "_schedule_debounced", fake_schedule)

        app._window_resize_last_size = (100, 100)
        app._schedule_window_resize_refresh(SimpleNamespace(widget=app, width=100, height=100))
        assert scheduled == []

        app._window_resize_last_size = (100, 100)
        app._schedule_window_resize_refresh(SimpleNamespace(widget=app, width=103, height=103))
        assert scheduled == []

        app._window_resize_last_size = (100, 100)
        app._schedule_window_resize_refresh(SimpleNamespace(widget=app, width=200, height=120))
        assert len(scheduled) == 1
        assert scheduled[0][0] == "_window_resize_refresh_after_id"
        assert scheduled[0][1] == max(app._gui_resize_debounce_ms(), 150)
        assert callable(scheduled[0][2])
    finally:
        app.destroy()


def test_window_resize_refresh_ignores_child_configure_events(monkeypatch: Any) -> None:
    app = App(testing_mode=True)
    try:
        scheduled: list[tuple[str, int, Any]] = []

        def fake_schedule(attr: str, delay_ms: int, callback: Any) -> None:
            scheduled.append((attr, delay_ms, callback))

        monkeypatch.setattr(app, "_schedule_debounced", fake_schedule)

        app._schedule_window_resize_refresh(SimpleNamespace(widget=object(), width=960, height=720))

        assert scheduled == []
    finally:
        app.destroy()


def test_review_layout_refresh_skips_structural_regrid_when_state_unchanged(monkeypatch: Any) -> None:
    app = App(testing_mode=True)
    try:
        app.tabs.set(t("gui.tab.review"))
        app.update_idletasks()
        app.update()

        monkeypatch.setattr(app, "_review_logical_width", lambda *_args: 980.0)
        app._refresh_review_tab_layout()

        calls = {"setup": 0, "divider": 0, "checkbox": 0, "preset": 0}
        first_checkbox = next(iter(app.type_checkboxes.values()))

        monkeypatch.setattr(app.review_setup_panel, "grid_forget", lambda: calls.__setitem__("setup", calls["setup"] + 1))
        monkeypatch.setattr(app.review_layout_divider, "grid_forget", lambda: calls.__setitem__("divider", calls["divider"] + 1))
        monkeypatch.setattr(first_checkbox, "grid_forget", lambda: calls.__setitem__("checkbox", calls["checkbox"] + 1))
        monkeypatch.setattr(app.review_preset_label, "grid_forget", lambda: calls.__setitem__("preset", calls["preset"] + 1))

        app._refresh_review_tab_layout()

        assert calls == {"setup": 0, "divider": 0, "checkbox": 0, "preset": 0}
    finally:
        app.destroy()


def test_results_layout_refresh_skips_structural_regrid_when_state_unchanged(monkeypatch: Any) -> None:
    app = App(testing_mode=True)
    try:
        app._show_issues(create_sample_issues())
        app.tabs.set(t("gui.tab.results"))
        app.update_idletasks()
        app.update()

        monkeypatch.setattr(app, "_results_logical_width", lambda *_args: 1280.0)
        app._refresh_results_tab_layout()

        calls = {"overview": 0, "quick": 0, "filter": 0, "bottom": 0}
        monkeypatch.setattr(app._overview_card_frames[0], "grid_forget", lambda: calls.__setitem__("overview", calls["overview"] + 1))
        monkeypatch.setattr(app._quick_filter_label, "grid_forget", lambda: calls.__setitem__("quick", calls["quick"] + 1))
        monkeypatch.setattr(app._filter_clear_btn, "grid_forget", lambda: calls.__setitem__("filter", calls["filter"] + 1))
        monkeypatch.setattr(app.finalize_btn, "grid_forget", lambda: calls.__setitem__("bottom", calls["bottom"] + 1))

        app._refresh_results_tab_layout()

        assert calls == {"overview": 0, "quick": 0, "filter": 0, "bottom": 0}
    finally:
        app.destroy()


def test_settings_layout_refresh_skips_structural_regrid_when_state_unchanged(monkeypatch: Any) -> None:
    app = App(testing_mode=True)
    try:
        app.tabs.set(t("gui.tab.settings"))
        app.update_idletasks()
        app.update()

        monkeypatch.setattr(app, "_settings_logical_width", lambda *_args: 1280.0)
        app._refresh_settings_tab_layout()

        calls = {"formats": 0, "buttons": 0}
        monkeypatch.setattr(
            app._settings_output_format_checkboxes[0],
            "grid_forget",
            lambda: calls.__setitem__("formats", calls["formats"] + 1),
        )
        monkeypatch.setattr(
            app._settings_save_btn,
            "grid_forget",
            lambda: calls.__setitem__("buttons", calls["buttons"] + 1),
        )

        app._refresh_settings_tab_layout()

        assert calls == {"formats": 0, "buttons": 0}
    finally:
        app.destroy()


def test_benchmark_layout_refresh_skips_structural_regrid_when_state_unchanged(monkeypatch: Any) -> None:
    app = App(testing_mode=True)
    try:
        app.tabs.set(t("gui.tab.benchmarks"))
        app.update_idletasks()
        app.update()

        monkeypatch.setattr(app, "_benchmark_logical_width", lambda *_args: 1280.0)
        app._refresh_benchmark_tab_layout()

        calls = {"actions": 0, "browser": 0, "compare": 0, "preview": 0}
        monkeypatch.setattr(
            app._benchmark_action_buttons[0],
            "grid_forget",
            lambda: calls.__setitem__("actions", calls["actions"] + 1),
        )
        monkeypatch.setattr(
            app.benchmark_catalog_box,
            "grid_forget",
            lambda: calls.__setitem__("browser", calls["browser"] + 1),
        )
        monkeypatch.setattr(
            app.benchmark_primary_summary_label,
            "grid_forget",
            lambda: calls.__setitem__("compare", calls["compare"] + 1),
        )
        monkeypatch.setattr(
            app.benchmark_preview_primary_label,
            "grid_forget",
            lambda: calls.__setitem__("preview", calls["preview"] + 1),
        )

        app._refresh_benchmark_tab_layout()

        assert calls == {"actions": 0, "browser": 0, "compare": 0, "preview": 0}
    finally:
        app.destroy()


def test_surface_layout_refresh_skips_inactive_tab_but_allows_detached_surface(monkeypatch: Any) -> None:
    app = App(testing_mode=True)
    try:
        app.tabs.set(t("gui.tab.review"))
        app.update_idletasks()
        app.update()

        scheduled: list[tuple[str, int, Any]] = []

        def fake_schedule(attr: str, delay_ms: int, callback: Any) -> None:
            scheduled.append((attr, delay_ms, callback))

        monkeypatch.setattr(app, "_schedule_configure_refresh", fake_schedule)

        app._schedule_surface_layout_refresh(
            "_settings_layout_refresh_after_id",
            lambda: None,
            tab_name=t("gui.tab.settings"),
            detached_window_attr="_detached_settings_window",
        )
        assert scheduled == []

        app._detached_settings_window = SimpleNamespace(winfo_exists=lambda: True)
        app._schedule_surface_layout_refresh(
            "_settings_layout_refresh_after_id",
            lambda: None,
            tab_name=t("gui.tab.settings"),
            detached_window_attr="_detached_settings_window",
        )

        assert len(scheduled) == 1
        assert scheduled[0][0] == "_settings_layout_refresh_after_id"
    finally:
        app.destroy()


def test_scroll_region_refresh_skips_hidden_results_surface(monkeypatch: Any) -> None:
    app = App(testing_mode=True)
    try:
        app._show_issues(create_sample_issues())
        app.tabs.set(t("gui.tab.review"))
        app.update_idletasks()
        app.update()

        hidden_results_refreshes = {"count": 0}
        active_review_refreshes = {"count": 0}

        monkeypatch.setattr(
            app.results_frame,
            "_acr_update_scroll_region",
            lambda: hidden_results_refreshes.__setitem__("count", hidden_results_refreshes["count"] + 1),
            raising=False,
        )
        monkeypatch.setattr(
            app.review_scroll_frame,
            "_acr_update_scroll_region",
            lambda: active_review_refreshes.__setitem__("count", active_review_refreshes["count"] + 1),
            raising=False,
        )

        app._refresh_scroll_regions()

        assert hidden_results_refreshes["count"] == 0
        assert active_review_refreshes["count"] >= 1
    finally:
        app.destroy()
