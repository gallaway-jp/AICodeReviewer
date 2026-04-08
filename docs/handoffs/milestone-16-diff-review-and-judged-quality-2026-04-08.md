# Milestone 16: Diff Review Surface And Judged Quality Baseline

## Summary

- added `src/aicodereviewer/addon_review_surface.py` and the new `aicodereviewer review-addon-preview ...` command for a richer diff-first maintainer review path on generated addon previews
- the review surface now shows generated-vs-default bundle diffs and, when applicable, installed-vs-generated addon diffs before a maintainer approves or rejects the preview
- expanded `benchmarks/addon_generation/external_repo_catalog.json` beyond the initial small sample set and added `.github/workflows/generated-addon-validation.yml` so heuristic catalog validation runs weekly and on manual dispatch
- added `tools/evaluate_generated_addon_review_quality.py`, `benchmarks/addon_generation/review_quality_catalog.json`, and representative repository fixtures under `benchmarks/addon_generation/review_quality/fixtures/`
- shifted the Milestone 16 relevance baseline from bundle-membership overlap to judged review-output quality by comparing default-bundle and generated-bundle review reports against expected findings on representative FastAPI and React repository fixtures

## Validation

- focused pytest run passed:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_addon_review_surface.py tests/test_addon_review_quality.py tests/test_addon_validation.py tests/test_cli_tool_mode.py -k "review_surface or review_quality or addon_validation or analyze_repo"
```

- editor diagnostics reported no errors in the new review-surface module, the main CLI integration, the judged-quality runner, or the new tests

## Outcome

- maintainers now have a richer diff-first review path before approving generated addons
- external repository heuristic validation is no longer a one-off manual check; the workflow can rerun it periodically
- the project now has a judged review-output quality baseline that compares generated bundles against the default bundle on representative repository fixtures instead of only comparing bundle memberships