# Milestone 14 Cleanup Plan

## What changed

- Added `docs/repository-maintenance.md` as the maintained cleanup and repository-standardization plan for Milestone 14.
- Updated the docs hub so the maintenance plan is discoverable alongside contributor and release guidance.
- Updated the Milestone 14 status block in `.github/specs/platform-extensibility/spec.md` so it reflects that cleanup planning now exists and that execution is the next step.

## Plan contents

- repository layout classes for maintained source, curated docs, benchmark inputs, generated outputs, and review-before-prune files
- a minimal layout expectation for long-term repository structure
- a phased execution plan covering inventory, ignore hygiene, release normalization, retention rules, and later enforcement
- the staged `release/0.2.0` normalization flow as the first official standardized release path

## Why this step matters

- Milestone 14 needed more than branch policy; it also needed a non-destructive cleanup plan so future repository pruning is based on documented ownership and retention rules.
- The current working tree is too active to justify immediate cleanup actions, so documenting the inventory and phases first keeps maintenance work reversible and explicit.

## Files updated

- `docs/repository-maintenance.md`
- `docs/README.md`
- `.github/specs/platform-extensibility/spec.md`
- `docs/handoffs/milestone-14-cleanup-plan-2026-04-07.md`

## Next steps

- perform the first explicit inventory pass over top-level files and folders using the categories in `docs/repository-maintenance.md`
- decide which cleanup items should be handled by ignore rules, relocation, archival, or deletion
- use the documented `release/0.2.0` flow when version normalization work is ready