# Release Process

This guide describes the maintainer workflow for preparing and documenting a release.

It is intentionally lightweight and repository-oriented. It does not assume any external release automation beyond Git, tests, and the current packaging metadata.

## Release Goals

Each release should leave the repository in a state where:
- code changes are validated
- docs match behavior
- release notes describe the meaningful changes
- packaging metadata is coherent with the intended version

## Source Of Truth

Use these files as the canonical release references:
- `pyproject.toml` for package version and Python requirement
- `src/aicodereviewer/__init__.py` for the runtime `__version__` constant exposed inside the application
- `README.md` for current user-facing entry guidance
- `docs/` for maintained reference content
- `RELEASE_NOTES.md` for changelog history

## Branch Roles In The Release Flow

- `main`
	- integration branch for validated, releasable work
- `milestone/<number>-<slug>`
	- roadmap execution branch for coordinated multi-change milestone work
- `feature/<slug>`
	- narrow branch for isolated implementation or documentation work
- `release/<version>`
	- release-preparation branch where version alignment, release-note cutover, and final validation happen immediately before merge and tagging

## Versioning Policy

- Use semantic versioning in `MAJOR.MINOR.PATCH` form.
- Treat `pyproject.toml` as the package-build source of truth for the next release version.
- Keep unreleased work in the `Unreleased` section of `RELEASE_NOTES.md` until a `release/<version>` branch is cut.
- Only bump the package version as part of the release flow, on a `release/*` branch, immediately before that branch is merged into `main`.
- Do not advance versions opportunistically on feature or milestone branches.

## Historical Normalization Plan

Milestone 14 treats `v0.1.0` as the only actual historical release and treats the later `v2.0.x` changelog entries as internal repository milestones rather than published releases.

Use this one-time normalization plan:

1. Preserve the existing historical notes, including `v0.1.0`, `v2.0.0`, and `v2.0.1`, but distinguish the tagged `v0.1.0` release from the later internal `v2.0.x` repository milestones rather than rewriting that history.
2. Treat the current mismatch between `pyproject.toml`, `RELEASE_NOTES.md`, and git tags as a repository-maintenance issue to be corrected in the first standardized release flow.
3. Cut the first standardized maintained release as `v0.2.0` on a `release/0.2.0` branch so the repository reflects that the product is still pre-1.0, while preserving the documented `v2.0.x` notes as internal repository milestones rather than the forward release line.
4. On that release branch, align `pyproject.toml`, `RELEASE_NOTES.md`, and the final git tag to the same `0.2.0` version before merging back to `main`.
5. After `v0.2.0`, continue future maintained releases from aligned `release/<version>` branches and matching tags on the pre-1.0 line until the project is ready for a deliberate `1.0.0` cutover.

## Pre-Release Checklist

1. Confirm the target version and update `pyproject.toml` if needed.
2. Review `git status` for unrelated or accidental changes.
3. Run focused tests for changed areas.
4. Run the full test suite when the release scope is broad enough to justify it.
5. Validate at least one CLI command path and, when relevant, one GUI path.
6. Rebuild the Windows release asset pair with `build_exe.bat` and confirm it regenerates both `dist/AICodeReviewer.exe` and `dist/AICodeReviewer.exe.sha256`.
7. Update documentation for any behavior, workflow, or configuration changes.
8. Update `RELEASE_NOTES.md` with user-visible changes.
9. Confirm `src/aicodereviewer/__init__.py` keeps `__version__` aligned with `pyproject.toml`.

## Windows Release Assets

The current Windows release flow is built around the checked-in packaging entry points:

- `AICodeReviewer.spec`
- `build_exe.bat`

The validated maintainer path is:

```bash
build_exe.bat
```

That script now:

- uses the repository `.venv` interpreter when present
- rebuilds the executable from the checked-in `AICodeReviewer.spec` file rather than regenerating the spec from `main.py`
- uses the maintained icon asset at `src/aicodereviewer/assets/icon.ico` instead of depending on ignored `build/` state
- refreshes third-party license outputs before packaging
- regenerates the release checksum file alongside the executable

The expected releasable asset pair is:

- `dist/AICodeReviewer.exe`
- `dist/AICodeReviewer.exe.sha256`

## Documentation Checklist

If the release changes behavior, check these areas:
- `README.md` for top-level install or quick-start changes
- `docs/backends.md` for backend setup or behavior changes
- `docs/cli.md` for flag or workflow changes
- `docs/gui.md` for GUI workflow changes
- `docs/configuration.md` for new defaults or settings
- `docs/review-types.md` for review inventory or semantics changes
- `examples/` for walkthroughs and sample commands if they changed

## Validation Commands

Typical commands:

```bash
pytest -v
python -m aicodereviewer --help
python tools/check_release_metadata.py
python tools/manual_test_gui.py
build_exe.bat
```

Use more targeted commands when a change is narrow.

For the `release/<version>` cutover, run the metadata check in strict mode before merge and tagging:

```bash
python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned
```

When you want the same command to validate local branch/tag readiness as well:

```bash
python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned --check-git --require-release-branch
```

After the merge and tag steps are complete, confirm the matching tag exists locally:

```bash
python tools/check_release_metadata.py --target-version 0.2.0 --check-git --require-release-tag
```

## Changelog Rules

Keep `RELEASE_NOTES.md` focused on:
- user-visible additions
- important fixes
- breaking changes
- historical context only when it still matters

Do not use release notes as the main install guide or config reference.

## Tagging And Publishing

This repository does not currently encode a single mandatory publish pipeline in docs.

If you publish a release:
1. cut or update the matching `release/<version>` branch
2. ensure the target commit is clean and tested
3. align `pyproject.toml`, `RELEASE_NOTES.md`, and any release packaging metadata to the same version
4. merge the release branch into `main`
5. create the matching tag from the merged `main` commit
6. run `build_exe.bat` and confirm the regenerated `dist/AICodeReviewer.exe` plus `dist/AICodeReviewer.exe.sha256` pair matches the release commit you are publishing
7. push the branch and tag, then publish the release artifact set according to your team process

If packaging workflows evolve later, extend this document rather than scattering release instructions across unrelated docs.

## After Release

1. Verify the released docs still reflect the tagged state.
2. Verify release notes are readable and accurate.
3. Record any release-specific follow-up work as issues instead of leaving draft notes in `docs/`.

## Related Guides

- [Contributing](contributing.md)
- [Architecture](architecture.md)
- [Documentation Hub](README.md)