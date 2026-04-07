# Milestone 9 Benchmark Source Folder Boundary Handoff

## Summary

This Milestone 9 slice closes the remaining benchmark-browser trust gap that was still letting saved summary payloads influence the GUI's "Open Scenario Folder" action.

## What Changed

- `src/aicodereviewer/gui/benchmark_mixin.py`
  - summary-embedded `project_dir` and `fixture_dir` values are now resolved relative to the configured benchmark fixtures root
  - source-folder paths that escape that fixtures root are ignored instead of being opened
  - when an embedded source path is rejected, the GUI falls back to the saved-run folder rather than opening an arbitrary external directory
- `tests/test_gui_workflows.py`
  - added a regression that verifies a malicious external `project_dir` embedded in a saved summary cannot drive the "Open Scenario Folder" action outside the configured fixtures root

## Security Review Note

- This keeps the Milestone 9 boundary-hardening rule consistent across benchmark browsing: saved summary payloads are treated as persisted app data that must stay within configured artifact or fixture roots before the GUI trusts them.

## Validation

- `python -m pytest tests/test_gui_workflows.py -k benchmark tests/test_benchmark_security.py -q` -> `12 passed, 97 deselected`

## Remaining Milestone 9 Follow-On Work

- keep reviewing remaining internal open/export surfaces that consume persisted or app-generated data
- continue expanding `docs/security.md` as additional whole-code security slices land