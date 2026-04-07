# Milestone 10 Detached Log Window Handoff

## Summary

Milestone 10 is now in progress in the current baseline.

The first detachable-window slice is implemented for the Output Log page so the project has a working pattern for multi-window lifecycle, shared UI state, persisted reopen state, and redock behavior before extending the feature to more complex pages.

## Completed Slice

- `src/aicodereviewer/gui/app_surfaces.py`
  - added an `Open In Window` action on the Output Log tab
  - added a detached `CTkToplevel` Output Log window with Clear, Save, and Redock actions
  - unified main-tab and detached-window log rendering so both views stay synchronized from the same `_log_lines` buffer
  - persisted detached-window state and geometry through `gui.detached_pages` and `gui.detached_log_geometry`
  - restored the detached Output Log window during startup when the saved GUI state indicates it was previously open
- `src/aicodereviewer/gui/app.py`
  - added app-level proxies for detached-log open, redock, and restore actions
- `src/aicodereviewer/gui/app_bootstrap.py`
  - initialized detached-log runtime attributes
- `src/aicodereviewer/gui/app_lifecycle.py`
  - restores detached windows after UI construction and preserves detached-window geometry during shutdown
- `src/aicodereviewer/config.py`
  - added GUI defaults for detached page tracking and detached log geometry
- `src/aicodereviewer/lang/en.py`
  - added localized strings for detached Output Log controls and restore messaging
- `src/aicodereviewer/lang/ja.py`
  - added localized strings for detached Output Log controls and restore messaging

## Validation

- `python -m pytest tests/test_gui_smoke.py tests/test_gui_workflows.py -k "detach or detached or log_tab_exposes_detach_window_action" -q` -> `3 passed, 144 deselected`
- `python -m pytest tests/test_gui_smoke.py tests/test_gui_workflows.py -k "log" -q` -> `7 passed, 140 deselected`

## Next Steps

- reuse the detached-window plumbing for the next approved non-Review page, likely Settings or Results depending on risk and state complexity
- decide how Milestone 10 should satisfy the keyboard shortcut or gesture acceptance item across the broader multi-window workflow
- add broader persistence and lifecycle coverage once more than one detachable page exists

## Resume Prompt

Resume from `docs/handoffs/milestone-10-detached-log-window-handoff-2026-04-06.md`. Milestone 10 is now active with the Output Log slice implemented: detached-window lifecycle, shared log synchronization, persisted reopen state, and redock behavior are in place and validated. The next continuation should generalize this pattern to additional non-Review pages without regressing the existing single-window tab workflow.