# Milestone 14 Ownership Decisions

## What changed

- Extended `docs/repository-maintenance.md` with explicit owner and destination decisions for the ambiguous top-level files and directories.
- Updated the Milestone 14 roadmap status so it now reflects that the repository has moved beyond generic inventory into named ownership guidance.
- The relocation follow-up has now been executed, so these decisions are no longer only planned destinations.

## Decisions recorded

- `debug_kiro_discovery.py` and `diagnose_kiro.py`
  - classify as contributor diagnostics
  - executed destination: `tools/diagnostics/kiro/`
- top-level model/dropdown `test_*.py` scripts
  - classify as manual smoke checks, not canonical pytest coverage
  - executed destination: `tools/manual_checks/models/`
- `gui_validation_report.json`
  - classify as generated validation output
  - executed default output path: `artifacts/gui_validation_report.json`
  - root-level report removed after the output path change
- `.kilocode/` and `.vscode/`
  - classify as local workspace configuration
  - keep ignored and out of maintained repository surfaces

## Why this matters

- Milestone 14 now has specific relocation targets instead of a generic “review later” bucket.
- The first cleanup execution step is complete without touching clearly maintained source, docs, or benchmark inputs.

## Files updated

- `docs/repository-maintenance.md`
- `.github/specs/platform-extensibility/spec.md`
- `docs/handoffs/milestone-14-ownership-decisions-2026-04-07.md`

## Next steps

- decide whether any relocated smoke scripts should become real pytest coverage under `tests/`
- prune or archive obsolete duplicate manual checks once the retained coverage surface is clear
- continue Milestone 14 release-normalization work after the remaining cleanup conversions are settled