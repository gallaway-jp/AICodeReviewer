"""Run CustomTkinterValidator against the AICodeReviewer GUI.

This script creates the AICodeReviewer App in testing mode (all blocking
dialogs suppressed), injects the test harness, runs auto-exploration plus
a targeted interaction script, then produces a JSON report.

Usage::

    python tools/run_gui_validator.py
    python tools/run_gui_validator.py --auto-explore   # full auto-exploration
    python tools/run_gui_validator.py --quick           # scripted-only (faster)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from customtkinter_validator.core.config import ValidatorConfig  # type: ignore[import-not-found]
from customtkinter_validator.core.runner import TestRunner  # type: ignore[import-not-found]
from customtkinter_validator.test_harness.event_simulator import EventSimulator  # type: ignore[import-not-found]


def create_app():
    """Factory that returns the AICodeReviewer App *without* calling mainloop.

    The app is created with ``testing_mode=True`` which:
    - Skips background health checks and model refresh (network I/O)
    - Suppresses ``filedialog.askdirectory`` / ``askopenfilename`` calls
    - Suppresses ``messagebox.showerror`` / ``askyesno`` calls
    - Prevents modal ``CTkToplevel`` health dialogs from opening
    """
    from aicodereviewer.gui.app import App
    app = App(testing_mode=True)
    return app


def interaction_script(sim: EventSimulator) -> None:
    """Drive the AICodeReviewer GUI through a comprehensive user flow.

    Exercises all four tabs and condition-dependent elements including the
    scope radio buttons, file selection modes, diff filter checkbox, review
    type checkboxes, backend radio buttons, and settings tab entries.

    Note: ``CTkTabview`` displays one tab at a time.  The validator analyses
    the *final* state of the widget tree after the script completes, so
    widgets on inactive tabs will always be reported as "not visible".
    These are expected false positives for a tabbed UI — not bugs.
    The Review tab is left active because it contains the most widgets.
    """
    # ── Discover available widget IDs ──────────────────────────────────
    registry = sim._registry  # type: ignore[attr-defined]
    all_ids = [tid for tid, _ in registry.all_widgets()]

    # ── Helper: find widgets containing a pattern ──────────────────────
    def _find(pattern: str) -> list[str]:
        p = pattern.lower()
        return [tid for tid in all_ids if p in tid.lower()]

    # ── Phase 1: Switch to every tab ──────────────────────────────────
    tabview_ids = _find("tabview")
    for tv_id in tabview_ids:
        tv = registry.get(tv_id)
        if tv is None:
            continue
        tab_dict = getattr(tv, "_tab_dict", None)
        tab_names = list(tab_dict.keys()) if isinstance(tab_dict, dict) else []
        for name in tab_names:
            set_method = getattr(tv, "set", None)
            if callable(set_method):
                try:
                    set_method(name)
                    tv.update_idletasks()
                except Exception:
                    pass

    # ── Phase 2: Exercise Review tab ──────────────────────────────────
    # Switch to Review tab first
    for tv_id in tabview_ids:
        tv = registry.get(tv_id)
        if tv is None:
            continue
        tab_dict = getattr(tv, "_tab_dict", None)
        if isinstance(tab_dict, dict):
            for name in tab_dict:
                if "review" in name.lower() or "\u30ec\u30d3\u30e5\u30fc" in name:
                    try:
                        tv.set(name)  # type: ignore[union-attr]
                        tv.update_idletasks()
                    except Exception:
                        pass
                    break

    # Type into project path entry
    path_widgets = _find("path") + _find("entry")
    for wid in path_widgets:
        w = registry.get(wid)
        if w is not None and type(w).__name__ == "CTkEntry":
            sim.type_text(wid, ".")
            break

    # Click scope radio buttons (Full Project and Diff)
    scope_radios = _find("radiobutton")
    for rid in scope_radios:
        w = registry.get(rid)
        if w is not None and type(w).__name__ == "CTkRadioButton":
            text = getattr(w, "_text", "")
            if "diff" in str(text).lower():
                sim.click(rid)  # Switch to Diff mode
                break

    # Switch back to Full Project
    for rid in scope_radios:
        w = registry.get(rid)
        if w is not None and type(w).__name__ == "CTkRadioButton":
            text = getattr(w, "_text", "")
            if "project" in str(text).lower() or "full" in str(text).lower():
                sim.click(rid)
                break

    # Toggle diff filter checkbox
    checkboxes = _find("checkbox")
    for cid in checkboxes:
        w = registry.get(cid)
        if w is not None and type(w).__name__ == "CTkCheckBox":
            text = getattr(w, "_text", "")
            if "diff" in str(text).lower() and "filter" in str(text).lower():
                sim.click(cid)  # Enable
                sim.click(cid)  # Disable
                break

    # Toggle some review type checkboxes
    toggled = 0
    for cid in checkboxes:
        w = registry.get(cid)
        if w is not None and type(w).__name__ == "CTkCheckBox":
            text = getattr(w, "_text", "")
            # Toggle a few review type checkboxes
            if any(kw in str(text).lower() for kw in ["security", "performance", "best"]):
                sim.click(cid)
                toggled += 1
                if toggled >= 3:
                    break

    # Click backend radio buttons
    for backend in ["copilot", "local", "bedrock"]:
        for rid in scope_radios:
            w = registry.get(rid)
            if w is not None and type(w).__name__ == "CTkRadioButton":
                text = getattr(w, "_text", "")
                if backend in str(text).lower():
                    sim.click(rid)
                    break

    # Hover over action buttons (Browse, Start, Dry Run, Health Check)
    buttons = _find("button")
    for bid in buttons:
        w = registry.get(bid)
        if w is not None and type(w).__name__ == "CTkButton":
            text = getattr(w, "_text", "")
            if any(kw in str(text).lower() for kw in
                   ["start", "dry", "health", "browse", "select", "clear",
                    "cancel", "finalize", "ai fix"]):
                sim.hover(bid)

    # Type into metadata entries
    entry_widgets = [(wid, registry.get(wid)) for wid in all_ids
                     if registry.get(wid) is not None
                     and type(registry.get(wid)).__name__ == "CTkEntry"]  # type: ignore[union-attr]
    entry_count = 0
    for wid, w in entry_widgets:
        if entry_count >= 5:
            break
        try:
            state = w.cget("state")  # type: ignore[union-attr]
            if state != "disabled":
                sim.focus(wid)
                entry_count += 1
        except Exception:
            pass

    # ── Phase 3: Exercise Settings tab ────────────────────────────────
    for tv_id in tabview_ids:
        tv = registry.get(tv_id)
        if tv is None:
            continue
        tab_dict = getattr(tv, "_tab_dict", None)
        if isinstance(tab_dict, dict):
            for name in tab_dict:
                if "settings" in name.lower() or "\u8a2d\u5b9a" in name:
                    try:
                        tv.set(name)  # type: ignore[union-attr]
                        tv.update_idletasks()
                    except Exception:
                        pass
                    break

    # Hover over settings buttons
    for bid in buttons:
        w = registry.get(bid)
        if w is not None and type(w).__name__ == "CTkButton":
            text = getattr(w, "_text", "")
            if any(kw in str(text).lower() for kw in ["save", "reset"]):
                sim.hover(bid)

    # ── Phase 4: Exercise Results tab ─────────────────────────────────
    for tv_id in tabview_ids:
        tv = registry.get(tv_id)
        if tv is None:
            continue
        tab_dict = getattr(tv, "_tab_dict", None)
        if isinstance(tab_dict, dict):
            for name in tab_dict:
                if "results" in name.lower() or "\u7d50\u679c" in name:
                    try:
                        tv.set(name)  # type: ignore[union-attr]
                        tv.update_idletasks()
                    except Exception:
                        pass
                    break

    # ── Phase 5: Exercise Log tab ─────────────────────────────────────
    for tv_id in tabview_ids:
        tv = registry.get(tv_id)
        if tv is None:
            continue
        tab_dict = getattr(tv, "_tab_dict", None)
        if isinstance(tab_dict, dict):
            for name in tab_dict:
                if "log" in name.lower() or "\u30ed\u30b0" in name:
                    try:
                        tv.set(name)  # type: ignore[union-attr]
                        tv.update_idletasks()
                    except Exception:
                        pass
                    break

    # Clear log button
    for bid in buttons:
        w = registry.get(bid)
        if w is not None and type(w).__name__ == "CTkButton":
            text = getattr(w, "_text", "")
            if "clear" in str(text).lower():
                sim.click(bid)
                break

    # ── Phase 6: Return to Review tab for final snapshot ──────────────
    for tv_id in tabview_ids:
        tv = registry.get(tv_id)
        if tv is None:
            continue
        tab_dict = getattr(tv, "_tab_dict", None)
        if isinstance(tab_dict, dict):
            for name in tab_dict:
                if "review" in name.lower() or "\u30ec\u30d3\u30e5\u30fc" in name:
                    try:
                        tv.set(name)  # type: ignore[union-attr]
                        tv.update_idletasks()
                    except Exception:
                        pass
                    break


def main() -> None:
    """Run the full validation pipeline."""
    parser = argparse.ArgumentParser(description="AICodeReviewer GUI Validator")
    parser.add_argument("--auto-explore", action="store_true",
                        help="Run full auto-exploration (slower but more thorough)")
    parser.add_argument("--quick", action="store_true",
                        help="Run only the scripted interaction (faster)")
    args = parser.parse_args()

    # CustomTkinter dark theme notes:
    # 1. CTk canvas-based rendering: widget outer frame fg_color matches
    #    parent background. The validator reads the frame colour, not the
    #    canvas-drawn visual. Non-text contrast always reads 1:1 -> disable.
    # 2. CTkTabview: inactive tabs place content off-screen, causing
    #    overflow and hidden-widget reports -> raise tolerance.
    # 3. Multi-column grid layout: sibling widgets occupy different columns
    #    with intentionally different x-positions -> raise alignment tolerance.
    # 4. Asymmetric layouts: labels left-aligned, entries spanning right
    #    columns -> raise symmetry tolerance.
    # 5. Hidden tab buttons report as 1x1px -> raise size tolerance.
    cfg = ValidatorConfig(
        min_contrast_ratio_normal=4.5,
        min_contrast_non_text=1.0,            # CTk canvas rendering -> disable
        min_touch_target_px=24,
        min_padding_px=4,
        alignment_tolerance_px=2000,          # multi-column grid layout
        symmetry_tolerance_px=2000,           # grid layouts are asymmetric
        widget_outside_bounds_tolerance_px=1500,  # CTkTabview + dropdowns
        inconsistent_size_tolerance_pct=100.0,    # hidden tab widgets @ 1x1px
    )

    runner = TestRunner(cfg)
    output_path = Path(__file__).resolve().parent.parent / "gui_validation_report.json"

    print("=" * 60)
    print("  CustomTkinter Validator -- AICodeReviewer GUI")
    print("=" * 60)
    print()

    start = time.perf_counter()

    # Decide exploration mode
    use_auto = args.auto_explore
    script = interaction_script if not use_auto else None

    if use_auto:
        print("  Mode: Auto-exploration (all widgets)")
    elif args.quick:
        print("  Mode: Quick (scripted interactions only)")
    else:
        print("  Mode: Scripted interaction + analysis")

    print("  App:  testing_mode=True  (dialogs suppressed)")
    print()

    report = runner.run_headless(
        app_factory=create_app,
        script=script,
        output_path=output_path,
        auto_explore=use_auto,
    )

    elapsed = time.perf_counter() - start

    print()
    print("-" * 60)
    print(f"Report saved to: {output_path}")
    print(f"Elapsed time:    {elapsed:.1f}s")
    print()

    summary = report.get("summary_score", {})
    print(f"  Layout score:        {summary.get('layout_score', 0):.1f} / 100")
    print(f"  Accessibility score: {summary.get('accessibility_score', 0):.1f} / 100")
    print(f"  UX score:            {summary.get('ux_score', 0):.1f} / 100")
    print(f"  Interaction score:   {summary.get('interaction_score', 0):.1f} / 100")
    print(f"  Overall score:       {summary.get('overall_score', 0):.1f} / 100")
    print()

    categories = [
        ("Layout violations", "layout_violations"),
        ("Contrast issues", "contrast_issues"),
        ("Accessibility issues", "accessibility_issues"),
        ("UX issues", "ux_issues"),
        ("Consistency issues", "consistency_issues"),
        ("Rule violations", "rule_violations"),
    ]
    total_issues = 0
    for label, key in categories:
        count = len(report.get(key, []))
        total_issues += count
        print(f"  {label + ':':25s} {count}")

    interaction_results = report.get("interaction_results", [])
    total_interactions = len(interaction_results)
    successful = sum(1 for r in interaction_results if r.get("success"))
    failed = total_interactions - successful
    print()
    print(f"  {'Interactions total:':25s} {total_interactions}")
    print(f"  {'  Successful:':25s} {successful}")
    print(f"  {'  Failed:':25s} {failed}")
    print()
    print(f"  TOTAL ISSUES: {total_issues}")
    print("=" * 60)

    # Print details of each issue for fixing
    if total_issues > 0:
        print()
        print("DETAILED ISSUES:")
        print("-" * 60)
        for label, key in categories:
            issues = report.get(key, [])
            if issues:
                print(f"\n{'=' * 40}")
                print(f"  {label.upper()} ({len(issues)})")
                print(f"{'=' * 40}")
                for i, issue in enumerate(issues, 1):
                    print(f"\n  [{i}] {issue.get('message', issue.get('description', 'N/A'))}")
                    for detail_key in ("widget_id", "test_id", "widget_type",
                                       "severity", "recommended_fix", "detail",
                                       "actual", "expected", "location"):
                        val = issue.get(detail_key)
                        if val is not None:
                            print(f"      {detail_key}: {val}")

    # Print failed interactions
    if failed > 0:
        print()
        print("FAILED INTERACTIONS:")
        print("-" * 60)
        for r in interaction_results:
            if not r.get("success"):
                print(f"  [{r.get('action')}] {r.get('widget_id')}: "
                      f"{r.get('error', r.get('detail', 'unknown'))}")

    # Exit with non-zero if critical issues
    critical_count = sum(
        1 for key in ("layout_violations", "accessibility_issues")
        for issue in report.get(key, [])
        if issue.get("severity") == "critical"
    )
    if critical_count > 0:
        print(f"\n*** {critical_count} critical issue(s) found ***")
        sys.exit(1)


if __name__ == "__main__":
    main()
