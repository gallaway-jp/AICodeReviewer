# Milestone 14 Repository Maintenance Kickoff

## What changed

- Audited the current repository state against the Milestone 14 goals for branching policy, release/version normalization, and repository cleanup.
- Updated the roadmap spec so the Milestone 14 section now includes a concrete current-status block instead of only an aspirational scope list.

## Current repository signals

- Branch state:
  - `git branch --all` currently shows only `main` and `origin/main`
  - the branch families named in the milestone (`milestone/*`, `feature/*`, `release/*`) are not yet documented as active conventions in repo docs or visible in git state
- Versioning state:
  - `pyproject.toml` currently reports version `2.0.0`
  - `RELEASE_NOTES.md` contains an `Unreleased` section plus a documented `v2.0.1` milestone entry
  - `git tag --list` currently returns only `v0.1.0`
  - this means the repository does not yet have one coherent version-story across package metadata, changelog history, and tags
- Maintainer process state:
  - `docs/contributing.md` and `docs/release-process.md` describe setup, validation, and release-note hygiene, but they do not yet define branch naming, merge expectations, CI gates, or a release-cut flow tied to `main`
- Cleanup state:
  - the current working tree is heavily in flight, with many modified and untracked docs, source, tests, and generated assets
  - Milestone 14 cleanup work therefore needs policy and categorization first, not immediate deletion or archiving

## Milestone 14 gaps now made explicit

- No documented branch taxonomy for `main`, `milestone/*`, `feature/*`, and `release/*`
- No documented merge policy or minimum validation bar by branch type
- No normalized policy for reconciling current package version, changelog releases, and git tags into a first official release line
- No recorded cleanup inventory separating live maintained artifacts from legacy or incidental repository clutter

## Recommended next steps

1. Write the branch and merge policy into contributor-facing docs, including when work lands directly on `main` versus a milestone, feature, or release branch.
2. Define the version normalization plan: how the actual `v0.1.0` release, the later internal `v2.0.1` milestone entry, and the current `2.0.0` metadata should be reconciled into the first maintained release tag.
3. Capture a cleanup inventory that distinguishes maintained docs/handoffs/artifacts from candidates for archival, deletion, or relocation.
4. Only after those rules exist, add any scripted cleanup or CI enforcement so repository maintenance follows a documented standard instead of one-off manual judgment.

## Files updated

- `.github/specs/platform-extensibility/spec.md`
- `docs/handoffs/milestone-14-repository-maintenance-kickoff-2026-04-07.md`