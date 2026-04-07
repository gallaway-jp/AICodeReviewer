# Milestone 14 Release-Metadata Preflight

## What changed

- Added `src/aicodereviewer/release_metadata.py` to evaluate alignment between `pyproject.toml`, `src/aicodereviewer/__init__.py`, and `RELEASE_NOTES.md`.
- Added `tools/check_release_metadata.py` so maintainers can run a release-metadata preflight from the repository root.
- Added `tests/test_release_metadata.py` to lock the parser and alignment logic.
- Updated the release-process guide and Milestone 14 roadmap status to reference the new preflight check.

## Why this matters

- Milestone 14 release normalization is no longer only a documented intention; contributors now have an explicit command that reports the current mismatch and can fail fast on a release branch when metadata is not aligned.
- The same check can be reused later in CI or release tasks without re-deriving the version-alignment rules from prose.

## Intended usage

- report current state:
  - `python tools/check_release_metadata.py`
- enforce release alignment on a release branch:
  - `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned`

## Validation

- `tests/test_release_metadata.py` covers heading parsing, mismatch reporting, and aligned target-version acceptance.
- running `python tools/check_release_metadata.py --json` in the current repository state reports the expected mismatch: `pyproject.toml` is still `2.0.0` while the latest versioned heading in `RELEASE_NOTES.md` is `v2.0.1`.
- after the later `0.2.0` normalization and runtime-version alignment work, `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned --json` now reports `package_version = 0.2.0`, `application_version = 0.2.0`, `latest_release_heading = v0.2.0`, and an empty `issues` list.

## Next steps

- use this baseline mismatch report as the before-state for the actual `release/0.2.0` metadata alignment change set
- rerun the strict target-version mode after the alignment edit to prove the cutover is complete