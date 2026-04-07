# Milestone 9 Benchmark Fixture Manifest Boundary Handoff

## Summary

This Milestone 9 slice extends the benchmark-browser hardening work down into benchmark fixture manifest loading itself.

## What Changed

- `src/aicodereviewer/benchmarking.py`
  - discovered benchmark fixtures now resolve `project_dir`, `diff_file`, and `spec_file` through a shared helper that rejects paths escaping the configured fixtures root
  - `discover_fixtures(...)` now passes the resolved fixtures root as the allowed boundary so both GUI catalog loading and CLI benchmark evaluation inherit the same fail-closed validation
- `tests/test_benchmark_security.py`
  - added a regression that verifies discovered fixture manifests cannot point `project_dir` outside the configured fixtures root
- `tests/test_gui_workflows.py`
  - added a GUI workflow regression that verifies the benchmark catalog load fails closed when a fixture manifest escapes the configured fixtures root

## Security Review Note

- This closes another persisted-data trust seam in the benchmark workflow: fixture manifests discovered under the configured root are no longer allowed to redirect review inputs to arbitrary external paths.

## Validation

- `python -m pytest tests/test_benchmark_security.py tests/test_gui_workflows.py -k benchmark -q` -> `14 passed, 97 deselected`

## Remaining Milestone 9 Follow-On Work

- keep reviewing remaining internal open/export surfaces and persisted-data loaders outside the benchmark workflow
- continue expanding `docs/security.md` as additional whole-code security slices land