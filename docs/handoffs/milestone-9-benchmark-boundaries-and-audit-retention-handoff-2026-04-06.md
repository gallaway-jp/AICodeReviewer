# Milestone 9 Benchmark Boundaries And Audit Retention Handoff

## Summary

This Milestone 9 slice continued the whole-code security pass into the benchmark browser and local API audit retention.

## What Changed

- `src/aicodereviewer/gui/benchmark_mixin.py`
  - benchmark summary browse/select actions now constrain chosen summary files to the configured saved-runs root
  - summary-referenced report paths that escape the saved-runs root are skipped instead of being opened, previewed, or used for report-directory derivation
- `src/aicodereviewer/http_api.py`
  - local API audit events now flow through the dedicated `aicodereviewer.audit` logger
- `src/aicodereviewer/main.py`
  - logging setup now configures a dedicated rotating audit log sink
- `src/aicodereviewer/config.py`
  - added dedicated audit-log configuration defaults
- `docs/configuration.md`
  - documents the new audit-log settings

## Security Review Decision

- Dedicated retained audit sink: accepted and implemented
- Reason: local API audit events are security-relevant enough to retain independently from general file logging, while still remaining low-volume and easy to rotate

## Validation

- `python -m pytest tests/test_benchmark_security.py tests/test_main_cli.py -k "audit or benchmark" tests/test_gui_workflows.py -k benchmark -q` -> `11 passed, 133 deselected`

## Remaining Milestone 9 Follow-On Work

- keep reviewing other internal file-open/export surfaces to distinguish intentional user-input pickers from implicit-trust artifact loaders
- continue expanding the remediation ledger as additional whole-code security passes land