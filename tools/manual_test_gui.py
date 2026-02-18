#!/usr/bin/env python3
# tools/manual_test_gui.py
"""
Launch the AICodeReviewer GUI in **manual testing mode**.

This opens the full GUI with:
- Isolated test-specific settings (real ``config.ini`` is never modified)
- Pre-populated Results tab with sample issues in every severity / status
- All tabs fully interactive for visual inspection

Usage::

    python tools/manual_test_gui.py            # default: English, dark theme
    python tools/manual_test_gui.py --lang ja   # Japanese UI
    python tools/manual_test_gui.py --theme light

The tester can click through every tab, inspect Results cards, try
Resolve / Skip / AI-Fix-Mode buttons, open the built-in editor etc.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── Ensure the project ``src/`` is importable ─────────────────────────────
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch the AICodeReviewer GUI in manual testing mode",
    )
    parser.add_argument(
        "--lang", choices=["en", "ja"], default="en",
        help="UI language (default: en)",
    )
    parser.add_argument(
        "--theme", choices=["dark", "light", "system"], default="dark",
        help="Appearance theme (default: dark)",
    )
    args = parser.parse_args()

    # ── 1. Apply isolated test config BEFORE the App reads it ──────────────
    from aicodereviewer.gui.test_fixtures import apply_test_config
    apply_test_config()

    # Override language / theme with CLI flags
    from aicodereviewer.config import config
    config.set_value("gui", "language", args.lang)
    config.set_value("gui", "theme", args.theme)

    # ── 2. Build the App in testing_mode ───────────────────────────────────
    from aicodereviewer.gui.app import App
    app = App(testing_mode=True)

    # Mark as manual-test so the app can enable extra demo behaviour
    app._manual_test_mode = True  # type: ignore[attr-defined]

    # ── 3. Inject sample issues into the Results tab ───────────────────────
    from aicodereviewer.gui.test_fixtures import create_sample_issues
    sample_issues = create_sample_issues()

    # Schedule injection after the event loop has started so all widgets
    # are fully realised.
    def _inject_results() -> None:
        app._show_issues(sample_issues)
        app.status_var.set("Manual Testing Mode — sample data loaded")

    app.after(200, _inject_results)

    # ── 4. Pre-populate Review tab fields ──────────────────────────────────
    def _populate_review_tab() -> None:
        # Project path
        app.path_entry.delete(0, "end")
        app.path_entry.insert(0, "C:/Projects/sample-app")

        # Programmers / reviewers
        app.programmers_entry.delete(0, "end")
        app.programmers_entry.insert(0, "Alice, Bob")
        app.reviewers_entry.delete(0, "end")
        app.reviewers_entry.insert(0, "Charlie")

        # Spec file
        app.spec_entry.delete(0, "end")
        app.spec_entry.insert(0, "review_spec.md")

        # Select some review types
        for key, var in app.type_vars.items():
            var.set(key in {"security", "performance", "error_handling"})

        # Set backend to Local LLM
        app.backend_var.set("local")

    app.after(100, _populate_review_tab)

    # ── 5. Start the event loop ────────────────────────────────────────────
    print("╔══════════════════════════════════════════════════════╗")
    print("║  AICodeReviewer — Manual GUI Testing Mode           ║")
    print("║                                                     ║")
    print("║  • Settings are ISOLATED (real config.ini untouched)║")
    print("║  • Results tab has 10 sample issues loaded          ║")
    print("║  • All tabs are fully interactive                   ║")
    print("║  • Close the window to exit                         ║")
    print("╚══════════════════════════════════════════════════════╝")
    app.mainloop()


if __name__ == "__main__":
    main()
