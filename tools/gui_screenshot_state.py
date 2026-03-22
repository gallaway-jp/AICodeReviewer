#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root / "src"))

logger = logging.getLogger(__name__)


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the GUI in a specific screenshot state")
    parser.add_argument("--state", choices=["review", "results", "ai-fix", "log"], required=True)
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
        else:
            app.tabs.set(t("gui.tab.log"))
            _populate_log_tab(app)

        app.update_idletasks()
        app.update()
        app.lift()
        app.focus_force()
        if args.hwnd_file:
            Path(args.hwnd_file).write_text(str(app.winfo_id()), encoding="utf-8")
        app.after(600, app.update_idletasks)
        app.after(1200, app.update)

    app.after(1000, _prepare)
    app.after(args.hold_ms, app.destroy)
    app.mainloop()


if __name__ == "__main__":
    main()