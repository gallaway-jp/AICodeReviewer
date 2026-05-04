from __future__ import annotations

import configparser
import json
import os
import shutil
import subprocess
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


PYTHON_EXE = Path(sys.executable)


def clone_current_config() -> configparser.ConfigParser:
    cloned = configparser.ConfigParser()
    for section in config.config.sections():
        cloned.add_section(section)
        for key, value in config.config.items(section):
            cloned.set(section, key, value)
    return cloned


def restore_config(config_path: Path, snapshot: configparser.ConfigParser) -> None:
    config.config_path = config_path
    config.config = configparser.ConfigParser()
    config._set_defaults()
    for section in snapshot.sections():
        if not config.config.has_section(section):
            config.config.add_section(section)
        for key, value in snapshot.items(section):
            config.config.set(section, key, value)


def reset_config_to_path(config_path: Path) -> None:
    config.config_path = config_path
    config.config = configparser.ConfigParser()
    config._set_defaults()
    if config_path.exists():
        config.config.read(config_path, encoding="utf-8")


def save_config(parser: configparser.ConfigParser, path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


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


def run_command(cwd: Path, *args: str) -> dict[str, Any]:
    env = dict(os.environ)
    current_pythonpath = env.get("PYTHONPATH", "")
    repo_src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = repo_src if not current_pythonpath else os.pathsep.join([repo_src, current_pythonpath])
    env.setdefault("PYTHONUTF8", "1")
    completed = subprocess.run(
        [str(PYTHON_EXE), "-m", "aicodereviewer", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "args": [str(PYTHON_EXE), "-m", "aicodereviewer", *args],
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def capture_gui_labels(config_path: Path, language: str) -> dict[str, Any]:
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")
    if not parser.has_section("gui"):
        parser.add_section("gui")
    parser.set("gui", "language", language)
    parser.set("gui", "review_language", language)
    save_config(parser, config_path)

    reset_config_to_path(config_path)
    app: App | None = None
    try:
        app = App(testing_mode=True)
        sync_ui(app, cycles=8)
        app._build_tab_if_needed(t("gui.tab.review"))
        app.tabs.set(t("gui.tab.review"))
        sync_ui(app, cycles=4)
        review_labels = {
            "run_button": str(app.run_btn.cget("text")),
            "dry_run_button": str(app.dry_btn.cget("text")),
            "health_button": str(app.health_btn.cget("text")),
            "status_text": str(app.status_var.get()),
        }

        app._build_tab_if_needed(t("gui.tab.settings"))
        app.tabs.set(t("gui.tab.settings"))
        sync_ui(app, cycles=4)
        settings_labels = {
            "local_http_status": str(app.local_http_status_label.cget("text")),
            "local_http_docs_excerpt": app.local_http_docs_box.get("0.0", "end-1c")[:500],
        }
        return {
            "language": language,
            "review": review_labels,
            "settings": settings_labels,
        }
    finally:
        close_app(app)


def main() -> None:
    output_dir = REPO_ROOT / "artifacts" / "manual-session10"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "recovery-localization-probe.json"

    original_config_path = config.config_path
    original_config_snapshot = clone_current_config()

    try:
        with tempfile.TemporaryDirectory(prefix="aicr-recovery-localization-") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            temp_config = temp_dir / "config.ini"
            source_config = REPO_ROOT / "config.ini"
            shutil.copy2(source_config, temp_config)

            parser = configparser.ConfigParser()
            parser.read(temp_config, encoding="utf-8")
            if not parser.has_section("backend"):
                parser.add_section("backend")
            parser.set("backend", "type", "local")
            if not parser.has_section("local_llm"):
                parser.add_section("local_llm")
            parser.set("local_llm", "timeout", "5")
            if not parser.has_section("gui"):
                parser.add_section("gui")
            parser.set("gui", "language", "en")
            parser.set("gui", "review_language", "en")

            valid_api_url = parser.get("local_llm", "api_url", fallback="http://localhost:1234")
            valid_model = parser.get("local_llm", "model", fallback="default")
            valid_api_type = parser.get("local_llm", "api_type", fallback="openai")

            parser.set("local_llm", "api_url", "http://127.0.0.1:9")
            save_config(parser, temp_config)
            bad_health = run_command(temp_dir, "--check-connection", "--backend", "local", "--lang", "en")

            parser.set("local_llm", "api_url", valid_api_url)
            parser.set("local_llm", "model", valid_model)
            parser.set("local_llm", "api_type", valid_api_type)
            save_config(parser, temp_config)
            good_health = run_command(temp_dir, "--check-connection", "--backend", "local", "--lang", "en")

            english_presets = run_command(temp_dir, "--list-type-presets", "--lang", "en")
            japanese_presets = run_command(temp_dir, "--list-type-presets", "--lang", "ja")

            english_gui = capture_gui_labels(temp_config, "en")
            japanese_gui = capture_gui_labels(temp_config, "ja")

            results = {
                "config_source": str(source_config),
                "temp_config": str(temp_config),
                "local_backend_recovery": {
                    "bad_config": {
                        "api_url": "http://127.0.0.1:9",
                        "model": valid_model,
                        "api_type": valid_api_type,
                    },
                    "good_config": {
                        "api_url": valid_api_url,
                        "model": valid_model,
                        "api_type": valid_api_type,
                    },
                    "bad_health": bad_health,
                    "good_health": good_health,
                },
                "cli_localization": {
                    "english_presets": english_presets,
                    "japanese_presets": japanese_presets,
                },
                "gui_localization": {
                    "english": english_gui,
                    "japanese": japanese_gui,
                },
                "sanity_checks": {
                    "bad_health_failed": bad_health["returncode"] != 0,
                    "good_health_passed": good_health["returncode"] == 0,
                    "english_cli_has_english_label": "Security" in english_presets["stdout"] or "Runtime Safety" in english_presets["stdout"],
                    "japanese_cli_has_japanese_label": "セキュリティ" in japanese_presets["stdout"] or "ランタイム安全性" in japanese_presets["stdout"],
                    "gui_run_button_translated": english_gui["review"]["run_button"] != japanese_gui["review"]["run_button"],
                    "gui_health_button_translated": english_gui["review"]["health_button"] != japanese_gui["review"]["health_button"],
                },
            }

            output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(results, ensure_ascii=True, indent=2))
    finally:
        restore_config(original_config_path, original_config_snapshot)


if __name__ == "__main__":
    main()