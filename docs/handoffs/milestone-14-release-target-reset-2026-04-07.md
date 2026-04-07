# Milestone 14 Release Target Reset

## What changed

- Superseded the temporary `v2.1.0` Milestone 14 release target with `v0.2.0`.
- Updated the checked-in package version, release notes, tests, and active release-process guidance to use the `0.2.0` target.
- Kept the earlier `v2.0.0` and `v2.0.1` entries in `RELEASE_NOTES.md` as internal repository milestones from the earlier arbitrary GUI-era version jump instead of the forward maintained release line.

## Why this matters

- The repository now reflects the intended project maturity level: a maintained pre-1.0 release line rather than an implied post-2.0 stability promise.
- Milestone 14 release normalization still has an executable preflight, but it now targets `release/0.2.0` and `v0.2.0` instead of the previously assumed `2.1.0` line.

## Validation target

- strict metadata alignment: `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned`
- git-aware release-branch readiness: `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned --check-git --require-release-branch`
- git-aware release-tag readiness: `python tools/check_release_metadata.py --target-version 0.2.0 --check-git --require-release-tag`

## Verified current state

- `python -m pytest tests/test_release_metadata.py -q` passes with the retargeted `0.2.0` expectations
- `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned --json` reports an empty `issues` list with `package_version = 0.2.0` and `latest_release_heading = v0.2.0`
- the live git-aware preflight still reports the expected remaining operational gap: the repository is on `main`, the historical `v0.1.0` tag is still the only observed local tag, and `v0.2.0` has not been created yet

## Remaining release follow-through

- cut or confirm the explicit `release/0.2.0` branch in Git
- merge that branch back into `main` when the release is ready
- create the matching `v0.2.0` tag from the merged `main` commit