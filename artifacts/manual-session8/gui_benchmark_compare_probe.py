from __future__ import annotations

import configparser
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aicodereviewer.config import config
from aicodereviewer.gui.app import App
from aicodereviewer.i18n import t


def reset_config_to_path(config_path: Path) -> None:
    config.config_path = config_path
    config.config = configparser.ConfigParser()
    config._set_defaults()
    config.config.read(config_path, encoding="utf-8")


def sync_ui(app: App, cycles: int = 4, delay_s: float = 0.03) -> None:
    for _ in range(cycles):
        app.update_idletasks()
        app.update()
        if delay_s > 0:
            time.sleep(delay_s)


def close_app(app: App | None) -> None:
    if app is None:
        return
    try:
        app._app_helpers().lifecycle().prepare_for_destroy()
    except Exception:
        pass
    try:
        app.destroy()
    except Exception:
        pass


def option_values(widget: Any) -> list[str]:
    try:
        values = widget.cget("values")
    except Exception:
        values = getattr(widget, "_values", [])
    return [str(value) for value in values]


def widget_texts(root: Any) -> list[str]:
    texts: list[str] = []

    def _walk(widget: Any) -> None:
        try:
            text = widget.cget("text")
        except Exception:
            text = None
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
        for child in getattr(widget, "winfo_children", lambda: [])():
            _walk(child)

    _walk(root)
    return texts


def set_entry(widget: Any, value: str) -> None:
    widget.delete(0, "end")
    widget.insert(0, value)


def copy_single_fixture(temp_root: Path, fixture_id: str) -> Path:
    source_root = REPO_ROOT / "benchmarks" / "holistic_review" / "fixtures" / fixture_id
    target_root = temp_root / fixture_id
    shutil.copytree(source_root, target_root)
    return temp_root


def newest_run_dir(artifacts_root: Path) -> Path | None:
    runs_root = artifacts_root / "holistic-benchmark-runs"
    if not runs_root.is_dir():
        return None
    candidates = [path for path in runs_root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    output_dir = REPO_ROOT / "artifacts" / "manual-session8"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "gui-benchmark-compare-probe.json"
    source_config = REPO_ROOT / "config.ini"
    fixture_ids = ["auth-guard-regression", "cache-invalidation-gap"]

    with tempfile.TemporaryDirectory(prefix="aicr-gui-benchmark-compare-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        temp_config = temp_dir / "config.ini"
        shutil.copy2(source_config, temp_config)
        fixture_roots = []
        for fixture_id in fixture_ids:
            fixture_roots.append(copy_single_fixture(temp_dir / fixture_id / "fixtures", fixture_id))

        reset_config_to_path(temp_config)
        config.set_value("backend", "type", "local")
        config.set_value("gui", "language", "en")
        config.set_value("gui", "review_language", "en")
        config.set_value("gui", "detached_pages", "")
        config.set_value("gui", "benchmark_artifacts_root", str(output_dir))
        config.save()

        app: App | None = App(testing_mode=True)
        toasts: list[dict[str, Any]] = []
        try:
            original_show_toast = app._show_toast

            def capture_toast(message: str, *, duration: int = 6000, error: bool = False) -> None:
                toasts.append({"message": message, "error": error, "duration": duration})

            app._show_toast = capture_toast
            sync_ui(app, cycles=6)
            app._build_tab_if_needed(t("gui.tab.benchmarks"))
            app.tabs.set(t("gui.tab.benchmarks"))
            sync_ui(app, cycles=6)

            visible_labels = widget_texts(app.benchmark_root_tab)
            before_selector = option_values(app.benchmark_summary_selector_menu)
            before_source = str(app.benchmark_source_value.cget("text"))

            run_records: list[dict[str, Any]] = []
            for fixture_id, fixture_root in zip(fixture_ids, fixture_roots):
                set_entry(app.benchmark_fixtures_root_entry, str(fixture_root))
                set_entry(app.benchmark_artifacts_root_entry, str(output_dir))
                started_at = time.perf_counter()
                app.benchmark_run_btn.invoke()
                sync_ui(app, cycles=8, delay_s=0.05)
                elapsed_seconds = round(time.perf_counter() - started_at, 3)
                latest_run_dir = newest_run_dir(output_dir)
                if latest_run_dir is None:
                    raise RuntimeError(f"No run directory created for {fixture_id}")
                summary_path = latest_run_dir / "summary.json"
                run_json_path = latest_run_dir / "run.json"
                run_payload = read_json(run_json_path)
                run_records.append(
                    {
                        "fixture_id": fixture_id,
                        "elapsed_seconds": elapsed_seconds,
                        "run_dir": str(latest_run_dir),
                        "summary_path": str(summary_path),
                        "run_json_path": str(run_json_path),
                        "generated_reports": [
                            str(item.get("output_path"))
                            for item in run_payload.get("generated_reports", [])
                            if isinstance(item, dict) and isinstance(item.get("output_path"), str)
                        ],
                        "summary_exists": summary_path.is_file(),
                        "run_json_exists": run_json_path.is_file(),
                    }
                )

            app._refresh_benchmark_summary_selector(output_dir)
            sync_ui(app, cycles=4)

            primary_label = str(Path(run_records[0]["summary_path"]).relative_to(output_dir))
            compare_label = str(Path(run_records[1]["summary_path"]).relative_to(output_dir))

            app.benchmark_summary_selector_var.set(primary_label)
            app._load_selected_benchmark_summary()
            sync_ui(app, cycles=4)
            primary_loaded_status = str(app.status_var.get())

            app.benchmark_summary_selector_var.set(compare_label)
            app._compare_selected_benchmark_summary()
            sync_ui(app, cycles=4)

            diff_records = getattr(app, "_benchmark_fixture_diff_records", [])

            results = {
                "fixture_ids": fixture_ids,
                "config_source": str(source_config),
                "artifacts_root": str(output_dir),
                "labels": {
                    "header_title": visible_labels[0] if visible_labels else "",
                    "run_button": str(app.benchmark_run_btn.cget("text")),
                    "load_summary_button": str(app.benchmark_load_summary_btn.cget("text")),
                    "compare_summary_button": str(app.benchmark_compare_summary_btn.cget("text")),
                    "visible_labels": visible_labels[:25],
                },
                "before_compare": {
                    "summary_selector_values": before_selector,
                    "source_text": before_source,
                },
                "run_records": run_records,
                "after_compare": {
                    "summary_selector_values": option_values(app.benchmark_summary_selector_menu),
                    "primary_label": primary_label,
                    "compare_label": compare_label,
                    "primary_path": str(app._current_primary_summary_path()) if app._current_primary_summary_path() else None,
                    "compare_path": str(app._benchmark_compare_summary_path) if getattr(app, "_benchmark_compare_summary_path", None) else None,
                    "primary_load_status": primary_loaded_status,
                    "status": str(app.status_var.get()),
                    "source_text": str(app.benchmark_source_value.cget("text")),
                    "count_text": str(app.benchmark_count_value.cget("text")),
                    "selected_fixture": str(app.benchmark_fixture_var.get()),
                    "catalog_excerpt": app.benchmark_catalog_box.get("0.0", "end-1c")[:1000],
                    "detail_excerpt": app.benchmark_detail_box.get("0.0", "end-1c")[:800],
                    "primary_summary_excerpt": app.benchmark_primary_summary_box.get("0.0", "end-1c")[:1000],
                    "compare_summary_excerpt": app.benchmark_compare_summary_box.get("0.0", "end-1c")[:1200],
                    "takeaways": str(app.benchmark_takeaways_label.cget("text")),
                },
                "diff_records": [
                    {
                        "fixture_id": str(record.get("fixture_id") or ""),
                        "presence": str(record.get("presence") or ""),
                        "summary": str(record.get("summary") or ""),
                        "primary_score": str(record.get("primary_score") or ""),
                        "compare_score": str(record.get("compare_score") or ""),
                        "primary_status": str(record.get("primary_status") or ""),
                        "compare_status": str(record.get("compare_status") or ""),
                    }
                    for record in diff_records
                ],
                "toasts": toasts,
            }

            output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(results, ensure_ascii=True, indent=2))
            app._show_toast = original_show_toast
        finally:
            close_app(app)


if __name__ == "__main__":
    main()