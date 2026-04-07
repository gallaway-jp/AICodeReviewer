# Milestone 10 Detached Settings Window Handoff

## Summary

Milestone 10 remains in progress in the current baseline.

The second detachable-window slice now covers the Settings page and turns the earlier Output Log implementation into a broader detached-page pattern with shared lifecycle persistence and a concrete keyboard workflow.

## Completed Slice

- `src/aicodereviewer/gui/settings_builder.py`
  - parameterized the Settings surface builder so it can render either inside the main Settings tab or inside a detached toplevel container
  - added an `Open In Window` action for the main Settings tab and a `Redock` action for detached Settings windows
- `src/aicodereviewer/gui/settings_mixin.py`
  - added Settings surface snapshot and restore helpers so unsaved Settings form state survives detach and redock
  - added detached Settings window creation, placeholder rendering in the main tab, redock handling, and detached-surface rebuild support
  - detached Settings now rebuilds the canonical Settings form in the active window instead of maintaining an unrelated duplicate state model
- `src/aicodereviewer/gui/settings_actions.py`
  - reset-defaults now rebuilds whichever Settings surface is currently active, including detached Settings windows
- `src/aicodereviewer/gui/app_surfaces.py`
  - generalized detached-page persistence helpers so startup restore and shutdown geometry preservation now cover both log and settings windows
  - added shared detached-page redock shortcut binding over the full widget tree so focused child controls can participate in the same redock workflow
- `src/aicodereviewer/gui/app_bootstrap.py`
  - added `Ctrl+Shift+O` as the app-level shortcut that opens the currently selected detachable page in its own window
  - initialized detached Settings runtime attributes
- `src/aicodereviewer/gui/app.py`
  - added app-level proxies for detached Settings open and redock actions plus the current-page detach shortcut handler
- `src/aicodereviewer/config.py`
  - added `gui.detached_settings_geometry` so detached Settings windows can restore their last geometry after restart

## Shortcut Decision

Milestone 10's shortcut requirement is now satisfied by a shared detached-page keyboard scheme:

- `Ctrl+Shift+O` opens the currently selected detachable page from the main window
- `Ctrl+W` redocks the active detached page back into the main app

This keeps the workflow consistent across detachable pages without binding additional page-specific chord sets.

## Validation

- `python -m pytest tests/test_gui_smoke.py tests/test_gui_workflows.py -k "detach or detached or shortcut" -q` -> `6 passed, 144 deselected`
- `python -m pytest tests/test_gui_smoke.py tests/test_gui_workflows.py -k "log or settings" -q` -> `22 passed, 128 deselected`

## Next Steps

- extend the detached-page pattern to the next approved non-Review page, likely Results or Benchmarks depending on desired state complexity
- decide whether additional page-specific drag-out gestures are still needed now that the milestone has a working keyboard and button-based detach/redock workflow
- add broader multi-page restore assertions once a third detachable page exists

## Resume Prompt

Resume from `docs/handoffs/milestone-10-detached-settings-window-handoff-2026-04-06.md`. Milestone 10 now has two detached pages in the baseline: Output Log and Settings. Shared detached-page persistence restores both windows after restart, `Ctrl+Shift+O` opens the selected detachable page, and `Ctrl+W` redocks detached pages. The next continuation should extend this pattern to another approved non-Review page without regressing the existing detached log/settings flows.