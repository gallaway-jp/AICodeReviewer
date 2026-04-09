# Milestone 16: Primary Profile Filtering

## Summary

- tightened `analyze-repo` so the capability profile reflects the primary repository instead of nested reference projects
- excluded nested `examples/`, `fixtures/`, `benchmarks/`, `samples/`, `demos/`, and `artifacts/` trees from source-file and manifest discovery inside `src/aicodereviewer/addon_generator.py`
- tightened framework import detection in `src/aicodereviewer/context_collector.py` so string literals and prompt snippets do not register as real framework usage

## Validation

- focused pytest run passed:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_addon_generator.py tests/test_cli_tool_mode.py -k "analyze_repo or addon_generator"
```

- real self-analysis run emitted clean JSON and a reduced framework profile:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m aicodereviewer.main analyze-repo D:/Development/Python/AICodeReviewer --output-dir %TEMP%/aicodereviewer-analyze-preview --addon-id aicodereviewer-self-preview
```

- resulting self-profile now reports:
  - `languages = ["Python"]`
  - `frameworks = ["pytest"]`
  - `manifests = ["pyproject.toml", "requirements.txt"]`

## Outcome

- generated preview addons are now less likely to inherit irrelevant web-framework guidance from embedded examples, benchmark fixtures, or test prompt snippets
- this closes the immediate false-positive issue found while running `analyze-repo` against the AICodeReviewer repository itself