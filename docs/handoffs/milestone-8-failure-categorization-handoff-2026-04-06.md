# Milestone 8 Failure Categorization Slice Handoff

## Summary

This slice implements the second concrete Milestone 8 deliverable: shared failure categorization for backend health and connection diagnostics.

The application now carries structured failure metadata through backend health checks, live connection tests, tool-mode health JSON, human CLI connection output, and the GUI health dialog. Instead of collapsing failures into generic pass/fail messaging, checks can now report both a failure `category` and an `origin`.

## Implemented

- Added categorized health metadata in `src/aicodereviewer/backends/health.py`:
  - `CheckResult.category`
  - `CheckResult.origin`
  - `HealthReport.failure_categories`
- Added backend connection diagnostic hook in `src/aicodereviewer/backends/base.py`:
  - `validate_connection_diagnostic()`
- Implemented categorized live connection diagnostics for built-in backends:
  - `src/aicodereviewer/backends/bedrock.py`
  - `src/aicodereviewer/backends/kiro.py`
  - `src/aicodereviewer/backends/copilot.py`
  - `src/aicodereviewer/backends/local_llm.py`
- Updated `src/aicodereviewer/backends/health.py` to classify prerequisite and connection-test failures into categories such as:
  - `auth`
  - `permission`
  - `transport`
  - `timeout`
  - `tool_compatibility`
  - `configuration`
  - `provider`
- Updated output surfaces:
  - `src/aicodereviewer/main.py`
    - `tool health` JSON now includes per-check `category` / `origin` plus report-level `failure_categories`
    - `--check-connection` now prints categorized failure details and suggested fixes
  - `src/aicodereviewer/gui/health_mixin.py`
    - GUI health dialog now shows category/stage metadata for reported checks
- Added localized health/connection metadata labels in:
  - `src/aicodereviewer/lang/en.py`
  - `src/aicodereviewer/lang/ja.py`

## Regression Coverage

- `tests/test_backend_health.py`
  - `HealthReport.failure_categories`
  - categorized `_run_connection_test(...)` result from backend diagnostics
- `tests/test_main_cli.py`
  - `--check-connection` now includes failure-category output
- `tests/test_cli_tool_mode.py`
  - tool-mode health JSON includes `failure_categories`, per-check `category`, and per-check `origin`
- `tests/test_gui_workflows.py -k health`
  - GUI health workflow still completes and restores controls after dialog rendering changes

## Validated Commands

- `./.venv/Scripts/python.exe -m pytest tests/test_backend_health.py tests/test_main_cli.py tests/test_cli_tool_mode.py -q`
  - result: `71 passed`
- `./.venv/Scripts/python.exe -m pytest tests/test_gui_workflows.py -k health -q`
  - result: `3 passed, 99 deselected`

## Remaining Milestone 8 Gaps

- Retry/backoff and recovery guidance is still mostly static hint text; the application does not yet provide a shared remediation planner or richer automated retry policy.
- Credential lifecycle support remains partial. The Local LLM keyring-backed reference flow exists, but explicit rotation/revocation/audit surfaces are still limited.
- Failure categorization is now shared for health and connection diagnostics, but broader runtime error propagation outside health-check paths can still be normalized further.

## Recommended Next Step

Extend the same categorized diagnostic model into runtime review/fix execution failures so non-health backend errors surface with the same auth/permission/transport/timeout/provider breakdown.