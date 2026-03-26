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

Manual GUI validation:

```bash
python tools/manual_test_gui.py
```

## Documentation Update Expectations

When you change behavior, update the affected docs in the same change set.

Typical examples:
- new CLI flag or changed default -> update [CLI Guide](cli.md) and root `README.md`
- new backend behavior -> update [Backend Guide](backends.md)
- new settings or defaults -> update [Configuration Reference](configuration.md)
- GUI workflow change -> update [GUI Guide](gui.md)
- new review type or changed semantics -> update [Review Types Reference](review-types.md)
- new benchmark fixture or runner behavior -> update contributor guidance and any affected benchmark docs or examples

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
- `src/aicodereviewer/config.py`
- `src/aicodereviewer/backends/base.py`
- `src/aicodereviewer/gui/`
- `src/aicodereviewer/reporter.py`
- `tests/`

## Docs Overhaul Spec

The documentation revamp is tracked in:

- `.github/specs/docs-overhaul/spec.md`

Use that spec when deciding whether a docs change is complete.

## Maintainer Workflow

For release preparation, changelog hygiene, and validation expectations, use:

- [Release Process](release-process.md)