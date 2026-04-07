# Milestone 14 Release Git Preflight

## What changed

- Added `src/aicodereviewer/release_git_state.py` so the release preflight can inspect local branch and tag state in addition to checked-in metadata.
- Extended `tools/check_release_metadata.py` with optional git checks for current branch, local release-branch presence, and local release-tag presence.
- Extended `tests/test_release_metadata.py` to cover missing and present `release/0.2.0` and `v0.2.0` states.
- Updated the release and repository-maintenance guides to show the git-aware preflight commands.

## Why this matters

- Milestone 14 no longer stops at metadata alignment inside tracked files; maintainers now have an executable check for the remaining operational release steps as well.
- The release workflow can fail fast when the repo is still on `main`, when `release/0.2.0` has not been cut locally, or when the matching `v0.2.0` tag has not been created yet.

## Verified current baseline

- current branch: `main`
- local branches include `main` only
- local tags include `v0.1.0` only
- therefore the git-aware preflight correctly shows that `release/0.2.0` and `v0.2.0` still need explicit operational creation outside the checked-in files

## Intended usage

- inspect metadata plus git state:
  - `python tools/check_release_metadata.py --target-version 0.2.0 --check-git --json`
- require the release branch during release preparation:
  - `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned --check-git --require-release-branch`
- require the tag after merge/tag follow-through:
  - `python tools/check_release_metadata.py --target-version 0.2.0 --check-git --require-release-tag`

## Validation

- `tests/test_release_metadata.py` now covers both metadata alignment and git release-state expectations
- running `python tools/check_release_metadata.py --target-version 0.2.0 --check-git --json` in the current repository reports aligned checked-in metadata alongside the live git baseline of `main`, local branches `['main']`, and local tags `['v0.1.0']`
- running `python tools/check_release_metadata.py --target-version 0.2.0 --check-git --require-release-tag` now fails with the expected missing-tag issue for `v0.2.0`, proving the git gate semantics work as an actual release preflight

Superseded live branch baseline on 2026-04-08:

- the repository now has a local `release/0.2.0` branch, and `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned --check-git --require-release-branch --json` reports an empty `issues` list with `current_branch = release/0.2.0` and `release_branch_present = true`
- the remaining git-side release gap is the still-missing `v0.2.0` tag