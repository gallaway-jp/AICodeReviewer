# Contributing

This project accepts changes to code, tests, docs, and examples. The documentation revamp expects contributors to keep docs aligned with behavior.

## Development Setup

```bash
git clone <repo-url>
cd AICodeReviewer
pip install -e ".[all]"
```

## Test Commands

Run the full test suite:

```bash
pytest -v
```

Run a focused test file:

```bash
pytest tests/test_scanner.py -v
```

Run the holistic benchmark tests:

```bash
pytest tests/test_benchmarking.py tests/test_run_holistic_benchmarks.py -v
```

Run the holistic benchmark runner against a configured backend:

```bash
python tools/run_holistic_benchmarks.py --backend local --skip-health-check
```

See [Quality Benchmarks](benchmarks.md) for the fixture layout, runner options, and update expectations.

For tranche-by-tranche repository adjudication and Milestone 13 execution workflow, use [Review Quality Program](review-quality-program.md).
Record completed tranche outcomes and approved benchmark-reviewer changes in [Review Quality Log](review-quality-log.md).

Manual GUI validation:

```bash
python tools/manual_test_gui.py
```

## Branching And Merge Workflow

Use the following branch families for maintained work:

- `main`
	- the default releasable branch
	- keep it in a state that can be validated and tagged without reconstructing missing docs or version metadata later
- `milestone/<number>-<slug>`
	- use for multi-change roadmap work that spans several commits or sub-features
	- example: `milestone/14-repository-maintenance`
- `feature/<slug>`
	- use for narrow scoped changes that can merge independently
	- example: `feature/release-branch-policy-docs`
- `release/<version>`
	- use for release preparation, version alignment, release-note cutover, and tag preparation
	- example: `release/0.2.0`

## Commit Expectations

- Prefer small, cohesive commits over mixed cleanup bundles.
- Use imperative commit subjects.
- Scoped prefixes are recommended when they improve scanability, for example:
	- `docs: define release branch policy`
	- `benchmarks: normalize ui_ux expectation aliases`
	- `gui: fix detached benchmark window focus handling`
- Keep version bumps, release-note cutovers, and release-only packaging changes on `release/*` branches unless an emergency correction is required.

## Merge Expectations

- Prefer squash merges or an equivalent history cleanup for `feature/*` branches unless preserving individual commits is important for auditability.
- Merge `feature/*` into the relevant `milestone/*` branch when work is part of an active roadmap milestone; otherwise merge directly into `main` when the scope is isolated and releasable.
- Merge `milestone/*` into `main` only when the milestone slice is documented, validated, and does not leave `main` in a half-migrated state.
- Cut `release/*` branches from `main`, perform the final version and release-note alignment there, and merge them back into `main` before tagging.

## Validation Gate

This repository does not currently define checked-in CI workflows under `.github/workflows/`, so merge gating is presently documentation-backed and manual rather than workflow-enforced.

Until CI rules are added, the minimum merge bar is:

- run focused tests for the changed area
- run `pytest -v` when the change is broad enough to justify it
- validate one CLI path when behavior changes are user-facing
- validate one GUI path when the change touches GUI behavior
- update the affected docs in the same change set

## Documentation Update Expectations

When you change behavior, update the affected docs in the same change set.

Typical examples:
- new CLI flag or changed default -> update [CLI Guide](cli.md) and root `README.md`
- new backend behavior -> update [Backend Guide](backends.md)
- addon discovery, manifest, or extension-surface change -> update [Addons Guide](addons.md), relevant examples under `examples/`, and any affected configuration or architecture docs
- local HTTP route, envelope, embedded startup, or Settings discovery change -> update [HTTP API Guide](http-api.md), [Local HTTP Quick Reference](local-http-quick-reference.md), and any affected GUI or configuration docs
- new settings or defaults -> update [Configuration Reference](configuration.md)
- GUI workflow change -> update [GUI Guide](gui.md)
- new review type or changed semantics -> update [Review Types Reference](review-types.md)
- new benchmark fixture or runner behavior -> update contributor guidance and any affected benchmark docs or examples
- new repository review-quality workflow, adjudication process, or tranche baseline -> update [Review Quality Program](review-quality-program.md) and the platform-extensibility spec if it changes Milestone 13 status

## Refreshing Docs Assets

Some documentation assets are generated from the live application state rather than maintained by hand.

Current refreshable assets:
- GUI screenshots in `docs/images/`

Refresh workflow:

```powershell
./tools/capture_gui_screenshots.ps1
```

This script launches the GUI in test mode, captures the maintained screenshot states, and rewrites the checked-in PNG assets.

Before committing refreshed assets:
- verify the screenshots still match the current GUI behavior
- confirm the affected docs pages still reference the correct image names
- include the script or docs update in the same change if the capture flow changed

If the change is release-relevant, also update:
- [Release Notes](../RELEASE_NOTES.md)
- [Release Process](release-process.md)

## Source of Truth

Use these as the primary references when editing docs:
- `src/aicodereviewer/main.py`
- `src/aicodereviewer/addons.py`
- `src/aicodereviewer/http_api.py`
- `src/aicodereviewer/gui/app_local_http.py`
- `src/aicodereviewer/config.py`
- `src/aicodereviewer/backends/base.py`
- `src/aicodereviewer/gui/`
- `src/aicodereviewer/reporter.py`
- `examples/addon-*/`
- `tests/test_http_api.py`
- `tests/`

## Docs Overhaul Spec

The documentation revamp is tracked in:

- `.github/specs/docs-overhaul/spec.md`

Use that spec when deciding whether a docs change is complete.

## Maintainer Workflow

For release preparation, changelog hygiene, and validation expectations, use:

- [Release Process](release-process.md)