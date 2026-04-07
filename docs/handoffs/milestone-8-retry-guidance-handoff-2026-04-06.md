# Milestone 8 Retry Guidance Handoff

## Summary

This slice addresses the remaining Milestone 8 retry/backoff guidance gap by making retry metadata a first-class part of the shared failure diagnostic model.

Transient failures no longer rely only on free-form hint text. Shared diagnostics can now explicitly declare that a failure is retryable and, when known, provide a suggested retry delay.

## Implemented

- Updated `src/aicodereviewer/diagnostics.py`:
  - `FailureDiagnostic` now supports:
    - `retryable`
    - `retry_delay_seconds`
  - timeout and transport failures now default to retryable guidance
  - temporary/provider throttling failures can now carry retry delays
  - HTTP 429 now maps into the shared provider category instead of collapsing into generic configuration handling
- Updated downstream consumers:
  - `src/aicodereviewer/main.py`
    - connection-check console output now prints retry guidance when present
    - `resume` failed-diagnostic summaries now preserve retry metadata
  - `src/aicodereviewer/interactive.py`
    - interactive AI-fix failures now print retry guidance when a transient diagnostic is present
  - `src/aicodereviewer/gui/results_popups.py`
    - failed batch AI-fix popup rows now show retry guidance when the failure is classified as transient
- Updated localization in `src/aicodereviewer/lang/en.py` and `src/aicodereviewer/lang/ja.py` for retry guidance lines across connection, interactive, and batch-fix popup surfaces

## Regression Coverage

- `tests/test_fixer.py`
  - timeout fix-generation failures now carry retry guidance
  - provider/rate-limit fix-generation failures now carry retry guidance with delay
- `tests/test_interactive.py`
  - interactive AI-fix failures now print retry guidance lines for transient diagnostics
- `tests/test_cli_tool_mode.py`
  - `resume` preserves retry metadata in failed diagnostic summaries
- `tests/test_gui_workflows.py`
  - batch-fix popup surfaces retry guidance for transient failed items

## Validated Command

- `./.venv/Scripts/python.exe -m pytest tests/test_fixer.py tests/test_interactive.py tests/test_cli_tool_mode.py -k "retry or generate_ai_fix_result or tool_resume_normalizes_apply_results_artifact or tool_resume_normalizes_fix_plan_artifact" tests/test_gui_workflows.py::test_batch_fix_popup_surfaces_failed_item_diagnostic_details -q`
  - result: `6 passed`

## Remaining Gap

- Diagnostics now explain when a retry is appropriate, but the application still does not run a shared automated retry planner for review/fix workflows. That remains a separate follow-on if Milestone 8 needs active retry execution rather than guidance alone.