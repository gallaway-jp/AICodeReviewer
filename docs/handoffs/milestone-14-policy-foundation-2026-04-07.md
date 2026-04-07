# Milestone 14 Policy Foundation

## What changed

- Added explicit branch and merge workflow guidance to `docs/contributing.md`.
- Added versioning, release-branch, and historical normalization guidance to `docs/release-process.md`.
- Updated the Milestone 14 status block in `.github/specs/platform-extensibility/spec.md` so it now reflects the newly documented policy foundation and the remaining cleanup work.

## Policy decisions recorded

- Branch taxonomy:
  - `main` for validated releasable integration
  - `milestone/<number>-<slug>` for roadmap-scale work
  - `feature/<slug>` for narrow scoped changes
  - `release/<version>` for release preparation, version alignment, and tagging
- Merge model:
  - prefer squash-style history cleanup for narrow feature work
  - keep milestone work off `main` until the slice is documented and validated
  - do version bumps and release-note cutover only on `release/*` branches
- Validation gate:
  - there are currently no checked-in CI workflows under `.github/workflows/`, so merge gating is documentation-backed and manual for now
- Version normalization plan:
  - preserve `v0.1.0` as the only tagged historical release and keep `v2.0.x` as internal repository-versioning context
  - cut the first standardized maintained pre-1.0 release as `v0.2.0`
  - align `pyproject.toml`, `RELEASE_NOTES.md`, and the final git tag on `release/0.2.0` before merging back to `main`

## Repository facts behind the policy

- `git branch --all` currently shows only `main` and `origin/main`
- `git tag --list` currently shows only `v0.1.0`
- `pyproject.toml` currently reports version `2.0.0`
- `RELEASE_NOTES.md` currently includes an `Unreleased` section and a documented `v2.0.1` internal milestone entry

## Remaining Milestone 14 work

- record a cleanup inventory that separates maintained assets from legacy or incidental repository clutter
- decide what cleanup should be scripted versus manual
- execute the eventual `release/0.2.0` normalization flow instead of only documenting it
- add CI enforcement later if the repository adopts checked-in workflows for merge validation

## Files updated

- `docs/contributing.md`
- `docs/release-process.md`
- `.github/specs/platform-extensibility/spec.md`
- `docs/handoffs/milestone-14-policy-foundation-2026-04-07.md`