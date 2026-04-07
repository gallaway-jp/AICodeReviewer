# Milestone 8 Per-Item Fix Diagnostics And Secret Scope Decision Handoff

## Summary

This slice closes the remaining normalization gap inside tool-mode fix workflows by extending the shared categorized diagnostic model into per-item fix-generation and apply-fixes failures.

It also records the Milestone 8 scope decision for secret management: the current repository baseline does not need a broader multi-secret audit or inventory surface beyond the Local LLM Rotate / Revoke workflow.

## Implemented

- Added explicit diagnostic construction support in `src/aicodereviewer/diagnostics.py`:
  - `build_failure_diagnostic(...)`
- Added structured fix-generation results in `src/aicodereviewer/fixer.py`:
  - `FixGenerationResult`
  - `generate_ai_fix_result(...)`
- `apply_ai_fix(...)` now remains as the legacy string-only wrapper, but the real failure classification now happens in `generate_ai_fix_result(...)` so callers that need diagnostics do not lose root-cause information.
- Updated `src/aicodereviewer/main.py`:
  - tool-mode `fix-plan` now emits per-item `diagnostic` payloads when an issue-level fix attempt fails
  - tool-mode `apply-fixes` now emits per-item `diagnostic` payloads when an individual file apply fails
  - stale/missing file paths during fix generation or fix application are classified as `configuration` instead of collapsing into generic provider failures
- Resume normalization continues to preserve item-level diagnostic metadata because fix/result items are already copied through as dictionaries.

## Secret Scope Decision

- Milestone 8 does **not** need a broader multi-secret audit or inventory/management surface in the current repository baseline.
- Rationale:
  - the only credential currently using the new secure reference path is `local_llm.api_key`
  - the current workflow already supports secure storage, masked config persistence, explicit rotation, and explicit revocation for that credential
  - adding a larger secret-management dashboard or audit log now would widen scope without a second in-repo secret-bearing backend to justify the abstraction
- Follow-on guidance:
  - if additional backends or addons begin storing managed secrets through the same keyring-reference path, revisit this decision and introduce a shared credential inventory/audit surface then

## Regression Coverage

- `tests/test_fixer.py`
  - structured fix-generation diagnostics for empty backend results and exception failures
- `tests/test_cli_tool_mode.py`
  - per-item `fix-plan` failure diagnostics
  - per-item `apply-fixes` failure diagnostics
  - fix-plan/apply-results resume normalization still preserves item-level diagnostic payloads

## Validated Commands

- `./.venv/Scripts/python.exe -m pytest tests/test_fixer.py tests/test_cli_tool_mode.py -q`
  - result: `34 passed`

## Remaining Milestone 8 Gaps

- Retry/backoff guidance is still mostly static text; there is no shared remediation planner yet.
- The broader secret-management surface is intentionally deferred, not missing by accident.

## Recommended Next Step

Leave secret-management scope where it is for Milestone 8 and focus any remaining effort on recovery guidance, retry policy, or other authenticated-tool robustness work rather than building a broader credential dashboard prematurely.