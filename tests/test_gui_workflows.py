from __future__ import annotations

import json
import logging
import configparser
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Generator

import pytest
import customtkinter as ctk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aicodereviewer.addons import AddonEditorDiagnostic
import aicodereviewer.auth as auth
from aicodereviewer.i18n import t
from aicodereviewer.models import ReviewIssue
from aicodereviewer.config import config
from aicodereviewer.gui.popup_surfaces import LARGE_FILE_PAGE_BYTES
from aicodereviewer.recommendations import (
    ReviewRecommendationCancelledError,
    ReviewRecommendationResult,
    ReviewTypeRecommendation,
)

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


def _reset_root_logging() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        try:
            handler.close()
        except Exception:
            pass
    root.handlers.clear()
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console)


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


def _find_all_widgets_by_text(root: Any, text: str) -> list[Any]:
    matches: list[Any] = []
    for widget in _walk_widgets(root):
        try:
            if widget.cget("text") == text:
                matches.append(widget)
        except Exception:
            continue
    if not matches:
        raise AssertionError(f"Widget with text {text!r} not found")
    return matches


def _find_widget_containing_text(root: Any, fragment: str) -> Any:
    for widget in _walk_widgets(root):
        try:
            if fragment in str(widget.cget("text")):
                return widget
        except Exception:
            continue
    raise AssertionError(f"Widget containing text {fragment!r} not found")


def _find_invokable_widget_containing_text(root: Any, fragment: str) -> Any:
    for widget in _walk_widgets(root):
        if not hasattr(widget, "invoke"):
            continue
        try:
            if fragment in str(widget.cget("text")):
                return widget
        except Exception:
            continue
    raise AssertionError(f"Invokable widget containing text {fragment!r} not found")


def _latest_toplevel(app: Any) -> Any:
    toplevels = [child for child in app.winfo_children() if isinstance(child, tk.Toplevel)]
    if not toplevels:
        raise AssertionError("Expected a popup window to be open")
    return toplevels[-1]


def _all_toplevels(app: Any) -> list[Any]:
    return [child for child in app.winfo_children() if isinstance(child, tk.Toplevel)]


def _find_normal_text_widget(root: Any) -> Any:
    for widget in _walk_widgets(root):
        if isinstance(widget, tk.Text):
            try:
                if str(widget.cget("state")) == "normal":
                    return widget
            except Exception:
                continue
    raise AssertionError("Expected a normal text widget")


def _find_ctk_entries(root: Any) -> list[Any]:
    return [widget for widget in _walk_widgets(root) if isinstance(widget, ctk.CTkEntry)]


def _reset_config_to_path(config_path: Path) -> None:
    config.config_path = config_path
    config.config = configparser.ConfigParser()
    config._set_defaults()
    if config_path.exists():
        config.config.read(config_path, encoding="utf-8")


def _save_default_config_to_path(config_path: Path) -> None:
    _reset_config_to_path(config_path)
    config.save()


def _write_sample_benchmark_summaries(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    reports_dir = artifacts_root / "holistic-benchmark-reports"
    reports_dir.mkdir()
    compare_reports_dir = artifacts_root / "holistic-benchmark-reports-compare"
    compare_reports_dir.mkdir()
    summary_path = artifacts_root / "benchmark-summary.json"
    compare_path = artifacts_root / "benchmark-summary-compare.json"

    primary_payload = {
        "backend": "local",
        "status": "completed",
        "overall_score": 0.5,
        "fixtures_evaluated": 2,
        "fixtures_passed": 1,
        "fixtures_failed": 1,
        "representative_fixtures": [
            {
                "id": "auth-jwt-bypass",
                "title": "JWT Auth Bypass",
                "scope": "project",
                "review_types": ["security", "data_validation"],
                "benchmark_metadata": {
                    "fixture_tags": ["auth", "jwt"],
                    "expected_focus": ["token validation", "trust boundaries"],
                    "review_types": [
                        {
                            "key": "security",
                            "label": "Security",
                            "group": "Quality",
                            "metadata": {
                                "fixture_tags": ["auth", "jwt"],
                                "expected_focus": ["token validation"],
                            },
                        }
                    ],
                },
            },
            {
                "id": "validation-gap",
                "title": "Validation Gap",
                "scope": "project",
                "review_types": ["data_validation"],
            },
        ],
        "generated_reports": [
            {
                "fixture_id": "auth-jwt-bypass",
                "output_path": str(reports_dir / "auth-jwt-bypass.json"),
                "status": "completed",
                "issue_count": 2,
                "success": True,
            },
            {
                "fixture_id": "validation-gap",
                "output_path": str(reports_dir / "validation-gap.json"),
                "status": "completed",
                "issue_count": 1,
                "success": True,
            },
        ],
        "score_summary": {
            "overall_score": 0.5,
            "fixtures_evaluated": 2,
            "fixtures_passed": 1,
            "fixtures_failed": 1,
            "results": [
                {
                    "fixture_id": "auth-jwt-bypass",
                    "title": "JWT Auth Bypass",
                    "status": "completed",
                    "score": 0.5,
                    "passed": False,
                    "report_path": str(reports_dir / "auth-jwt-bypass.json"),
                    "selected_review_types": ["security", "data_validation"],
                },
                {
                    "fixture_id": "validation-gap",
                    "title": "Validation Gap",
                    "status": "completed",
                    "score": 0.0,
                    "passed": False,
                    "report_path": str(reports_dir / "validation-gap.json"),
                    "selected_review_types": ["data_validation"],
                },
            ],
        },
    }
    compare_payload = {
        "backend": "copilot",
        "status": "completed",
        "overall_score": 0.75,
        "fixtures_evaluated": 2,
        "fixtures_passed": 2,
        "fixtures_failed": 0,
        "representative_fixtures": [
            {
                "id": "auth-jwt-bypass",
                "title": "JWT Auth Bypass",
                "scope": "project",
                "review_types": ["security"],
            },
            {
                "id": "cache-gap",
                "title": "Cache Gap",
                "scope": "project",
                "review_types": ["performance"],
            },
        ],
        "score_summary": {
            "overall_score": 0.75,
            "fixtures_evaluated": 2,
            "fixtures_passed": 2,
            "fixtures_failed": 0,
            "results": [
                {
                    "fixture_id": "auth-jwt-bypass",
                    "title": "JWT Auth Bypass",
                    "status": "completed",
                    "score": 0.75,
                    "passed": True,
                    "selected_review_types": ["security"],
                    "report_path": str(compare_reports_dir / "auth-jwt-bypass.json"),
                },
                {
                    "fixture_id": "cache-gap",
                    "title": "Cache Gap",
                    "status": "completed",
                    "score": 1.0,
                    "passed": True,
                    "selected_review_types": ["performance"],
                },
            ],
        },
    }

    summary_path.write_text(json.dumps(primary_payload), encoding="utf-8")
    compare_path.write_text(json.dumps(compare_payload), encoding="utf-8")
    return artifacts_root, summary_path, compare_path


def _runner_with_report_context(
    meta: dict[str, Any] | None = None,
    **kwargs: Any,
) -> SimpleNamespace:
    return SimpleNamespace(
        serialized_report_context=dict(meta or {}),
        **kwargs,
    )


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
        _reset_root_logging()
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
            self.serialized_report_context: dict[str, Any] | None = None
            runner_instances.append(self)

        def run(self, **kwargs: Any) -> list[ReviewIssue]:
            self.run_calls.append(kwargs)
            self.serialized_report_context = {
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
        lambda: not harness.review_runtime.is_running() and harness.results_tab.issue_count() == 1,
        message="review did not populate the Results tab",
    )

    assert harness.results_tab.issues() == [issue]
    assert harness.review_runtime.current_runner() is runner_instances[0]
    assert harness.review_runtime.active_runner() is runner_instances[0]
    assert harness.review_runtime.controller_running() is False
    assert harness.review_runtime.progress_message() is None
    assert harness.review_runtime.progress_current() == 0
    assert harness.review_runtime.progress_total() == 0
    assert harness.review_runtime.elapsed_started_at() is None
    assert harness.review_runtime.elapsed_after_id() is None
    assert runner_instances[0].run_calls[0]["interactive"] is False
    assert runner_instances[0].run_calls[0]["dry_run"] is False
    assert runner_instances[0].run_calls[0]["event_sink"] is not None
    assert harness.results_tab.current_tab() == t("gui.tab.results")
    assert harness.results_tab.finalize_state() == "disabled"
    assert harness.results_tab.save_session_state() == "normal"
    assert harness.app.cancel_btn.cget("state") == "disabled"
    assert harness.results_tab.active_review_client() is None
    assert harness.review_runtime.active_client() is None
    assert harness.review_runtime.cancel_event() is None


def test_benchmark_tab_loads_representative_fixture_summary_artifact(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    artifacts_root, summary_path, compare_path = _write_sample_benchmark_summaries(tmp_path)

    harness.benchmark_tab.open()
    harness.benchmark_tab.refresh_summary_selector(artifacts_root)
    harness.benchmark_tab.select_summary_by_fragment("benchmark-summary.json")
    harness.benchmark_tab.load_selected_summary()
    harness.benchmark_tab.select_summary_by_fragment("benchmark-summary-compare.json")
    harness.benchmark_tab.compare_selected_summary()

    assert harness.benchmark_tab.current_tab() == t("gui.tab.benchmarks")
    assert "benchmark-summary.json" in harness.benchmark_tab.source_text()
    assert harness.benchmark_tab.count_text() == "2"
    assert "auth-jwt-bypass" in harness.benchmark_tab.selected_fixture()
    assert "auth, jwt" in harness.benchmark_tab.catalog_text()
    detail_text = harness.benchmark_tab.detail_text()
    assert "token validation" in detail_text
    assert "trust boundaries" in detail_text
    assert "Security [security]" in detail_text
    primary_summary_text = harness.benchmark_tab.primary_summary_text()
    compare_summary_text = harness.benchmark_tab.compare_summary_text()
    assert "benchmark-summary.json" in primary_summary_text
    assert "0.5000" in primary_summary_text
    assert "benchmark-summary-compare.json" in compare_summary_text
    assert "+0.2500" in compare_summary_text
    assert "cache-gap" in compare_summary_text
    assert (
        "Scenario-by-Scenario Changes:" in compare_summary_text
        or "シナリオごとの差分：" in compare_summary_text
        or "Fixture-Level Changes:" in compare_summary_text
        or "フィクスチャ単位の差分：" in compare_summary_text
    )
    assert "auth-jwt-bypass" in compare_summary_text
    assert "score delta +0.2500" in compare_summary_text or "スコア差 +0.2500" in compare_summary_text
    takeaways_text = harness.benchmark_tab.takeaways_text()
    assert "+0.2500" in takeaways_text
    assert "copilot" in takeaways_text or "local" in takeaways_text
    assert set(harness.benchmark_tab.fixture_diff_ids()) == {"auth-jwt-bypass", "cache-gap", "validation-gap"}


def test_review_backend_dropdown_stays_in_sync_with_settings(
    harness: GuiTestHarness,
) -> None:
    copilot_display = t("gui.review.backend_copilot")
    local_display = t("gui.settings.backend_local")

    assert hasattr(harness.app, "review_backend_menu")
    assert copilot_display in list(harness.app.review_backend_menu.cget("values"))

    harness.app._on_review_backend_selected(copilot_display)
    harness.app.update_idletasks()

    assert harness.app.backend_var.get() == "copilot"
    assert harness.app._settings_backend_var.get() == t("gui.settings.backend_copilot")

    harness.app._settings_backend_var.set(local_display)
    harness.app.update_idletasks()

    assert harness.app.backend_var.get() == "local"
    assert harness.app.review_backend_display_var.get() == t("gui.review.backend_local")


def test_benchmark_tab_opens_fixture_diff_report_json_files(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    primary_report = artifacts_root / "primary-auth.json"
    primary_validation_report = artifacts_root / "primary-validation.json"
    compare_report = artifacts_root / "compare-auth.json"
    compare_cache_report = artifacts_root / "compare-cache.json"
    summary_path = artifacts_root / "primary-summary.json"
    compare_path = artifacts_root / "compare-summary.json"

    summary_path.write_text(
        json.dumps(
            {
                "backend": "local",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security", "data_validation"]}
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.25,
                            "report_path": str(primary_report),
                            "selected_review_types": ["security", "data_validation"],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    compare_path.write_text(
        json.dumps(
            {
                "backend": "copilot",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security"]}
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.75,
                            "report_path": str(compare_report),
                            "selected_review_types": ["security"],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    opened_paths: list[Path] = []
    monkeypatch.setattr(harness.app, "_open_path", lambda path: opened_paths.append(path))

    harness.benchmark_tab.open()
    harness.benchmark_tab.load_summary(summary_path)
    harness.benchmark_tab.compare_summary(compare_path)
    harness.benchmark_tab.open_fixture_diff_primary_report("auth-jwt-bypass")
    harness.benchmark_tab.open_fixture_diff_compare_report("auth-jwt-bypass")

    assert opened_paths == [primary_report.resolve(), compare_report.resolve()]


def test_benchmark_tab_previews_and_diffs_fixture_reports(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    primary_report = artifacts_root / "primary-auth.json"
    primary_validation_report = artifacts_root / "primary-validation.json"
    compare_report = artifacts_root / "compare-auth.json"
    compare_cache_report = artifacts_root / "compare-cache.json"
    summary_path = artifacts_root / "primary-summary.json"
    compare_path = artifacts_root / "compare-summary.json"

    primary_report.write_text(
        json.dumps({"issues_found": [{"issue_id": "issue-1", "severity": "medium"}]}),
        encoding="utf-8",
    )
    compare_report.write_text(
        json.dumps({"issues_found": [{"issue_id": "issue-1", "severity": "high"}]}),
        encoding="utf-8",
    )
    primary_validation_report.write_text(
        json.dumps({"issues_found": [{"issue_id": "issue-2", "severity": "low"}]}),
        encoding="utf-8",
    )
    compare_cache_report.write_text(
        json.dumps({"issues_found": [{"issue_id": "issue-3", "severity": "medium"}]}),
        encoding="utf-8",
    )

    summary_path.write_text(
        json.dumps(
            {
                "backend": "local",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security"]},
                    {"id": "validation-gap", "title": "Validation Gap", "scope": "project", "review_types": ["data_validation"]},
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.25,
                            "report_path": str(primary_report),
                            "selected_review_types": ["security"],
                        },
                        {
                            "fixture_id": "validation-gap",
                            "title": "Validation Gap",
                            "status": "completed",
                            "score": 0.0,
                            "report_path": str(primary_validation_report),
                            "selected_review_types": ["data_validation"],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    compare_path.write_text(
        json.dumps(
            {
                "backend": "copilot",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security"]},
                    {"id": "cache-gap", "title": "Cache Gap", "scope": "project", "review_types": ["performance"]},
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.75,
                            "report_path": str(compare_report),
                            "selected_review_types": ["security"],
                        },
                        {
                            "fixture_id": "cache-gap",
                            "title": "Cache Gap",
                            "status": "completed",
                            "score": 1.0,
                            "report_path": str(compare_cache_report),
                            "selected_review_types": ["performance"],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    harness.benchmark_tab.open()
    harness.benchmark_tab.load_summary(summary_path)
    harness.benchmark_tab.compare_summary(compare_path)

    assert set(harness.benchmark_tab.fixture_diff_ids()) == {"auth-jwt-bypass", "cache-gap", "validation-gap"}

    harness.benchmark_tab.preview_fixture_diff_reports("auth-jwt-bypass")
    assert '"severity": "medium"' in harness.benchmark_tab.preview_primary_text()
    assert '"severity": "high"' in harness.benchmark_tab.preview_compare_text()
    assert "Issue-Level Summary" in harness.benchmark_tab.preview_diff_text() or "問題単位の要約" in harness.benchmark_tab.preview_diff_text()
    assert "issue-1" in harness.benchmark_tab.preview_diff_text()
    assert "severity medium -> high" in harness.benchmark_tab.preview_diff_text() or "重大度 medium -> high" in harness.benchmark_tab.preview_diff_text()
    assert "severity" in harness.benchmark_tab.preview_diff_text()

    harness.benchmark_tab.preview_fixture_diff_reports("validation-gap")
    assert '"issue-2"' in harness.benchmark_tab.preview_primary_text()
    assert "No comparison report JSON" in harness.benchmark_tab.preview_compare_text() or "比較側のレポートJSONがありません" in harness.benchmark_tab.preview_compare_text()

    harness.benchmark_tab.diff_fixture_reports("cache-gap")
    assert "No primary report JSON" in harness.benchmark_tab.preview_primary_text() or "プライマリのレポートJSONがありません" in harness.benchmark_tab.preview_primary_text()
    assert '"issue-3"' in harness.benchmark_tab.preview_compare_text()
    assert "Added issues:" in harness.benchmark_tab.preview_diff_text() or "追加された問題:" in harness.benchmark_tab.preview_diff_text()


def test_benchmark_tab_filters_fixture_diff_rows_by_presence(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    summary_path = artifacts_root / "primary-summary.json"
    compare_path = artifacts_root / "compare-summary.json"

    summary_path.write_text(
        json.dumps(
            {
                "backend": "local",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security"]},
                    {"id": "validation-gap", "title": "Validation Gap", "scope": "project", "review_types": ["data_validation"]},
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.25,
                            "selected_review_types": ["security"],
                        },
                        {
                            "fixture_id": "validation-gap",
                            "title": "Validation Gap",
                            "status": "completed",
                            "score": 0.0,
                            "selected_review_types": ["data_validation"],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    compare_path.write_text(
        json.dumps(
            {
                "backend": "copilot",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security"]},
                    {"id": "cache-gap", "title": "Cache Gap", "scope": "project", "review_types": ["performance"]},
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.75,
                            "selected_review_types": ["security"],
                        },
                        {
                            "fixture_id": "cache-gap",
                            "title": "Cache Gap",
                            "status": "completed",
                            "score": 1.0,
                            "selected_review_types": ["performance"],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    harness.benchmark_tab.open()
    harness.benchmark_tab.load_summary(summary_path)
    harness.benchmark_tab.compare_summary(compare_path)

    assert harness.benchmark_tab.selected_fixture_filter() == t("gui.benchmark.fixture_filter_all")
    assert set(harness.benchmark_tab.fixture_diff_ids()) == {"auth-jwt-bypass", "cache-gap", "validation-gap"}

    harness.benchmark_tab.select_fixture_filter(t("gui.benchmark.fixture_filter_shared"))
    assert harness.benchmark_tab.fixture_diff_ids() == ["auth-jwt-bypass"]

    harness.benchmark_tab.select_fixture_filter(t("gui.benchmark.fixture_filter_primary_only"))
    assert harness.benchmark_tab.fixture_diff_ids() == ["validation-gap"]

    harness.benchmark_tab.select_fixture_filter(t("gui.benchmark.fixture_filter_compare_only"))
    assert harness.benchmark_tab.fixture_diff_ids() == ["cache-gap"]

    harness.benchmark_tab.select_fixture_filter(t("gui.benchmark.fixture_filter_all"))
    assert set(harness.benchmark_tab.fixture_diff_ids()) == {"auth-jwt-bypass", "cache-gap", "validation-gap"}


def test_benchmark_tab_sorts_fixture_diff_rows_by_delta_and_status_churn(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    summary_path = artifacts_root / "primary-summary.json"
    compare_path = artifacts_root / "compare-summary.json"

    summary_path.write_text(
        json.dumps(
            {
                "backend": "local",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security"]},
                    {"id": "session-timeout-drift", "title": "Session Timeout Drift", "scope": "project", "review_types": ["reliability"]},
                    {"id": "validation-gap", "title": "Validation Gap", "scope": "project", "review_types": ["data_validation"]},
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.25,
                            "selected_review_types": ["security"],
                        },
                        {
                            "fixture_id": "session-timeout-drift",
                            "title": "Session Timeout Drift",
                            "status": "completed",
                            "score": 0.6,
                            "selected_review_types": ["reliability"],
                        },
                        {
                            "fixture_id": "validation-gap",
                            "title": "Validation Gap",
                            "status": "completed",
                            "score": 0.0,
                            "selected_review_types": ["data_validation"],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    compare_path.write_text(
        json.dumps(
            {
                "backend": "copilot",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security"]},
                    {"id": "cache-gap", "title": "Cache Gap", "scope": "project", "review_types": ["performance"]},
                    {"id": "session-timeout-drift", "title": "Session Timeout Drift", "scope": "project", "review_types": ["reliability"]},
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.9,
                            "selected_review_types": ["security"],
                        },
                        {
                            "fixture_id": "cache-gap",
                            "title": "Cache Gap",
                            "status": "completed",
                            "score": 1.0,
                            "selected_review_types": ["performance"],
                        },
                        {
                            "fixture_id": "session-timeout-drift",
                            "title": "Session Timeout Drift",
                            "status": "failed",
                            "score": 0.5,
                            "selected_review_types": ["reliability"],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    harness.benchmark_tab.open()
    harness.benchmark_tab.load_summary(summary_path)
    harness.benchmark_tab.compare_summary(compare_path)

    assert harness.benchmark_tab.selected_fixture_sort() == t("gui.benchmark.fixture_sort_default")
    assert harness.benchmark_tab.fixture_diff_ids() == [
        "auth-jwt-bypass",
        "session-timeout-drift",
        "validation-gap",
        "cache-gap",
    ]

    harness.benchmark_tab.select_fixture_sort(t("gui.benchmark.fixture_sort_score_delta"))
    assert harness.benchmark_tab.fixture_diff_ids() == [
        "auth-jwt-bypass",
        "session-timeout-drift",
        "validation-gap",
        "cache-gap",
    ]

    harness.benchmark_tab.select_fixture_sort(t("gui.benchmark.fixture_sort_status_churn"))
    assert harness.benchmark_tab.fixture_diff_ids() == [
        "session-timeout-drift",
        "auth-jwt-bypass",
        "validation-gap",
        "cache-gap",
    ]

    harness.benchmark_tab.select_fixture_filter(t("gui.benchmark.fixture_filter_shared"))
    assert harness.benchmark_tab.fixture_diff_ids() == [
        "session-timeout-drift",
        "auth-jwt-bypass",
    ]


def test_benchmark_tab_restores_saved_filter_and_sort_for_summary_pair(
    app_factory: Any,
    tmp_path: Path,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    summary_path = artifacts_root / "primary-summary.json"
    compare_path = artifacts_root / "compare-summary.json"
    temporary_config_path = tmp_path / "config.ini"
    original_config_path = config.config_path or (Path.cwd() / "config.ini")

    summary_path.write_text(
        json.dumps(
            {
                "backend": "local",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security"]},
                    {"id": "session-timeout-drift", "title": "Session Timeout Drift", "scope": "project", "review_types": ["reliability"]},
                    {"id": "validation-gap", "title": "Validation Gap", "scope": "project", "review_types": ["data_validation"]},
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.25,
                            "selected_review_types": ["security"],
                        },
                        {
                            "fixture_id": "session-timeout-drift",
                            "title": "Session Timeout Drift",
                            "status": "completed",
                            "score": 0.6,
                            "selected_review_types": ["reliability"],
                        },
                        {
                            "fixture_id": "validation-gap",
                            "title": "Validation Gap",
                            "status": "completed",
                            "score": 0.0,
                            "selected_review_types": ["data_validation"],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    compare_path.write_text(
        json.dumps(
            {
                "backend": "copilot",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "auth-jwt-bypass", "title": "JWT Auth Bypass", "scope": "project", "review_types": ["security"]},
                    {"id": "cache-gap", "title": "Cache Gap", "scope": "project", "review_types": ["performance"]},
                    {"id": "session-timeout-drift", "title": "Session Timeout Drift", "scope": "project", "review_types": ["reliability"]},
                ],
                "score_summary": {
                    "results": [
                        {
                            "fixture_id": "auth-jwt-bypass",
                            "title": "JWT Auth Bypass",
                            "status": "completed",
                            "score": 0.9,
                            "selected_review_types": ["security"],
                        },
                        {
                            "fixture_id": "cache-gap",
                            "title": "Cache Gap",
                            "status": "completed",
                            "score": 1.0,
                            "selected_review_types": ["performance"],
                        },
                        {
                            "fixture_id": "session-timeout-drift",
                            "title": "Session Timeout Drift",
                            "status": "failed",
                            "score": 0.5,
                            "selected_review_types": ["reliability"],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    try:
        _save_default_config_to_path(temporary_config_path)

        first_harness = GuiTestHarness(app_factory())
        first_harness.benchmark_tab.open()
        first_harness.benchmark_tab.load_summary(summary_path)
        first_harness.benchmark_tab.compare_summary(compare_path)
        first_harness.benchmark_tab.select_fixture_filter(t("gui.benchmark.fixture_filter_shared"))
        first_harness.benchmark_tab.select_fixture_sort(t("gui.benchmark.fixture_sort_status_churn"))

        _reset_config_to_path(temporary_config_path)

        second_harness = GuiTestHarness(app_factory())
        second_harness.benchmark_tab.open()
        assert second_harness.benchmark_tab.selected_fixture_filter() == t("gui.benchmark.fixture_filter_shared")
        assert second_harness.benchmark_tab.selected_fixture_sort() == t("gui.benchmark.fixture_sort_status_churn")

        second_harness.benchmark_tab.load_summary(summary_path)
        second_harness.benchmark_tab.compare_summary(compare_path)

        assert second_harness.benchmark_tab.selected_fixture_filter() == t("gui.benchmark.fixture_filter_shared")
        assert second_harness.benchmark_tab.selected_fixture_sort() == t("gui.benchmark.fixture_sort_status_churn")
        assert second_harness.benchmark_tab.fixture_diff_ids() == [
            "session-timeout-drift",
            "auth-jwt-bypass",
        ]
    finally:
        _reset_config_to_path(original_config_path)


def test_benchmark_tab_opens_selected_fixture_folder(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixtures_root = tmp_path / "fixtures"
    fixture_dir = fixtures_root / "open-fixture"
    project_dir = fixture_dir / "project"
    project_dir.mkdir(parents=True)
    (fixture_dir / "fixture.json").write_text(
        json.dumps(
            {
                "id": "open-fixture",
                "title": "Open Fixture",
                "description": "Fixture for open folder coverage.",
                "scope": "project",
                "project_dir": "project",
                "review_types": ["security"],
                "expected_findings": [],
            }
        ),
        encoding="utf-8",
    )

    opened_paths: list[Path] = []
    monkeypatch.setattr(harness.app, "_open_directory_path", lambda path: opened_paths.append(path))

    harness.benchmark_tab.open()
    harness.benchmark_tab.load_catalog(fixtures_root)
    harness.benchmark_tab.open_source_folder()

    assert opened_paths == [project_dir.resolve()]


def test_benchmark_tab_opens_selected_summary_json_and_report_directory(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    reports_dir = artifacts_root / "reports"
    reports_dir.mkdir(parents=True)
    summary_path = artifacts_root / "selected-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "backend": "local",
                "status": "completed",
                "representative_fixtures": [
                    {"id": "fixture-a", "title": "Fixture A", "scope": "project", "review_types": ["security"]}
                ],
                "generated_reports": [
                    {
                        "fixture_id": "fixture-a",
                        "output_path": str(reports_dir / "fixture-a.json"),
                        "status": "completed",
                        "issue_count": 1,
                        "success": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    opened_paths: list[Path] = []
    monkeypatch.setattr(harness.app, "_open_path", lambda path: opened_paths.append(path))
    monkeypatch.setattr(harness.app, "_open_directory_path", lambda path: opened_paths.append(path))

    harness.benchmark_tab.open()
    harness.benchmark_tab.refresh_summary_selector(artifacts_root)
    harness.benchmark_tab.select_summary_by_fragment("selected-summary.json")
    harness.benchmark_tab.open_summary_json()
    harness.benchmark_tab.open_report_directory()

    assert opened_paths == [summary_path.resolve(), reports_dir.resolve()]


def test_benchmark_tab_open_source_folder_ignores_summary_embedded_path_outside_fixtures_root(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    external_source = tmp_path / "external-source"
    external_source.mkdir()
    summary_path = artifacts_root / "selected-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "backend": "local",
                "status": "completed",
                "representative_fixtures": [
                    {
                        "id": "fixture-a",
                        "title": "Fixture A",
                        "scope": "project",
                        "review_types": ["security"],
                        "project_dir": str(external_source),
                    }
                ],
                "generated_reports": [],
            }
        ),
        encoding="utf-8",
    )

    opened_paths: list[Path] = []
    monkeypatch.setattr(harness.app, "_open_directory_path", lambda path: opened_paths.append(path))

    harness.benchmark_tab.open()
    harness.app.benchmark_fixtures_root_entry.delete(0, "end")
    harness.app.benchmark_fixtures_root_entry.insert(0, str(fixtures_root))
    harness.benchmark_tab.refresh_summary_selector(artifacts_root)
    harness.benchmark_tab.select_summary_by_fragment("selected-summary.json")
    harness.benchmark_tab.load_selected_summary()
    harness.benchmark_tab.open_source_folder()

    assert opened_paths == [artifacts_root.resolve()]


def test_benchmark_tab_load_catalog_rejects_manifest_path_outside_fixtures_root(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    fixtures_root = tmp_path / "fixtures"
    scenario_dir = fixtures_root / "scenario-a"
    scenario_dir.mkdir(parents=True)
    external_root = tmp_path / "external"
    external_root.mkdir()
    (scenario_dir / "fixture.json").write_text(
        json.dumps(
            {
                "id": "scenario-a",
                "title": "Scenario A",
                "description": "Escaped fixture paths should be rejected.",
                "scope": "project",
                "review_types": ["security"],
                "project_dir": str(external_root),
                "expected_findings": [],
            }
        ),
        encoding="utf-8",
    )

    harness.benchmark_tab.open()
    harness.benchmark_tab.load_catalog(fixtures_root)

    assert any(
        "must stay within the fixtures root" in message and error
        for message, error in harness.toasts
    )


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
            finish_run.wait(timeout=5.0)
            return None

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: backend)
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.AppRunner", _BlockingRunner)

    harness.enable_runtime_actions()
    harness.fill_valid_review_form(project_path)
    harness.start_review()
    harness.wait_until(entered_run.is_set, message="review worker never started")
    harness.wait_until(
        lambda: harness.review_runtime.is_running(),
        message="review never entered running state",
    )
    assert harness.app.cancel_btn.cget("state") == "normal"

    harness.app._cancel_operation()
    harness.pump()

    assert backend.cancelled is True
    assert harness.status_bar.text() == t("gui.val.cancellation_requested")

    harness.wait_until(cancellation_seen.is_set, message="runner never observed cancellation")
    finish_run.set()
    harness.wait_until(
        lambda: not harness.review_runtime.is_running() and harness.status_bar.text() == t("gui.val.cancelled"),
        message="review never finished after cancellation",
    )

    assert harness.status_bar.text() == t("gui.val.cancelled")
    assert harness.app.cancel_btn.cget("state") == "disabled"
    assert harness.results_tab.active_review_client() is None
    assert harness.review_runtime.controller_running() is False
    assert harness.review_runtime.cancel_event() is None
    assert backend.closed is True


def test_global_cancel_routes_active_review_cancellation_through_scheduler(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_panel = harness.queue_panel
    backend = _FakeBackend()
    entered_run = threading.Event()
    finish_run = threading.Event()
    project_path = tmp_path / "project"
    project_path.mkdir()
    cancelled_ids: list[int] = []

    class _BlockingRunner:
        def __init__(self, client: Any, *, scan_fn: Any, backend_name: str) -> None:
            self.client = client

        def run(self, **kwargs: Any) -> None:
            cancel_check = kwargs["cancel_check"]
            entered_run.set()
            while not cancel_check():
                time.sleep(0.01)
            finish_run.wait(timeout=5.0)
            return None

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: backend)
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.AppRunner", _BlockingRunner)

    harness.enable_runtime_actions()
    harness.fill_valid_review_form(project_path)
    harness.start_review()
    harness.wait_until(entered_run.is_set, message="review worker never started")
    harness.wait_until(
        lambda: queue_panel.active_submission_id() is not None,
        message="active scheduler submission never appeared",
    )
    active_submission_id = queue_panel.active_submission_id()
    original_cancel_submission = harness.app._review_execution_scheduler.cancel_submission

    def _recording_cancel_submission(submission_id: int) -> bool:
        cancelled_ids.append(submission_id)
        return original_cancel_submission(submission_id)

    monkeypatch.setattr(harness.app._review_execution_scheduler, "cancel_submission", _recording_cancel_submission)

    harness.app._cancel_operation()
    harness.pump()

    assert cancelled_ids == [active_submission_id]
    assert backend.cancelled is True

    finish_run.set()
    harness.wait_until(
        lambda: not harness.review_runtime.is_running(),
        message="review never finished after scheduler-routed cancellation",
    )


def test_queue_panel_can_target_and_cancel_a_queued_review_submission(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_panel = harness.queue_panel
    project_path = tmp_path / "project"
    project_path.mkdir()
    entered_runs: list[threading.Event] = [threading.Event(), threading.Event()]
    finish_first = threading.Event()
    runner_calls: list[int] = []

    class _QueueingRunner:
        def __init__(self, client: Any, *, scan_fn: Any, backend_name: str) -> None:
            self.client = client

        def run(self, **kwargs: Any) -> None:
            run_index = len(runner_calls)
            runner_calls.append(run_index)
            entered_runs[run_index].set()
            if run_index == 0:
                finish_first.wait(timeout=5.0)
            return None

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: _FakeBackend())
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.AppRunner", _QueueingRunner)

    harness.enable_runtime_actions()
    harness.fill_valid_review_form(project_path)

    harness.start_review()
    harness.wait_until(
        lambda: bool(queue_panel.snapshots()) and any(snapshot.is_active for snapshot in queue_panel.snapshots()),
        message="first review snapshot never appeared",
    )
    harness.wait_until(
        lambda: bool(queue_panel.snapshots()) and queue_panel.snapshots()[0].is_active,
        message="active review snapshot never appeared",
    )

    harness.start_review()
    harness.pump()

    snapshots = queue_panel.snapshots()
    assert len(snapshots) == 2
    assert snapshots[0].is_active is True
    assert snapshots[0].submission_kind == "review"
    assert snapshots[1].status == "queued"
    assert snapshots[1].submission_kind == "review"
    assert harness.app.run_btn.cget("state") == "normal"
    assert queue_panel.summary_text() == t("gui.review.queue_summary", active=1, queued=1, recent=0)

    queued_snapshot = snapshots[1]
    queue_panel.select_submission(queued_snapshot.submission_id)
    harness.pump()

    assert queue_panel.selected_submission_id() == queued_snapshot.submission_id
    assert queue_panel.detail_text() == t(
        "gui.review.queue_detail_selected_queued",
        submission_id=queued_snapshot.submission_id,
        kind=t("gui.review.queue_kind_review"),
        status=t("gui.review.queue_status_queued"),
        cancel_state=t("gui.review.queue_cancel_available"),
    )

    queue_panel.invoke_cancel()
    harness.pump()

    assert harness.status_bar.text() == t("gui.review.queue_cancelled", submission_id=queued_snapshot.submission_id)
    remaining_snapshots = queue_panel.snapshots()
    assert len(remaining_snapshots) == 2
    assert any(
        snapshot.submission_id == queued_snapshot.submission_id and snapshot.status == "cancelled"
        for snapshot in remaining_snapshots
    )
    assert any(
        snapshot.is_active is True and snapshot.submission_id != queued_snapshot.submission_id
        for snapshot in remaining_snapshots
    )
    assert queue_panel.summary_text() == t("gui.review.queue_summary", active=1, queued=0, recent=1)
    assert entered_runs[1].is_set() is False

    finish_first.set()
    harness.wait_until(
        lambda: not harness.review_runtime.is_running(),
        message="first queued review never finished",
    )


def test_queue_panel_surfaces_recent_completed_submission_after_review_finishes(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_panel = harness.queue_panel
    project_path = tmp_path / "project"
    project_path.mkdir()

    class _CompletingRunner:
        def __init__(self, client: Any, *, scan_fn: Any, backend_name: str) -> None:
            self.client = client

        def run(self, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: _FakeBackend())
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.AppRunner", _CompletingRunner)

    harness.enable_runtime_actions()
    harness.fill_valid_review_form(project_path)
    harness.start_review()
    harness.wait_until(
        lambda: any(snapshot.status == "completed" for snapshot in queue_panel.snapshots()),
        message="completed submission never appeared in the queue panel",
    )

    snapshots = [snapshot for snapshot in queue_panel.snapshots() if snapshot.status == "completed"]
    assert len(snapshots) == 1
    assert queue_panel.summary_text() == t("gui.review.queue_summary", active=0, queued=0, recent=1)

    queue_panel.select_submission(snapshots[0].submission_id)
    harness.pump()

    assert queue_panel.detail_text() == t(
        "gui.review.queue_detail_selected_recent",
        submission_id=snapshots[0].submission_id,
        kind=t("gui.review.queue_kind_review"),
        status=t("gui.review.queue_status_completed"),
        cancel_state=t("gui.review.queue_cancel_unavailable"),
    )


def test_queue_panel_orders_queued_reviews_before_dry_runs_and_uses_kind_badges(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queue_panel = harness.queue_panel
    project_path = tmp_path / "project"
    project_path.mkdir()
    entered_runs: list[threading.Event] = [threading.Event(), threading.Event(), threading.Event()]
    finish_first = threading.Event()
    runner_calls: list[int] = []

    class _QueueingRunner:
        def __init__(self, client: Any, *, scan_fn: Any, backend_name: str) -> None:
            self.client = client

        def run(self, **kwargs: Any) -> None:
            run_index = len(runner_calls)
            runner_calls.append(run_index)
            entered_runs[run_index].set()
            if run_index == 0:
                finish_first.wait(timeout=5.0)
            return None

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: _FakeBackend())
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.AppRunner", _QueueingRunner)

    harness.enable_runtime_actions()
    harness.fill_valid_review_form(project_path)

    harness.start_review()
    harness.wait_until(entered_runs[0].is_set, message="first review never started")

    harness.start_dry_run()
    harness.pump()
    harness.start_review()
    harness.pump()

    snapshots = queue_panel.snapshots()
    assert [snapshot.submission_kind for snapshot in snapshots] == ["review", "dry_run", "review"]

    display_ids = queue_panel.display_ids()
    assert display_ids == [
        snapshots[0].submission_id,
        snapshots[2].submission_id,
        snapshots[1].submission_id,
    ]

    labels_by_id = {
        submission_id: label
        for label, submission_id in queue_panel.labels().items()
    }
    assert labels_by_id[snapshots[2].submission_id].startswith(t("gui.review.queue_badge_review"))
    assert labels_by_id[snapshots[1].submission_id].startswith(t("gui.review.queue_badge_dry_run"))
    assert queue_panel.detail_text() == t(
        "gui.review.queue_detail_selected_active",
        submission_id=snapshots[0].submission_id,
        kind=t("gui.review.queue_kind_review"),
        status=t("gui.review.queue_status_running"),
        cancel_state=t("gui.review.queue_cancel_available"),
    )

    finish_first.set()
    harness.wait_until(
        lambda: not harness.review_runtime.is_running(),
        message="queued submissions never finished",
    )


def test_review_validation_uses_localized_selected_file_requirement_toast(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()

    harness.enable_runtime_actions()
    harness.fill_valid_review_form(project_path)
    harness.app.file_select_mode_var.set("selected")
    harness.app.selected_files = []

    assert harness.app._validate_inputs() is None
    assert any(
        message == t("gui.review.select_files_required") and error
        for message, error in harness.toasts
    )


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
        lambda: not harness.review_runtime.is_running() and harness.status_text() == t("gui.val.dry_run_done"),
        message="dry run did not complete",
    )
    harness.wait_until(
        lambda: "Dry run inspected" in harness.log_text(),
        message="dry run log output never appeared in the Output Log tab",
    )

    assert harness.app.tabs.get() == t("gui.tab.log")
    assert harness.results_tab.active_review_client() is None


def test_active_review_controller_stream_handler_accumulates_preview_and_resets(
    harness: GuiTestHarness,
) -> None:
    seen_status: list[str] = []
    controller = harness.app._active_review
    coordinator = harness.app._review_execution

    stream_handler = coordinator.build_stream_handler(seen_status.append)
    stream_handler("hello")
    stream_handler("\nworld")

    assert controller.stream_preview_text == "hello world"
    assert seen_status[-1] == "\u23f3 hello world"

    controller.begin()

    assert controller.stream_preview_text == ""


def test_active_review_controller_event_sink_updates_progress_snapshot(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.execution import JobProgressUpdated

    seen_progress: list[tuple[float, str]] = []
    controller = harness.app._active_review
    coordinator = harness.app._review_execution
    sink = coordinator.build_event_sink(lambda fraction, status: seen_progress.append((fraction, status)))

    sink.emit(
        JobProgressUpdated(
            job_id="job-1",
            kind="job.progress",
            current=2,
            total=5,
            message="Reviewing",
        )
    )

    assert controller.progress_current == 2
    assert controller.progress_total == 5
    assert controller.progress_message == "Reviewing"
    assert seen_progress[-1] == (0.4, "Reviewing 2/5")


def test_review_execution_coordinator_activate_client_binds_backend_and_stream_handler(
    harness: GuiTestHarness,
) -> None:
    backend = _FakeBackend()
    seen_status: list[str] = []
    controller = harness.app._active_review
    coordinator = harness.app._review_execution

    client = coordinator.activate_client(
        "copilot",
        lambda backend_name: backend if backend_name == "copilot" else None,
        seen_status.append,
    )

    assert client is backend
    assert controller.client is backend
    assert backend.stream_callbacks

    stream_handler = backend.stream_callbacks[-1]
    assert callable(stream_handler)
    stream_handler("token")

    assert controller.stream_preview_text == "token"
    assert seen_status[-1] == "\u23f3 token"


def test_review_execution_coordinator_classifies_issue_results(
    harness: GuiTestHarness,
) -> None:
    coordinator = harness.app._review_execution
    issue = ReviewIssue(file_path="a.py", issue_type="security", description="x")
    runner = object()

    outcome = coordinator.classify_run_result(
        dry_run=False,
        result=[issue],
        runner=runner,
        cancel_requested=False,
    )

    assert outcome.kind == "issues_found"
    assert outcome.issues == [issue]
    assert outcome.runner is runner


def test_review_execution_coordinator_classifies_cancelled_run(
    harness: GuiTestHarness,
) -> None:
    coordinator = harness.app._review_execution

    outcome = coordinator.classify_run_result(
        dry_run=False,
        result=None,
        runner=None,
        cancel_requested=True,
    )

    assert outcome.kind == "cancelled"


def test_review_execution_facade_executes_review_and_returns_issue_outcome(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    facade = harness.app._review_execution_facade
    backend = _FakeBackend()
    project_path = tmp_path / "project"
    project_path.mkdir()
    issue = ReviewIssue(file_path=str(project_path / "a.py"), issue_type="security", description="x")
    runner_instances: list[Any] = []

    class _Runner:
        def __init__(self, client: Any, *, scan_fn: Any, backend_name: str) -> None:
            self.client = client
            self.scan_fn = scan_fn
            self.backend_name = backend_name
            self.run_calls: list[dict[str, Any]] = []
            runner_instances.append(self)

        def run(self, **kwargs: Any) -> list[ReviewIssue]:
            self.run_calls.append(kwargs)
            return [issue]

    outcome = facade.execute_run(
        params={
            "backend": "copilot",
            "path": str(project_path),
            "scope": "project",
            "diff_file": None,
            "commits": None,
            "review_types": ["security"],
            "spec_content": None,
            "target_lang": "en",
            "programmers": ["dev"],
            "reviewers": ["rev"],
            "selected_files": None,
            "diff_filter_file": None,
            "diff_filter_commits": None,
        },
        dry_run=False,
        cancel_check=lambda: False,
        publish_status=lambda _status: None,
        create_client=lambda backend_name: backend if backend_name == "copilot" else None,
        create_runner=_Runner,
        event_sink=object(),
        scan_project_with_scope_fn=lambda directory, scope, diff_file=None, commits=None: [str(project_path / "a.py")],
        get_diff_from_commits_fn=lambda directory, commits: None,
        parse_diff_file_fn=lambda diff_content: [],
    )

    assert outcome.kind == "issues_found"
    assert outcome.issues == [issue]
    assert outcome.runner is runner_instances[0]
    assert runner_instances[0].backend_name == "copilot"
    assert runner_instances[0].run_calls[0]["event_sink"] is not None


def test_review_execution_scheduler_accepts_submission_and_dispatches_outcome_and_finished_callbacks(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    dispatched: list[str] = []
    started: list[tuple[int, str]] = []
    seen_cancel_events: list[threading.Event] = []

    class _ImmediateThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _ImmediateThread(**kwargs),
    )

    def _execute_run(cancel_event: threading.Event) -> ReviewExecutionOutcome:
        seen_cancel_events.append(cancel_event)
        return ReviewExecutionOutcome(kind="no_report")

    submission = scheduler.submit_run(
        execute_run=_execute_run,
        on_started=lambda accepted: started.append((accepted.submission_id, accepted.status)),
        on_outcome=lambda outcome: dispatched.append(outcome.kind),
        on_error=lambda exc: dispatched.append(f"error:{exc}"),
        on_finished=lambda: dispatched.append("finished"),
    )

    assert submission.submission_id == 1
    assert submission.status == "completed"
    assert seen_cancel_events == [submission.cancel_event]
    assert started == [(1, "running")]
    assert dispatched == ["no_report", "finished"]
    assert scheduler.active_submission_id is None
    assert scheduler.queued_submission_ids == ()
    assert harness.review_runtime.controller_running() is False
    assert harness.review_runtime.cancel_event() is None


def test_review_execution_scheduler_dispatches_error_before_finished_and_releases_client(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    backend = _FakeBackend()
    dispatched: list[str] = []
    controller = harness.app._active_review

    class _ImmediateThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _ImmediateThread(**kwargs),
    )

    def _execute_run(_cancel_event: threading.Event) -> Any:
        controller.bind_client(backend)
        raise RuntimeError("boom")

    submission = scheduler.submit_run(
        execute_run=_execute_run,
        on_outcome=lambda outcome: dispatched.append(outcome.kind),
        on_error=lambda exc: dispatched.append(f"error:{exc}"),
        on_finished=lambda: dispatched.append("finished"),
    )

    assert submission.submission_id == 1
    assert submission.status == "failed"
    assert dispatched == ["error:boom", "finished"]
    assert backend.closed is True
    assert controller.client is None
    assert controller.cancel_event is None
    assert controller.running is False
    assert scheduler.active_submission_id is None


def test_review_execution_scheduler_dispatches_cancelled_before_finished(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    dispatched: list[str] = []

    class _ImmediateThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _ImmediateThread(**kwargs),
    )

    def _execute_run(cancel_event: threading.Event) -> ReviewExecutionOutcome:
        cancel_event.set()
        return ReviewExecutionOutcome(kind="cancelled")

    submission = scheduler.submit_run(
        execute_run=_execute_run,
        on_outcome=lambda outcome: dispatched.append(outcome.kind),
        on_error=lambda exc: dispatched.append(f"error:{exc}"),
        on_finished=lambda: dispatched.append("finished"),
    )

    assert submission.submission_id == 1
    assert submission.cancel_event.is_set() is True
    assert submission.status == "cancelled"
    assert dispatched == ["cancelled", "finished"]
    assert scheduler.active_submission_id is None


def test_review_execution_scheduler_cancels_when_requested_during_on_started_side_effects(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    dispatched: list[str] = []
    started: list[tuple[int, str]] = []
    executed: list[str] = []
    scheduler_ref: dict[str, ReviewExecutionScheduler | None] = {"value": None}

    class _ImmediateThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    def _on_started(accepted: Any) -> None:
        started.append((accepted.submission_id, accepted.status))
        cancelled = scheduler_ref["value"].cancel_submission(accepted.submission_id) if scheduler_ref["value"] is not None else False
        dispatched.append(f"cancel:{cancelled}")

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _ImmediateThread(**kwargs),
    )
    scheduler_ref["value"] = scheduler

    submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: executed.append("executed"),
        on_started=_on_started,
        on_outcome=lambda outcome: dispatched.append(outcome.kind),
        on_error=lambda exc: dispatched.append(f"error:{exc}"),
        on_finished=lambda: dispatched.append("finished"),
    )

    assert submission.submission_id == 1
    assert submission.status == "cancelled"
    assert submission.cancel_event.is_set() is True
    assert started == [(1, "running")]
    assert executed == []
    assert dispatched == ["cancel:True", "cancelled", "finished"]
    assert scheduler.active_submission_id is None


def test_review_execution_scheduler_treats_post_cancel_exception_as_cancelled(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    backend = _FakeBackend()
    dispatched: list[str] = []
    controller = harness.app._active_review

    class _ImmediateThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _ImmediateThread(**kwargs),
    )

    def _execute_run(cancel_event: threading.Event) -> Any:
        controller.bind_client(backend)
        cancel_event.set()
        raise RuntimeError("late boom")

    submission = scheduler.submit_run(
        execute_run=_execute_run,
        on_outcome=lambda outcome: dispatched.append(outcome.kind),
        on_error=lambda exc: dispatched.append(f"error:{exc}"),
        on_finished=lambda: dispatched.append("finished"),
    )

    assert submission.submission_id == 1
    assert submission.status == "cancelled"
    assert dispatched == ["cancelled", "finished"]
    assert backend.closed is True
    assert controller.client is None
    assert controller.cancel_event is None
    assert controller.running is False
    assert scheduler.active_submission_id is None


def test_review_execution_scheduler_ignores_active_cancel_after_outcome_before_finished(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    backend = _FakeBackend()
    controller = harness.app._active_review
    dispatched: list[str] = []
    cancel_results: list[bool] = []
    seen_active_ids: list[int | None] = []

    class _ImmediateThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _ImmediateThread(**kwargs),
    )

    def _execute_run(_cancel_event: threading.Event) -> ReviewExecutionOutcome:
        controller.bind_client(backend)
        return ReviewExecutionOutcome(kind="no_report")

    submission_id: dict[str, int | None] = {"value": None}

    submission = scheduler.submit_run(
        execute_run=_execute_run,
        on_started=lambda accepted: submission_id.__setitem__("value", accepted.submission_id),
        on_outcome=lambda outcome: (
            dispatched.append(outcome.kind),
            seen_active_ids.append(scheduler.active_submission_id),
            cancel_results.append(scheduler.cancel_submission(submission_id["value"] or -1)),
        ),
        on_error=lambda exc: dispatched.append(f"error:{exc}"),
        on_finished=lambda: dispatched.append("finished"),
    )

    assert submission.submission_id == 1
    assert submission.status == "completed"
    assert submission.cancel_event.is_set() is False
    assert cancel_results == [False]
    assert seen_active_ids == [1]
    assert dispatched == ["no_report", "finished"]
    assert backend.cancelled is False
    assert backend.closed is True
    assert controller.client is None
    assert controller.cancel_event is None
    assert controller.running is False
    assert scheduler.active_submission_id is None


def test_review_execution_scheduler_queues_later_submission_until_active_run_finishes(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    events: list[str] = []
    threads: list[Any] = []

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon
            threads.append(self)

        def start(self) -> None:
            return None

        def run(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    first_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: events.append(f"started:{submission.submission_id}:{submission.status}"),
        on_outcome=lambda outcome: events.append(f"first:{outcome.kind}"),
        on_error=lambda exc: events.append(f"first-error:{exc}"),
        on_finished=lambda: events.append("first:finished"),
    )
    second_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: events.append(f"started:{submission.submission_id}:{submission.status}"),
        on_outcome=lambda outcome: events.append(f"second:{outcome.kind}"),
        on_error=lambda exc: events.append(f"second-error:{exc}"),
        on_finished=lambda: events.append("second:finished"),
    )

    assert first_submission.submission_id == 1
    assert first_submission.status == "running"
    assert second_submission.submission_id == 2
    assert second_submission.status == "queued"
    assert scheduler.active_submission_id == 1
    assert scheduler.queued_submission_ids == (2,)
    assert len(threads) == 1

    threads[0].run()

    assert first_submission.status == "completed"
    assert second_submission.status == "running"
    assert scheduler.active_submission_id == 2
    assert scheduler.queued_submission_ids == ()
    assert len(threads) == 2
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "started:2:running",
    ]

    threads[1].run()

    assert second_submission.status == "completed"
    assert scheduler.active_submission_id is None
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "started:2:running",
        "second:no_report",
        "second:finished",
    ]


def test_review_execution_scheduler_dispatches_next_queued_submission_after_late_cancel_during_finish_cleanup(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    events: list[str] = []
    cancel_results: list[bool] = []
    threads: list[Any] = []
    first_submission_id: dict[str, int | None] = {"value": None}

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon
            threads.append(self)

        def start(self) -> None:
            return None

        def run(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    def _finish_first() -> None:
        events.append("first:finished")
        late_cancelled = scheduler.cancel_submission(first_submission_id["value"] or -1)
        cancel_results.append(late_cancelled)
        events.append(f"first:late_cancel:{late_cancelled}")

    first_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: (
            first_submission_id.__setitem__("value", submission.submission_id),
            events.append(f"started:{submission.submission_id}:{submission.status}"),
        ),
        on_outcome=lambda outcome: events.append(f"first:{outcome.kind}"),
        on_error=lambda exc: events.append(f"first-error:{exc}"),
        on_finished=_finish_first,
    )
    second_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: events.append(f"started:{submission.submission_id}:{submission.status}"),
        on_outcome=lambda outcome: events.append(f"second:{outcome.kind}"),
        on_error=lambda exc: events.append(f"second-error:{exc}"),
        on_finished=lambda: events.append("second:finished"),
    )

    assert first_submission.submission_id == 1
    assert second_submission.submission_id == 2
    assert first_submission.status == "running"
    assert second_submission.status == "queued"
    assert len(threads) == 1

    threads[0].run()

    assert first_submission.status == "completed"
    assert second_submission.status == "running"
    assert scheduler.active_submission_id == 2
    assert scheduler.queued_submission_ids == ()
    assert cancel_results == [False]
    assert len(threads) == 2
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "first:late_cancel:False",
        "started:2:running",
    ]

    threads[1].run()

    assert second_submission.status == "completed"
    assert scheduler.active_submission_id is None
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "first:late_cancel:False",
        "started:2:running",
        "second:no_report",
        "second:finished",
    ]


def test_review_execution_scheduler_rejects_cancel_for_next_submission_reserved_active_before_on_started(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    events: list[str] = []
    cancel_results: list[bool] = []
    threads: list[Any] = []
    second_submission_id: dict[str, int | None] = {"value": None}

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon
            threads.append(self)

        def start(self) -> None:
            return None

        def run(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    def _finish_first() -> None:
        events.append("first:finished")
        late_cancelled = scheduler.cancel_submission(second_submission_id["value"] or -1)
        cancel_results.append(late_cancelled)
        events.append(f"second:late_cancel:{late_cancelled}")

    first_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: events.append(f"started:{submission.submission_id}:{submission.status}"),
        on_outcome=lambda outcome: events.append(f"first:{outcome.kind}"),
        on_error=lambda exc: events.append(f"first-error:{exc}"),
        on_finished=_finish_first,
    )
    second_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: (
            second_submission_id.__setitem__("value", submission.submission_id),
            events.append(f"started:{submission.submission_id}:{submission.status}"),
        ),
        on_outcome=lambda outcome: events.append(f"second:{outcome.kind}"),
        on_error=lambda exc: events.append(f"second-error:{exc}"),
        on_finished=lambda: events.append("second:finished"),
    )
    second_submission_id["value"] = second_submission.submission_id

    assert first_submission.submission_id == 1
    assert second_submission.submission_id == 2
    assert first_submission.status == "running"
    assert second_submission.status == "queued"
    assert len(threads) == 1

    threads[0].run()

    assert first_submission.status == "completed"
    assert second_submission.status == "running"
    assert scheduler.active_submission_id == 2
    assert scheduler.queued_submission_ids == ()
    assert cancel_results == [False]
    assert len(threads) == 2
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "second:late_cancel:False",
        "started:2:running",
    ]

    threads[1].run()

    assert second_submission.status == "completed"
    assert scheduler.active_submission_id is None
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "second:late_cancel:False",
        "started:2:running",
        "second:no_report",
        "second:finished",
    ]


def test_review_execution_scheduler_exposes_reserved_active_snapshot_during_on_finished_refresh_side_effects(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    events: list[str] = []
    threads: list[Any] = []
    observed_snapshots: list[list[tuple[int, str, bool, bool]]] = []
    observed_active: list[tuple[int, str, bool, bool] | None] = []

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon
            threads.append(self)

        def start(self) -> None:
            return None

        def run(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    def _finish_first() -> None:
        events.append("first:finished")
        snapshots = scheduler.list_submission_snapshots()
        observed_snapshots.append(
            [
                (
                    snapshot.submission_id,
                    snapshot.status,
                    snapshot.is_active,
                    snapshot.thread_attached,
                )
                for snapshot in snapshots
            ]
        )
        active_snapshot = scheduler.get_active_submission_snapshot()
        observed_active.append(
            None
            if active_snapshot is None
            else (
                active_snapshot.submission_id,
                active_snapshot.status,
                active_snapshot.is_active,
                active_snapshot.thread_attached,
            )
        )
        events.append("first:refreshed")

    first_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: events.append(f"started:{submission.submission_id}:{submission.status}"),
        on_outcome=lambda outcome: events.append(f"first:{outcome.kind}"),
        on_error=lambda exc: events.append(f"first-error:{exc}"),
        on_finished=_finish_first,
    )
    second_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: events.append(f"started:{submission.submission_id}:{submission.status}"),
        on_outcome=lambda outcome: events.append(f"second:{outcome.kind}"),
        on_error=lambda exc: events.append(f"second-error:{exc}"),
        on_finished=lambda: events.append("second:finished"),
    )

    assert first_submission.submission_id == 1
    assert second_submission.submission_id == 2
    assert first_submission.status == "running"
    assert second_submission.status == "queued"
    assert len(threads) == 1

    threads[0].run()

    assert first_submission.status == "completed"
    assert second_submission.status == "running"
    assert scheduler.active_submission_id == 2
    assert observed_snapshots == [[(2, "queued", True, False)]]
    assert observed_active == [(2, "queued", True, False)]
    assert len(threads) == 2
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "first:refreshed",
        "started:2:running",
    ]

    threads[1].run()

    assert second_submission.status == "completed"
    assert scheduler.active_submission_id is None
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "first:refreshed",
        "started:2:running",
        "second:no_report",
        "second:finished",
    ]


def test_review_execution_scheduler_rejects_reentrant_cancel_from_second_on_finished_side_effects(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    events: list[str] = []
    cancel_results: list[bool] = []
    observed_snapshots: list[tuple[tuple[int, str], ...]] = []
    second_submission_id: dict[str, int | None] = {"value": None}
    threads: list[Any] = []

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon
            threads.append(self)

        def start(self) -> None:
            return None

        def run(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    first_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: events.append(f"started:{submission.submission_id}:{submission.status}"),
        on_outcome=lambda outcome: events.append(f"first:{outcome.kind}"),
        on_error=lambda exc: events.append(f"first-error:{exc}"),
        on_finished=lambda: events.append("first:finished"),
    )
    second_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: (
            second_submission_id.__setitem__("value", submission.submission_id),
            events.append(f"started:{submission.submission_id}:{submission.status}"),
        ),
        on_outcome=lambda outcome: events.append(f"second:{outcome.kind}"),
        on_error=lambda exc: events.append(f"second-error:{exc}"),
        on_finished=lambda: (
            events.append("second:finished"),
            observed_snapshots.append(
                tuple((snapshot.submission_id, snapshot.status) for snapshot in scheduler.list_submission_snapshots())
            ),
            cancel_results.append(scheduler.cancel_submission(second_submission_id["value"] or -1)),
            events.append(f"second:late_cancel:{cancel_results[-1]}"),
        ),
    )
    second_submission_id["value"] = second_submission.submission_id

    assert first_submission.submission_id == 1
    assert second_submission.submission_id == 2
    assert first_submission.status == "running"
    assert second_submission.status == "queued"
    assert len(threads) == 1

    threads[0].run()

    assert first_submission.status == "completed"
    assert second_submission.status == "running"
    assert scheduler.active_submission_id == 2
    assert len(threads) == 2
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "started:2:running",
    ]

    threads[1].run()

    assert second_submission.status == "completed"
    assert scheduler.active_submission_id is None
    assert scheduler.queued_submission_ids == ()
    assert observed_snapshots == [()]
    assert cancel_results == [False]
    assert events == [
        "started:1:running",
        "first:no_report",
        "first:finished",
        "started:2:running",
        "second:no_report",
        "second:finished",
        "second:late_cancel:False",
    ]


def test_review_execution_scheduler_exposes_active_and_queued_submission_snapshots(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            return None

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    first_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_outcome=lambda outcome: None,
        on_error=lambda exc: None,
        on_finished=lambda: None,
    )
    second_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_outcome=lambda outcome: None,
        on_error=lambda exc: None,
        on_finished=lambda: None,
    )

    active_snapshot = scheduler.get_active_submission_snapshot()
    second_snapshot = scheduler.get_submission_snapshot(second_submission.submission_id)
    all_snapshots = scheduler.list_submission_snapshots()

    assert active_snapshot is not None
    assert active_snapshot.submission_id == first_submission.submission_id
    assert active_snapshot.submission_kind == "review"
    assert active_snapshot.status == "running"
    assert active_snapshot.cancel_requested is False
    assert active_snapshot.is_active is True
    assert active_snapshot.thread_attached is True

    assert second_snapshot is not None
    assert second_snapshot.submission_id == second_submission.submission_id
    assert second_snapshot.submission_kind == "review"
    assert second_snapshot.status == "queued"
    assert second_snapshot.cancel_requested is False
    assert second_snapshot.is_active is False
    assert second_snapshot.thread_attached is False

    assert all_snapshots == (active_snapshot, second_snapshot)


def test_review_execution_scheduler_snapshot_reflects_queued_cancellation(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            return None

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_outcome=lambda outcome: None,
        on_error=lambda exc: None,
        on_finished=lambda: None,
    )
    queued_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_outcome=lambda outcome: None,
        on_error=lambda exc: None,
        on_finished=lambda: None,
    )

    assert scheduler.cancel_submission(queued_submission.submission_id) is True
    assert scheduler.get_submission_snapshot(queued_submission.submission_id) is None
    assert scheduler.list_submission_snapshots()[0].is_active is True


def test_review_execution_scheduler_marks_dry_run_submission_kind_in_snapshots(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            return None

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    dry_run_submission = scheduler.submit_run(
        submission_kind="dry_run",
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="dry_run_complete"),
        on_outcome=lambda outcome: None,
        on_error=lambda exc: None,
        on_finished=lambda: None,
    )

    snapshot = scheduler.get_active_submission_snapshot()

    assert dry_run_submission.submission_kind == "dry_run"
    assert snapshot is not None
    assert snapshot.submission_id == dry_run_submission.submission_id
    assert snapshot.submission_kind == "dry_run"


def test_review_execution_scheduler_can_drop_queued_submission_before_dispatch(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    events: list[str] = []
    threads: list[Any] = []

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon
            threads.append(self)

        def start(self) -> None:
            return None

        def run(self) -> None:
            self._target()

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    first_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: events.append(f"started:{submission.submission_id}:{submission.status}"),
        on_outcome=lambda outcome: events.append(f"first:{outcome.kind}"),
        on_error=lambda exc: events.append(f"first-error:{exc}"),
        on_finished=lambda: events.append("first:finished"),
    )
    second_submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_started=lambda submission: events.append(f"started:{submission.submission_id}:{submission.status}"),
        on_outcome=lambda outcome: events.append(f"second:{outcome.kind}"),
        on_error=lambda exc: events.append(f"second-error:{exc}"),
        on_finished=lambda: events.append("second:finished"),
    )

    assert scheduler.cancel_submission(second_submission.submission_id) is True
    assert second_submission.status == "cancelled"
    assert second_submission.cancel_event.is_set() is True
    assert scheduler.queued_submission_ids == ()
    assert events == [
        "started:1:running",
        "second:cancelled",
        "second:finished",
    ]


def test_review_execution_scheduler_routes_active_cancellation_through_controller(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionOutcome
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    backend = _FakeBackend()
    controller = harness.app._active_review

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            return None

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    submission = scheduler.submit_run(
        execute_run=lambda _cancel_event: ReviewExecutionOutcome(kind="no_report"),
        on_outcome=lambda outcome: None,
        on_error=lambda exc: None,
        on_finished=lambda: None,
    )
    controller.bind_client(backend)

    assert submission.status == "running"
    assert submission.cancel_event.is_set() is False
    assert scheduler.cancel_submission(submission.submission_id) is True
    assert submission.cancel_event.is_set() is True
    assert backend.cancelled is True


def test_review_execution_scheduler_cancel_submission_sets_active_cancel_event(
    harness: GuiTestHarness,
) -> None:
    from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler

    threads: list[Any] = []

    class _DeferredThread:
        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon
            threads.append(self)

        def start(self) -> None:
            return None

    scheduler = ReviewExecutionScheduler(
        harness.app._review_execution_facade,
        _thread_factory=lambda **kwargs: _DeferredThread(**kwargs),
    )

    submission = scheduler.submit_run(
        execute_run=lambda cancel_event: (_ for _ in ()).throw(AssertionError(f"cancelled={cancel_event.is_set()}")),
        on_outcome=lambda outcome: None,
        on_error=lambda exc: None,
        on_finished=lambda: None,
    )

    assert submission.status == "running"
    assert submission.cancel_event.is_set() is False
    assert scheduler.cancel_submission(submission.submission_id) is True
    assert submission.cancel_event.is_set() is True
    assert scheduler.cancel_submission(9999) is False


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
            self.serialized_report_context: dict[str, Any] | None = None

        def run(self, **kwargs: Any) -> list[ReviewIssue]:
            self.serialized_report_context = {
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
        lambda: not first_harness.review_runtime.is_running() and first_harness.results_tab.issue_count() == 1,
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

    second_runner = second_harness.review_runtime.current_runner()
    first_runner = first_harness.review_runtime.current_runner()

    assert second_harness.results_tab.issue_count() == 1
    assert second_harness.results_tab.issue_descriptions() == [issue.description]
    assert second_runner is not None
    assert first_runner is not None
    assert second_runner.serialized_report_context["backend"] == first_runner.serialized_report_context["backend"]
    assert second_runner.serialized_report_context["project_path"] == str(project_path)
    assert second_runner.last_execution is not None
    assert second_runner.last_execution.status == "issues_found"
    assert second_runner.last_job is not None
    assert second_runner.last_job.state == "awaiting_gui_finalize"


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


def test_review_type_preset_picker_applies_bundle_and_tracks_exact_match(
    harness: GuiTestHarness,
) -> None:
    runtime_safety_label = harness.app._review_preset_labels["runtime_safety"]
    harness.app._on_review_preset_selected(runtime_safety_label)
    harness.pump()

    assert harness.app.review_preset_var.get() == runtime_safety_label
    assert harness.app.type_vars["security"].get() is True
    assert harness.app.type_vars["error_handling"].get() is True
    assert harness.app.type_vars["data_validation"].get() is True
    assert harness.app.type_vars["dependency"].get() is True
    assert harness.app.type_vars["best_practices"].get() is False

    harness.app.type_vars["testing"].set(True)
    harness.app._on_review_types_changed()

    assert harness.app.review_preset_var.get() == harness.app._review_preset_labels["custom"]
    assert t("gui.review.preset_custom_summary") == harness.app.review_preset_summary_label.cget("text")


def test_review_tab_switches_between_stacked_and_split_run_queue_layout(
    harness: GuiTestHarness,
) -> None:
    harness.app.geometry("980x900")
    harness.wait_until(
        lambda: getattr(harness.app, "review_layout_mode", "") == "stacked",
        message="review tab never entered stacked layout",
    )

    stacked_grid = harness.app.review_run_panel.grid_info()
    assert harness.app.review_layout_mode == "stacked"
    assert int(stacked_grid["row"]) == 2
    assert int(stacked_grid["column"]) == 0
    assert int(stacked_grid["columnspan"]) == 3

    harness.app.geometry("1500x900")
    harness.wait_until(
        lambda: getattr(harness.app, "review_layout_mode", "") == "split",
        message="review tab never entered split layout",
    )

    split_grid = harness.app.review_run_panel.grid_info()
    divider_grid = harness.app.review_layout_divider.grid_info()
    assert harness.app.review_layout_mode == "split"
    assert int(split_grid["row"]) == 0
    assert int(split_grid["column"]) == 2
    assert int(divider_grid["row"]) == 0
    assert int(divider_grid["column"]) == 1
    assert harness.queue_panel.is_bound() is True


def test_review_recommendation_applies_types_and_rationale(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    harness.set_entry(harness.app.path_entry, str(project_path))

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: object())
    monkeypatch.setattr(
        "aicodereviewer.gui.review_mixin.recommend_review_types",
        lambda **kwargs: ReviewRecommendationResult(
            review_types=["security", "error_handling", "data_validation", "dependency"],
            rationale=[
                ReviewTypeRecommendation("security", "Service boundaries are in scope."),
                ReviewTypeRecommendation("error_handling", "Workflow edges merit failure-path review."),
                ReviewTypeRecommendation("data_validation", "Inputs should be validated at boundaries."),
                ReviewTypeRecommendation("dependency", "Manifest review is relevant for this target."),
            ],
            project_signals=["Frameworks: fastapi", "Dependency manifests: pyproject.toml"],
            recommended_preset="runtime_safety",
            source="ai",
        ),
    )

    harness.app._start_review_recommendation()
    harness.pump()

    assert harness.app.type_vars["security"].get() is True
    assert harness.app.type_vars["error_handling"].get() is True
    assert harness.app.type_vars["data_validation"].get() is True
    assert harness.app.type_vars["dependency"].get() is True
    assert harness.app.review_preset_var.get() == harness.app._review_preset_labels["runtime_safety"]
    assert "Frameworks: fastapi" in harness.app.review_recommendation_label.cget("text")
    assert harness.app.pin_review_set_btn.cget("state") == "normal"
    assert any(message == t("gui.review.recommendation_applied") and not error for message, error in harness.toasts)


def test_review_recommendation_can_be_cancelled(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    harness.set_entry(harness.app.path_entry, str(project_path))
    harness.enable_runtime_actions()

    class _CancelableBackend:
        def __init__(self) -> None:
            self.cancelled = False
            self.closed = False

        def cancel(self) -> None:
            self.cancelled = True

        def close(self) -> None:
            self.closed = True

    backend = _CancelableBackend()

    def _slow_recommendation(**kwargs: Any) -> ReviewRecommendationResult:
        cancel_check = kwargs["cancel_check"]
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if cancel_check():
                raise ReviewRecommendationCancelledError("Recommendation cancelled")
            time.sleep(0.01)
        raise AssertionError("Recommendation worker was not cancelled in time")

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: backend)
    monkeypatch.setattr("aicodereviewer.gui.review_mixin.recommend_review_types", _slow_recommendation)

    harness.app._start_review_recommendation()
    harness.wait_until(
        lambda: harness.app.cancel_btn.cget("state") == "normal",
        message="global cancel button never enabled for recommendation run",
    )

    harness.app._cancel_operation()
    harness.wait_until(
        lambda: harness.app.review_recommendation_label.cget("text") == t("gui.review.recommendation_cancelled"),
        message="recommendation cancel state was never applied",
    )

    assert backend.cancelled is True
    assert backend.closed is True
    assert harness.app.cancel_btn.cget("state") == "disabled"
    assert harness.app.status_var.get() == t("gui.val.cancelled")
    assert any(
        message == t("gui.review.recommendation_cancelled_short") and not error
        for message, error in harness.toasts
    )


def test_benchmark_tab_reflows_between_stacked_and_split_layouts(
    harness: GuiTestHarness,
) -> None:
    harness.benchmark_tab.open()

    harness.app.geometry("960x540")
    harness.wait_until(
        lambda: int(harness.app.benchmark_detail_box.grid_info().get("row", 0)) == 3,
        message="benchmark detail pane never stacked at narrow width",
    )
    assert int(harness.app.benchmark_compare_summary_box.grid_info()["row"]) == 4
    assert int(harness.app.benchmark_preview_compare_box.grid_info()["row"]) == 3

    harness.app.geometry("1500x980")
    harness.wait_until(
        lambda: int(harness.app.benchmark_detail_box.grid_info().get("row", 0)) == 2,
        message="benchmark detail pane never returned to split layout",
    )
    assert int(harness.app.benchmark_compare_summary_box.grid_info()["row"]) == 2
    assert int(harness.app.benchmark_preview_compare_box.grid_info()["row"]) == 1


def test_pinned_review_recommendation_overrides_last_used_selection_on_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-pinned-review-types.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    project_path = tmp_path / "project"
    project_path.mkdir()
    first_harness.set_entry(first_harness.app.path_entry, str(project_path))

    monkeypatch.setattr("aicodereviewer.gui.review_mixin.create_backend", lambda backend_name: object())
    monkeypatch.setattr(
        "aicodereviewer.gui.review_mixin.recommend_review_types",
        lambda **kwargs: ReviewRecommendationResult(
            review_types=["security", "error_handling", "data_validation", "dependency"],
            rationale=[
                ReviewTypeRecommendation("security", "Service boundaries are in scope."),
                ReviewTypeRecommendation("error_handling", "Workflow edges merit failure-path review."),
                ReviewTypeRecommendation("data_validation", "Inputs should be validated at boundaries."),
                ReviewTypeRecommendation("dependency", "Manifest review is relevant for this target."),
            ],
            project_signals=["Frameworks: fastapi"],
            recommended_preset="runtime_safety",
            source="ai",
        ),
    )

    first_harness.app._start_review_recommendation()
    first_harness.pump()
    first_harness.app._pin_current_review_selection()
    first_harness.pump()

    assert config.get("gui", "pinned_review_preset") == "runtime_safety"
    assert set(str(config.get("gui", "pinned_review_types")).split(",")) == {
        "security",
        "error_handling",
        "data_validation",
        "dependency",
    }

    first_harness.app.type_vars["dependency"].set(False)
    first_harness.app.type_vars["testing"].set(True)
    first_harness.app._on_review_types_changed()
    first_harness.app._save_form_values()

    assert set(str(config.get("gui", "review_types")).split(",")) == {
        "security",
        "error_handling",
        "data_validation",
        "testing",
    }

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app.type_vars["security"].get() is True
    assert second_harness.app.type_vars["error_handling"].get() is True
    assert second_harness.app.type_vars["data_validation"].get() is True
    assert second_harness.app.type_vars["dependency"].get() is True
    assert second_harness.app.type_vars["testing"].get() is False
    assert second_harness.app.review_preset_var.get() == second_harness.app._review_preset_labels["runtime_safety"]
    assert second_harness.app.review_pin_status_label.cget("text") == t(
        "gui.review.pin_active_preset_summary",
        preset=t("review_preset.runtime_safety.label"),
        types=", ".join(
            t(f"review_type.{review_type}")
            for review_type in ["security", "error_handling", "dependency", "data_validation"]
        ),
    )


def test_clearing_pinned_review_set_restores_last_used_selection_on_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-clear-pinned-review-types.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app.type_vars["security"].set(True)
    first_harness.app.type_vars["performance"].set(True)
    first_harness.app.type_vars["best_practices"].set(False)
    first_harness.app._on_review_types_changed()
    first_harness.app._pin_current_review_selection()
    first_harness.pump()

    assert config.get("gui", "pinned_review_types") == "security,performance"

    first_harness.app.type_vars["security"].set(False)
    first_harness.app.type_vars["performance"].set(False)
    first_harness.app.type_vars["compatibility"].set(True)
    first_harness.app.type_vars["testing"].set(True)
    first_harness.app._on_review_types_changed()
    first_harness.app._save_form_values()
    first_harness.app._clear_pinned_review_selection()
    first_harness.pump()

    assert config.get("gui", "pinned_review_types") == ""

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app.type_vars["compatibility"].get() is True
    assert second_harness.app.type_vars["testing"].get() is True
    assert second_harness.app.type_vars["security"].get() is False
    assert second_harness.app.type_vars["performance"].get() is False
    assert second_harness.app.clear_pinned_review_set_btn.cget("state") == "disabled"


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
    secret_store: dict[tuple[str, str], str] = {}

    monkeypatch.setattr(
        auth.keyring,
        "set_password",
        lambda service, name, value: secret_store.__setitem__((service, name), value),
    )
    monkeypatch.setattr(
        auth.keyring,
        "get_password",
        lambda service, name: secret_store.get((service, name)),
    )
    monkeypatch.setattr(
        auth.keyring,
        "delete_password",
        lambda service, name: secret_store.pop((service, name), None),
    )

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
    first_harness.app._setting_entries[("local_llm", "enable_web_search")].set(False)

    first_harness.app._save_settings()
    first_harness.pump()

    assert config.get("backend", "type") == "local"
    assert config.get("local_llm", "api_url") == "http://127.0.0.1:11434"
    assert config.get("local_llm", "api_type") == "ollama"
    assert config.get("local_llm", "model") == "llama3.2"
    assert config.get("local_llm", "api_key") == auth.build_credential_reference("local_llm", "api_key")
    assert config.get("local_llm", "timeout") == "360"
    assert config.get("local_llm", "max_tokens") == "8192"
    assert config.get("local_llm", "enable_web_search") is False
    assert secret_store[("AICodeReviewer", "credential:local_llm.api_key")] == "local-secret"

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
    assert second_harness.app._setting_entries[("local_llm", "enable_web_search")].get() is False


def test_local_http_settings_persist_across_app_restart(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "gui-local-http.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._setting_entries[("local_http", "enabled")].set(True)
    first_harness.set_entry(first_harness.app._setting_entries[("local_http", "port")], "8877")

    first_harness.app._save_settings()
    first_harness.pump()

    assert config.get("local_http", "enabled") is True
    assert config.get("local_http", "port") == 8877

    _reset_config_to_path(config_path)
    second_harness = GuiTestHarness(app_factory())

    assert second_harness.app._setting_entries[("local_http", "enabled")].get() is True
    assert second_harness.app._setting_entries[("local_http", "port")].get() == "8877"
    assert t("gui.settings.local_http_status_running", port=8877) == second_harness.app.local_http_status_var.get()
    assert second_harness.app.local_http_base_url_var.get() == "http://127.0.0.1:8877"
    assert "GET /api/jobs" in second_harness.app.local_http_docs_box.get("0.0", "end")
    assert "POST /api/recommendations/review-types" in second_harness.app.local_http_docs_box.get("0.0", "end")


def test_local_llm_api_key_rotate_and_revoke_buttons_manage_keyring_reference(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_store: dict[tuple[str, str], str] = {}

    monkeypatch.setattr(
        auth.keyring,
        "set_password",
        lambda service, name, value: secret_store.__setitem__((service, name), value),
    )
    monkeypatch.setattr(
        auth.keyring,
        "get_password",
        lambda service, name: secret_store.get((service, name)),
    )
    monkeypatch.setattr(
        auth.keyring,
        "delete_password",
        lambda service, name: secret_store.pop((service, name), None),
    )

    config_path = tmp_path / "gui-local-llm-rotate.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)
    config.set_value("local_llm", "api_key", auth.build_credential_reference("local_llm", "api_key"))
    config.save()
    secret_store[("AICodeReviewer", "credential:local_llm.api_key")] = "local-secret"

    harness = GuiTestHarness(app_factory())

    assert harness.app._setting_entries[("local_llm", "api_key")].get() == "local-secret"

    harness.app._local_api_key_rotate_btn.invoke()
    harness.pump()

    assert harness.app._setting_entries[("local_llm", "api_key")].get() == ""
    assert config.get("local_llm", "api_key") == auth.build_credential_reference("local_llm", "api_key")
    assert ("AICodeReviewer", "credential:local_llm.api_key") not in secret_store
    assert any(message == t("gui.settings.local_api_key_rotated") and not error for message, error in harness.toasts)

    harness.set_entry(harness.app._setting_entries[("local_llm", "api_key")], "replacement-secret")
    harness.app._save_settings()
    harness.pump()
    assert secret_store[("AICodeReviewer", "credential:local_llm.api_key")] == "replacement-secret"

    harness.app._local_api_key_revoke_btn.invoke()
    harness.pump()

    assert harness.app._setting_entries[("local_llm", "api_key")].get() == ""
    assert config.get("local_llm", "api_key") == ""
    assert ("AICodeReviewer", "credential:local_llm.api_key") not in secret_store
    assert any(message == t("gui.settings.local_api_key_revoked") and not error for message, error in harness.toasts)


def test_gui_starts_and_stops_local_http_server_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App
    import aicodereviewer.gui.app as app_module

    config_path = tmp_path / "gui-local-http-startup.ini"
    _save_default_config_to_path(config_path)
    monkeypatch.setattr(config, "config_path", config_path)
    _reset_config_to_path(config_path)
    config.set_value("local_http", "enabled", "true")
    config.set_value("local_http", "port", "8899")
    config.save()

    created: dict[str, Any] = {}

    class _FakeHandle:
        def __init__(self) -> None:
            self.base_url = "http://127.0.0.1:8899"
            self.port = 8899
            self.closed = False

        def close(self, *, wait: bool = True, timeout: float = 1.0) -> None:
            self.closed = True

    def _fake_create_local_http_app(*, runtime: Any = None, **_kwargs: Any) -> object:
        created["runtime"] = runtime
        return object()

    def _fake_start_local_http_server(app: Any, *, host: str, port: int, **_kwargs: Any) -> _FakeHandle:
        created["app"] = app
        created["host"] = host
        created["port"] = port
        handle = _FakeHandle()
        created["handle"] = handle
        return handle

    monkeypatch.setattr(app_module, "create_local_http_app", _fake_create_local_http_app)
    monkeypatch.setattr(app_module, "start_local_http_server", _fake_start_local_http_server)

    application = None
    clipboard: dict[str, Any] = {}
    try:
        application = App(testing_mode=True)
        application.update_idletasks()

        monkeypatch.setattr(application, "clipboard_clear", lambda: clipboard.clear())
        monkeypatch.setattr(application, "clipboard_append", lambda value: clipboard.__setitem__("value", value))

        assert created["runtime"] is application._review_runtime
        assert created["host"] == "127.0.0.1"
        assert created["port"] == 8899
        assert application._local_http_server_handle is created["handle"]
        assert application.local_http_status_var.get() == t("gui.settings.local_http_status_running", port=8899)
        assert application.local_http_base_url_var.get() == "http://127.0.0.1:8899"
        assert "GET /api/review-presets" in application.local_http_docs_box.get("0.0", "end")
        assert "POST /api/recommendations/review-types" in application.local_http_docs_box.get("0.0", "end")

        application._copy_local_http_base_url()
        assert clipboard["value"] == "http://127.0.0.1:8899"
    finally:
        if application is not None:
            handle = created.get("handle")
            application.destroy()
            if handle is not None:
                assert handle.closed is True


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

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.app._show_issues([issue])
    harness.pump()

    card = harness.results_tab.card(0)
    card["skip_btn"].invoke()
    harness.pump()

    assert issue.status == "skipped"
    assert harness.results_tab.finalize_state() == "normal"
    assert harness.app.review_changes_btn.cget("state") == "disabled"
    assert card["skip_frame"].winfo_manager() != ""

    card["undo_btn"].invoke()
    harness.pump()

    assert issue.status == "pending"
    assert issue.resolution_reason is None
    assert card["skip_frame"].winfo_manager() == ""
    assert harness.results_tab.finalize_state() == "disabled"


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
    harness.app._bind_session_runner(_runner_with_report_context(
        {"backend": "local"},
        generate_report=_generate_report,
    ))
    harness.app._show_issues([issue])
    harness.pump()

    assert harness.app.review_changes_btn.cget("state") == "normal"
    assert harness.results_tab.active_review_client() is None
    assert hasattr(harness.app, "_legacy_compat_state") is False
    assert not hasattr(harness.app, "_review_changes_running")

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
    assert harness.app.cancel_btn.cget("state") == "disabled"
    harness.wait_until(
        lambda: report_calls and not harness.review_runtime.is_review_changes_running(),
        message="review changes did not complete and finalize",
    )

    assert backend_creations == ["local"]
    assert len(verify_calls) == 1
    assert verify_calls[0][1] is verification_backend
    assert report_calls == [["fixed"]]
    assert verification_backend.closed is True
    assert harness.results_tab.active_review_client() is None
    assert harness.review_runtime.active_client() is None
    assert harness.app._active_review_changes.running is False
    assert hasattr(harness.app, "_legacy_compat_state") is False
    assert harness.results_tab.issues() == []
    assert harness.review_runtime.current_runner() is None
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
    harness.app._bind_session_runner(SimpleNamespace(generate_report=_generate_report))
    harness.app._show_issues(issues)
    harness.pump()

    assert harness.results_tab.finalize_state() == "normal"

    harness.app.finalize_btn.invoke()
    harness.pump()

    assert report_calls == [["fixed", "skipped"]]
    assert harness.status_text() == t("gui.val.report_saved", path=str(report_path))
    assert harness.results_tab.issues() == []
    assert harness.results_tab.issue_count() == 0
    assert harness.review_runtime.current_runner() is None
    assert harness.results_tab.finalize_state() == "disabled"
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
        lambda: harness.app._active_health_check.backend_name is None and shown_reports,
        message="health check did not finish and surface a report",
    )

    assert shown_reports == [fake_report]
    assert harness.app._active_health_check.running is False
    assert harness.app._active_health_check.backend_name is None
    assert harness.app._active_health_check.timer is None
    assert harness.status_text() == t("common.ready")
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
        lambda: harness.app._active_health_check.backend_name == "local",
        message="health check never entered running state",
    )
    assert harness.app._active_health_check.running is True
    assert harness.app._active_health_check.backend_name == "local"
    assert harness.app._active_health_check.timer is not None
    assert harness.app.cancel_btn.cget("state") == "normal"

    harness.app.cancel_btn.invoke()
    harness.pump()

    assert harness.status_text() == t("gui.val.cancelled")
    assert harness.app._active_health_check.backend_name is None
    assert harness.app._active_health_check.running is False
    assert harness.app._active_health_check.backend_name is None
    assert harness.app._active_health_check.timer is None
    assert harness.app._active_health_check.countdown_ends_at is None
    assert harness.app._active_health_check.countdown_after_id is None
    assert not hasattr(harness.app, "_health_countdown_end")
    assert not hasattr(harness.app, "_health_countdown_after_id")
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
    shown_popups: list[tuple[list[int], dict[int, Any]]] = []
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
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    card = harness.results_tab.card(0)
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

    harness.results_tab.start_ai_fix()
    harness.wait_until(
        lambda: bool(shown_popups),
        message="AI Fix did not produce preview results",
    )

    assert shown_popups[0][0] == [0]
    assert shown_popups[0][1][0]["content"] is not None
    assert "security" in shown_popups[0][1][0]["content"]
    assert harness.results_tab.ai_fix_runtime_running() is False
    assert harness.results_tab.ai_fix_runtime_client() is None
    assert harness.results_tab.ai_fix_cancel_event() is None
    assert backend.closed is True
    assert harness.results_tab.active_review_client() is None


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
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
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

    harness.results_tab.start_ai_fix()
    harness.wait_until(entered_fix.is_set, message="AI Fix worker never started")
    assert harness.results_tab.is_ai_fix_running() is True
    assert harness.results_tab.is_busy() is True
    assert harness.results_tab.ai_fix_runtime_running() is True
    assert harness.results_tab.ai_fix_cancel_event() is not None

    harness.results_tab.cancel_ai_fix()
    harness.pump()

    cancel_event = harness.results_tab.ai_fix_cancel_event()
    assert cancel_event is not None
    assert cancel_event.is_set() is True
    assert harness.status_text() == t("gui.results.cancelling_status")

    release_fix.set()
    harness.results_tab.wait_until_ai_fix_stops(message="AI Fix did not finish cancellation cleanup")
    harness.pump()

    assert popup_calls == []
    assert harness.status_text() == t("common.ready")
    assert harness.results_tab.ai_fix_cancel_button_text() == t("gui.results.cancel_ai_fix")
    assert harness.results_tab.ai_fix_runtime_running() is False
    assert harness.results_tab.ai_fix_cancel_event() is None
    assert harness.results_tab.ai_fix_runtime_client() is None
    assert backend.closed is True
    assert harness.results_tab.active_review_client() is None


def test_health_check_does_not_start_while_ai_fix_is_running(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered_fix = threading.Event()
    release_fix = threading.Event()

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
        description="Health checks should not start while AI Fix is running.",
        ai_feedback="Optimize the loop.",
        code_snippet="for item in items: pass\n",
    )

    harness.enable_runtime_actions()
    harness.app.backend_var.set("local")
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.create_backend",
        lambda backend_name: backend,
    )

    harness.results_tab.start_ai_fix()
    harness.wait_until(entered_fix.is_set, message="AI Fix worker never started")

    harness.start_health_check()
    harness.pump()

    assert harness.app._active_health_check.running is False
    assert harness.app._active_health_check.backend_name is None

    harness.results_tab.cancel_ai_fix()
    harness.pump()
    release_fix.set()
    harness.results_tab.wait_until_ai_fix_stops(message="AI Fix did not finish after cancellation")


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

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.app._show_issues(issues)
    harness.pump()

    assert harness.results_tab.visible_issue_count() == 3

    harness.results_tab.set_severity_filter("High")
    harness.results_tab.apply_filters()
    harness.pump()

    assert harness.results_tab.visible_issue_count() == 1
    assert harness.results_tab.filter_count_text() == t("gui.results.filter_count", visible=1, total=3)

    harness.results_tab.set_severity_filter(t("gui.results.filter_all"))
    harness.results_tab.set_status_filter("Skipped")
    harness.results_tab.set_type_filter(t("review_type.performance"))
    harness.results_tab.apply_filters()
    harness.pump()

    assert harness.results_tab.visible_issue_count() == 1
    assert harness.results_tab.card(1)["card"].winfo_manager() != ""

    harness.results_tab.clear_filters()
    harness.pump()

    assert harness.results_tab.visible_issue_count() == 3
    assert harness.results_tab.filter_count_text() == ""


def test_restored_session_review_changes_recreates_backend_and_finalizes(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App

    session_path = tmp_path / "session.json"
    report_path = tmp_path / "restored-report.json"
    session_data = {
        "format_version": 2,
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
        "report_context": {
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
    runner = harness.review_runtime.current_runner()
    assert runner is not None
    runner.generate_report = lambda issues: str(report_path)

    harness.app.review_changes_btn.invoke()
    assert harness.app.cancel_btn.cget("state") == "disabled"
    harness.wait_until(
        lambda: harness.results_tab.issues() == [] and not harness.review_runtime.is_review_changes_running(),
        message="restored session review changes did not finish",
    )

    assert len(verify_calls) == 1
    assert verify_calls[0][1] is backend
    assert backend.closed is True
    assert harness.review_runtime.current_runner() is None
    assert any(message == t("gui.results.all_fixed") and not error for message, error in harness.toasts)


def test_restored_session_ai_fix_recreates_backend_and_opens_preview(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App

    session_path = tmp_path / "session.json"
    session_data = {
        "format_version": 2,
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
        "report_context": {
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
    shown_popups: list[tuple[list[int], dict[int, Any]]] = []

    monkeypatch.setattr(App, "_session_path", property(lambda _self: session_path))

    harness = GuiTestHarness(app_factory())
    harness.enable_runtime_actions()
    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.filedialog.askopenfilename",
        lambda **_: str(session_path),
    )
    harness.app.load_session_btn.invoke()
    harness.pump()

    assert harness.results_tab.ai_fix_mode_button_state() == "normal"

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

    harness.results_tab.enter_ai_fix_mode()
    harness.pump()
    harness.results_tab.start_ai_fix()
    harness.wait_until(
        lambda: bool(shown_popups),
        message="restored session AI Fix did not produce preview results",
    )

    assert shown_popups[0][0] == [0]
    assert shown_popups[0][1][0]["content"] is not None
    assert backend.closed is True
    assert harness.results_tab.active_review_client() is None


def test_ai_fix_worker_surfaces_failed_fix_diagnostic_results(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FakeBackend()
    shown_popups: list[tuple[list[int], dict[int, Any]]] = []
    issue = ReviewIssue(
        file_path="src/missing_for_fix.py",
        line_number=9,
        issue_type="security",
        severity="high",
        description="Missing files should surface a structured diagnostic in AI Fix results.",
        ai_feedback="Regenerate the file safely.",
        status="pending",
    )

    harness.enable_runtime_actions()
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

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

    harness.results_tab.start_ai_fix()
    harness.wait_until(
        lambda: bool(shown_popups),
        message="AI Fix did not surface failed diagnostic results",
    )

    assert shown_popups[0][0] == [0]
    assert shown_popups[0][1][0]["content"] is None
    assert shown_popups[0][1][0]["status"] == "failed"
    assert shown_popups[0][1][0]["diagnostic"]["category"] == "configuration"
    assert shown_popups[0][1][0]["diagnostic"]["origin"] == "fix_generation"


def test_batch_fix_popup_surfaces_failed_item_diagnostic_details(
    harness: GuiTestHarness,
) -> None:
    issues = [
        ReviewIssue(
            file_path="src/diagnostic_ok.py",
            line_number=3,
            issue_type="security",
            severity="high",
            description="Successful fixes should still preview normally.",
            ai_feedback="Successful fix.",
            status="pending",
        ),
        ReviewIssue(
            file_path="src/diagnostic_fail.py",
            line_number=4,
            issue_type="performance",
            severity="medium",
            description="Failed fixes should show diagnostic detail in the popup.",
            ai_feedback="Failed fix.",
            status="pending",
        ),
    ]

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues(issues)
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup(
        {
            0: "safe_ok()\n",
            1: {
                "status": "failed",
                "content": None,
                "diagnostic": {
                    "category": "configuration",
                    "origin": "fix_generation",
                    "detail": "Fix generation disabled for this file.",
                    "fix_hint": "Check backend settings.",
                    "retryable": True,
                    "retry_delay_seconds": 5,
                },
            },
        }
    )
    harness.pump()

    popup = _latest_toplevel(harness.app)
    assert _find_widget_containing_text(popup, "diagnostic_fail.py")
    assert _find_widget_containing_text(
        popup,
        t("gui.results.batch_fix_failure_detail", category=t("gui.results.diagnostic_category_configuration"), detail="Fix generation disabled for this file."),
    )
    assert _find_widget_containing_text(
        popup,
        t("gui.results.batch_fix_failure_hint", hint="Check backend settings."),
    )
    assert _find_widget_containing_text(
        popup,
        t("gui.results.batch_fix_failure_retry_after", seconds=5),
    )


def test_batch_fix_popup_all_failed_toast_includes_diagnostic_summary(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/all_failed.py",
        line_number=7,
        issue_type="security",
        severity="high",
        description="All-failed AI Fix runs should surface failure details in the toast.",
        ai_feedback="Failed fix.",
        status="pending",
    )

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup(
        {
            0: {
                "status": "failed",
                "content": None,
                "diagnostic": {
                    "category": "configuration",
                    "origin": "fix_generation",
                    "detail": "Fix generation disabled for this file.",
                    "fix_hint": "Check backend settings.",
                },
            }
        }
    )
    harness.pump()

    assert any(
        message == (
            f"{t('gui.results.no_fix')} "
            f"{t('gui.results.batch_fix_failure_detail', category=t('gui.results.diagnostic_category_configuration'), detail='Fix generation disabled for this file.')}"
        ) and error
        for message, error in harness.toasts
    )


def test_popup_recovery_restores_unsaved_editor_draft(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App

    session_path = tmp_path / "session.json"
    popup_recovery_path = tmp_path / "popup-recovery.json"
    monkeypatch.setattr(App, "_session_path", property(lambda _self: session_path))

    first_harness = GuiTestHarness(app_factory())
    first_harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    first_harness.results_tab.show_issues(
        [
            ReviewIssue(
                file_path="src/restored_editor.py",
                line_number=2,
                issue_type="best_practices",
                severity="low",
                description="Unsaved editor drafts should survive restart.",
                ai_feedback="Keep the popup draft when the app is reopened.",
                status="pending",
                code_snippet="alpha = 1\nbeta = 2\n",
            )
        ]
    )
    first_harness.pump()

    first_harness.app._ensure_popup_surface_controller().recovery_store.save_active_popup(
        {
            "kind": "editor",
            "issue_index": 0,
            "file_path": "src/restored_editor.py",
            "display_name": "restored_editor.py",
            "line_number": 2,
            "content": "alpha = 1\nbeta = 2\ngamma = 3\n",
            "original_content": "alpha = 1\nbeta = 2\n",
            "cursor_index": "3.0",
            "read_only": False,
        }
    )

    assert popup_recovery_path.exists()

    recovery_payload = json.loads(popup_recovery_path.read_text(encoding="utf-8"))
    assert recovery_payload["active_popup"]["kind"] == "editor"
    assert "gamma = 3" in recovery_payload["active_popup"]["content"]

    first_harness.app.destroy()

    second_harness = GuiTestHarness(app_factory())
    second_harness.wait_until(
        lambda: second_harness.results_tab.issue_count() == 1,
        message="popup recovery did not restore the editor issue list",
    )

    restored_popup = _latest_toplevel(second_harness.app)
    restored_text = _find_normal_text_widget(restored_popup)
    assert "gamma = 3" in restored_text.get("1.0", "end-1c")
    assert any(
        message == t("gui.results.popup_recovery_restored") and not error
        for message, error in second_harness.toasts
    )


def test_popup_recovery_restores_staged_batch_fix_edits_and_selection(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App

    session_path = tmp_path / "session.json"
    popup_recovery_path = tmp_path / "popup-recovery.json"
    monkeypatch.setattr(App, "_session_path", property(lambda _self: session_path))

    edited_target = tmp_path / "restored_edited.py"
    deselected_target = tmp_path / "restored_deselected.py"
    edited_target.write_text("run(user_input)\n", encoding="utf-8")
    deselected_target.write_text("print('leave me')\n", encoding="utf-8")

    generated_fix = "safe_run(user_input)\n"
    edited_fix = "validated = sanitize(user_input)\nsafe_run(validated)\n"
    deselected_fix = "print('should stay unchanged')\n"

    first_harness = GuiTestHarness(app_factory())
    first_harness.enable_runtime_actions()
    first_harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    first_harness.results_tab.show_issues(
        [
            ReviewIssue(
                file_path=str(edited_target),
                line_number=1,
                issue_type="security",
                severity="high",
                description="Staged preview edits should survive restart.",
                ai_feedback="Sanitize user input before execution.",
                status="pending",
                code_snippet=edited_target.read_text(encoding="utf-8"),
            ),
            ReviewIssue(
                file_path=str(deselected_target),
                line_number=1,
                issue_type="documentation",
                severity="low",
                description="Unchecked fixes should remain unchecked after restore.",
                ai_feedback="Leave this file unchanged when deselected.",
                status="pending",
                code_snippet=deselected_target.read_text(encoding="utf-8"),
            ),
        ]
    )
    first_harness.results_tab.enter_ai_fix_mode()
    first_harness.pump()

    first_harness.results_tab.show_batch_fix_popup({0: generated_fix, 1: deselected_fix})
    first_harness.pump()

    batch_popup = _latest_toplevel(first_harness.app)
    monkeypatch.setattr(
        first_harness.app,
        "_open_builtin_editor",
        lambda idx, _initial_content=None, _on_save=None, **_kwargs: _on_save and _on_save(edited_fix),
    )

    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    first_harness.pump(2)

    preview_popup = _latest_toplevel(first_harness.app)
    edit_button = _find_widget_containing_text(preview_popup, "Edit")
    edit_button.invoke()
    first_harness.pump()

    save_and_close_button = _find_widget_containing_text(preview_popup, "Save and Close")
    save_and_close_button.invoke()
    first_harness.pump()

    deselected_checkbox = _find_widget_by_text(batch_popup, deselected_target.name)
    deselected_checkbox.deselect()
    first_harness.wait_until(
        lambda: popup_recovery_path.exists(),
        message="popup recovery file was not written for the batch fix popup",
    )

    recovery_payload = json.loads(popup_recovery_path.read_text(encoding="utf-8"))
    assert recovery_payload["active_popup"]["kind"] == "batch_fix"
    assert recovery_payload["active_popup"]["current_fixes"]["0"] == edited_fix
    assert recovery_payload["active_popup"]["enabled_issue_indexes"] == [0]

    first_harness.app.destroy()

    second_harness = GuiTestHarness(app_factory())
    second_harness.enable_runtime_actions()
    second_harness.wait_until(
        lambda: second_harness.results_tab.issue_count() == 2,
        message="popup recovery did not restore the batch fix issue list",
    )

    restored_popup = _latest_toplevel(second_harness.app)
    apply_button = _find_widget_by_text(restored_popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    second_harness.pump(3)

    restored_issues = second_harness.results_tab.issues()
    assert edited_target.read_text(encoding="utf-8") == edited_fix
    assert deselected_target.read_text(encoding="utf-8") == "print('leave me')\n"
    assert restored_issues[0].status == "resolved"
    assert restored_issues[0].resolution_provenance == "ai_edited"
    assert restored_issues[0].ai_fix_suggested == generated_fix
    assert restored_issues[0].ai_fix_applied == edited_fix
    assert restored_issues[1].status == "pending"
    assert restored_issues[1].resolution_provenance is None
    assert restored_issues[1].ai_fix_applied is None
    assert any(
        message == t("gui.results.popup_recovery_restored") and not error
        for message, error in second_harness.toasts
    )


def test_popup_recovery_rejects_issue_file_path_outside_workspace(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App

    session_path = tmp_path / "session.json"
    popup_recovery_path = tmp_path / "popup-recovery.json"
    monkeypatch.setattr(App, "_session_path", property(lambda _self: session_path))

    popup_recovery_path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "saved_at": "2026-04-06T00:00:00",
                "session_state": {
                    "format_version": 2,
                    "saved_at": "2026-04-06T00:00:00",
                    "issues": [
                        {
                            "file_path": str(tmp_path.parent / "outside.py"),
                            "issue_type": "security",
                            "description": "outside path",
                        }
                    ],
                    "report_context": None,
                },
                "active_popup": {
                    "kind": "editor",
                    "issue_index": 0,
                    "file_path": str(tmp_path.parent / "outside.py"),
                    "display_name": "outside.py",
                    "line_number": 1,
                    "content": "dangerous\n",
                    "original_content": "dangerous\n",
                    "cursor_index": "1.0",
                    "read_only": False,
                },
            }
        ),
        encoding="utf-8",
    )

    harness = GuiTestHarness(app_factory())
    harness.pump(2)

    assert harness.results_tab.issue_count() == 0
    assert not popup_recovery_path.exists()
    assert not any(
        message == t("gui.results.popup_recovery_restored") and not error
        for message, error in harness.toasts
    )


def test_restored_session_issue_detail_shows_resolution_provenance(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aicodereviewer.gui.app import App

    session_path = tmp_path / "session.json"
    session_data = {
        "format_version": 2,
        "saved_at": "2026-03-20T00:00:00",
        "issues": [
            {
                "file_path": "src/restored-detail.py",
                "line_number": 11,
                "issue_type": "security",
                "severity": "high",
                "description": "Restored session issue should keep provenance visible.",
                "code_snippet": "unsafe()\n",
                "ai_feedback": "Use a safe wrapper.",
                "status": "resolved",
                "resolution_reason": "Applied edited fix",
                "resolved_at": "2026-03-20T10:15:00",
                "resolution_provenance": "ai_edited",
                "ai_fix_suggested": "unsafe()\n",
                "ai_fix_applied": "safe()\n",
                "related_issues": [],
                "interaction_summary": None,
            }
        ],
        "report_context": {
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
    session_path.write_text(json.dumps(session_data), encoding="utf-8")

    monkeypatch.setattr(App, "_session_path", property(lambda _self: session_path))

    harness = GuiTestHarness(app_factory())
    harness.enable_runtime_actions()
    monkeypatch.setattr(
        "aicodereviewer.gui.results_mixin.filedialog.askopenfilename",
        lambda **_: str(session_path),
    )

    harness.app.load_session_btn.invoke()
    harness.pump()

    view_button = _find_widget_by_text(harness.app, t("gui.results.action_view"))
    view_button.invoke()
    harness.pump()

    popup = _latest_toplevel(harness.app)
    detail_text_widgets = [widget for widget in _walk_widgets(popup) if isinstance(widget, tk.Text)]
    assert detail_text_widgets
    detail_content = detail_text_widgets[0].get("1.0", "end-1c")

    expected_path_line = t(
        "gui.detail.resolution_path",
        resolution_path=t("gui.detail.provenance_ai_edited"),
    )
    assert expected_path_line in detail_content
    assert t("gui.detail.ai_fix_suggested") in detail_content
    assert "unsafe()" in detail_content
    assert t("gui.detail.ai_fix_applied") in detail_content
    assert "safe()" in detail_content


def test_large_file_editor_opens_read_only_with_truncation_message(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    target_file = tmp_path / "large_preview.py"
    target_file.write_text("print('x')\n" * 250000, encoding="utf-8")

    harness.enable_runtime_actions()
    harness.results_tab.show_issues(
        [
            ReviewIssue(
                file_path=str(target_file),
                line_number=1,
                issue_type="performance",
                severity="medium",
                description="Large files should load with guardrails.",
                ai_feedback="Do not try to keep the whole file editable in memory.",
                status="pending",
                code_snippet="print('x')\n",
            )
        ]
    )
    harness.pump()

    harness.app._open_builtin_editor(0)
    harness.wait_until(
        lambda: any(isinstance(widget, tk.Text) and str(widget.cget("state")) == "disabled" for widget in _walk_widgets(_latest_toplevel(harness.app))),
        message="large-file editor did not enter read-only mode",
    )

    editor_popup = _latest_toplevel(harness.app)
    save_button = _find_widget_by_text(editor_popup, t("gui.results.editor_save"))
    assert str(save_button.cget("state")) == "disabled"
    assert _find_widget_containing_text(editor_popup, target_file.name)


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

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues(issues)
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup(results)
    harness.pump()

    popup = _latest_toplevel(harness.app)
    second_checkbox = _find_widget_by_text(popup, Path(issues[1].file_path).name)
    second_checkbox.deselect()
    harness.pump()

    apply_button = _find_widget_by_text(popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert issues[0].status == "resolved"
    assert issues[0].resolution_provenance == "ai_applied"
    assert issues[0].ai_fix_suggested == results[0]
    assert issues[0].ai_fix_applied == results[0]
    assert issues[1].status == "pending"
    assert issues[1].resolution_provenance is None
    assert issues[1].ai_fix_applied is None
    assert harness.results_tab.is_ai_fix_mode_active() is False
    assert harness.results_tab.ai_fix_mode_button_visible() is True
    assert any(
        message == t("gui.results.batch_fix_applied", count=1) and not error
        for message, error in harness.toasts
    )


def test_log_tab_detach_and_redock_keeps_log_state_synced(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "detached-log.ini"
    _save_default_config_to_path(config_path)

    harness.app.tabs.set(t("gui.tab.log"))
    harness.pump()

    harness.app._log_queue.put((20, "main info"))
    harness.app._poll_log_queue()
    harness.pump()

    harness.app.detach_log_btn.invoke()
    harness.pump()

    detached = _latest_toplevel(harness.app)
    assert harness.app._detached_log_window == detached
    assert config.get("gui", "detached_pages", "") == "log"
    assert "main info" in harness.app._detached_log_box.get("0.0", "end")

    harness.app._log_queue.put((40, "detached error"))
    harness.app._poll_log_queue()
    harness.pump()

    assert "detached error" in harness.app.log_box.get("0.0", "end")
    assert "detached error" in harness.app._detached_log_box.get("0.0", "end")

    harness.app._detached_log_clear_btn.invoke()
    harness.pump()

    assert harness.app.log_box.get("0.0", "end").strip() == ""
    assert harness.app._detached_log_box.get("0.0", "end").strip() == ""

    harness.app._detached_log_redock_btn.invoke()
    harness.pump()

    assert harness.app._detached_log_window is None
    assert config.get("gui", "detached_pages", "") == ""
    assert harness.app.tabs.get() == t("gui.tab.log")


def test_settings_tab_detach_and_redock_preserves_unsaved_state(
    app_factory: Any,
    tmp_path: Path,
) -> None:
    original_config_path = config.config_path
    temporary_config_path = tmp_path / "detached-settings.ini"

    try:
        _save_default_config_to_path(temporary_config_path)

        settings_harness = GuiTestHarness(app_factory())
        settings_harness.app.tabs.set(t("gui.tab.settings"))
        settings_harness.pump()

        settings_harness.set_entry(settings_harness.app._setting_entries[("local_http", "port")], "8877")
        settings_harness.app._setting_entries[("processing", "combine_files")].set(False)

        settings_harness.app.detach_settings_btn.invoke()
        settings_harness.pump(2)

        assert settings_harness.app._detached_settings_window is not None
        assert config.get("gui", "detached_pages", "") == "settings"
        assert settings_harness.app._setting_entries[("local_http", "port")].get() == "8877"
        assert settings_harness.app._setting_entries[("processing", "combine_files")].get() is False

        settings_harness.set_entry(settings_harness.app._setting_entries[("local_http", "port")], "9001")
        settings_harness.app._setting_entries[("processing", "combine_files")].set(True)
        settings_harness.app._detached_settings_redock_btn.invoke()
        settings_harness.pump(2)

        assert settings_harness.app._detached_settings_window is None
        assert settings_harness.app.tabs.get() == t("gui.tab.settings")
        assert config.get("gui", "detached_pages", "") == ""
        assert settings_harness.app._setting_entries[("local_http", "port")].get() == "9001"
        assert settings_harness.app._setting_entries[("processing", "combine_files")].get() is True
    finally:
        _reset_config_to_path(original_config_path)


def test_benchmark_tab_detach_and_redock_preserves_loaded_state(
    app_factory: Any,
    tmp_path: Path,
) -> None:
    original_config_path = config.config_path
    temporary_config_path = tmp_path / "detached-benchmark.ini"

    try:
        _save_default_config_to_path(temporary_config_path)
        artifacts_root, summary_path, compare_path = _write_sample_benchmark_summaries(tmp_path)

        benchmark_harness = GuiTestHarness(app_factory())
        benchmark_harness.benchmark_tab.open()
        benchmark_harness.benchmark_tab.refresh_summary_selector(artifacts_root)
        benchmark_harness.benchmark_tab.load_summary(summary_path)
        benchmark_harness.benchmark_tab.compare_summary(compare_path)
        benchmark_harness.benchmark_tab.toggle_advanced_sources()
        benchmark_harness.benchmark_tab.select_fixture_filter(t("gui.benchmark.fixture_filter_shared"))
        benchmark_harness.benchmark_tab.select_fixture_sort(t("gui.benchmark.fixture_sort_status_churn"))
        benchmark_harness.benchmark_tab.preview_fixture_diff_reports("auth-jwt-bypass")

        primary_summary_text = benchmark_harness.benchmark_tab.primary_summary_text()
        compare_summary_text = benchmark_harness.benchmark_tab.compare_summary_text()
        preview_diff_text = benchmark_harness.benchmark_tab.preview_diff_text()

        benchmark_harness.app.detach_benchmark_btn.invoke()
        benchmark_harness.pump(2)

        assert benchmark_harness.app._detached_benchmark_window is not None
        assert config.get("gui", "detached_pages", "") == "benchmark"
        assert benchmark_harness.benchmark_tab.advanced_sources_visible() is True
        assert benchmark_harness.benchmark_tab.selected_fixture_filter() == t("gui.benchmark.fixture_filter_shared")
        assert benchmark_harness.benchmark_tab.selected_fixture_sort() == t("gui.benchmark.fixture_sort_status_churn")
        assert benchmark_harness.benchmark_tab.primary_summary_text() == primary_summary_text
        assert benchmark_harness.benchmark_tab.compare_summary_text() == compare_summary_text
        assert benchmark_harness.benchmark_tab.preview_diff_text() == preview_diff_text

        benchmark_harness.app._detached_benchmark_redock_btn.invoke()
        benchmark_harness.pump(2)

        assert benchmark_harness.app._detached_benchmark_window is None
        assert benchmark_harness.app.tabs.get() == t("gui.tab.benchmarks")
        assert config.get("gui", "detached_pages", "") == ""
        assert benchmark_harness.benchmark_tab.advanced_sources_visible() is True
        assert benchmark_harness.benchmark_tab.selected_fixture_filter() == t("gui.benchmark.fixture_filter_shared")
        assert benchmark_harness.benchmark_tab.selected_fixture_sort() == t("gui.benchmark.fixture_sort_status_churn")
        assert benchmark_harness.benchmark_tab.primary_summary_text() == primary_summary_text
        assert benchmark_harness.benchmark_tab.compare_summary_text() == compare_summary_text
        assert benchmark_harness.benchmark_tab.preview_diff_text() == preview_diff_text
    finally:
        _reset_config_to_path(original_config_path)


def test_detachable_pages_support_keyboard_shortcuts_for_open_and_redock(
    app_factory: Any,
    tmp_path: Path,
) -> None:
    original_config_path = config.config_path
    temporary_config_path = tmp_path / "detached-shortcuts.ini"

    try:
        _save_default_config_to_path(temporary_config_path)

        shortcut_harness = GuiTestHarness(app_factory())

        shortcut_harness.app.tabs.set(t("gui.tab.settings"))
        assert shortcut_harness.app._detach_current_page_shortcut() == "break"
        shortcut_harness.pump(2)

        assert shortcut_harness.app._detached_settings_window is not None

        shortcut_harness.app._detached_settings_redock_btn.invoke()
        shortcut_harness.pump(2)

        assert shortcut_harness.app._detached_settings_window is None

        shortcut_harness.app.tabs.set(t("gui.tab.log"))
        assert shortcut_harness.app._detach_current_page_shortcut() == "break"
        shortcut_harness.pump(2)

        assert shortcut_harness.app._detached_log_window is not None

        shortcut_harness.app._detached_log_redock_btn.invoke()
        shortcut_harness.pump(2)

        assert shortcut_harness.app._detached_log_window is None

        shortcut_harness.app.tabs.set(t("gui.tab.benchmarks"))
        assert shortcut_harness.app._detach_current_page_shortcut() == "break"
        shortcut_harness.pump(2)

        assert shortcut_harness.app._detached_benchmark_window is not None

        shortcut_harness.app._detached_benchmark_redock_btn.invoke()
        shortcut_harness.pump(2)

        assert shortcut_harness.app._detached_benchmark_window is None
    finally:
        _reset_config_to_path(original_config_path)


def test_log_tab_detached_window_restores_after_restart(
    app_factory: Any,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "detached-log-restore.ini"
    _save_default_config_to_path(config_path)

    first_app = app_factory()
    first_app.tabs.set(t("gui.tab.log"))
    first_app.update_idletasks()
    first_app.update()
    first_app.detach_log_btn.invoke()
    first_app.update_idletasks()
    first_app.update()

    assert config.get("gui", "detached_pages", "") == "log"
    assert first_app._detached_log_window is not None

    first_app.destroy()

    second_app = app_factory()
    second_app.update_idletasks()
    second_app.update()

    restored = _latest_toplevel(second_app)
    assert second_app._detached_log_window == restored
    assert second_app._detached_log_redock_btn.cget("text") == t("gui.log.redock")
    assert config.get("gui", "detached_pages", "") == "log"


def test_three_detached_pages_restore_after_restart(
    app_factory: Any,
    tmp_path: Path,
) -> None:
    original_config_path = config.config_path
    temporary_config_path = tmp_path / "detached-pages-restore.ini"

    try:
        _save_default_config_to_path(temporary_config_path)
        artifacts_root, summary_path, compare_path = _write_sample_benchmark_summaries(tmp_path)

        first_app = app_factory()
        first_app.tabs.set(t("gui.tab.log"))
        first_app.update_idletasks()
        first_app.update()
        first_app.detach_log_btn.invoke()
        first_app.tabs.set(t("gui.tab.settings"))
        first_app.update_idletasks()
        first_app.update()
        first_app.detach_settings_btn.invoke()
        first_app.tabs.set(t("gui.tab.benchmarks"))
        first_app.update_idletasks()
        first_app.update()
        first_app._refresh_benchmark_summary_selector(artifacts_root)
        first_app._load_benchmark_summary_artifact(summary_path)
        first_app._load_benchmark_summary_artifact(compare_path, compare=True)
        first_app.benchmark_fixture_filter_var.set(t("gui.benchmark.fixture_filter_shared"))
        first_app._on_fixture_diff_filter_selected(t("gui.benchmark.fixture_filter_shared"))
        first_app.benchmark_fixture_sort_var.set(t("gui.benchmark.fixture_sort_status_churn"))
        first_app._on_fixture_diff_sort_selected(t("gui.benchmark.fixture_sort_status_churn"))
        first_app.detach_benchmark_btn.invoke()
        first_app.update_idletasks()
        first_app.update()

        assert set(filter(None, config.get("gui", "detached_pages", "").split(","))) == {"benchmark", "log", "settings"}
        assert config.get("gui", "detached_log_geometry", "") != ""
        assert config.get("gui", "detached_settings_geometry", "") != ""
        assert config.get("gui", "detached_benchmark_geometry", "") != ""

        first_app.destroy()

        second_app = app_factory()
        second_app.update_idletasks()
        second_app.update()

        assert second_app._detached_log_window is not None
        assert second_app._detached_settings_window is not None
        assert second_app._detached_benchmark_window is not None
        assert len(_all_toplevels(second_app)) >= 3
        assert set(filter(None, config.get("gui", "detached_pages", "").split(","))) == {"benchmark", "log", "settings"}
        assert second_app.benchmark_artifacts_root_entry.get() == str(artifacts_root.resolve())
        assert second_app.benchmark_fixture_filter_var.get() == t("gui.benchmark.fixture_filter_shared")
        assert second_app.benchmark_fixture_sort_var.get() == t("gui.benchmark.fixture_sort_status_churn")

        second_app._detached_benchmark_redock_btn.invoke()
        second_app._detached_settings_redock_btn.invoke()
        second_app._detached_log_redock_btn.invoke()
        second_app.update_idletasks()
        second_app.update()

        assert config.get("gui", "detached_pages", "") == ""
    finally:
        _reset_config_to_path(original_config_path)


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

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    card = harness.results_tab.card(0)
    card["fix_checkbox"].deselect()
    harness.pump()

    harness.results_tab.start_ai_fix()
    harness.pump()

    assert harness.results_tab.is_ai_fix_running() is False
    assert harness.results_tab.ai_fix_runtime_running() is False
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

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup({0: generated_fix})
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
    assert issue.resolution_provenance == "ai_edited"
    assert issue.ai_fix_suggested == generated_fix
    assert issue.ai_fix_applied == edited_fix
    assert any(
        message == t("gui.results.batch_fix_applied", count=1) and not error
        for message, error in harness.toasts
    )


def test_builtin_editor_go_to_line_moves_cursor_to_requested_line(
    harness: GuiTestHarness,
) -> None:
    code_snippet = "".join(f"line_{line_number} = {line_number}\n" for line_number in range(1, 13))
    issue = ReviewIssue(
        file_path="src/goto_editor.py",
        line_number=2,
        issue_type="best_practices",
        severity="low",
        description="Go-to-line should move the editor cursor to the requested line.",
        ai_feedback="Navigate directly to the reported line.",
        status="pending",
        code_snippet=code_snippet,
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._open_builtin_editor(0)
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    entries = _find_ctk_entries(editor_popup)
    assert entries

    goto_entry = entries[0]
    goto_entry.delete(0, "end")
    goto_entry.insert(0, "7")

    go_button = _find_widget_by_text(editor_popup, t("gui.results.editor_go"))
    go_button.invoke()
    harness.pump()

    editor_text = _find_normal_text_widget(editor_popup)
    assert editor_text.index("insert").startswith("7.")


def test_builtin_editor_json_fallback_highlights_keys_literals_and_language(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="config/settings.json",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="JSON files should get fallback syntax highlighting in the popup editor.",
        ai_feedback="Use a readable fallback highlighter for config files.",
        status="pending",
        code_snippet='{"enabled": true, "retries": 3, "name": "demo"}\n',
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._open_builtin_editor(0)
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    editor_text = _find_normal_text_widget(editor_popup)

    assert editor_text.tag_ranges("property")
    assert editor_text.tag_ranges("keyword")
    assert editor_text.tag_ranges("number")
    assert _find_widget_by_text(editor_popup, "JSON")


def test_builtin_editor_typescript_fallback_highlights_keywords_comments_and_language(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/widget.ts",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="TypeScript files should get fallback syntax highlighting in the popup editor.",
        ai_feedback="Use a readable fallback highlighter for script files.",
        status="pending",
        code_snippet="const count = 3;\n// keep this in sync\nexport function render(): string {\n    return `count:${count}`\n}\n",
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._open_builtin_editor(0)
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    editor_text = _find_normal_text_widget(editor_popup)

    assert editor_text.tag_ranges("keyword")
    assert editor_text.tag_ranges("comment")
    assert editor_text.tag_ranges("number")
    assert editor_text.tag_ranges("string")
    assert _find_widget_by_text(editor_popup, "TypeScript")


def test_builtin_editor_replace_and_match_navigation_updates_content_and_cursor(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/search_replace.py",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="The built-in editor should support replace and next/previous match navigation.",
        ai_feedback="Let users update repeated terms without leaving the popup.",
        status="pending",
        code_snippet="alpha target\nbeta target\ngamma target\n",
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._open_builtin_editor(0)
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    replace_toolbar_button = _find_widget_by_text(editor_popup, t("gui.results.editor_replace"))
    replace_toolbar_button.invoke()
    harness.pump()

    entries = _find_ctk_entries(editor_popup)
    assert len(entries) >= 3
    find_entry = entries[1]
    replace_entry = entries[2]
    find_entry.delete(0, "end")
    find_entry.insert(0, "target")
    replace_entry.delete(0, "end")
    replace_entry.insert(0, "updated")
    harness.pump()

    editor_text = _find_normal_text_widget(editor_popup)
    assert editor_text.index("insert").startswith("1.")

    next_match_button = _find_widget_by_text(editor_popup, t("gui.results.editor_next_match"))
    prev_match_button = _find_widget_by_text(editor_popup, t("gui.results.editor_prev_match"))
    next_match_button.invoke()
    harness.pump()
    assert editor_text.index("insert").startswith("2.")

    prev_match_button.invoke()
    harness.pump()
    assert editor_text.index("insert").startswith("1.")

    replace_action_button = [
        widget
        for widget in _find_all_widgets_by_text(editor_popup, t("gui.results.editor_replace_one"))
        if hasattr(widget, "invoke")
    ][1]
    replace_action_button.invoke()
    harness.pump()

    assert "alpha updated" in editor_text.get("1.0", "end-1c")


def test_builtin_editor_bookmarks_navigate_between_marked_lines(
    harness: GuiTestHarness,
) -> None:
    code_snippet = "".join(f"line_{line_number}\n" for line_number in range(1, 10))
    issue = ReviewIssue(
        file_path="src/bookmarks.py",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="Bookmarks should support line-oriented review workflows.",
        ai_feedback="Let users hop between marked lines in the popup editor.",
        status="pending",
        code_snippet=code_snippet,
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._open_builtin_editor(0)
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    editor_text = _find_normal_text_widget(editor_popup)
    toggle_bookmark_button = _find_widget_by_text(editor_popup, t("gui.results.editor_toggle_bookmark"))
    next_bookmark_button = _find_widget_by_text(editor_popup, t("gui.results.editor_next_bookmark"))
    prev_bookmark_button = _find_widget_by_text(editor_popup, t("gui.results.editor_prev_bookmark"))

    editor_text.mark_set("insert", "3.0")
    toggle_bookmark_button.invoke()
    harness.pump()

    editor_text.mark_set("insert", "7.0")
    toggle_bookmark_button.invoke()
    harness.pump()

    editor_text.mark_set("insert", "1.0")
    next_bookmark_button.invoke()
    harness.pump()
    assert editor_text.index("insert").startswith("3.")

    next_bookmark_button.invoke()
    harness.pump()
    assert editor_text.index("insert").startswith("7.")

    prev_bookmark_button.invoke()
    harness.pump()
    assert editor_text.index("insert").startswith("3.")


def test_builtin_editor_sections_populate_symbol_menu_and_support_folding(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/sections.py",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="The built-in editor should expose sections and folding for line-oriented review.",
        ai_feedback="Give reviewers lightweight structure without requiring a language server.",
        status="pending",
        code_snippet="def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n",
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._open_builtin_editor(0)
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    editor_text = _find_normal_text_widget(editor_popup)
    fold_button = _find_widget_by_text(editor_popup, t("gui.results.editor_fold_section"))
    symbol_menu = next(
        widget
        for widget in _walk_widgets(editor_popup)
        if widget.__class__.__name__ == "CTkOptionMenu"
    )

    assert str(symbol_menu.cget("state")) == "normal"
    assert symbol_menu.cget("values") == ["L1: alpha", "L5: beta"]

    editor_text.mark_set("insert", "1.0")
    fold_button.invoke()
    harness.pump()

    assert editor_text.tag_ranges("folded_section")

    editor_popup.destroy()
    harness.pump()


def test_builtin_editor_section_picker_jumps_to_selected_section(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/sections.py",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="The built-in editor should move to the selected section.",
        ai_feedback="Drive the section picker through the popup widget path.",
        status="pending",
        code_snippet="def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n",
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._open_builtin_editor(0)
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    editor_text = _find_normal_text_widget(editor_popup)
    symbol_menu = next(
        widget
        for widget in _walk_widgets(editor_popup)
        if widget.__class__.__name__ == "CTkOptionMenu"
    )

    symbol_menu._dropdown_callback("L5: beta")
    harness.pump()

    assert editor_text.index("insert").startswith("5.")

    editor_popup.destroy()
    harness.pump()


def test_builtin_editor_tabbed_navigation_switches_between_working_copy_and_reference(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/tabbed_sections.py",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="The built-in editor should expose a working tab and a read-only reference tab.",
        ai_feedback="Let reviewers switch between the draft and the original snippet without opening another popup.",
        status="pending",
        code_snippet="def reference_example():\n    return 'reference'\n",
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._ensure_popup_surface_controller().open_builtin_editor(
        0,
        issue,
        initial_content="def working_example():\n    return 'working'\n",
    )
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    editor_text = _find_normal_text_widget(editor_popup)
    working_tab = _find_invokable_widget_containing_text(editor_popup, t("gui.results.editor_buffer_working"))
    reference_tab = _find_invokable_widget_containing_text(editor_popup, t("gui.results.editor_buffer_reference"))
    save_button = _find_widget_by_text(editor_popup, t("gui.results.editor_save"))

    assert "working_example" in editor_text.get("1.0", "end-1c")
    assert str(save_button.cget("state")) == "normal"

    reference_tab.invoke()
    harness.pump()

    assert "reference_example" in editor_text.get("1.0", "end-1c")
    assert str(editor_text.cget("state")) == "disabled"
    assert str(save_button.cget("state")) == "disabled"

    working_tab.invoke()
    harness.pump()

    assert "working_example" in editor_text.get("1.0", "end-1c")
    assert str(editor_text.cget("state")) == "normal"
    assert str(save_button.cget("state")) == "normal"

    editor_popup.destroy()
    harness.pump()


def test_builtin_editor_supports_keyboard_tab_switching_and_status_summary(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/tabbed_keyboard.py",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="Keyboard-first tab switching should work without leaving the editor flow.",
        ai_feedback="Let reviewers cycle buffers and keep active buffer state visible in the status bar.",
        status="pending",
        code_snippet="def reference_keyboard():\n    return 'reference'\n",
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._ensure_popup_surface_controller().open_builtin_editor(
        0,
        issue,
        initial_content="def working_keyboard():\n    return 'working'\n",
    )
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    editor_text = _find_normal_text_widget(editor_popup)
    toggle_bookmark_button = _find_widget_by_text(editor_popup, t("gui.results.editor_toggle_bookmark"))
    fold_button = _find_widget_by_text(editor_popup, t("gui.results.editor_fold_section"))
    status_label = editor_popup._acr_buffer_status_label

    editor_text.focus_set()
    editor_text.mark_set("insert", "1.0")
    toggle_bookmark_button.invoke()
    harness.pump()
    fold_button.invoke()
    harness.pump()
    editor_text.insert("1.0", "# draft\n")
    editor_text.event_generate("<KeyRelease>")
    harness.pump()

    assert str(status_label.cget("text")) == (
        f"{t('gui.results.editor_buffer_working')}  ·  {t('gui.results.editor_status_dirty')}"
        f"  ·  {t('gui.results.editor_status_bookmarks', count=1)}"
        f"  ·  {t('gui.results.editor_status_folds', count=1)}"
    )

    editor_text.event_generate("<Control-Tab>")
    harness.pump()

    assert "reference_keyboard" in editor_text.get("1.0", "end-1c")
    assert str(status_label.cget("text")) == f"{t('gui.results.editor_buffer_reference')}  ·  {t('gui.results.editor_status_read_only')}"

    editor_text.event_generate("<Control-Key-1>")
    harness.pump()

    assert "working_keyboard" in editor_text.get("1.0", "end-1c")
    assert str(status_label.cget("text")) == (
        f"{t('gui.results.editor_buffer_working')}  ·  {t('gui.results.editor_status_dirty')}"
        f"  ·  {t('gui.results.editor_status_bookmarks', count=1)}"
        f"  ·  {t('gui.results.editor_status_folds', count=1)}"
    )

    editor_text.event_generate("<Control-Key-2>")
    harness.pump()

    assert "reference_keyboard" in editor_text.get("1.0", "end-1c")

    editor_text.event_generate("<Control-Shift-Tab>")
    harness.pump()

    assert "working_keyboard" in editor_text.get("1.0", "end-1c")

    editor_popup.destroy()
    harness.pump()


def test_builtin_editor_tab_strip_surfaces_dirty_bookmark_and_fold_indicators_per_buffer(
    harness: GuiTestHarness,
) -> None:
    issue = ReviewIssue(
        file_path="src/tab_badges.py",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="The tab strip should surface buffer-local reviewer state.",
        ai_feedback="Show which tab is dirty and which buffers carry bookmarks or folded sections.",
        status="pending",
        code_snippet="def reference_section():\n    return 'reference'\n",
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._ensure_popup_surface_controller().open_builtin_editor(
        0,
        issue,
        initial_content="def working_section():\n    return 'working'\n",
    )
    harness.pump()

    editor_popup = _latest_toplevel(harness.app)
    editor_text = _find_normal_text_widget(editor_popup)
    toggle_bookmark_button = _find_widget_by_text(editor_popup, t("gui.results.editor_toggle_bookmark"))
    fold_button = _find_widget_by_text(editor_popup, t("gui.results.editor_fold_section"))
    working_tab = _find_invokable_widget_containing_text(editor_popup, t("gui.results.editor_buffer_working"))
    reference_tab = _find_invokable_widget_containing_text(editor_popup, t("gui.results.editor_buffer_reference"))

    editor_text.mark_set("insert", "1.0")
    toggle_bookmark_button.invoke()
    harness.pump()
    fold_button.invoke()
    harness.pump()
    editor_text.insert("1.0", "# draft\n")

    reference_tab.invoke()
    harness.pump()

    working_markers = working_tab._acr_tab_markers
    reference_markers = reference_tab._acr_tab_markers

    assert str(working_tab.cget("text")) == t("gui.results.editor_buffer_working")
    assert str(reference_tab.cget("text")) == t("gui.results.editor_buffer_reference")
    assert int(working_tab.cget("border_width")) == 1
    assert str(working_markers["dirty"].cget("text")) == "*"
    assert str(working_markers["bookmarks"].cget("text")) == "B1"
    assert str(working_markers["folds"].cget("text")) == "F1"
    assert working_markers["dirty"].winfo_manager() == "pack"
    assert working_markers["bookmarks"].winfo_manager() == "pack"
    assert working_markers["folds"].winfo_manager() == "pack"
    assert working_markers["dirty"].cget("text_color") == ("#9a3412", "#fb923c")
    assert working_markers["bookmarks"].cget("text_color") == ("#1d4ed8", "#60a5fa")
    assert working_markers["folds"].cget("text_color") == ("#0f766e", "#2dd4bf")
    assert t("gui.results.editor_tab_dirty") in str(working_tab._acr_tooltip.text)
    assert t("gui.results.editor_tab_bookmarks", count=1) in str(working_tab._acr_tooltip.text)
    assert t("gui.results.editor_tab_folds", count=1) in str(working_tab._acr_tooltip.text)

    toggle_bookmark_button.invoke()
    harness.pump()
    fold_button.invoke()
    harness.pump()

    assert str(working_tab.cget("text")) == t("gui.results.editor_buffer_working")
    assert str(reference_tab.cget("text")) == t("gui.results.editor_buffer_reference")
    assert int(reference_tab.cget("border_width")) == 1
    assert working_markers["dirty"].winfo_manager() == "pack"
    assert reference_markers["dirty"].winfo_manager() == ""
    assert str(reference_markers["bookmarks"].cget("text")) == "B1"
    assert str(reference_markers["folds"].cget("text")) == "F1"
    assert reference_markers["bookmarks"].winfo_manager() == "pack"
    assert reference_markers["folds"].winfo_manager() == "pack"
    assert reference_markers["bookmarks"].cget("text_color") == ("#2563eb", "#93c5fd")
    assert reference_markers["folds"].cget("text_color") == ("#0f766e", "#5eead4")
    assert t("gui.results.editor_tab_reference") in str(reference_tab._acr_tooltip.text)
    assert t("gui.results.editor_tab_bookmarks", count=1) in str(reference_tab._acr_tooltip.text)
    assert t("gui.results.editor_tab_folds", count=1) in str(reference_tab._acr_tooltip.text)

    editor_popup.destroy()
    harness.pump()


def test_builtin_editor_surfaces_addon_diagnostics_and_emits_hook_events(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffer_events: list[str] = []
    patch_events: list[dict[str, Any]] = []

    monkeypatch.setattr(
        "aicodereviewer.gui.popup_surfaces.emit_addon_editor_buffer_event",
        lambda event_name, payload: buffer_events.append(event_name),
    )
    monkeypatch.setattr(
        "aicodereviewer.gui.popup_surfaces.collect_addon_editor_diagnostics",
        lambda payload: (
            AddonEditorDiagnostic(
                addon_id="demo-addon",
                message="TODO marker present",
                severity="warning",
            ),
        )
        if "TODO" in payload.get("content", "")
        else (),
    )
    monkeypatch.setattr(
        "aicodereviewer.gui.popup_surfaces.emit_addon_patch_applied_event",
        lambda payload: patch_events.append(payload),
    )

    issue = ReviewIssue(
        file_path="src/addon_hooks.py",
        line_number=1,
        issue_type="best_practices",
        severity="low",
        description="Addon editor hooks should surface diagnostics and receive lifecycle events.",
        ai_feedback="Expose popup editor state through a stable addon hook contract.",
        status="pending",
        code_snippet="TODO = True\nprint(TODO)\n",
    )

    harness.results_tab.show_issues([issue])
    harness.pump()

    harness.app._open_builtin_editor(0)
    harness.pump(6)

    editor_popup = _latest_toplevel(harness.app)
    save_button = _find_widget_by_text(editor_popup, t("gui.results.editor_save"))

    assert "buffer_opened" in buffer_events
    assert _find_widget_containing_text(editor_popup, "TODO marker present")

    save_button.invoke()
    harness.pump()

    assert patch_events
    assert patch_events[0]["source"] == "editor_save"
    assert patch_events[0]["file_path"] == "src/addon_hooks.py"
    assert "buffer_saved" in buffer_events


def test_diff_preview_emits_preview_events_and_surfaces_addon_diagnostics(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted_events: list[tuple[str, dict[str, Any]]] = []
    harness.app._ensure_popup_surface_controller().recovery_store.clear()

    monkeypatch.setattr(
        "aicodereviewer.gui.popup_surfaces.emit_addon_editor_event",
        lambda event_name, payload: emitted_events.append((event_name, payload)),
    )
    monkeypatch.setattr(
        "aicodereviewer.gui.popup_surfaces.collect_addon_editor_diagnostics",
        lambda payload: (
            AddonEditorDiagnostic(
                addon_id="preview-addon",
                message="Preview contains staged edits",
                severity="info",
            ),
        )
        if payload.get("surface") == "diff_preview"
        else (),
    )

    issue = ReviewIssue(
        file_path="src/preview_hooks.py",
        line_number=1,
        issue_type="security",
        severity="high",
        description="Diff preview hook events should reflect staged-review actions.",
        ai_feedback="Track preview opens, navigation, and staged edits.",
        status="pending",
        code_snippet="run(user_input)\n",
    )
    generated_fix = "safe_run(user_input)\nextra_context()\n"
    edited_fix = "validated = sanitize(user_input)\nsafe_run(validated)\n"

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup({0: generated_fix})
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    monkeypatch.setattr(
        harness.app,
        "_open_builtin_editor",
        lambda idx, _initial_content=None, _on_save=None, **_kwargs: _on_save and _on_save(edited_fix),
    )

    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump(4)

    preview_popup = _latest_toplevel(harness.app)
    assert _find_widget_containing_text(preview_popup, "Preview contains staged edits")
    assert any(event_name == "staged_preview_opened" for event_name, _payload in emitted_events)

    next_button = _find_widget_by_text(preview_popup, t("gui.results.diff_next_change"))
    next_button.invoke()
    harness.pump()
    assert any(event_name == "change_navigation" for event_name, _payload in emitted_events)

    edit_button = _find_widget_containing_text(preview_popup, "Edit")
    edit_button.invoke()
    harness.pump()

    save_and_close_button = _find_widget_containing_text(preview_popup, "Save and Close")
    save_and_close_button.invoke()
    harness.pump()

    staged_payloads = [payload for event_name, payload in emitted_events if event_name == "preview_staged"]
    assert staged_payloads
    assert staged_payloads[-1]["edited"] is True
    assert staged_payloads[-1]["surface"] == "diff_preview"

    cancel_button = _find_widget_by_text(batch_popup, t("common.cancel"))
    cancel_button.invoke()
    harness.pump()
    harness.app._ensure_popup_surface_controller().recovery_store.clear()


def test_large_file_editor_uses_paged_read_only_navigation(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    target_file = tmp_path / "paged_large_file.txt"
    page_one_bytes = b"PAGE1\n" + (b"a" * (LARGE_FILE_PAGE_BYTES - len(b"PAGE1\n")))
    page_two_bytes = b"PAGE2\nrest of file\n"
    target_file.write_bytes(page_one_bytes + page_two_bytes)

    harness.enable_runtime_actions()
    harness.results_tab.show_issues(
        [
            ReviewIssue(
                file_path=str(target_file),
                line_number=1,
                issue_type="performance",
                severity="medium",
                description="Large files should page through read-only chunks in the editor.",
                ai_feedback="Make oversized files navigable instead of showing only the first chunk.",
                status="pending",
                code_snippet="PAGE1\n",
            )
        ]
    )
    harness.pump()

    harness.app._open_builtin_editor(0)

    harness.wait_until(
        lambda: any(
            isinstance(widget, tk.Text)
            and str(widget.cget("state")) == "disabled"
            and widget.get("1.0", "1.5") == "PAGE1"
            for widget in _walk_widgets(_latest_toplevel(harness.app))
        ),
        message="large-file first page did not load in read-only mode",
    )

    editor_popup = _latest_toplevel(harness.app)
    editor_text = next(
        widget
        for widget in _walk_widgets(editor_popup)
        if isinstance(widget, tk.Text)
        and str(widget.cget("state")) == "disabled"
        and widget.get("1.0", "1.5") == "PAGE1"
    )
    save_button = _find_widget_by_text(editor_popup, t("gui.results.editor_save"))
    next_page_button = _find_widget_by_text(editor_popup, t("gui.results.editor_next_page"))

    assert editor_text.get("1.0", "1.5") == "PAGE1"
    assert str(save_button.cget("state")) == "disabled"

    next_page_button.invoke()
    harness.wait_until(
        lambda: editor_text.get("1.0", "1.5") == "PAGE2",
        message="large-file next-page navigation did not load the second page",
    )
    assert _find_widget_containing_text(
        editor_popup,
        t("gui.results.editor_page_status", current=2, total=2),
    )


def test_diff_preview_change_navigation_updates_change_counter(
    harness: GuiTestHarness,
) -> None:
    original = "".join(
        [
            "alpha\n",
            "danger()\n",
            "charlie\n",
            "delta\n",
            "echo\n",
            "foxtrot\n",
            "golf\n",
            "hotel\n",
            "slow()\n",
            "juliet\n",
        ]
    )
    generated_fix = "".join(
        [
            "alpha\n",
            "safe_danger()\n",
            "charlie\n",
            "delta\n",
            "echo\n",
            "foxtrot\n",
            "golf\n",
            "hotel\n",
            "fast()\n",
            "juliet\n",
        ]
    )
    issue = ReviewIssue(
        file_path="src/diff_navigation.py",
        line_number=2,
        issue_type="security",
        severity="high",
        description="Diff preview should navigate between changes.",
        ai_feedback="Review the generated patch in order.",
        status="pending",
        code_snippet=original,
    )

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup({0: generated_fix})
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump(3)

    preview_popup = _latest_toplevel(harness.app)
    next_button = _find_widget_by_text(preview_popup, t("gui.results.diff_next_change"))
    next_button.invoke()
    harness.pump()

    assert _find_widget_containing_text(preview_popup, "1 / 2")

    next_button.invoke()
    harness.pump()

    assert _find_widget_containing_text(preview_popup, "2 / 2")


def test_diff_preview_supports_keyboard_pane_switching_and_numeric_jumps(
    harness: GuiTestHarness,
) -> None:
    original = "alpha\nlegacy_call()\nomega\n"
    generated_fix = "alpha\nsafe_call()\nomega\n"
    issue = ReviewIssue(
        file_path="src/diff_pane_navigation.py",
        line_number=2,
        issue_type="security",
        severity="high",
        description="Diff preview panes should support keyboard-first navigation.",
        ai_feedback="Cycle and jump between compare panes without reaching for the mouse.",
        status="pending",
        code_snippet=original,
    )

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup({0: generated_fix})
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump(3)

    preview_popup = _latest_toplevel(harness.app)
    preview_panes = preview_popup._acr_preview_panes
    original_pane = next(pane for pane in preview_panes if pane["name"] == "original")
    fixed_pane = next(pane for pane in preview_panes if pane["name"] == "fixed")

    assert preview_popup._acr_preview_active_pane == "original"

    original_pane["text"].event_generate("<Control-Tab>")
    harness.pump()

    assert preview_popup._acr_preview_active_pane == "fixed"
    assert str(fixed_pane["label"].cget("bg")) != str(original_pane["label"].cget("bg"))

    fixed_pane["text"].event_generate("<Control-Key-1>")
    harness.pump()

    assert preview_popup._acr_preview_active_pane == "original"

    close_button = _find_widget_by_text(preview_popup, t("common.close"))
    close_button.invoke()
    harness.pump()
    cancel_button = _find_widget_by_text(batch_popup, t("common.cancel"))
    cancel_button.invoke()
    harness.pump()


def test_diff_preview_surfaces_active_pane_status_text(
    harness: GuiTestHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = "alpha\nlegacy_call()\nomega\n"
    generated_fix = "alpha\nsafe_call()\nomega\n"
    edited_fix = "alpha\nvalidated_call()\nomega\n"
    issue = ReviewIssue(
        file_path="src/diff_status.py",
        line_number=2,
        issue_type="security",
        severity="high",
        description="Diff preview should keep the active pane context visible in status text.",
        ai_feedback="Mirror editor-style status context for pane-focused keyboard review.",
        status="pending",
        code_snippet=original,
    )

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup({0: generated_fix})
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    monkeypatch.setattr(
        harness.app,
        "_open_builtin_editor",
        lambda idx, _initial_content=None, _on_save=None, **_kwargs: _on_save and _on_save(edited_fix),
    )

    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump(3)

    preview_popup = _latest_toplevel(harness.app)
    status_label = preview_popup._acr_preview_status_label
    preview_panes = preview_popup._acr_preview_panes
    original_pane = next(pane for pane in preview_panes if pane["name"] == "original")
    fixed_pane = next(pane for pane in preview_panes if pane["name"] == "fixed")

    assert str(status_label.cget("text")) == (
        f"{t('gui.results.diff_pane_original')}  ·  {t('gui.results.diff_status_change', current=1, total=1)}"
    )

    original_pane["text"].event_generate("<Control-Tab>")
    harness.pump()

    assert preview_popup._acr_preview_active_pane == "fixed"
    assert str(status_label.cget("text")) == (
        f"{t('gui.results.diff_pane_fixed')}  ·  {t('gui.results.diff_status_change', current=1, total=1)}"
    )

    edit_button = _find_widget_containing_text(preview_popup, "Edit")
    edit_button.invoke()
    harness.pump(2)

    fixed_pane["text"].event_generate("<Control-Key-3>")
    harness.pump()

    assert preview_popup._acr_preview_active_pane == "user_fixed"
    assert str(status_label.cget("text")) == (
        f"{t('gui.results.diff_pane_user_fixed')}  ·  {t('gui.results.diff_status_change', current=1, total=1)}"
    )

    save_and_close_button = _find_widget_containing_text(preview_popup, "Save and Close")
    save_and_close_button.invoke()
    harness.pump()

    cancel_button = _find_widget_by_text(batch_popup, t("common.cancel"))
    cancel_button.invoke()
    harness.pump()


def test_batch_fix_popup_supports_keyboard_issue_jumps_and_status_text(
    harness: GuiTestHarness,
) -> None:
    issues = [
        ReviewIssue(
            file_path="src/batch_jump_one.py",
            line_number=1,
            issue_type="security",
            severity="high",
            description="First generated fix participates in popup issue jumps.",
            ai_feedback="First fix.",
            status="pending",
        ),
        ReviewIssue(
            file_path="src/batch_jump_two.py",
            line_number=1,
            issue_type="performance",
            severity="medium",
            description="Second generated fix should become the active issue via numeric shortcuts.",
            ai_feedback="Second fix.",
            status="pending",
        ),
        ReviewIssue(
            file_path="src/batch_jump_three.py",
            line_number=1,
            issue_type="documentation",
            severity="low",
            description="Third generated fix should still be reachable by sequential issue cycling.",
            ai_feedback="Third fix.",
            status="pending",
        ),
    ]

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues(issues)
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup(
        {
            0: "safe_first()\n",
            1: "safe_second()\n",
            2: "safe_third()\n",
        }
    )
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    status_label = batch_popup._acr_batch_fix_status_label

    assert batch_popup._acr_batch_fix_active_issue == 0
    assert str(status_label.cget("text")) == (
        f"{t('gui.results.batch_fix_status_issue', current=1, total=3)}  ·  batch_jump_one.py"
    )

    batch_popup.event_generate("<Control-Key-2>")
    harness.pump()

    assert batch_popup._acr_batch_fix_active_issue == 1
    assert str(status_label.cget("text")) == (
        f"{t('gui.results.batch_fix_status_issue', current=2, total=3)}  ·  batch_jump_two.py"
    )

    second_checkbox = _find_widget_by_text(batch_popup, "batch_jump_two.py")
    second_checkbox.deselect()
    harness.pump()

    assert str(status_label.cget("text")) == (
        f"{t('gui.results.batch_fix_status_issue', current=2, total=3)}  ·  batch_jump_two.py"
        f"  ·  {t('gui.results.batch_fix_status_disabled')}"
    )

    batch_popup.event_generate("<Control-Tab>")
    harness.pump()

    assert batch_popup._acr_batch_fix_active_issue == 2
    assert str(status_label.cget("text")) == (
        f"{t('gui.results.batch_fix_status_issue', current=3, total=3)}  ·  batch_jump_three.py"
    )

    cancel_button = _find_widget_by_text(batch_popup, t("common.cancel"))
    cancel_button.invoke()
    harness.pump()


def test_diff_preview_pages_large_compare_sessions_instead_of_partial_only(
    harness: GuiTestHarness,
    tmp_path: Path,
) -> None:
    target_file = tmp_path / "paged_diff_preview.txt"
    original_page_one = b"ORIG1\n" + (b"a" * (LARGE_FILE_PAGE_BYTES - len(b"ORIG1\n")))
    original_page_two = b"ORIG2\nrest of original\n"
    target_file.write_bytes(original_page_one + original_page_two)

    generated_fix = (
        ("FIX1\n" + ("b" * (LARGE_FILE_PAGE_BYTES - len("FIX1\n".encode("utf-8")))))
        + "FIX2\nrest of fix\n"
    )
    issue = ReviewIssue(
        file_path=str(target_file),
        line_number=1,
        issue_type="performance",
        severity="medium",
        description="Large compare sessions should page through the diff preview.",
        ai_feedback="Avoid collapsing oversized previews to the first chunk only.",
        status="pending",
        code_snippet="ORIG1\n",
    )

    harness.enable_runtime_actions()
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup({0: generated_fix})
    harness.pump()

    batch_popup = _latest_toplevel(harness.app)
    preview_button = _find_widget_by_text(batch_popup, t("gui.results.preview_changes"))
    preview_button.invoke()
    harness.pump(3)

    preview_popup = _latest_toplevel(harness.app)
    next_page_button = _find_widget_by_text(preview_popup, t("gui.results.editor_next_page"))
    edit_button = _find_widget_containing_text(preview_popup, "Edit")

    assert str(edit_button.cget("state")) == "normal"
    assert _find_widget_containing_text(
        preview_popup,
        t("gui.results.diff_page_status", current=1, total=2),
    )

    next_page_button.invoke()
    harness.wait_until(
        lambda: any(
            isinstance(widget, tk.Text)
            and str(widget.cget("state")) == "disabled"
            and widget.get("1.0", "1.5") in {"ORIG2", "FIX2"}
            for widget in _walk_widgets(preview_popup)
        ),
        message="diff preview next-page navigation did not load the second page",
    )

    assert _find_widget_containing_text(
        preview_popup,
        t("gui.results.diff_page_status", current=2, total=2),
    )
    assert _find_widget_containing_text(
        preview_popup,
        t("gui.results.large_file_preview_paged", file=target_file.name, current=2, total=2),
    )

    close_button = _find_widget_by_text(preview_popup, t("common.close"))
    close_button.invoke()
    harness.pump()
    cancel_button = _find_widget_by_text(batch_popup, t("common.cancel"))
    cancel_button.invoke()
    harness.pump()


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

    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup({0: generated_fix})
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
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup({0: generated_fix})
    harness.pump()

    popup = _latest_toplevel(harness.app)
    apply_button = _find_widget_by_text(popup, t("gui.results.apply_fixes"))
    apply_button.invoke()
    harness.pump(3)

    assert target_file.read_text(encoding="utf-8") == generated_fix
    assert issue.status == "resolved"
    assert issue.ai_fix_applied == generated_fix
    assert harness.results_tab.is_ai_fix_mode_active() is False
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
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues([issue])
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup({0: generated_fix})
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
    assert harness.results_tab.is_ai_fix_mode_active() is False
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
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues(issues)
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup(
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
    assert harness.results_tab.is_ai_fix_mode_active() is False
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
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues(issues)
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup(
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
    assert harness.results_tab.is_ai_fix_mode_active() is False
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
    harness.app._bind_session_runner(_runner_with_report_context({"backend": "local"}))
    harness.results_tab.show_issues(issues)
    harness.results_tab.enter_ai_fix_mode()
    harness.pump()

    harness.results_tab.show_batch_fix_popup(
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
    assert harness.results_tab.is_ai_fix_mode_active() is False
    assert any(
        message == t("gui.results.batch_fix_applied", count=1) and not error
        for message, error in harness.toasts
    )
