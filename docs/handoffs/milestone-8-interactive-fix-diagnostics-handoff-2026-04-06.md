# Milestone 8 Interactive Fix Diagnostics Handoff

## Summary

This slice closes the remaining generic failed-fix surface in Milestone 8 by upgrading the legacy interactive terminal `AI FIX` flow to use the structured fix-generation result path.

Interactive fix failures no longer stop at the generic `interactive.fix_failed` line when a categorized diagnostic is available. The CLI now prints the failure category, detailed cause, and remediation hint directly in the terminal review flow.

## Implemented

- Updated `src/aicodereviewer/interactive.py`:
  - `_action_ai_fix(...)` now uses `generate_ai_fix_result(...)` instead of the legacy string-only wrapper
  - failed interactive AI-fix attempts print diagnostic category/detail/hint output when present
  - successful interactive AI-fix preview/apply behavior still uses the generated fixed content exactly as before
- Updated `src/aicodereviewer/lang/en.py` and `src/aicodereviewer/lang/ja.py`:
  - added localized interactive failure-detail and hint lines
- Updated `docs/cli.md` and the Milestone 8 spec status to record the interactive terminal diagnostic surface

## Regression Coverage

- `tests/test_interactive.py`
  - accepted AI fix still applies successfully
  - rejected AI fix still leaves the issue pending
  - failed AI fix now prints the structured diagnostic detail and hint lines

## Validated Command

- `./.venv/Scripts/python.exe -m pytest tests/test_interactive.py -q`

## Remaining Milestone 8 Gap

- Broader retry/backoff guidance remains the main follow-on robustness gap; failure classification and messaging coverage is now present across health, runtime, tool mode, GUI batch fixes, resume artifacts, and the interactive AI-fix surface.