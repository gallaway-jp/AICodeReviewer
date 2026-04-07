# Milestone 14 Manual-Check Pruning

## What changed

- Removed the four overlapping Kiro dropdown smoke scripts from `tools/manual_checks/models/`.
- Kept the two manual scripts that still provide live environment probe value.
- Updated the maintenance plan, roadmap status, and manual-check audit to reflect the narrower retained manual-check surface.

## Removed scripts

- `tools/manual_checks/models/test_dropdown_init.py`
- `tools/manual_checks/models/test_kiro_complete.py`
- `tools/manual_checks/models/test_kiro_dropdown.py`
- `tools/manual_checks/models/test_kiro_model_selector.py`

## Retained scripts

- `tools/manual_checks/models/test_copilot_models.py`
- `tools/manual_checks/models/test_model_autoload.py`

## Why these were removed

- they duplicated static wiring checks that are now covered by `tests/test_backend_model_cache.py`, `tests/test_kiro_backend.py`, `tests/test_gui_workflows.py`, and `tests/test_health_mixin.py`
- keeping them alongside the new pytest coverage would leave two maintenance surfaces for the same Kiro dropdown behavior without adding much diagnostic value

## Why the retained scripts remain

- `test_copilot_models.py` still acts as a live Copilot auth and SDK-backed discovery probe
- `test_model_autoload.py` still acts as a live local-endpoint and model auto-load probe

## Validation

- `python -m pytest tests/test_health_mixin.py -q` remained green before the prune and still covers the removed Kiro dropdown wiring path

## Next steps

- continue Milestone 14 release normalization work for `release/0.2.0`
- decide later whether the retained live probes should gain a short contributor note or stay self-documenting