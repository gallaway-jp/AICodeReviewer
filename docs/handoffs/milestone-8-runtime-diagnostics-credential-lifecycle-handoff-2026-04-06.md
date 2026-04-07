# Milestone 8 Runtime Diagnostics And Credential Lifecycle Slice Handoff

## Summary

This slice extends the earlier Milestone 8 work in two directions:

- the shared categorized diagnostic model now propagates through runtime review failures and tool-mode fix execution failures instead of stopping at health and connection checks
- the Local LLM keyring-backed credential flow now has explicit Settings-tab rotation and revocation actions on top of the existing secure reference model

## Implemented

- Added a shared failure diagnostic helper in `src/aicodereviewer/diagnostics.py`:
  - `FailureDiagnostic`
  - `failure_category_from_exception(...)`
  - `failure_category_from_http_status(...)`
  - `diagnostic_from_exception(...)`
- Updated `src/aicodereviewer/backends/health.py` to reuse the shared classifier instead of keeping a health-only copy.
- Propagated structured failure diagnostics through runtime execution state:
  - `src/aicodereviewer/execution/models.py`
    - `ReviewJob.error_diagnostic`
    - `ReviewJob.fail_with_error(..., diagnostic=...)`
  - `src/aicodereviewer/execution/events.py`
    - `JobFailed.error_diagnostic`
  - `src/aicodereviewer/execution/service.py`
    - review execution failures now classify as runtime diagnostics with `origin="review"`
  - `src/aicodereviewer/execution/runtime.py`
    - runtime-owned failures now classify with `origin="runtime"`
- Updated serialized runtime/API surfaces:
  - `src/aicodereviewer/http_api.py`
    - job detail payloads now include `error_diagnostic`
    - serialized `job.failed` events now include `error_diagnostic`
  - `src/aicodereviewer/main.py`
    - tool-mode `review`, `fix-plan`, and `apply-fixes` failures now emit `error.diagnostic`
    - spec-file load failures now classify as `configuration` instead of returning only a flat message
- Added explicit Local LLM credential lifecycle UI:
  - `src/aicodereviewer/gui/settings_builder.py`
    - Local API key row now renders `Rotate` and `Revoke` buttons
  - `src/aicodereviewer/gui/settings_actions.py`
    - `rotate_local_llm_api_key()` clears the keyring secret and UI entry while leaving the config reference in place for replacement-on-save flows
    - `revoke_local_llm_api_key()` clears the keyring secret, empties the config value, and saves immediately
  - `src/aicodereviewer/gui/settings_mixin.py`
    - added host methods for the new settings actions
  - localized labels/tooltips/toasts added in:
    - `src/aicodereviewer/lang/en.py`
    - `src/aicodereviewer/lang/ja.py`

## Regression Coverage

- `tests/test_execution_service.py`
  - failed jobs now retain structured diagnostics
  - `job.failed` events carry categorized review-failure metadata
- `tests/test_http_api.py`
  - failed job payloads and serialized runtime events expose `error_diagnostic`
- `tests/test_cli_tool_mode.py`
  - tool-mode `review`, `fix-plan`, and `apply-fixes` error envelopes now include categorized diagnostics
- `tests/test_settings_actions.py`
  - Local credential rotate/revoke controller actions clear the right state and produce the right toasts
- `tests/test_gui_workflows.py`
  - Local LLM API key still persists across restart through the keyring-backed reference path
  - Settings `Rotate` / `Revoke` buttons work against the real GUI widgets and config/keyring flow
- `tests/test_execution_runtime.py`
  - runtime queue behavior still passes after the failure-model change

## Validated Commands

- `./.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_http_api.py tests/test_cli_tool_mode.py tests/test_settings_actions.py -q`
  - result: `73 passed`
- `./.venv/Scripts/python.exe -m pytest tests/test_gui_workflows.py -k "local_llm_settings_persist_across_app_restart or local_llm_api_key_rotate_and_revoke_buttons_manage_keyring_reference" -q`
  - result: `2 passed, 101 deselected`
- `./.venv/Scripts/python.exe -m pytest tests/test_execution_runtime.py -q`
  - result: `2 passed`

## Remaining Milestone 8 Gaps

- Retry/backoff guidance is still mostly static text; there is no shared remediation planner yet.
- Per-issue fix-generation failures and per-item apply-fixes failures are covered in the follow-on handoff `docs/handoffs/milestone-8-item-fix-diagnostics-scope-decision-handoff-2026-04-06.md`.
- The broader multi-secret audit or inventory surface has been explicitly deferred for Milestone 8 because the current repository baseline only manages one keyring-backed credential path (`local_llm.api_key`).

## Recommended Next Step

Focus any remaining Milestone 8 effort on recovery guidance or retry policy for authenticated-tool failures rather than widening the secret-management UX beyond the current Local LLM Rotate / Revoke path.