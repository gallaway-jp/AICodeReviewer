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
from unittest.mock import patch

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

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


@pytest.fixture()
def app() -> Generator[Any, None, None]:
    """Create and yield an App in testing mode, then destroy it."""
    from aicodereviewer.gui.app import App
    application = App(testing_mode=True)
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

    def test_tabs_exist(self, app: Any) -> None:
        """All four tabs should be created."""
        assert hasattr(app, "tabs")
        # CTkTabview stores tabs in _tab_dict
        tab_dict = getattr(app.tabs, "_tab_dict", {})
        assert len(tab_dict) >= 4, f"Expected >= 4 tabs, got {len(tab_dict)}"

    def test_review_tab_widgets(self, app: Any) -> None:
        """Key Review tab widgets should exist."""
        assert hasattr(app, "path_entry")
        assert hasattr(app, "scope_var")
        assert hasattr(app, "backend_var")
        assert hasattr(app, "run_btn")
        assert hasattr(app, "dry_btn")
        assert hasattr(app, "health_btn")
        assert hasattr(app, "progress")

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

    def test_open_file_selector_noop(self, app: Any) -> None:
        """_open_file_selector should not open a modal window in testing mode."""
        app._open_file_selector()

    def test_show_health_error_noop(self, app: Any) -> None:
        """_show_health_error should log instead of showing messagebox."""
        app._show_health_error("test error")  # Should not block

    def test_reset_defaults_noop(self, app: Any) -> None:
        """_reset_defaults should return immediately in testing mode."""
        app._reset_defaults()  # Should not show confirmation dialog


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
