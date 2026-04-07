# Milestone 14 Manual-Check Audit

## What changed

- Audited the relocated model and dropdown manual checks under `tools/manual_checks/models/` against the existing pytest suite.
- Added direct automated coverage for Kiro dropdown refresh and apply behavior in `tests/test_health_mixin.py`.
- Updated Milestone 14 maintenance docs and roadmap status to distinguish retained live environment probes from overlapping static smoke scripts.
- The overlapping Kiro dropdown smoke scripts were then removed, so this audit now reflects the retained surface rather than only a recommendation.

## Coverage outcome

- Keep as live environment probes:
  - `tools/manual_checks/models/test_copilot_models.py`
  - `tools/manual_checks/models/test_model_autoload.py`
- Pruned after automated coverage closed the overlap:
  - `tools/manual_checks/models/test_dropdown_init.py`
  - `tools/manual_checks/models/test_kiro_complete.py`
  - `tools/manual_checks/models/test_kiro_dropdown.py`
  - `tools/manual_checks/models/test_kiro_model_selector.py`

## Why the split is reasonable

- the retained scripts still provide operator value because they exercise real local environment state such as Copilot auth, CLI availability, and local model endpoints
- the overlapping Kiro dropdown scripts mainly check static wiring, cached discovery seams, backend model fields, and settings persistence that are now covered in pytest

## Automated coverage now in place

- `tests/test_backend_model_cache.py` covers Kiro and Copilot model-cache keying
- `tests/test_copilot_backend.py` covers Copilot model discovery behavior
- `tests/test_local_model_discovery.py` covers local model auto-load behavior with mocked discovery seams
- `tests/test_kiro_backend.py` covers Kiro backend model handling and command construction
- `tests/test_gui_workflows.py` covers persisted Kiro settings state across app restart
- `tests/test_health_mixin.py` now covers Kiro dropdown refresh/apply wiring

## Validation

- `python -m pytest tests/test_health_mixin.py -q` -> `4 passed`

## Next steps

- keep the live environment probes under `tools/manual_checks/models/` for backend and local-runtime troubleshooting
- continue Milestone 14 with release normalization and any remaining root-layout cleanup that still lacks an explicit owner