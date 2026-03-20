from __future__ import annotations

import logging
import configparser
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Generator

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aicodereviewer.i18n import t
from aicodereviewer.models import ReviewIssue
from aicodereviewer.config import config

from gui_test_utils import GuiTestHarness

try:
    import tkinter as tk

    _root = tk.Tk()
    _root.destroy()
    del _root
    HAS_DISPLAY = True
except (tk.TclError, RuntimeError):
    HAS_DISPLAY = False

pytestmark = pytest.mark.skipif(not HAS_DISPLAY, reason="No display available")


def _visible_issue_count(app: Any) -> int:
    return sum(1 for rec in app._issue_cards if rec["card"].winfo_manager() != "")


def _walk_widgets(widget: Any) -> list[Any]:
    widgets = [widget]
    for child in widget.winfo_children():
        widgets.extend(_walk_widgets(child))
    return widgets


def _find_widget_by_text(root: Any, text: str) -> Any:
    for widget in _walk_widgets(root):
        try:
            if widget.cget("text") == text:
                return widget
        except Exception:
            continue
    raise AssertionError(f"Widget with text {text!r} not found")


def _find_widget_containing_text(root: Any, fragment: str) -> Any:
    for widget in _walk_widgets(root):
        try:
            if fragment in str(widget.cget("text")):
                return widget
        except Exception:
            continue
    raise AssertionError(f"Widget containing text {fragment!r} not found")


def _latest_toplevel(app: Any) -> Any:
    toplevels = [child for child in app.winfo_children() if isinstance(child, tk.Toplevel)]
    if not toplevels:
        raise AssertionError("Expected a popup window to be open")
    return toplevels[-1]


def _reset_config_to_path(config_path: Path) -> None:
    config.config_path = config_path
    config.config = configparser.ConfigParser()
    config._set_defaults()
    if config_path.exists():
        config.config.read(config_path, encoding="utf-8")


def _save_default_config_to_path(config_path: Path) -> None:
    _reset_config_to_path(config_path)
    config.save()


class _FakeBackend:
    def __init__(self) -> None:
        self.cancelled = False
        self.closed = False
        self.stream_callbacks: list[Any] = []

    def set_stream_callback(self, callback: Any) -> None:
        self.stream_callbacks.append(callback)

    def cancel(self) -> None:
        self.cancelled = True

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def app_factory() -> Generator[Any, None, None]:
    from aicodereviewer.gui.app import App
    from aicodereviewer.config import config

    created_apps: list[Any] = []
    original_config_text = None
    if config.config_path and config.config_path.exists():
        original_config_text = config.config_path.read_text(encoding="utf-8")

    def _create() -> Any:
        try:
            application = App(testing_mode=True)
        except tk.TclError as exc:
            error_text = str(exc)
            known_tcl_env_failures = ("auto.tcl", "tcl_findLibrary", "tk.tcl", "usable tk.tcl")
            if any(marker in error_text for marker in known_tcl_env_failures):
                pytest.skip(f"Tk unavailable during App setup: {exc}")
            raise
        application._refresh_current_backend_models_async = lambda: None
        application._auto_health_check = lambda: None
        application.update_idletasks()
        created_apps.append(application)
        return application

    yield _create

    for application in reversed(created_apps):
        try:
            application.destroy()
        except Exception:
            pass
    if original_config_text is not None and config.config_path:
        config.config_path.write_text(original_config_text, encoding="utf-8")
        config.config.clear()
        config._set_defaults()
        config.config.read_string(original_config_text)


@pytest.fixture()
def harness(app_factory: Any) -> GuiTestHarness:
    return GuiTestHarness(app_factory())


def test_review_workflow_displays_results_and_releases_backend(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    runner_instances: list[Any] = []
    project_path = tmp_path / "project"
    project_path.mkdir()

    issue = ReviewIssue(
        file_path=str(project_path / "app.py"),
        line_number=7,
        issue_type="security",
        severity="high",
        description="Unsanitized input reaches a command invocation",
        code_snippet="run(cmd + user_input)",
        ai_feedback="Validate or escape user input before invoking the shell.",
    )

    class _SuccessfulRunner:
        def __init__(self, client: Any, *, scan_fn: Any, backend_name: str) -> None:
            self.client = client
            self.scan_fn = scan_fn
            self.backend_name = backend_name
            self.run_calls: list[dict[str, Any]] = []
            runner_instances.append(self)

        def run(self, **kwargs: Any) -> list[ReviewIssue]:
            self.run_calls.append(kwargs)
            self._pending_report_meta = {
                "project_path": kwargs["path"],
                "review_types": list(kwargs["review_types"]),
                "scope": kwargs["scope"],
                "total_files_scanned": 1,
                "language": kwargs["target_lang"],
                "diff_source": None,
                "programmers": list(kwargs["programmers"]),
                "reviewers": list(kwargs["reviewers"]),
                "backend": self.backend_name,
            }
            logging.getLogger("tests.gui.workflows").info("Simulated review for %s", kwargs["path"])
            return [issue]

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: backend)
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.AppRunner", _SuccessfulRunner)

    harness.enable_runtime_actions()
    harness.fill_valid_review_form(project_path)

    harness.start_review()
    harness.wait_until(
        lambda: not harness.app._running and len(harness.app._issue_cards) == 1,
        message="review did not populate the Results tab",
    )

    assert harness.app._issues == [issue]
    assert harness.app._review_runner is runner_instances[0]
    assert runner_instances[0].run_calls[0]["interactive"] is False
    assert runner_instances[0].run_calls[0]["dry_run"] is False
    assert harness.app.tabs.get() == t("gui.tab.results")
    assert harness.app.finalize_btn.cget("state") == "disabled"
    assert harness.app.save_session_btn.cget("state") == "normal"
    assert harness.app.cancel_btn.cget("state") == "disabled"
    assert harness.app._review_client is None
    assert backend.closed is True
    assert backend.stream_callbacks[-1] is None


def test_cancel_review_workflow_reports_requested_then_cancelled(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    entered_run = threading.Event()
    cancellation_seen = threading.Event()
    finish_run = threading.Event()
    project_path = tmp_path / "project"
    project_path.mkdir()

    class _BlockingRunner:
        def __init__(self, client: Any, *, scan_fn: Any, backend_name: str) -> None:
            self.client = client

        def run(self, **kwargs: Any) -> None:
            cancel_check = kwargs["cancel_check"]
            entered_run.set()
            while not cancel_check():
                time.sleep(0.01)
            cancellation_seen.set()
            finish_run.wait(timeout=1.0)
            return None

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: backend)
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.AppRunner", _BlockingRunner)

    harness.enable_runtime_actions()
    harness.fill_valid_review_form(project_path)
    harness.start_review()
    harness.wait_until(entered_run.is_set, message="review worker never started")
    harness.wait_until(lambda: harness.app._running, message="review never entered running state")

    harness.app._cancel_operation()
    harness.pump()

    assert backend.cancelled is True
    assert harness.app.status_var.get() == t("gui.val.cancellation_requested")

    harness.wait_until(cancellation_seen.is_set, message="runner never observed cancellation")
    finish_run.set()
    harness.wait_until(
        lambda: not harness.app._running and harness.app.status_var.get() == t("gui.val.cancelled"),
        message="review never finished after cancellation",
    )

    assert harness.app.status_var.get() == t("gui.val.cancelled")
    assert harness.app.cancel_btn.cget("state") == "disabled"
    assert harness.app._review_client is None
    assert backend.closed is True


def test_dry_run_workflow_switches_to_log_tab_and_records_output(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()

    class _DryRunRunner:
        def __init__(self, client: Any, *, scan_fn: Any, backend_name: str) -> None:
            self.client = client

        def run(self, **kwargs: Any) -> None:
            logging.getLogger("tests.gui.workflows").info(
                "Dry run inspected %s with %d review type(s)",
                kwargs["path"],
                len(kwargs["review_types"]),
            )
            return None

    def _unexpected_backend(_backend_name: str) -> Any:
        raise AssertionError("dry run should not create a backend")

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", _unexpected_backend)
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.AppRunner", _DryRunRunner)

    harness.enable_runtime_actions()
    harness.fill_valid_review_form(project_path)
    harness.start_dry_run()
    harness.wait_until(
        lambda: not harness.app._running and harness.app.status_var.get() == t("gui.val.dry_run_done"),
        message="dry run did not complete",
    )
    harness.wait_until(
        lambda: "Dry run inspected" in harness.log_text(),
        message="dry run log output never appeared in the Output Log tab",
    )

    assert harness.app.tabs.get() == t("gui.tab.log")
    assert harness.app._review_client is None


def test_session_can_be_saved_and_loaded_into_a_fresh_app(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App

    session_path = tmp_path / "session.json"
    backend = _FakeBackend()
    project_path = tmp_path / "project"
    project_path.mkdir()

    issue = ReviewIssue(
        file_path=str(project_path / "main.py"),
        line_number=11,
        issue_type="security",
        severity="medium",
        description="Session persistence should retain review metadata",
        ai_feedback="The saved session must preserve enough context to finalize later.",
    )

    class _SessionRunner:
        def __init__(self, client: Any, *, scan_fn: Any, backend_name: str) -> None:
            self.client = client
            self.backend_name = backend_name

        def run(self, **kwargs: Any) -> list[ReviewIssue]:
            self._pending_report_meta = {
                "project_path": kwargs["path"],
                "review_types": list(kwargs["review_types"]),
                "scope": kwargs["scope"],
                "total_files_scanned": 1,
                "language": kwargs["target_lang"],
                "diff_source": None,
                "programmers": list(kwargs["programmers"]),
                "reviewers": list(kwargs["reviewers"]),
                "backend": self.backend_name,
            }
            return [issue]

    monkeypatch.setattr(App, "_session_path", property(lambda _self: session_path))
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: backend)
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.AppRunner", _SessionRunner)

    first_harness = GuiTestHarness(app_factory())
    first_harness.enable_runtime_actions()
    first_harness.fill_valid_review_form(project_path)
    first_harness.start_review()
    first_harness.wait_until(
        lambda: not first_harness.app._running and len(first_harness.app._issue_cards) == 1,
        message="session setup review did not complete",
    )

    first_harness.app.save_session_btn.invoke()
    first_harness.pump()

    assert session_path.exists()

    second_harness = GuiTestHarness(app_factory())
    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.filedialog.askopenfilename",
        lambda **_: str(session_path),
    )

    second_harness.app.load_session_btn.invoke()
    second_harness.pump()

    assert len(second_harness.app._issues) == 1
    assert second_harness.app._issues[0].description == issue.description
    assert second_harness.app._review_runner is not None
    assert second_harness.app._review_runner._pending_report_meta["backend"] == (
        first_harness.app._review_runner._pending_report_meta["backend"]
    )
    assert second_harness.app._review_runner._pending_report_meta["project_path"] == str(project_path)


def test_settings_tab_values_persist_across_app_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-settings.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._theme_var.set(t("gui.settings.ui_theme_dark"))
    first_harness.app._lang_setting_var.set(t("gui.settings.ui_lang_ja"))
    first_harness.app._settings_backend_var.set(first_harness.app._backend_display_map["local"])
    first_harness.app._setting_entries[("local_llm", "api_url")].delete(0, "end")
    first_harness.app._setting_entries[("local_llm", "api_url")].insert(0, "http://127.0.0.1:9999")
    first_harness.app._setting_entries[("processing", "combine_files")].set(False)
    first_harness.app._format_vars["json"].set(False)
    first_harness.app._format_vars["txt"].set(True)
    first_harness.app._format_vars["md"].set(True)

    first_harness.app._save_settings()
    first_harness.pump()

    assert any(message == t("gui.settings.saved_ok") and not error for message, error in first_harness.toasts)
    assert config.get("gui", "theme") == "dark"
    assert config.get("gui", "language") == "ja"
    assert config.get("backend", "type") == "local"
    assert config.get("local_llm", "api_url") == "http://127.0.0.1:9999"
    assert config.get("processing", "combine_files") == "false"
    assert config.get("output", "formats") == "txt,md"

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._ui_lang == "ja"
    assert second_harness.app._theme_var.get() == t("gui.settings.ui_theme_dark")
    assert second_harness.app._lang_setting_var.get() == t("gui.settings.ui_lang_ja")
    assert second_harness.app._settings_backend_var.get() == second_harness.app._backend_display_map["local"]
    assert second_harness.app.backend_var.get() == "local"
    assert second_harness.app._setting_entries[("local_llm", "api_url")].get() == "http://127.0.0.1:9999"
    assert second_harness.app._setting_entries[("processing", "combine_files")].get() is False
    assert second_harness.app._format_vars["json"].get() is False
    assert second_harness.app._format_vars["txt"].get() is True
    assert second_harness.app._format_vars["md"].get() is True


def test_review_tab_form_values_persist_across_app_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-review.ini"
    project_path = tmp_path / "persisted-project"
    project_path.mkdir()
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.set_entry(first_harness.app.path_entry, str(project_path))
    first_harness.set_entry(first_harness.app.programmers_entry, "Alice, Bob")
    first_harness.set_entry(first_harness.app.reviewers_entry, "Charlie")
    first_harness.set_entry(first_harness.app.spec_entry, "review_spec.md")
    first_harness.app.file_select_mode_var.set("selected")
    first_harness.app.selected_files = ["src/app.py", "src/utils.py"]
    first_harness.app._file_count_lbl.configure(text="2 file(s) selected")
    first_harness.app.lang_var.set(t("gui.review.lang_ja"))
    first_harness.app.arch_analysis_var.set(True)
    first_harness.select_review_types("security", "performance")

    first_harness.app._save_form_values()
    first_harness.pump()

    assert config.get("gui", "project_path") == str(project_path)
    assert config.get("gui", "programmers") == "Alice, Bob"
    assert config.get("gui", "reviewers") == "Charlie"
    assert config.get("gui", "spec_file") == "review_spec.md"
    assert config.get("gui", "file_select_mode") == "selected"
    assert config.get("gui", "selected_files") == "src/app.py|src/utils.py"
    assert config.get("processing", "enable_architectural_review") is True
    assert set(str(config.get("gui", "review_types")).split(",")) == {"security", "performance"}
    config.set_value("gui", "review_language", "ja")
    config.save()

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app.path_entry.get() == str(project_path)
    assert second_harness.app.programmers_entry.get() == "Alice, Bob"
    assert second_harness.app.reviewers_entry.get() == "Charlie"
    assert second_harness.app.spec_entry.get() == "review_spec.md"
    assert second_harness.app.file_select_mode_var.get() == "selected"
    assert second_harness.app.selected_files == ["src/app.py", "src/utils.py"]
    assert second_harness.app.lang_var.get() == t("gui.review.lang_ja")
    assert second_harness.app.arch_analysis_var.get() is True
    assert second_harness.app.type_vars["security"].get() is True
    assert second_harness.app.type_vars["performance"].get() is True
    assert second_harness.app.type_vars["best_practices"].get() is False


def test_settings_invalid_numeric_value_does_not_persist_partial_changes(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-settings-invalid.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._theme_var.set(t("gui.settings.ui_theme_dark"))
    rate_limit_entry = first_harness.app._setting_entries[("performance", "max_requests_per_minute")]
    rate_limit_entry.delete(0, "end")
    rate_limit_entry.insert(0, "0")

    first_harness.app._save_settings()
    first_harness.pump()

    assert any("not a valid" in message and error for message, error in first_harness.toasts)
    assert config.get("gui", "theme") == "system"

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._theme_var.get() == t("gui.settings.ui_theme_system")
    assert second_harness.app._setting_entries[("performance", "max_requests_per_minute")].get() == "10"


def test_settings_require_at_least_one_output_format_without_persisting_invalid_state(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-settings-formats.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._format_vars["json"].set(False)
    first_harness.app._format_vars["txt"].set(False)
    first_harness.app._format_vars["md"].set(False)

    first_harness.app._save_settings()
    first_harness.pump()

    assert any(
        message == "At least one output format must be selected. JSON has been re-enabled." and error
        for message, error in first_harness.toasts
    )
    assert first_harness.app._format_vars["json"].get() is True
    assert first_harness.app._format_vars["txt"].get() is False
    assert first_harness.app._format_vars["md"].get() is False

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._format_vars["json"].get() is True
    assert second_harness.app._format_vars["txt"].get() is True
    assert second_harness.app._format_vars["md"].get() is False


def test_bedrock_settings_persist_across_app_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-bedrock.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._settings_backend_var.set(first_harness.app._backend_display_map["bedrock"])
    first_harness.app._setting_entries[("model", "model_id")].set("anthropic.claude-3-7-sonnet-20250219-v1:0")
    first_harness.set_entry(first_harness.app._setting_entries[("aws", "region")], "ap-northeast-1")
    first_harness.set_entry(first_harness.app._setting_entries[("aws", "sso_session")], "corp-sso")
    first_harness.set_entry(first_harness.app._setting_entries[("aws", "access_key_id")], "AKIA_TEST_KEY")

    first_harness.app._save_settings()
    first_harness.pump()

    assert config.get("backend", "type") == "bedrock"
    assert config.get("model", "model_id") == "anthropic.claude-3-7-sonnet-20250219-v1:0"
    assert config.get("aws", "region") == "ap-northeast-1"
    assert config.get("aws", "sso_session") == "corp-sso"
    assert config.get("aws", "access_key_id") == "AKIA_TEST_KEY"

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._settings_backend_var.get() == second_harness.app._backend_display_map["bedrock"]
    assert second_harness.app.backend_var.get() == "bedrock"
    assert second_harness.app._setting_entries[("model", "model_id")].get() == "anthropic.claude-3-7-sonnet-20250219-v1:0"
    assert second_harness.app._setting_entries[("aws", "region")].get() == "ap-northeast-1"
    assert second_harness.app._setting_entries[("aws", "sso_session")].get() == "corp-sso"
    assert second_harness.app._setting_entries[("aws", "access_key_id")].get() == "AKIA_TEST_KEY"


def test_kiro_settings_persist_across_app_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-kiro.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._settings_backend_var.set(first_harness.app._backend_display_map["kiro"])
    first_harness.app._setting_entries[("kiro", "wsl_distro")].set("Ubuntu-24.04")
    first_harness.set_entry(first_harness.app._setting_entries[("kiro", "cli_command")], "kiro-cli")
    first_harness.set_entry(first_harness.app._setting_entries[("kiro", "timeout")], "450")
    first_harness.app._setting_entries[("kiro", "model")].set("claude-sonnet-4")

    first_harness.app._save_settings()
    first_harness.pump()

    assert config.get("backend", "type") == "kiro"
    assert config.get("kiro", "wsl_distro") == "Ubuntu-24.04"
    assert config.get("kiro", "cli_command") == "kiro-cli"
    assert config.get("kiro", "timeout") == "450"
    assert config.get("kiro", "model") == "claude-sonnet-4"

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._settings_backend_var.get() == second_harness.app._backend_display_map["kiro"]
    assert second_harness.app.backend_var.get() == "kiro"
    assert second_harness.app._setting_entries[("kiro", "wsl_distro")].get() == "Ubuntu-24.04"
    assert second_harness.app._setting_entries[("kiro", "cli_command")].get() == "kiro-cli"
    assert second_harness.app._setting_entries[("kiro", "timeout")].get() == "450"
    assert second_harness.app._setting_entries[("kiro", "model")].get() == "claude-sonnet-4"


def test_copilot_settings_persist_across_app_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-copilot.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._settings_backend_var.set(first_harness.app._backend_display_map["copilot"])
    first_harness.set_entry(first_harness.app._setting_entries[("copilot", "copilot_path")], "gh-copilot")
    first_harness.set_entry(first_harness.app._setting_entries[("copilot", "timeout")], "420")
    first_harness.app._setting_entries[("copilot", "model")].set("gpt-5")

    first_harness.app._save_settings()
    first_harness.pump()

    assert config.get("backend", "type") == "copilot"
    assert config.get("copilot", "copilot_path") == "gh-copilot"
    assert config.get("copilot", "timeout") == "420"
    assert config.get("copilot", "model") == "gpt-5"

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._settings_backend_var.get() == second_harness.app._backend_display_map["copilot"]
    assert second_harness.app.backend_var.get() == "copilot"
    assert second_harness.app._setting_entries[("copilot", "copilot_path")].get() == "gh-copilot"
    assert second_harness.app._setting_entries[("copilot", "timeout")].get() == "420"
    assert second_harness.app._setting_entries[("copilot", "model")].get() == "gpt-5"


def test_local_llm_settings_persist_across_app_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-local-llm.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._settings_backend_var.set(first_harness.app._backend_display_map["local"])
    first_harness.set_entry(first_harness.app._setting_entries[("local_llm", "api_url")], "http://127.0.0.1:11434")
    first_harness.app._setting_entries[("local_llm", "api_type")].set("ollama")
    first_harness.app._setting_entries[("local_llm", "model")].set("llama3.2")
    first_harness.set_entry(first_harness.app._setting_entries[("local_llm", "api_key")], "local-secret")
    first_harness.set_entry(first_harness.app._setting_entries[("local_llm", "timeout")], "360")
    first_harness.set_entry(first_harness.app._setting_entries[("local_llm", "max_tokens")], "8192")

    first_harness.app._save_settings()
    first_harness.pump()

    assert config.get("backend", "type") == "local"
    assert config.get("local_llm", "api_url") == "http://127.0.0.1:11434"
    assert config.get("local_llm", "api_type") == "ollama"
    assert config.get("local_llm", "model") == "llama3.2"
    assert config.get("local_llm", "api_key") == "local-secret"
    assert config.get("local_llm", "timeout") == "360"
    assert config.get("local_llm", "max_tokens") == "8192"

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._settings_backend_var.get() == second_harness.app._backend_display_map["local"]
    assert second_harness.app.backend_var.get() == "local"
    assert second_harness.app._setting_entries[("local_llm", "api_url")].get() == "http://127.0.0.1:11434"
    assert second_harness.app._setting_entries[("local_llm", "api_type")].get() == "ollama"
    assert second_harness.app._setting_entries[("local_llm", "model")].get() == "llama3.2"
    assert second_harness.app._setting_entries[("local_llm", "api_key")].get() == "local-secret"
    assert second_harness.app._setting_entries[("local_llm", "timeout")].get() == "360"
    assert second_harness.app._setting_entries[("local_llm", "max_tokens")].get() == "8192"


def test_runtime_tuning_settings_persist_across_app_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-runtime-tuning.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.set_entry(first_harness.app._setting_entries[("performance", "max_requests_per_minute")], "24")
    first_harness.set_entry(first_harness.app._setting_entries[("performance", "min_request_interval_seconds")], "1.5")
    first_harness.set_entry(first_harness.app._setting_entries[("performance", "max_file_size_mb")], "25")
    first_harness.set_entry(first_harness.app._setting_entries[("processing", "batch_size")], "8")
    first_harness.app._setting_entries[("processing", "combine_files")].set(False)

    first_harness.app._save_settings()
    first_harness.pump()

    assert config.get("performance", "max_requests_per_minute") == 24
    assert config.get("performance", "min_request_interval_seconds") == 1.5
    assert config.get("performance", "max_file_size_mb") == 25 * 1024 * 1024
    assert config.get("processing", "batch_size") == 8
    assert config.get("processing", "combine_files") == "false"

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._setting_entries[("performance", "max_requests_per_minute")].get() == "24"
    assert second_harness.app._setting_entries[("performance", "min_request_interval_seconds")].get() == "1.5"
    assert second_harness.app._setting_entries[("performance", "max_file_size_mb")].get() == "25"
    assert second_harness.app._setting_entries[("processing", "batch_size")].get() == "8"
    assert second_harness.app._setting_entries[("processing", "combine_files")].get() is False


def test_settings_save_failure_shows_error_and_does_not_persist_to_disk(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-save-failure.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._theme_var.set(t("gui.settings.ui_theme_dark"))
    first_harness.set_entry(first_harness.app._setting_entries[("local_llm", "api_url")], "http://127.0.0.1:8888")

    monkeypatch.setattr(config, "save", lambda: (_ for _ in ()).throw(RuntimeError("disk full")))

    first_harness.app._save_settings()
    first_harness.pump()

    assert any(
        message == t("gui.settings.save_error", error="disk full") and error
        for message, error in first_harness.toasts
    )

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._theme_var.get() == t("gui.settings.ui_theme_system")
    assert second_harness.app._setting_entries[("local_llm", "api_url")].get() == "http://localhost:1234"


def test_skip_and_undo_workflow_updates_results_actions(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/example.py",
        line_number=10,
        issue_type="performance",
        severity="medium",
        description="A skipped issue should still be finalizable until it is undone.",
        ai_feedback="Skipping should preserve a reviewer reason.",
    )

    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues([issue])
    harness.pump()

    card = harness.app._issue_cards[0]
    card["skip_btn"].invoke()
    harness.pump()

    assert issue.status == "skipped"
    assert harness.app.finalize_btn.cget("state") == "normal"
    assert harness.app.review_changes_btn.cget("state") == "disabled"
    assert card["skip_frame"].winfo_manager() != ""

    card["undo_btn"].invoke()
    harness.pump()

    assert issue.status == "pending"
    assert issue.resolution_reason is None
    assert card["skip_frame"].winfo_manager() == ""
    assert harness.app.finalize_btn.cget("state") == "disabled"


def test_review_changes_recreates_backend_and_auto_finalizes(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    verification_backend = _FakeBackend()
    report_path = tmp_path / "review-report.json"
    issue = ReviewIssue(
        file_path="src/example.py",
        line_number=22,
        issue_type="security",
        severity="high",
        description="Resolved issues should be re-verified even without a live backend client.",
        ai_feedback="Review Changes should recreate a client from saved metadata.",
        status="resolved",
    )
    report_calls: list[list[str]] = []
    verify_calls: list[tuple[Any, Any, str, str]] = []
    backend_creations: list[str] = []

    def _generate_report(issues: list[ReviewIssue]) -> str:
        report_calls.append([current.status for current in issues])
        return str(report_path)

    harness.enable_runtime_actions()
    harness.app._review_runner = SimpleNamespace(
        _pending_report_meta={"backend": "local"},
        generate_report=_generate_report,
    )
    harness.app._show_issues([issue])
    harness.pump()

    assert harness.app.review_changes_btn.cget("state") == "normal"
    assert harness.app._review_client is None

    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.create_backend",
        lambda backend_name: backend_creations.append(backend_name) or verification_backend,
    )
    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.verify_issue_resolved",
        lambda current_issue, client, issue_type, language: verify_calls.append(
            (current_issue, client, issue_type, language)
        ) or True,
    )

    harness.app.review_changes_btn.invoke()
    harness.wait_until(
        lambda: not harness.app._running and report_calls,
        message="review changes did not complete and finalize",
    )

    assert backend_creations == ["local"]
    assert len(verify_calls) == 1
    assert verify_calls[0][1] is verification_backend
    assert report_calls == [["fixed"]]
    assert verification_backend.closed is True
    assert harness.app._review_client is None
    assert harness.app._issues == []
    assert harness.app._review_runner is None
    assert any(message == t("gui.results.all_fixed") and not error for message, error in harness.toasts)


def test_finalize_workflow_saves_report_and_clears_results(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "final-report.json"
    issues = [
        ReviewIssue(
            file_path="src/fixed.py",
            line_number=12,
            issue_type="security",
            severity="high",
            description="A fixed issue should be included in the final report.",
            ai_feedback="Finalize should persist the reviewed issue set.",
            status="fixed",
        ),
        ReviewIssue(
            file_path="src/skipped.py",
            line_number=14,
            issue_type="performance",
            severity="low",
            description="A skipped issue should also be included in the final report.",
            ai_feedback="Skipped issues still belong in the report.",
            status="skipped",
        ),
    ]
    report_calls: list[list[str]] = []

    def _generate_report(current_issues: list[ReviewIssue]) -> str:
        report_calls.append([issue.status for issue in current_issues])
        return str(report_path)

    harness.enable_runtime_actions()
    harness.app._review_runner = SimpleNamespace(generate_report=_generate_report)
    harness.app._show_issues(issues)
    harness.pump()

    assert harness.app.finalize_btn.cget("state") == "normal"

    harness.app.finalize_btn.invoke()
    harness.pump()

    assert report_calls == [["fixed", "skipped"]]
    assert harness.app.status_var.get() == t("gui.val.report_saved", path=str(report_path))
    assert harness.app._issues == []
    assert harness.app._issue_cards == []
    assert harness.app._review_runner is None
    assert harness.app.finalize_btn.cget("state") == "disabled"
    assert any(message == t("gui.results.finalized") and not error for message, error in harness.toasts)


def test_health_check_workflow_shows_report_and_restores_controls(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown_reports: list[Any] = []
    fake_report = SimpleNamespace(backend="local", ready=True, summary="Local backend ready", checks=[])

    harness.enable_runtime_actions()
    harness.app.backend_var.set("local")
    harness.pump()

    monkeypatch.setattr("aicodereviewer.gui.health_mixin.check_backend", lambda backend_name: fake_report)
    monkeypatch.setattr(harness.app, "_show_health_dialog", lambda report: shown_reports.append(report))

    harness.start_health_check()
    harness.wait_until(
        lambda: harness.app._health_check_backend is None and shown_reports,
        message="health check did not finish and surface a report",
    )

    assert shown_reports == [fake_report]
    assert harness.app.status_var.get() == t("common.ready")
    assert harness.app.health_btn.cget("state") == "normal"
    assert harness.app.cancel_btn.cget("state") == "disabled"


def test_health_check_can_be_cancelled_before_backend_returns(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered_check = threading.Event()
    release_check = threading.Event()
    shown_reports: list[Any] = []

    def _blocking_check(_backend_name: str) -> Any:
        entered_check.set()
        release_check.wait(timeout=1.0)
        return SimpleNamespace(backend="local", ready=True, summary="should not surface", checks=[])

    harness.enable_runtime_actions()
    harness.app.backend_var.set("local")
    harness.pump()

    monkeypatch.setattr("aicodereviewer.gui.health_mixin.check_backend", _blocking_check)
    monkeypatch.setattr(harness.app, "_show_health_dialog", lambda report: shown_reports.append(report))

    harness.start_health_check()
    harness.wait_until(entered_check.is_set, message="health check worker never started")
    harness.wait_until(
        lambda: harness.app._health_check_backend == "local",
        message="health check never entered running state",
    )

    harness.app.cancel_btn.invoke()
    harness.pump()

    assert harness.app.status_var.get() == t("gui.val.cancelled")
    assert harness.app._health_check_backend is None
    assert harness.app.cancel_btn.cget("state") == "disabled"

    release_check.set()
    harness.wait_until(lambda: True, timeout=0.05)
    harness.pump(3)

    assert shown_reports == []
    assert harness.app.health_btn.cget("state") == "normal"


def test_ai_fix_recreates_backend_and_generates_preview_results(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FixBackend(_FakeBackend):
        def get_fix(self, *, code_content: str, issue_feedback: str, review_type: str, lang: str) -> str:
            return f"# fixed for {review_type} in {lang}\n{code_content or issue_feedback}"

    backend = _FixBackend()
    shown_popups: list[tuple[list[int], dict[int, str | None]]] = []
    issue = ReviewIssue(
        file_path="src/needs_fix.py",
        line_number=30,
        issue_type="security",
        severity="high",
        description="Pending issue should request an AI fix with a recreated backend.",
        ai_feedback="Generate a safer implementation.",
        code_snippet="dangerous_call()\n",
    )

    harness.enable_runtime_actions()
    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues([issue])
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    card = harness.app._issue_cards[0]
    assert card["fix_checkbox"].winfo_manager() != ""
    assert card["fix_check_var"].get() is True

    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.create_backend",
        lambda backend_name: backend,
    )
    monkeypatch.setattr(
        harness.app,
        "_show_batch_fix_popup",
        lambda selected, results: shown_popups.append(
            ([idx for idx, _rec in selected], dict(results))
        ),
    )

    harness.app.start_ai_fix_btn.invoke()
    harness.wait_until(
        lambda: bool(shown_popups),
        message="AI Fix did not produce preview results",
    )

    assert shown_popups[0][0] == [0]
    assert shown_popups[0][1][0] is not None
    assert "security" in shown_popups[0][1][0]
    assert backend.closed is True
    assert harness.app._review_client is None


def test_ai_fix_can_be_cancelled_while_generating(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered_fix = threading.Event()
    release_fix = threading.Event()
    popup_calls: list[Any] = []

    class _BlockingFixBackend(_FakeBackend):
        def get_fix(self, *, code_content: str, issue_feedback: str, review_type: str, lang: str) -> str:
            entered_fix.set()
            release_fix.wait(timeout=1.0)
            return "# late fix"

    backend = _BlockingFixBackend()
    issue = ReviewIssue(
        file_path="src/slow_fix.py",
        line_number=8,
        issue_type="performance",
        severity="medium",
        description="Long-running AI fixes should be cancellable.",
        ai_feedback="Optimize the loop.",
        code_snippet="for item in items: pass\n",
    )

    harness.enable_runtime_actions()
    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues([issue])
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.create_backend",
        lambda backend_name: backend,
    )
    monkeypatch.setattr(
        harness.app,
        "_show_batch_fix_popup",
        lambda selected, results: popup_calls.append((selected, results)),
    )

    harness.app.start_ai_fix_btn.invoke()
    harness.wait_until(entered_fix.is_set, message="AI Fix worker never started")

    harness.app.cancel_ai_fix_btn.invoke()
    harness.pump()

    assert harness.app._ai_fix_cancel_event.is_set() is True
    assert harness.app.status_var.get() == t("gui.results.cancelling_status")

    release_fix.set()
    harness.wait_until(
        lambda: not harness.app._ai_fix_running,
        message="AI Fix did not finish cancellation cleanup",
    )
    harness.pump()

    assert popup_calls == []
    assert harness.app.status_var.get() == t("common.ready")
    assert harness.app.cancel_ai_fix_btn.cget("text") == t("gui.results.cancel_ai_fix")
    assert backend.closed is True
    assert harness.app._review_client is None


def test_results_filters_match_visible_issue_cards(
    harness: GuiTestHarness,
) -> None:
    issues = [
        ReviewIssue(
            file_path="src/security.py",
            line_number=5,
            issue_type="security",
            severity="high",
            description="Security issue visible through severity and type filters.",
            ai_feedback="Use parameterized queries.",
            status="pending",
        ),
        ReviewIssue(
            file_path="src/perf.py",
            line_number=6,
            issue_type="performance",
            severity="low",
            description="Performance issue visible through status and type filters.",
            ai_feedback="Avoid nested loops.",
            status="skipped",
        ),
        ReviewIssue(
            file_path="src/docs.py",
            line_number=7,
            issue_type="documentation",
            severity="info",
            description="Documentation issue should be hidden by unrelated filters.",
            ai_feedback="Add missing contributor setup docs.",
            status="fixed",
        ),
    ]

    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues(issues)
    harness.pump()

    assert _visible_issue_count(harness.app) == 3

    harness.app._filter_sev_var.set("High")
    harness.app._apply_filters()
    harness.pump()

    assert _visible_issue_count(harness.app) == 1
    assert harness.app._filter_count_lbl.cget("text") == t("gui.results.filter_count", visible=1, total=3)

    harness.app._filter_sev_var.set(t("gui.results.filter_all"))
    harness.app._filter_status_var.set("Skipped")
    harness.app._filter_type_var.set(t("review_type.performance"))
    harness.app._apply_filters()
    harness.pump()

    assert _visible_issue_count(harness.app) == 1
    assert harness.app._issue_cards[1]["card"].winfo_manager() != ""

    harness.app._clear_filters()
    harness.pump()

    assert _visible_issue_count(harness.app) == 3
    assert harness.app._filter_count_lbl.cget("text") == ""


def test_restored_session_review_changes_recreates_backend_and_finalizes(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App

    session_path = tmp_path / "session.json"
    report_path = tmp_path / "restored-report.json"
    session_data = {
        "saved_at": "2026-03-20T00:00:00",
        "issues": [
            {
                "file_path": "src/restored.py",
                "line_number": 9,
                "issue_type": "security",
                "severity": "high",
                "description": "Restored session should allow review verification.",
                "code_snippet": "run(user_input)",
                "ai_feedback": "Escape or validate user input.",
                "status": "resolved",
                "resolution_reason": None,
                "resolved_at": None,
                "ai_fix_applied": None,
                "related_issues": [],
                "interaction_summary": None,
            }
        ],
        "report_meta": {
            "project_path": str(tmp_path / "project"),
            "review_types": ["security"],
            "scope": "project",
            "total_files_scanned": 1,
            "language": "en",
            "diff_source": None,
            "programmers": ["Alice"],
            "reviewers": ["Bob"],
            "backend": "local",
        },
    }
    session_path.write_text(__import__("json").dumps(session_data), encoding="utf-8")

    backend = _FakeBackend()
    verify_calls: list[tuple[Any, Any, str, str]] = []

    monkeypatch.setattr(App, "_session_path", property(lambda _self: session_path))

    harness = GuiTestHarness(app_factory())
    harness.enable_runtime_actions()
    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.filedialog.askopenfilename",
        lambda **_: str(session_path),
    )
    harness.app.load_session_btn.invoke()
    harness.pump()

    assert harness.app.review_changes_btn.cget("state") == "normal"

    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.create_backend",
        lambda backend_name: backend,
    )
    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.verify_issue_resolved",
        lambda issue, client, issue_type, language: verify_calls.append(
            (issue, client, issue_type, language)
        ) or True,
    )
    harness.app._review_runner.generate_report = lambda issues: str(report_path)

    harness.app.review_changes_btn.invoke()
    harness.wait_until(
        lambda: not harness.app._running and harness.app._issues == [],
        message="restored session review changes did not finish",
    )

    assert len(verify_calls) == 1
    assert verify_calls[0][1] is backend
    assert backend.closed is True
    assert harness.app._review_runner is None
    assert any(message == t("gui.results.all_fixed") and not error for message, error in harness.toasts)


def test_restored_session_ai_fix_recreates_backend_and_opens_preview(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App

    session_path = tmp_path / "session.json"
    session_data = {
        "saved_at": "2026-03-20T00:00:00",
        "issues": [
            {
                "file_path": "src/restored-fix.py",
                "line_number": 11,
                "issue_type": "performance",
                "severity": "medium",
                "description": "Restored session should allow AI Fix preview.",
                "code_snippet": "for item in items: pass\n",
                "ai_feedback": "Use a more efficient approach.",
                "status": "pending",
                "resolution_reason": None,
                "resolved_at": None,
                "ai_fix_applied": None,
                "related_issues": [],
                "interaction_summary": None,
            }
        ],
        "report_meta": {
            "project_path": str(tmp_path / "project"),
            "review_types": ["performance"],
            "scope": "project",
            "total_files_scanned": 1,
            "language": "en",
            "diff_source": None,
            "programmers": ["Alice"],
            "reviewers": ["Bob"],
            "backend": "local",
        },
    }
    session_path.write_text(__import__("json").dumps(session_data), encoding="utf-8")

    class _FixBackend(_FakeBackend):
        def get_fix(self, *, code_content: str, issue_feedback: str, review_type: str, lang: str) -> str:
            return f"# restored session fix for {review_type}\n{code_content or issue_feedback}"

    backend = _FixBackend()
    shown_popups: list[tuple[list[int], dict[int, str | None]]] = []

    monkeypatch.setattr(App, "_session_path", property(lambda _self: session_path))

    harness = GuiTestHarness(app_factory())
    harness.enable_runtime_actions()
    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.filedialog.askopenfilename",
        lambda **_: str(session_path),
    )
    harness.app.load_session_btn.invoke()
    harness.pump()

    assert harness.app.ai_fix_mode_btn.cget("state") == "normal"

    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.create_backend",
        lambda backend_name: backend,
    )
    monkeypatch.setattr(
        harness.app,
        "_show_batch_fix_popup",
        lambda selected, results: shown_popups.append(
            ([idx for idx, _rec in selected], dict(results))
        ),
    )

    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()
    harness.app.start_ai_fix_btn.invoke()
    harness.wait_until(
        lambda: bool(shown_popups),
        message="restored session AI Fix did not produce preview results",
    )

    assert shown_popups[0][0] == [0]
    assert shown_popups[0][1][0] is not None
    assert backend.closed is True
    assert harness.app._review_client is None


def test_ai_fix_apply_popup_can_apply_only_selected_fixes(
    harness: GuiTestHarness,
) -> None:
    issues = [
        ReviewIssue(
            file_path="src/first.py",
            line_number=3,
            issue_type="security",
            severity="high",
            description="First pending issue should be applied.",
            ai_feedback="First fix.",
            status="pending",
        ),
        ReviewIssue(
            file_path="src/second.py",
            line_number=4,
            issue_type="performance",
            severity="medium",
            description="Second pending issue should stay pending if unchecked.",
            ai_feedback="Second fix.",
            status="pending",
        ),
    ]
    selected = []
    results = {
        0: "# first fixed\nprint('first')\n",
        1: "# second fixed\nprint('second')\n",
    }

    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues(issues)
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    selected = list(enumerate(harness.app._issue_cards))
    harness.app._show_batch_fix_popup(selected, results)
    harness.pump()

    popup = _latest_toplevel(harness.app)
    second_checkbox = _find_widget_by_text(popup, Path(issues[1].file_path).name)
    second_checkbox.deselect()
    harness.pump()

    apply_button = _find_widget_by_text(popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert issues[0].status == "resolved"
    assert issues[0].ai_fix_applied == results[0]
    assert issues[1].status == "pending"
    assert issues[1].ai_fix_applied is None
    assert harness.app._ai_fix_mode is False
    assert harness.app.ai_fix_mode_btn.winfo_manager() != ""
    assert any(
        message == t("gui.results.batch_fix_applied", count=1) and not error
        for message, error in harness.toasts
    )


def test_ai_fix_start_requires_at_least_one_selected_issue(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/unselected.py",
        line_number=5,
        issue_type="security",
        severity="high",
        description="Starting AI Fix with nothing selected should show an error toast.",
        ai_feedback="This fix will not be requested.",
        status="pending",
    )

    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues([issue])
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    card = harness.app._issue_cards[0]
    card["fix_checkbox"].deselect()
    harness.pump()

    harness.app.start_ai_fix_btn.invoke()
    harness.pump()

    assert harness.app._ai_fix_running is False
    assert any(
        message == t("gui.results.no_issues_selected") and error
        for message, error in harness.toasts
    )


def test_ai_fix_preview_edit_save_applies_user_edited_fix(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = ReviewIssue(
        file_path="src/edited_fix.py",
        line_number=12,
        issue_type="security",
        severity="high",
        description="Saving an edited preview should replace the generated AI fix.",
        ai_feedback="Use a safer command invocation.",
        status="pending",
        code_snippet="run(user_input)\n",
    )
    generated_fix = "safe_run(user_input)\n"
    edited_fix = "validated = sanitize(user_input)\nsafe_run(validated)\n"

    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues([issue])
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    selected = list(enumerate(harness.app._issue_cards))
    harness.app._show_batch_fix_popup(selected, {0: generated_fix})
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    monkeypatch.setattr(
        harness.app,
        "_open_builtin_editor",
        lambda idx, _initial_content=None, _on_save=None: _on_save and _on_save(edited_fix),
    )

    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump()

    preview_popup = _latest_toplevel(harness.app)
    edit_button = _find_widget_containing_text(preview_popup, "Edit")
    edit_button.invoke()
    harness.pump()

    save_and_close_button = _find_widget_containing_text(preview_popup, "Save and Close")
    save_and_close_button.invoke()
    harness.pump()

    assert issue.status == "pending"
    assert any(message == t("gui.results.preview_staged") and not error for message, error in harness.toasts)

    apply_button = _find_widget_by_text(batch_popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert issue.status == "resolved"
    assert issue.ai_fix_applied == edited_fix
    assert any(
        message == t("gui.results.batch_fix_applied", count=1) and not error
        for message, error in harness.toasts
    )


def test_ai_fix_preview_undo_restores_original_generated_fix(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = ReviewIssue(
        file_path="src/undo_fix.py",
        line_number=13,
        issue_type="performance",
        severity="medium",
        description="Undoing user preview edits should keep the original AI fix.",
        ai_feedback="Reduce duplicate work.",
        status="pending",
        code_snippet="for item in items:\n    work(item)\n",
    )
    generated_fix = "for item in unique_items:\n    work(item)\n"
    edited_fix = "cached_items = tuple(unique_items)\nfor item in cached_items:\n    work(item)\n"

    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues([issue])
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    selected = list(enumerate(harness.app._issue_cards))
    harness.app._show_batch_fix_popup(selected, {0: generated_fix})
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    monkeypatch.setattr(
        harness.app,
        "_open_builtin_editor",
        lambda idx, _initial_content=None, _on_save=None: _on_save and _on_save(edited_fix),
    )

    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump()

    preview_popup = _latest_toplevel(harness.app)
    edit_button = _find_widget_containing_text(preview_popup, "Edit")
    edit_button.invoke()
    harness.pump()

    undo_button = _find_widget_containing_text(preview_popup, "Undo User Changes")
    undo_button.invoke()
    harness.pump()

    close_button = _find_widget_by_text(preview_popup, t("common.close"))
    close_button.invoke()
    harness.pump()

    apply_button = _find_widget_by_text(batch_popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert issue.status == "resolved"
    assert issue.ai_fix_applied == generated_fix
    assert not any(message == t("gui.results.editor_saved") and not error for message, error in harness.toasts)


def test_ai_fix_apply_popup_writes_selected_fix_to_real_file(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    target_file = tmp_path / "apply_fix.py"
    target_file.write_text("run(user_input)\n", encoding="utf-8")
    generated_fix = "validated = sanitize(user_input)\nsafe_run(validated)\n"
    issue = ReviewIssue(
        file_path=str(target_file),
        line_number=1,
        issue_type="security",
        severity="high",
        description="Applying a selected AI fix should write the generated content to disk.",
        ai_feedback="Sanitize user input before execution.",
        status="pending",
        code_snippet=target_file.read_text(encoding="utf-8"),
    )

    harness.enable_runtime_actions()
    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues([issue])
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    selected = list(enumerate(harness.app._issue_cards))
    harness.app._show_batch_fix_popup(selected, {0: generated_fix})
    harness.pump()

    popup = _latest_toplevel(harness.app)
    apply_button = _find_widget_by_text(popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert target_file.read_text(encoding="utf-8") == generated_fix
    assert issue.status == "resolved"
    assert issue.ai_fix_applied == generated_fix
    assert harness.app._ai_fix_mode is False
    assert any(
        message == t("gui.results.batch_fix_applied", count=1) and not error
        for message, error in harness.toasts
    )


def test_ai_fix_preview_save_and_close_stages_edited_content_until_apply(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target_file = tmp_path / "preview_edit_fix.py"
    target_file.write_text("run(user_input)\n", encoding="utf-8")
    generated_fix = "safe_run(user_input)\n"
    edited_fix = "validated = sanitize(user_input)\nsafe_run(validated)\n"
    issue = ReviewIssue(
        file_path=str(target_file),
        line_number=1,
        issue_type="security",
        severity="high",
        description="Saving a preview edit in runtime mode should stage the edited content until apply.",
        ai_feedback="Sanitize user input before execution.",
        status="pending",
        code_snippet=target_file.read_text(encoding="utf-8"),
    )

    harness.enable_runtime_actions()
    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues([issue])
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    selected = list(enumerate(harness.app._issue_cards))
    harness.app._show_batch_fix_popup(selected, {0: generated_fix})
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    monkeypatch.setattr(
        harness.app,
        "_open_builtin_editor",
        lambda idx, _initial_content=None, _on_save=None: _on_save and _on_save(edited_fix),
    )

    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump()

    preview_popup = _latest_toplevel(harness.app)
    edit_button = _find_widget_containing_text(preview_popup, "Edit")
    edit_button.invoke()
    harness.pump()

    save_and_close_button = _find_widget_containing_text(preview_popup, "Save and Close")
    save_and_close_button.invoke()
    harness.pump()

    assert target_file.read_text(encoding="utf-8") == "run(user_input)\n"
    assert issue.status == "pending"
    assert any(message == t("gui.results.preview_staged") and not error for message, error in harness.toasts)

    apply_button = _find_widget_by_text(batch_popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert target_file.read_text(encoding="utf-8") == edited_fix
    assert issue.status == "resolved"
    assert issue.ai_fix_applied == edited_fix
    assert harness.app._ai_fix_mode is False
    assert any(
        message == t("gui.results.batch_fix_applied", count=1) and not error
        for message, error in harness.toasts
    )


def test_ai_fix_mixed_runtime_batch_preserves_edited_and_direct_applied_fixes(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    edited_target = tmp_path / "edited_batch_fix.py"
    direct_target = tmp_path / "direct_batch_fix.py"
    edited_target.write_text("run(user_input)\n", encoding="utf-8")
    direct_target.write_text("for item in items:\n    work(item)\n", encoding="utf-8")

    edited_generated_fix = "safe_run(user_input)\n"
    edited_user_fix = "validated = sanitize(user_input)\nsafe_run(validated)\n"
    direct_generated_fix = "for item in unique_items:\n    work(item)\n"

    issues = [
        ReviewIssue(
            file_path=str(edited_target),
            line_number=1,
            issue_type="security",
            severity="high",
            description="First issue should keep the user-edited preview content.",
            ai_feedback="Sanitize user input before execution.",
            status="pending",
            code_snippet=edited_target.read_text(encoding="utf-8"),
        ),
        ReviewIssue(
            file_path=str(direct_target),
            line_number=1,
            issue_type="performance",
            severity="medium",
            description="Second issue should use the directly applied generated fix.",
            ai_feedback="Avoid duplicate work.",
            status="pending",
            code_snippet=direct_target.read_text(encoding="utf-8"),
        ),
    ]

    harness.enable_runtime_actions()
    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues(issues)
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    selected = list(enumerate(harness.app._issue_cards))
    harness.app._show_batch_fix_popup(
        selected,
        {
            0: edited_generated_fix,
            1: direct_generated_fix,
        },
    )
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    monkeypatch.setattr(
        harness.app,
        "_open_builtin_editor",
        lambda idx, _initial_content=None, _on_save=None: _on_save and _on_save(edited_user_fix),
    )

    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump()

    preview_popup = _latest_toplevel(harness.app)
    edit_button = _find_widget_containing_text(preview_popup, "Edit")
    edit_button.invoke()
    harness.pump()

    save_and_close_button = _find_widget_containing_text(preview_popup, "Save and Close")
    save_and_close_button.invoke()
    harness.pump()

    assert edited_target.read_text(encoding="utf-8") == "run(user_input)\n"
    assert direct_target.read_text(encoding="utf-8") == "for item in items:\n    work(item)\n"
    assert issues[0].status == "pending"
    assert any(message == t("gui.results.preview_staged") and not error for message, error in harness.toasts)

    apply_button = _find_widget_by_text(batch_popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert edited_target.read_text(encoding="utf-8") == edited_user_fix
    assert direct_target.read_text(encoding="utf-8") == direct_generated_fix
    assert issues[0].status == "resolved"
    assert issues[1].status == "resolved"
    assert issues[0].ai_fix_applied == edited_user_fix
    assert issues[1].ai_fix_applied == direct_generated_fix
    assert harness.app._ai_fix_mode is False
    assert any(
        message == t("gui.results.batch_fix_applied", count=2) and not error
        for message, error in harness.toasts
    )


def test_ai_fix_mixed_runtime_batch_can_deselect_one_issue_after_editing_another(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    edited_target = tmp_path / "edited_then_keep.py"
    direct_target = tmp_path / "direct_apply.py"
    deselected_target = tmp_path / "deselected.py"
    edited_target.write_text("run(user_input)\n", encoding="utf-8")
    direct_target.write_text("for item in items:\n    work(item)\n", encoding="utf-8")
    deselected_target.write_text("print('leave me alone')\n", encoding="utf-8")

    edited_generated_fix = "safe_run(user_input)\n"
    edited_user_fix = "validated = sanitize(user_input)\nsafe_run(validated)\n"
    direct_generated_fix = "for item in unique_items:\n    work(item)\n"
    deselected_generated_fix = "print('should not be written')\n"

    issues = [
        ReviewIssue(
            file_path=str(edited_target),
            line_number=1,
            issue_type="security",
            severity="high",
            description="First issue should preserve the preview-edited content.",
            ai_feedback="Sanitize user input before execution.",
            status="pending",
            code_snippet=edited_target.read_text(encoding="utf-8"),
        ),
        ReviewIssue(
            file_path=str(direct_target),
            line_number=1,
            issue_type="performance",
            severity="medium",
            description="Second issue should use the generated fix directly.",
            ai_feedback="Avoid duplicate work.",
            status="pending",
            code_snippet=direct_target.read_text(encoding="utf-8"),
        ),
        ReviewIssue(
            file_path=str(deselected_target),
            line_number=1,
            issue_type="documentation",
            severity="low",
            description="Third issue should remain unchanged when its checkbox is cleared.",
            ai_feedback="Leave this file unchanged when deselected.",
            status="pending",
            code_snippet=deselected_target.read_text(encoding="utf-8"),
        ),
    ]

    harness.enable_runtime_actions()
    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues(issues)
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    selected = list(enumerate(harness.app._issue_cards))
    harness.app._show_batch_fix_popup(
        selected,
        {
            0: edited_generated_fix,
            1: direct_generated_fix,
            2: deselected_generated_fix,
        },
    )
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    monkeypatch.setattr(
        harness.app,
        "_open_builtin_editor",
        lambda idx, _initial_content=None, _on_save=None: _on_save and _on_save(edited_user_fix),
    )

    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump()

    preview_popup = _latest_toplevel(harness.app)
    edit_button = _find_widget_containing_text(preview_popup, "Edit")
    edit_button.invoke()
    harness.pump()

    save_and_close_button = _find_widget_containing_text(preview_popup, "Save and Close")
    save_and_close_button.invoke()
    harness.pump()

    deselected_checkbox = _find_widget_by_text(batch_popup, deselected_target.name)
    deselected_checkbox.deselect()
    harness.pump()

    assert edited_target.read_text(encoding="utf-8") == "run(user_input)\n"
    assert direct_target.read_text(encoding="utf-8") == "for item in items:\n    work(item)\n"
    assert deselected_target.read_text(encoding="utf-8") == "print('leave me alone')\n"
    assert issues[0].status == "pending"
    assert any(message == t("gui.results.preview_staged") and not error for message, error in harness.toasts)

    apply_button = _find_widget_by_text(batch_popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert edited_target.read_text(encoding="utf-8") == edited_user_fix
    assert direct_target.read_text(encoding="utf-8") == direct_generated_fix
    assert deselected_target.read_text(encoding="utf-8") == "print('leave me alone')\n"
    assert issues[0].status == "resolved"
    assert issues[1].status == "resolved"
    assert issues[2].status == "pending"
    assert issues[0].ai_fix_applied == edited_user_fix
    assert issues[1].ai_fix_applied == direct_generated_fix
    assert issues[2].ai_fix_applied is None
    assert harness.app._ai_fix_mode is False
    assert any(
        message == t("gui.results.batch_fix_applied", count=2) and not error
        for message, error in harness.toasts
    )


def test_ai_fix_mixed_runtime_batch_can_deselect_the_edited_issue_and_apply_another(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    edited_target = tmp_path / "edited_then_deselected.py"
    direct_target = tmp_path / "direct_after_edit.py"
    untouched_target = tmp_path / "untouched_pending.py"
    edited_target.write_text("run(user_input)\n", encoding="utf-8")
    direct_target.write_text("for item in items:\n    work(item)\n", encoding="utf-8")
    untouched_target.write_text("print('still pending')\n", encoding="utf-8")

    edited_generated_fix = "safe_run(user_input)\n"
    edited_user_fix = "validated = sanitize(user_input)\nsafe_run(validated)\n"
    direct_generated_fix = "for item in unique_items:\n    work(item)\n"
    untouched_generated_fix = "print('should stay pending')\n"

    issues = [
        ReviewIssue(
            file_path=str(edited_target),
            line_number=1,
            issue_type="security",
            severity="high",
            description="First issue is edited in preview, then unchecked before batch apply.",
            ai_feedback="Sanitize user input before execution.",
            status="pending",
            code_snippet=edited_target.read_text(encoding="utf-8"),
        ),
        ReviewIssue(
            file_path=str(direct_target),
            line_number=1,
            issue_type="performance",
            severity="medium",
            description="Second issue should still be directly applied.",
            ai_feedback="Avoid duplicate work.",
            status="pending",
            code_snippet=direct_target.read_text(encoding="utf-8"),
        ),
        ReviewIssue(
            file_path=str(untouched_target),
            line_number=1,
            issue_type="documentation",
            severity="low",
            description="Third issue stays pending and unchanged after being deselected.",
            ai_feedback="Leave this issue untouched.",
            status="pending",
            code_snippet=untouched_target.read_text(encoding="utf-8"),
        ),
    ]

    harness.enable_runtime_actions()
    harness.app._review_runner = SimpleNamespace(_pending_report_meta={"backend": "local"})
    harness.app._show_issues(issues)
    harness.app.ai_fix_mode_btn.invoke()
    harness.pump()

    selected = list(enumerate(harness.app._issue_cards))
    harness.app._show_batch_fix_popup(
        selected,
        {
            0: edited_generated_fix,
            1: direct_generated_fix,
            2: untouched_generated_fix,
        },
    )
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    monkeypatch.setattr(
        harness.app,
        "_open_builtin_editor",
        lambda idx, _initial_content=None, _on_save=None: _on_save and _on_save(edited_user_fix),
    )

    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump()

    preview_popup = _latest_toplevel(harness.app)
    edit_button = _find_widget_containing_text(preview_popup, "Edit")
    edit_button.invoke()
    harness.pump()

    save_and_close_button = _find_widget_containing_text(preview_popup, "Save and Close")
    save_and_close_button.invoke()
    harness.pump()

    edited_checkbox = _find_widget_by_text(batch_popup, edited_target.name)
    untouched_checkbox = _find_widget_by_text(batch_popup, untouched_target.name)
    edited_checkbox.deselect()
    untouched_checkbox.deselect()
    harness.pump()

    assert edited_target.read_text(encoding="utf-8") == "run(user_input)\n"
    assert direct_target.read_text(encoding="utf-8") == "for item in items:\n    work(item)\n"
    assert untouched_target.read_text(encoding="utf-8") == "print('still pending')\n"
    assert issues[0].status == "pending"
    assert any(message == t("gui.results.preview_staged") and not error for message, error in harness.toasts)

    apply_button = _find_widget_by_text(batch_popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert edited_target.read_text(encoding="utf-8") == "run(user_input)\n"
    assert direct_target.read_text(encoding="utf-8") == direct_generated_fix
    assert untouched_target.read_text(encoding="utf-8") == "print('still pending')\n"
    assert issues[0].status == "pending"
    assert issues[1].status == "resolved"
    assert issues[2].status == "pending"
    assert issues[0].ai_fix_applied is None
    assert issues[1].ai_fix_applied == direct_generated_fix
    assert issues[2].ai_fix_applied is None
    assert harness.app._ai_fix_mode is False
    assert any(
        message == t("gui.results.batch_fix_applied", count=1) and not error
        for message, error in harness.toasts
    )
