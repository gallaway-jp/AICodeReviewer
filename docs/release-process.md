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
- `README.md` for current user-facing entry guidance
- `docs/` for maintained reference content
- `RELEASE_NOTES.md` for changelog history

## Pre-Release Checklist

1. Confirm the target version and update `pyproject.toml` if needed.
2. Review `git status` for unrelated or accidental changes.
3. Run focused tests for changed areas.
4. Run the full test suite when the release scope is broad enough to justify it.
5. Validate at least one CLI command path and, when relevant, one GUI path.
6. Update documentation for any behavior, workflow, or configuration changes.
7. Update `RELEASE_NOTES.md` with user-visible changes.

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
python tools/manual_test_gui.py
```

Use more targeted commands when a change is narrow.

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
1. ensure the target commit is clean and tested
2. create the release commit if needed
3. push the branch
4. create the tag and release artifact set according to your team process

If packaging workflows evolve later, extend this document rather than scattering release instructions across unrelated docs.

## After Release

1. Verify the released docs still reflect the tagged state.
2. Verify release notes are readable and accurate.
3. Record any release-specific follow-up work as issues instead of leaving draft notes in `docs/`.

## Related Guides

- [Contributing](contributing.md)
- [Architecture](architecture.md)
- [Documentation Hub](README.md)