# Milestone 8 Credential Reference Slice Handoff

## Summary

This slice implements the first concrete Milestone 8 deliverable: secure credential references for Local LLM API keys.

The Local LLM settings path no longer needs to persist `local_llm.api_key` as plain text in `config.ini` when the value is saved through the GUI. Instead, the app stores the secret in the system keyring and writes a stable reference such as `keyring://local_llm/api_key` into config. Runtime and health-check consumers resolve that reference transparently.

## Implemented

- Added generic keyring-backed credential helpers in `src/aicodereviewer/auth.py`:
  - `build_credential_reference(...)`
  - `resolve_credential_value(...)`
  - `store_config_credential(...)`
  - `clear_config_credential(...)`
- Updated `src/aicodereviewer/backends/local_llm.py` to resolve `local_llm.api_key` references before issuing requests.
- Updated `src/aicodereviewer/backends/health.py` so Local backend health reports explicitly fail the `API Credential` check when a configured keyring reference cannot be resolved.
- Updated GUI settings load/save flow:
  - `src/aicodereviewer/gui/settings_builder.py` now loads the resolved secret value into the Local API key field.
  - `src/aicodereviewer/gui/settings_actions.py` now stores the entered secret in keyring and persists only the reference in config.
- Updated docs in `docs/configuration.md`, `docs/backends.md`, and the Milestone 8 status block in `.github/specs/platform-extensibility/spec.md`.

## Regression Coverage

- `tests/test_config_and_auth.py`
  - keyring reference storage helper
  - keyring reference resolution
  - missing keyring reference detection
- `tests/test_local_llm.py`
  - Local backend constructor resolves `keyring://local_llm/api_key`
- `tests/test_backend_health.py`
  - Local health reports missing keyring-backed credential references explicitly
- `tests/test_gui_workflows.py`
  - Local settings restart flow now asserts config stores only the reference while the reloaded UI still shows the resolved secret

## Validated Commands

- `./.venv/Scripts/python.exe -m pytest tests/test_config_and_auth.py tests/test_local_llm.py tests/test_backend_health.py -q`
  - result: `77 passed, 1 warning`
- `./.venv/Scripts/python.exe -m pytest tests/test_gui_workflows.py -k local_llm_settings_persist_across_app_restart -q`
  - result: `1 passed, 101 deselected`

## Remaining Milestone 8 Gaps

- Shared failure categorization is still not normalized across all backends; auth, permission, transport, timeout, and tool-compatibility failures still need a common diagnostic model.
- Secure credential references currently cover the Local LLM API key flow; additional backend/tool secret surfaces still need the same treatment if they become config-backed.
- Credential lifecycle work is only partially covered here. Rotation and revocation are possible by overwriting or clearing the keyring entry, but there is not yet a dedicated user-facing management surface or audit trail.

## Recommended Next Step

Implement the shared backend diagnostic model next and thread it through backend health plus runtime failure reporting so Milestone 8 can satisfy the remaining failure-classification acceptance criteria.