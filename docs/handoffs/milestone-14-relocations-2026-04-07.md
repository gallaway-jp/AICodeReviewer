# Milestone 14 Relocations

## What changed

- Moved the Kiro troubleshooting scripts from the repository root into `tools/diagnostics/kiro/`.
- Moved the top-level model and dropdown smoke scripts into `tools/manual_checks/models/`.
- Updated `tools/run_gui_validator.py` so GUI validation output now goes to `artifacts/gui_validation_report.json` instead of the repository root.
- Updated Milestone 14 maintenance docs and roadmap status to reflect the executed relocations.

## Files relocated

- `debug_kiro_discovery.py` -> `tools/diagnostics/kiro/debug_kiro_discovery.py`
- `diagnose_kiro.py` -> `tools/diagnostics/kiro/diagnose_kiro.py`
- `test_copilot_models.py` -> `tools/manual_checks/models/test_copilot_models.py`
- `test_dropdown_init.py` -> `tools/manual_checks/models/test_dropdown_init.py`
- `test_kiro_complete.py` -> `tools/manual_checks/models/test_kiro_complete.py`
- `test_kiro_dropdown.py` -> `tools/manual_checks/models/test_kiro_dropdown.py`
- `test_kiro_model_selector.py` -> `tools/manual_checks/models/test_kiro_model_selector.py`
- `test_model_autoload.py` -> `tools/manual_checks/models/test_model_autoload.py`

## Repository effect

- the repository root is now cleaner and better aligned with the Milestone 14 layout rules
- contributor diagnostics remain available, but under `tools/` where they are easier to categorize as non-product utilities
- future GUI validation runs no longer default to creating a tracked-looking JSON file at the repository root

## Remaining follow-up

- decide whether any relocated smoke scripts should become real pytest coverage under `tests/`
- remove stale references to the old root-level layout if any are discovered later
- decide whether old generated GUI validation artifacts should be retained under `artifacts/` or treated as disposable local output