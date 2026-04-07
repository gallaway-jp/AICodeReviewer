# Milestone 8 Failed-Fix Messaging Handoff

## Summary

This slice takes the item-level fix diagnostics added earlier in Milestone 8 and actually surfaces them in the places that were still flattening failures to generic "failed item" copy.

The main UX change is in the Results-tab batch AI Fix flow: failed rows in the popup now show categorized diagnostic detail and remediation hints, and an all-failed batch reports a classified summary instead of only a generic toast.

Tool-mode `resume` also now lifts failed fix diagnostics into top-level summary fields so automation can explain fix-plan/apply-fixes failures without re-walking nested item payloads.

## Implemented

- Updated `src/aicodereviewer/gui/results_mixin.py`:
  - batch AI Fix worker now returns structured per-item popup results with `status`, `content`, and optional `diagnostic`
  - GUI generation keeps the existing snippet fallback for reviewed issues whose source file is unavailable on disk, so preview generation behavior stays compatible with prior GUI flows and tests
- Updated `src/aicodereviewer/gui/results_popups.py`:
  - batch popup now accepts both legacy string payloads and the new structured result dictionaries
  - failed rows render diagnostic category/detail/hint text when available
  - popup recovery persists both successful and failed generated results as JSON-safe dictionaries
  - all-failed batches now show a diagnostic-aware toast summary instead of only `gui.results.no_fix`
- Updated `src/aicodereviewer/main.py`:
  - `resume` normalization for `fix-plan` and `apply-fixes` now emits:
    - `failed_diagnostics`
    - `failed_diagnostic_categories`
- Updated localization in `src/aicodereviewer/lang/en.py` and `src/aicodereviewer/lang/ja.py` for batch-fix failure details, hints, summaries, and diagnostic category labels

## Compatibility Notes

- Existing popup callers that pass `dict[int, str | None]` continue to work.
- Popup recovery stays JSON-safe because structured results are serialized as plain dictionaries.
- The batch popup still only exposes preview/edit controls for successfully generated fixes; failed rows remain informational.

## Regression Coverage

- `tests/test_gui_workflows.py`
  - GUI worker surfaces structured failed-fix diagnostics
  - batch popup shows failed-item diagnostic detail and hint text
  - all-failed toast includes diagnostic-aware messaging
  - existing popup recovery, selective apply, edited preview, and keyboard navigation flows still pass with the new result shape
- `tests/test_cli_tool_mode.py`
  - `resume` exposes `failed_diagnostics`
  - `resume` exposes `failed_diagnostic_categories`

## Validated Commands

- `./.venv/Scripts/python.exe -m pytest tests/test_gui_workflows.py::test_ai_fix_recreates_backend_and_generates_preview_results tests/test_gui_workflows.py::test_restored_session_ai_fix_recreates_backend_and_opens_preview tests/test_gui_workflows.py::test_ai_fix_worker_surfaces_failed_fix_diagnostic_results tests/test_gui_workflows.py::test_batch_fix_popup_surfaces_failed_item_diagnostic_details tests/test_gui_workflows.py::test_batch_fix_popup_all_failed_toast_includes_diagnostic_summary tests/test_cli_tool_mode.py::test_tool_resume_normalizes_fix_plan_artifact tests/test_cli_tool_mode.py::test_tool_resume_normalizes_apply_results_artifact -q`
  - result: `7 passed`
- `./.venv/Scripts/python.exe -m pytest tests/test_gui_workflows.py::test_popup_recovery_restores_staged_batch_fix_edits_and_selection tests/test_gui_workflows.py::test_ai_fix_apply_popup_can_apply_only_selected_fixes tests/test_gui_workflows.py::test_ai_fix_preview_edit_save_applies_user_edited_fix tests/test_gui_workflows.py::test_batch_fix_popup_supports_keyboard_issue_jumps_and_status_text -q`
  - result: `4 passed`

## Remaining Gap

- Interactive terminal `AI FIX` messaging still uses the legacy generic `interactive.fix_failed` line. The structured diagnostics now exist, but that CLI/interactive surface has not been upgraded yet.