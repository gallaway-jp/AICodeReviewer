#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import tempfile
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root / "src"))

logger = logging.getLogger(__name__)


def _window_handle(window) -> int:
    frame_handle = str(getattr(window, "wm_frame", lambda: "")() or "").strip()
    if frame_handle.lower().startswith("0x"):
        return int(frame_handle, 16)
    if frame_handle:
        return int(frame_handle)
    return int(window.winfo_id())


def _write_sample_benchmark_summaries() -> tuple[Path, Path, Path]:
    artifacts_root = Path(tempfile.mkdtemp(prefix="aicr-gui-benchmarks-"))
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
                },
            },
            {
                "id": "validation-gap",
                "title": "Validation Gap",
                "scope": "project",
                "review_types": ["data_validation"],
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


def _populate_review_tab(app) -> None:
    app.path_entry.delete(0, "end")
    app.path_entry.insert(0, "C:/Projects/sample-app")

    app.programmers_entry.delete(0, "end")
    app.programmers_entry.insert(0, "Alice, Bob")
    app.reviewers_entry.delete(0, "end")
    app.reviewers_entry.insert(0, "Charlie")

    app.spec_entry.delete(0, "end")
    app.spec_entry.insert(0, "review_spec.md")

    for key, var in app.type_vars.items():
        var.set(key in {"security", "performance", "error_handling"})

    app.backend_var.set("local")
    app.status_var.set("Screenshot mode ready")
    logger.info("Prepared Review tab screenshot state")


def _populate_review_partial_tab(app) -> None:
    _populate_review_tab(app)
    app.path_entry.delete(0, "end")
    app.path_entry.insert(0, str(_project_root))

    app.file_select_mode_var.set("selected")
    app.selected_files = [
        "src/aicodereviewer/gui/review_mixin.py",
        "src/aicodereviewer/gui/review_execution_facade.py",
    ]
    app._file_count_lbl.configure(text=app._selected_file_count_text(len(app.selected_files)))

    app.diff_filter_var.set(True)
    app.diff_filter_commits_entry.delete(0, "end")
    app.diff_filter_commits_entry.insert(0, "HEAD~2..HEAD")
    app.diff_filter_file_entry.delete(0, "end")
    app.diff_filter_file_entry.insert(0, "")

    for key, var in app.type_vars.items():
        var.set(key in {"best_practices", "testing"})

    app.tabs.set("Review")
    app.update_idletasks()
    app.update()
    if getattr(app, "review_scroll_canvas", None) is not None:
        app.review_scroll_canvas.yview_moveto(0.12)
    app.status_var.set("Partial project workflow screenshot")
    logger.info("Prepared Review partial-project screenshot state")


def _populate_log_tab(app) -> None:
    entries = [
        "Manual GUI test app created (lang=en, theme=dark)",
        "Preselected review types: security, performance, error_handling",
        "Injected 10 sample issues into the Results tab",
        "Displaying 10 issues on the Results tab",
        "Screenshot capture: Output Log tab ready",
    ]
    app._log_lines = [(20, entry) for entry in entries]
    app._log_level_var.set("All")
    app._on_log_level_changed()
    app.status_var.set("Output Log screenshot")
    logger.info("Prepared Output Log tab screenshot state")


def _populate_benchmark_tab(app, *, detached: bool = False) -> None:
    artifacts_root, summary_path, compare_path = _write_sample_benchmark_summaries()
    from aicodereviewer.i18n import t

    app.tabs.set(t("gui.tab.benchmarks"))
    app._refresh_benchmark_summary_selector(artifacts_root)
    app._load_benchmark_summary_artifact(summary_path)
    app._load_benchmark_summary_artifact(compare_path, compare=True)
    app._set_benchmark_advanced_sources_visible(True)
    app.benchmark_fixture_filter_var.set(t("gui.benchmark.fixture_filter_shared"))
    app._on_fixture_diff_filter_selected(t("gui.benchmark.fixture_filter_shared"))
    app.benchmark_fixture_sort_var.set(t("gui.benchmark.fixture_sort_status_churn"))
    app._on_fixture_diff_sort_selected(t("gui.benchmark.fixture_sort_status_churn"))
    app._preview_fixture_diff_reports("auth-jwt-bypass")
    app.status_var.set("Benchmarks screenshot")

    if detached:
        app._open_detached_benchmark_window()
        app.update_idletasks()
        app.update()
        app.status_var.set("Detached Benchmarks screenshot")

    logger.info("Prepared Benchmarks tab screenshot state")


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the GUI in a specific screenshot state")
    parser.add_argument("--state", choices=["review", "review-partial", "results", "ai-fix", "log", "benchmarks", "benchmark-detached"], required=True)
    parser.add_argument("--theme", choices=["dark", "light", "system"], default="dark")
    parser.add_argument("--lang", choices=["en", "ja"], default="en")
    parser.add_argument("--hold-ms", type=int, default=30000)
    parser.add_argument("--hwnd-file", help="Optional path where the prepared GUI window handle is written")
    args = parser.parse_args()

    from aicodereviewer.gui.test_fixtures import apply_test_config, create_sample_issues
    apply_test_config()

    from aicodereviewer.config import config
    config.set_value("gui", "language", args.lang)
    config.set_value("gui", "theme", args.theme)

    from aicodereviewer.gui.app import App
    from aicodereviewer.i18n import t

    app = App(testing_mode=True)
    app.geometry("1500x980+60+40")
    app.attributes("-topmost", True)

    sample_issues = create_sample_issues()

    def _prepare() -> None:
        _populate_review_tab(app)

        if args.state == "review":
            app.tabs.set(t("gui.tab.review"))
            app.status_var.set("Review tab screenshot")
        elif args.state == "review-partial":
            _populate_review_partial_tab(app)
        elif args.state == "results":
            app._show_issues(sample_issues)
            logger.info("Loaded %d sample issues for screenshot capture", len(sample_issues))
            app.tabs.set(t("gui.tab.results"))
            app.status_var.set("Results tab screenshot")
        elif args.state == "ai-fix":
            app._show_issues(sample_issues)
            logger.info("Loaded %d sample issues for screenshot capture", len(sample_issues))
            app.tabs.set(t("gui.tab.results"))
            app._enter_ai_fix_mode()
            app.status_var.set("AI Fix mode screenshot")
        elif args.state == "benchmarks":
            _populate_benchmark_tab(app)
        elif args.state == "benchmark-detached":
            _populate_benchmark_tab(app, detached=True)
        else:
            app.tabs.set(t("gui.tab.log"))
            _populate_log_tab(app)

        app.update_idletasks()
        app.update()
        app.lift()
        app.focus_force()
        if args.hwnd_file:
            window_handle = _window_handle(app)
            if args.state == "benchmark-detached" and getattr(app, "_detached_benchmark_window", None) is not None:
                window_handle = _window_handle(app._detached_benchmark_window)
            Path(args.hwnd_file).write_text(str(window_handle), encoding="utf-8")
        app.after(600, app.update_idletasks)
        app.after(1200, app.update)

    app.after(1000, _prepare)
    app.after(args.hold_ms, app.destroy)
    app.mainloop()


if __name__ == "__main__":
    main()