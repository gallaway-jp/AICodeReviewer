# Milestone 10 Detached Benchmark Window Handoff

## What shipped

- Added Benchmarks as the third detachable Milestone 10 page using the same shared detached-page shell as Output Log and Settings.
- The Benchmark builder now supports rendering into either the main tab or a detached `CTkToplevel` host.
- The main Benchmarks tab now exposes an `Open In Window` action, and the detached benchmark window exposes a `Redock` action plus `Ctrl+W` support.
- The main tab switches to a placeholder surface while Benchmarks is detached so the app keeps one canonical benchmark widget tree active at a time.

## State model

- Detached benchmark lifecycle lives in `src/aicodereviewer/gui/benchmark_mixin.py`.
- The implementation snapshots the active benchmark browser surface before detach and restores it when rebuilding in the detached window or back in the main tab.
- Preserved detach/redock state includes:
  - loaded benchmark entries and source label
  - discovered summary selector choices and current selection
  - primary and comparison summary payloads
  - current fixture filter and sort selection
  - preview/diff textbox contents
  - advanced-source visibility
- Restart restore for the detached window itself uses the shared `gui.detached_pages` list plus the new `gui.detached_benchmark_geometry` key.

## Shared Milestone 10 decision

- Milestone 10 now treats explicit page-level detach actions and keyboard shortcuts as the required detachable workflow.
- `Ctrl+Shift+O` opens the currently selected detachable page in a window.
- `Ctrl+W` redocks the active detached page.
- True drag-out gestures are not being treated as a blocker for Milestone 10 closeout; they remain an optional UX enhancement if we want to revisit them later.

## Validation

- `python -m pytest tests/test_gui_workflows.py -k "benchmark_tab_detach_and_redock_preserves_loaded_state or detachable_pages_support_keyboard_shortcuts_for_open_and_redock or three_detached_pages_restore_after_restart"`
  - `3 passed, 112 deselected`
- `python -m pytest tests/test_gui_workflows.py -k "log_tab_detach_and_redock_keeps_log_state_synced or settings_tab_detach_and_redock_preserves_unsaved_state or benchmark_tab_detach_and_redock_preserves_loaded_state or detachable_pages_support_keyboard_shortcuts_for_open_and_redock or log_tab_detached_window_restores_after_restart or three_detached_pages_restore_after_restart"`
  - `6 passed, 145 deselected`
- `python -m pytest tests/test_gui_smoke.py -k "benchmark_tab_widgets or tabs_keep_key_surfaces_visible_across_window_resize"`
  - `2 passed, 149 deselected`

## Follow-on options

- Extend the detached-page pattern to Results if Milestone 10 should cover one more complex non-Review surface.
- Leave drag-out gestures deferred unless a future milestone explicitly requires gesture-driven detach instead of action-driven detach.