# Milestone 14 Release Normalization

## What changed

- Updated `pyproject.toml` from `2.0.0` to `0.2.0` to match the first standardized maintained pre-1.0 release target defined by Milestone 14.
- Moved the current `RELEASE_NOTES.md` `Unreleased` content into a new `v0.2.0` section.
- Reopened an empty `Unreleased` section so future post-release work has a stable landing zone.
- Updated the repository-maintenance guide and roadmap status to reflect that the checked-in metadata surfaces are now aligned.

## Why this matters

- The repository no longer carries a checked-in mismatch between package metadata and the latest versioned release-notes heading.
- Maintainers can now use the strict `tools/check_release_metadata.py --target-version 0.2.0 --require-aligned` mode as a real gate for the remaining release branch and tag steps.

## Validation

- `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned`
- targeted release-metadata tests continue to validate the parser and alignment rules in `tests/test_release_metadata.py`

## Remaining release follow-through

- cut or confirm the explicit `release/0.2.0` branch in Git
- merge that branch back into `main` when the release is ready
- create the matching `v0.2.0` tag from the merged `main` commit