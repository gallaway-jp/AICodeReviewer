# Milestone 14 Top-Level Inventory

## What changed

- Extended `docs/repository-maintenance.md` with the first explicit top-level inventory pass for the repository root.
- Updated the Milestone 14 status block in `.github/specs/platform-extensibility/spec.md` so it now reflects that actual classification work has started, not just abstract cleanup planning.

## Inventory decisions recorded

- Keep at root:
  - source, tests, tools, docs, benchmarks, examples, legal files, primary packaging/config files
- Keep but treat as generated or reproducible:
  - `artifacts/`, `.benchmarks/`, `build/`, `dist/`
- Delete or recreate freely:
  - empty temp projects, empty benchmark scratch dirs, and one-off local run logs
- Review before relocating or deleting:
  - top-level debug helpers
  - top-level targeted test scripts outside `tests/`
  - local validation outputs
  - workspace-local directories such as `.kilocode/` and `.vscode/`
- Revisit during release normalization:
  - `AICodeReviewer.spec`, `build_exe.bat`, and `requirements.txt`

## Why this matters

- Milestone 14 now has a concrete cleanup decision framework for the actual repository root instead of only high-level layout goals.
- The next cleanup step can be narrow and reversible: move or retire the ambiguous top-level files instead of touching clearly maintained source or documentation areas.

## Files updated

- `docs/repository-maintenance.md`
- `.github/specs/platform-extensibility/spec.md`
- `docs/handoffs/milestone-14-top-level-inventory-2026-04-07.md`

## Next steps

- decide owners and destinations for the review-before-relocating items
- clean up empty temp projects and disposable local logs as local maintenance rather than milestone decisions
- prepare the release-normalization execution work for `release/0.2.0`