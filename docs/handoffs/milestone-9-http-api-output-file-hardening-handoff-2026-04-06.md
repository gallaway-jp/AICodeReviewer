# Milestone 9 HTTP API Output File Hardening Handoff

## Summary

This slice starts Milestone 9 by hardening the local HTTP API's `POST /api/jobs` handling for `output_file`.

## What Changed

- `src/aicodereviewer/http_api.py` now resolves `output_file` before job submission and rejects any destination that escapes both:
  - the requested review root
  - the current workspace directory
- the API returns HTTP `400` with a clear validation error when an out-of-scope path is supplied
- `tests/test_http_api.py` now covers:
  - an allowed in-root report path
  - a rejected out-of-root report path
- `docs/http-api.md` documents the new constraint
- `docs/security.md` now records the Milestone 9 threat model and remediation ledger, including this finding
- `.github/specs/platform-extensibility/spec.md` records this as the first concrete Milestone 9 hardening slice

## Validation

- `python -m pytest tests/test_http_api.py -q` -> `11 passed`

## Remaining Milestone 9 Follow-On Work

- write the broader threat model artifact and remediation ledger
- continue hardening other security-sensitive seams identified during kickoff review