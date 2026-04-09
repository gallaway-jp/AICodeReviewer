# tests/test_gui_smoke.py
"""Smoke tests for the GUI application.

These tests verify that the GUI can be created and destroyed without errors,
and that key widgets and state are correctly initialised.  All tests use
``testing_mode=True`` so no network I/O, file dialogs, or message boxes
are triggered.

Run with::

    python -m pytest tests/test_gui_smoke.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Generator
import json
import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aicodereviewer.i18n import t
from aicodereviewer.addons import AddonDiagnostic, AddonRuntime
from aicodereviewer.review_definitions import install_review_registry
from gui_test_utils import BenchmarkTabHarness, QueuePanelHarness, ReviewRuntimeHarness, StatusBarHarness

# Skip the entire module if display is not available (headless CI)
try:
    import tkinter as tk
    _root = tk.Tk()
    _root.destroy()
    del _root
    HAS_DISPLAY = True
except (tk.TclError, RuntimeError):
    HAS_DISPLAY = False

pytestmark = pytest.mark.skipif(not HAS_DISPLAY, reason="No display available")


def _noop_wait_until(*_args: Any, **_kwargs: Any) -> None:
    return None


def _assert_widget_within_window(app: Any, widget: Any, *, slack: int = 24) -> None:
    if widget.winfo_manager() == "":
        return
    app.update_idletasks()
    app.update()
    widget_right = widget.winfo_rootx() + widget.winfo_width()
    window_right = app.winfo_rootx() + app.winfo_width()
    assert widget_right <= window_right + slack


@pytest.fixture()
def app() -> Generator[Any, None, None]:
    """Create and yield an App in testing mode, then destroy it."""
    from aicodereviewer.gui.app import App
    try:
        application = App(testing_mode=True)
    except tk.TclError as exc:
        error_text = str(exc)
        known_tcl_env_failures = (
            "auto.tcl",
            "tcl_findLibrary",
            "tk.tcl",
            "init.tcl",
            "usable tk.tcl",
            "usable init.tcl",
        )
        if any(marker in error_text for marker in known_tcl_env_failures):
            pytest.skip(f"Tk unavailable during App setup: {exc}")
        raise
    application.update_idletasks()
    yield application
    try:
        application.destroy()
    except Exception:
        pass


class TestAppCreation:
    """Verify that the App initialises correctly in testing mode."""

    def test_app_creates_without_error(self, app: Any) -> None:
        """App should instantiate and render without exceptions."""
        assert app is not None
        assert app._testing_mode is True
        assert hasattr(app, "_legacy_compat_state") is False
        assert hasattr(app, "_model_refresh_in_progress") is False
        assert hasattr(type(app), "_running") is False
        removed_legacy_properties = (
            "_review_runner",
            "_review_client",
            "_cancel_event",
            "_ai_fix_running",
            "_ai_fix_cancel_event",
            "_health_check_backend",
            "_health_check_timer",
        )
        assert all(not hasattr(type(app), name) for name in removed_legacy_properties)

    def test_tabs_exist(self, app: Any) -> None:
        """All primary tabs should be created."""
        assert hasattr(app, "tabs")
        # CTkTabview stores tabs in _tab_dict
        tab_dict = getattr(app.tabs, "_tab_dict", {})
        assert len(tab_dict) >= 5, f"Expected >= 5 tabs, got {len(tab_dict)}"

    def test_settings_tab_exposes_tool_file_access_toggle(self, app: Any) -> None:
        app.tabs.set(t("gui.tab.settings"))
        app.update_idletasks()
        app.update()

        assert ("tool_file_access", "enabled") in app._setting_entries
        assert hasattr(app, "detach_settings_btn")
        assert app.detach_settings_btn.cget("text") == t("gui.settings.open_window")

    def test_benchmark_tab_widgets(self, app: Any) -> None:
        benchmark_tab = BenchmarkTabHarness(app)

        benchmark_tab.open()

        assert benchmark_tab.current_tab() == t("gui.tab.benchmarks")
        assert hasattr(app, "benchmark_fixtures_root_entry")
        assert hasattr(app, "benchmark_load_catalog_btn")
        assert hasattr(app, "benchmark_load_summary_btn")
        assert hasattr(app, "benchmark_compare_summary_btn")
        assert hasattr(app, "benchmark_advanced_toggle_btn")
        assert hasattr(app, "benchmark_artifacts_root_entry")
        assert hasattr(app, "benchmark_summary_selector_menu")
        assert hasattr(app, "benchmark_load_selected_summary_btn")
        assert hasattr(app, "benchmark_compare_selected_summary_btn")
        assert hasattr(app, "benchmark_open_source_btn")
        assert hasattr(app, "benchmark_open_summary_json_btn")
        assert hasattr(app, "benchmark_open_report_dir_btn")
        assert hasattr(app, "detach_benchmark_btn")
        assert app.detach_benchmark_btn.cget("text") == t("gui.benchmark.open_window")
        assert hasattr(app, "benchmark_fixture_menu")
        assert hasattr(app, "benchmark_catalog_box")
        assert hasattr(app, "benchmark_detail_box")
        assert hasattr(app, "benchmark_primary_summary_box")
        assert hasattr(app, "benchmark_compare_summary_box")
        assert hasattr(app, "benchmark_fixture_diff_scroll")
        assert hasattr(app, "benchmark_fixture_diff_empty_label")
        assert hasattr(app, "benchmark_fixture_filter_menu")
        assert hasattr(app, "benchmark_fixture_sort_menu")
        assert hasattr(app, "benchmark_preview_primary_box")
        assert hasattr(app, "benchmark_preview_compare_box")
        assert hasattr(app, "benchmark_preview_diff_box")
        assert benchmark_tab.advanced_sources_visible() is False

        benchmark_tab.toggle_advanced_sources()

        assert benchmark_tab.advanced_sources_visible() is True

    def test_review_tab_widgets(self, app: Any) -> None:
        """Key Review tab widgets should exist."""
        queue_panel = QueuePanelHarness(app)
        assert hasattr(app, "path_entry")
        assert hasattr(app, "scope_var")
        assert hasattr(app, "backend_var")
        assert hasattr(app, "review_preset_var")
        assert hasattr(app, "review_preset_menu")
        assert hasattr(app, "review_preset_summary_label")
        assert hasattr(app, "review_types_hint_label")
        assert hasattr(app, "run_btn")
        assert hasattr(app, "dry_btn")
        assert hasattr(app, "health_btn")
        assert hasattr(app, "progress")
        assert queue_panel.is_bound() is True

    def test_review_types_hint_text_is_localized(self, app: Any) -> None:
        """Review types helper text should be present and translated."""
        assert app.review_types_hint_label.cget("text") == t("gui.review.types_hint")

    def test_review_tab_outer_scrollbar_auto_hides(self, app: Any) -> None:
        """The Review tab outer scrollbar should hide without overflow and show with overflow."""
        app.tabs.set(t("gui.tab.review"))
        app.update_idletasks()
        app.update()

        app.review_scroll_canvas._acr_sync_scrollbar(0.0, 1.0)
        assert app.review_scrollbar.winfo_manager() == ""

        app.review_scroll_canvas._acr_sync_scrollbar(0.0, 0.4)
        assert app.review_scrollbar.winfo_manager() == "grid"

    def test_review_type_list_reflows_to_two_and_three_columns(self, app: Any) -> None:
        app.tabs.set(t("gui.tab.review"))

        app.geometry("960x720")
        app.update_idletasks()
        app.update()
        narrow_columns = {
            int(checkbox.grid_info().get("column", 0))
            for checkbox in app.type_checkboxes.values()
            if checkbox.winfo_manager() == "grid"
        }
        assert len(narrow_columns) >= 2

        original_width_helper = app._review_logical_width
        app._review_logical_width = lambda *_args: 980.0
        app._refresh_review_type_layout()
        wide_columns = {
            int(checkbox.grid_info().get("column", 0))
            for checkbox in app.type_checkboxes.values()
            if checkbox.winfo_manager() == "grid"
        }
        app._review_logical_width = original_width_helper
        assert len(wide_columns) >= 3

    def test_tabs_keep_key_surfaces_visible_across_window_resize(self, app: Any) -> None:
        """Primary tabs should keep their key surfaces mapped across narrow and wide window sizes."""
        for width, height in ((960, 540), (1500, 980)):
            app.geometry(f"{width}x{height}")
            app.update_idletasks()
            app.update()

            app.tabs.set(t("gui.tab.review"))
            app.update_idletasks()
            app.update()
            assert app.review_setup_panel.winfo_manager() == "grid"
            assert app.review_run_panel.winfo_manager() == "grid"
            assert app.run_btn.winfo_manager() == "grid"
            assert app.progress.winfo_manager() == "grid"
            _assert_widget_within_window(app, app.review_preset_menu)
            _assert_widget_within_window(app, app.recommend_btn)
            _assert_widget_within_window(app, app.pin_review_set_btn)

            app.tabs.set(t("gui.tab.results"))
            app.update_idletasks()
            app.update()
            assert app.results_summary.winfo_manager() != ""
            assert app.results_frame.winfo_manager() != ""
            assert app.finalize_btn.winfo_manager() != ""
            _assert_widget_within_window(app, app._filter_type_menu)
            _assert_widget_within_window(app, app.finalize_btn)

            app.tabs.set(t("gui.tab.settings"))
            app.update_idletasks()
            app.update()
            assert app.addon_summary_box.winfo_manager() != ""
            assert app.local_http_docs_box.winfo_manager() != ""
            assert app.detach_settings_btn.winfo_manager() != ""
            _assert_widget_within_window(app, app.local_http_docs_box)

            app.tabs.set(t("gui.tab.benchmarks"))
            app.update_idletasks()
            app.update()
            assert app.benchmark_catalog_box.winfo_manager() != ""
            assert app.benchmark_detail_box.winfo_manager() != ""
            assert app.benchmark_primary_summary_box.winfo_manager() != ""
            assert app.benchmark_open_source_btn.winfo_manager() != ""
            assert app.detach_benchmark_btn.winfo_manager() != ""
            _assert_widget_within_window(app, app.benchmark_load_catalog_btn)
            _assert_widget_within_window(app, app.benchmark_open_source_btn)
            _assert_widget_within_window(app, app.detach_benchmark_btn)
            _assert_widget_within_window(app, app.benchmark_primary_summary_box)

            app.tabs.set(t("gui.tab.log"))
            app.update_idletasks()
            app.update()
            assert app.log_box.winfo_manager() != ""
            assert app.save_log_btn.winfo_manager() != ""
            assert app.detach_log_btn.winfo_manager() != ""
            _assert_widget_within_window(app, app._log_level_menu)
            _assert_widget_within_window(app, app.save_log_btn)

    def test_log_tab_exposes_detach_window_action(self, app: Any) -> None:
        app.tabs.set(t("gui.tab.log"))
        app.update_idletasks()
        app.update()

        assert hasattr(app, "detach_log_btn")
        assert app.detach_log_btn.cget("text") == t("gui.log.open_window")

    def test_results_settings_and_log_reflow_explicitly_by_logical_width(self, app: Any) -> None:
        app.tabs.set(t("gui.tab.results"))

        original_results_width = app._results_logical_width
        app._results_logical_width = lambda *_args: 820.0
        app._refresh_results_tab_layout()
        narrow_overview_rows = {
            int(card.grid_info().get("row", 0))
            for card in app._overview_card_frames
            if card.winfo_manager() == "grid"
        }
        narrow_action_rows = {
            int(widget.grid_info().get("row", 0))
            for widget in (app.ai_fix_mode_btn, app.review_changes_btn, app.finalize_btn, app.save_session_btn, app.load_session_btn)
            if widget.winfo_manager() == "grid"
        }
        assert len(narrow_overview_rows) >= 2
        assert len(narrow_action_rows) >= 2

        app._results_logical_width = lambda *_args: 1440.0
        app._refresh_results_tab_layout()
        wide_overview_rows = {
            int(card.grid_info().get("row", 0))
            for card in app._overview_card_frames
            if card.winfo_manager() == "grid"
        }
        wide_action_rows = {
            int(widget.grid_info().get("row", 0))
            for widget in (app.ai_fix_mode_btn, app.review_changes_btn, app.finalize_btn, app.save_session_btn, app.load_session_btn)
            if widget.winfo_manager() == "grid"
        }
        app._results_logical_width = original_results_width
        assert wide_overview_rows == {0}
        assert wide_action_rows == {0}

        app.tabs.set(t("gui.tab.settings"))
        original_settings_width = app._settings_logical_width
        app._settings_logical_width = lambda *_args: 860.0
        app._refresh_settings_tab_layout()
        narrow_format_rows = {
            int(checkbox.grid_info().get("row", 0))
            for checkbox in app._settings_output_format_checkboxes
            if checkbox.winfo_manager() == "grid"
        }
        narrow_settings_button_rows = {
            int(button.grid_info().get("row", 0))
            for button in (app._settings_save_btn, app._settings_reset_btn, app.detach_settings_btn)
            if button.winfo_manager() == "grid"
        }
        assert len(narrow_format_rows) >= 2
        assert len(narrow_settings_button_rows) >= 2

        app._settings_logical_width = lambda *_args: 1320.0
        app._refresh_settings_tab_layout()
        wide_format_rows = {
            int(checkbox.grid_info().get("row", 0))
            for checkbox in app._settings_output_format_checkboxes
            if checkbox.winfo_manager() == "grid"
        }
        wide_settings_button_rows = {
            int(button.grid_info().get("row", 0))
            for button in (app._settings_save_btn, app._settings_reset_btn, app.detach_settings_btn)
            if button.winfo_manager() == "grid"
        }
        app._settings_logical_width = original_settings_width
        assert wide_format_rows == {0}
        assert wide_settings_button_rows == {0}

        app.tabs.set(t("gui.tab.log"))
        original_log_width = app._log_logical_width
        app._log_logical_width = lambda *_args: 700.0
        app._refresh_log_tab_layout()
        narrow_log_button_rows = {
            int(button.grid_info().get("row", 0))
            for button in (app.clear_log_btn, app.save_log_btn)
            if button.winfo_manager() == "grid"
        }
        assert len(narrow_log_button_rows) >= 2

        app._log_logical_width = lambda *_args: 1080.0
        app._refresh_log_tab_layout()
        wide_log_button_rows = {
            int(button.grid_info().get("row", 0))
            for button in (app.clear_log_btn, app.save_log_btn)
            if button.winfo_manager() == "grid"
        }
        app._log_logical_width = original_log_width
        assert wide_log_button_rows == {0}

    def test_review_tab_renders_custom_subtype_hierarchy(self, tmp_path: Path) -> None:
        pack_path = tmp_path / "gui-pack.json"
        pack_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "review_definitions": [
                        {
                            "key": "secure_defaults",
                            "parent_key": "security",
                            "label": "Secure Defaults",
                            "summary_key": "",
                            "prompt_append": "Check opt-out security defaults.",
                        }
                    ],
                    "review_presets": [
                        {
                            "key": "secure_runtime",
                            "group": "Custom Bundles",
                            "label": "Secure Runtime",
                            "summary": "Security defaults plus validation.",
                            "review_types": ["secure_defaults", "data_validation"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        from aicodereviewer.gui.app import App

        install_review_registry([pack_path])
        application = None
        try:
            application = App(testing_mode=True)
            application.update_idletasks()

            assert "secure_defaults" in application.type_vars
            assert application._review_type_depths["secure_defaults"] == 1
            assert application.type_checkboxes["secure_defaults"].cget("text") == "> Secure Defaults"
            assert "secure_runtime" in application._review_preset_labels
            assert "Custom Bundles / Secure Runtime [secure_runtime]" == application._review_preset_labels["secure_runtime"]
            application._on_review_preset_selected(application._review_preset_labels["secure_runtime"])
            assert application.type_vars["secure_defaults"].get() is True
        finally:
            if application is not None:
                try:
                    application.destroy()
                except Exception:
                    pass
            install_review_registry([])

    def test_file_select_frame_exists(self, app: Any) -> None:
        """File selection frame should exist for project mode."""
        assert hasattr(app, "file_select_frame")
        assert hasattr(app, "file_select_mode_var")
        assert hasattr(app, "select_files_btn")

    def test_diff_filter_frame_exists(self, app: Any) -> None:
        """Diff filter frame should exist for project mode."""
        assert hasattr(app, "diff_filter_frame")
        assert hasattr(app, "diff_filter_var")
        assert hasattr(app, "diff_filter_file_entry")
        assert hasattr(app, "diff_filter_commits_entry")

    def test_initial_scope_is_project(self, app: Any) -> None:
        """Default scope should be 'project'."""
        assert app.scope_var.get() == "project"

    def test_status_bar_exists(self, app: Any) -> None:
        """Status bar and cancel button should exist."""
        assert hasattr(app, "status_var")
        assert hasattr(app, "cancel_btn")

    def test_settings_addon_diagnostics_widgets(self, app: Any) -> None:
        """Settings tab should expose addon summary and diagnostics surfaces."""
        assert hasattr(app, "addon_summary_box")
        assert hasattr(app, "addon_diagnostics_box")
        assert hasattr(app, "addon_contributions_frame")
        assert hasattr(app, "_refresh_addons_btn")
        assert hasattr(app, "open_addon_review_btn")
        assert hasattr(app, "local_http_status_label")
        assert hasattr(app, "local_http_base_url_entry")
        assert hasattr(app, "local_http_copy_btn")
        assert hasattr(app, "local_http_docs_box")

    def test_addon_review_widgets(self, app: Any) -> None:
        """Addon Review should expose the standalone preview review widgets."""
        assert hasattr(app, "addon_review_preview_entry")
        assert hasattr(app, "addon_review_status_box")
        assert hasattr(app, "addon_review_metadata_box")
        assert hasattr(app, "addon_review_checklist_box")
        assert hasattr(app, "addon_review_diff_box")
        assert hasattr(app, "addon_review_approve_btn")
        assert hasattr(app, "addon_review_reject_btn")
        assert hasattr(app, "detach_addon_review_btn")

    def test_addon_review_surface_loads_preview(self, app: Any, tmp_path: Path) -> None:
        from aicodereviewer.addon_generator import generate_addon_preview

        project_root = tmp_path / "service_repo"
        project_root.mkdir()
        (project_root / "pyproject.toml").write_text(
            "[project]\nname = 'service-repo'\nversion = '0.1.0'\n\n[tool.pytest.ini_options]\naddopts = '-q'\n",
            encoding="utf-8",
        )
        (project_root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "api.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

        preview = generate_addon_preview(project_root, tmp_path / "preview", addon_id="desktop-preview")

        app.tabs.set(t("gui.tab.addon_review"))
        app.update_idletasks()
        app.update()
        app.addon_review_preview_entry.delete(0, "end")
        app.addon_review_preview_entry.insert(0, str(preview.output_dir))
        app.addon_review_reviewer_entry.delete(0, "end")
        app.addon_review_reviewer_entry.insert(0, "Colin")

        app._load_addon_review_surface(show_toast=False)

        metadata_text = app.addon_review_metadata_box.get("0.0", "end")
        diff_text = app.addon_review_diff_box.get("0.0", "end")
        assert "desktop-preview" in metadata_text
        assert "Generated Bundle vs Default Bundle" in app.addon_review_diff_var.get()
        assert "api_design" in diff_text

    def test_settings_addon_diagnostics_render_runtime(self, app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """Addon summary and diagnostic text boxes should reflect the active runtime."""
        from aicodereviewer.addons import AddonManifest, AddonUIContributorSpec
        import aicodereviewer.gui.settings_mixin as settings_mixin

        runtime = AddonRuntime(
            manifests=(
                AddonManifest(
                    addon_id="demo-addon",
                    addon_version="1.2.3",
                    name="Demo Addon",
                    manifest_path=Path(__file__).resolve(),
                    root_dir=Path(__file__).resolve().parent,
                    ui_contributor_specs=(
                        AddonUIContributorSpec(
                            addon_id="demo-addon",
                            surface="settings_section",
                            title="Demo Settings Surface",
                            description="Rendered in the Settings tab.",
                            lines=("Backend key: demo-addon",),
                        ),
                    ),
                ),
            ),
            diagnostics=(
                AddonDiagnostic(
                    severity="error",
                    message="Demo addon failed validation",
                ),
            ),
        )
        monkeypatch.setattr(settings_mixin, "get_active_addon_runtime", lambda: runtime)

        app._populate_addon_diagnostics()

        summary_text = app.addon_summary_box.get("0.0", "end").strip()
        diagnostics_text = app.addon_diagnostics_box.get("0.0", "end").strip()
        contribution_texts: list[str] = []

        def _collect_texts(widget: Any) -> None:
            for child in widget.winfo_children():
                if hasattr(child, "cget"):
                    try:
                        text = child.cget("text")
                    except Exception:
                        text = ""
                    if text:
                        contribution_texts.append(text)
                if hasattr(child, "winfo_children"):
                    _collect_texts(child)

        _collect_texts(app.addon_contributions_frame)

        assert "Demo Addon [demo-addon] v1.2.3" in summary_text
        assert "settings_section: Demo Settings Surface" in summary_text
        assert "Demo addon failed validation" in diagnostics_text
        assert "Demo Settings Surface" in contribution_texts
        assert "Rendered in the Settings tab." in contribution_texts
        assert "- Backend key: demo-addon" in contribution_texts


class TestTestingMode:
    """Verify that testing_mode correctly suppresses blocking operations."""

    def test_browse_path_noop(self, app: Any) -> None:
        """_browse_path should not open a file dialog in testing mode."""
        # Should not raise or block
        app._browse_path()

    def test_browse_diff_noop(self, app: Any) -> None:
        """_browse_diff should not open a file dialog in testing mode."""
        app._browse_diff()

    def test_browse_diff_filter_noop(self, app: Any) -> None:
        """_browse_diff_filter should not open a file dialog in testing mode."""
        app._browse_diff_filter()

    def test_browse_benchmark_sources_noop(self, app: Any) -> None:
        """Benchmark browse helpers should not open dialogs in testing mode."""
        app._browse_benchmark_fixtures_root()
        app._browse_benchmark_artifacts_root()
        app._browse_benchmark_summary_artifact()
        app._browse_benchmark_compare_artifact()

    def test_benchmark_tab_loads_fixture_catalog_entries(self, app: Any, tmp_path: Path) -> None:
        fixtures_root = tmp_path / "fixtures"
        fixture_dir = fixtures_root / "sample-fixture"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "fixture.json").write_text(
            json.dumps(
                {
                    "id": "catalog-browser-fixture",
                    "title": "Catalog Browser Fixture",
                    "description": "Fixture for benchmark browser smoke coverage.",
                    "scope": "project",
                    "review_types": ["security", "performance"],
                    "expected_findings": [],
                }
            ),
            encoding="utf-8",
        )

        benchmark_tab = BenchmarkTabHarness(app)
        benchmark_tab.load_catalog(fixtures_root)

        assert "catalog-browser-fixture" in benchmark_tab.catalog_text()
        detail_text = benchmark_tab.detail_text()
        assert "security" in detail_text
        assert "performance" in detail_text
        assert "fixture_tags" not in detail_text.lower()

    def test_benchmark_tab_selector_lists_summary_artifacts(self, app: Any, tmp_path: Path) -> None:
        artifacts_root = tmp_path / "artifacts"
        artifacts_root.mkdir()
        (artifacts_root / "first-summary.json").write_text(
            json.dumps(
                {
                    "backend": "local",
                    "status": "completed",
                    "overall_score": 0.5,
                    "representative_fixtures": [{"id": "fixture-a", "title": "Fixture A", "scope": "project", "review_types": ["security"]}],
                }
            ),
            encoding="utf-8",
        )

        benchmark_tab = BenchmarkTabHarness(app)
        benchmark_tab.refresh_summary_selector(artifacts_root)

        values = benchmark_tab.summary_selector_values()
        assert any("first-summary.json" in value for value in values)

    def test_open_file_selector_noop(self, app: Any) -> None:
        """_open_file_selector should not open a modal window in testing mode."""
        app._open_file_selector()

    def test_show_health_error_noop(self, app: Any) -> None:
        """_show_health_error should log instead of showing messagebox."""
        app._show_health_error("test error")  # Should not block

    def test_reset_defaults_noop(self, app: Any) -> None:
        """_reset_defaults should return immediately in testing mode."""
        app._reset_defaults()  # Should not show confirmation dialog

    def test_destroy_releases_review_client(self, app: Any) -> None:
        """Destroying the app should close any active review backend."""
        review_runtime = ReviewRuntimeHarness(app)

        class _DummyClient:
            def __init__(self) -> None:
                self.closed = False

            def set_stream_callback(self, _callback: Any) -> None:
                return None

            def close(self) -> None:
                self.closed = True

        client = _DummyClient()
        app._attach_active_review_client(client)

        app.destroy()

        assert client.closed is True
        assert review_runtime.active_client() is None
        assert hasattr(app, "_legacy_compat_state") is False

    def test_destroy_releases_ai_fix_client(self, app: Any) -> None:
        """Destroying the app should close any active AI Fix backend."""
        class _DummyClient:
            def __init__(self) -> None:
                self.closed = False

            def set_stream_callback(self, _callback: Any) -> None:
                return None

            def close(self) -> None:
                self.closed = True

        client = _DummyClient()
        app._attach_active_ai_fix_client(client)

        app.destroy()

        assert client.closed is True
        assert app._active_ai_fix.client is None
        assert hasattr(app, "_legacy_compat_state") is False

    def test_destroy_cancels_active_health_check_timer(self, app: Any) -> None:
        """Destroying the app should cancel any active health-check timer."""
        class _DummyTimer:
            def __init__(self) -> None:
                self.cancelled = False

            def cancel(self) -> None:
                self.cancelled = True

        timer = _DummyTimer()
        app._begin_active_health_check("local")
        app._bind_active_health_check_timer(timer)

        app.destroy()

        assert timer.cancelled is True
        assert app._active_health_check.running is False
        assert app._active_health_check.backend_name is None
        assert app._active_health_check.timer is None
        assert hasattr(app, "_legacy_compat_state") is False

    def test_cancel_operation_sets_requested_status(self, app: Any) -> None:
        """Cancelling a running review should report that cancellation is pending."""
        status_bar = StatusBarHarness(app, _noop_wait_until)

        app._active_review.begin()
        app._attach_active_review_client(None)

        app._cancel_operation()

        assert status_bar.text() == t("gui.val.cancellation_requested")


class TestScopeToggle:
    """Verify scope switching shows/hides the correct frames."""

    def test_project_to_diff(self, app: Any) -> None:
        """Switching to diff scope should show diff_frame and hide file_select_frame."""
        app.scope_var.set("diff")
        app.update_idletasks()
        # diff_frame should be visible, file_select_frame hidden
        assert app.diff_frame.winfo_manager() != ""
        assert app.file_select_frame.winfo_manager() == ""

    def test_diff_to_project(self, app: Any) -> None:
        """Switching back to project should show file_select_frame and hide diff_frame."""
        app.scope_var.set("diff")
        app.update_idletasks()
        app.scope_var.set("project")
        app.update_idletasks()
        assert app.file_select_frame.winfo_manager() != ""
        assert app.diff_frame.winfo_manager() == ""


class TestDiffFilterToggle:
    """Verify diff filter checkbox enables/disables entry fields."""

    def test_enable_diff_filter(self, app: Any) -> None:
        """Enabling diff filter should enable related entry fields."""
        app.diff_filter_var.set(True)
        app.update_idletasks()
        assert app.diff_filter_file_entry.cget("state") == "normal"
        assert app.diff_filter_commits_entry.cget("state") == "normal"

    def test_disable_diff_filter(self, app: Any) -> None:
        """Disabling diff filter should disable related entry fields."""
        app.diff_filter_var.set(True)
        app.update_idletasks()
        app.diff_filter_var.set(False)
        app.update_idletasks()
        assert app.diff_filter_file_entry.cget("state") == "disabled"
        assert app.diff_filter_commits_entry.cget("state") == "disabled"


class TestBackendRadio:
    """Verify backend radio button switching."""

    def test_switch_backends(self, app: Any) -> None:
        """All backend values should be settable without error."""
        for backend in ["bedrock", "kiro", "copilot", "local"]:
            app.backend_var.set(backend)
            app.update_idletasks()
            assert app.backend_var.get() == backend
