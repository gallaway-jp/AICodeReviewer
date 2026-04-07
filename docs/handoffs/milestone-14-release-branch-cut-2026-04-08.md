# Milestone 14 Release Branch Cut

## What changed

- Cut the local `release/0.2.0` branch from the current repository state.
- Re-ran the git-aware release preflight against the new branch baseline.
- Updated the Milestone 14 status docs to reflect that the branch-side release step is now complete locally.

## Verified current baseline

- current branch: `release/0.2.0`
- local branches include `main` and `release/0.2.0`
- local tags still include only `v0.1.0`
- `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned --check-git --require-release-branch --json` reports an empty `issues` list

## Remaining release follow-through

- keep validating the branch-local release work on `release/0.2.0`
- create the matching `v0.2.0` tag after the release branch is ready to merge
- rerun `python tools/check_release_metadata.py --target-version 0.2.0 --check-git --require-release-tag` after tagging