# Milestone 16: HITL Approval, External Validation, And Relevance Baseline

## Summary

- extended `analyze-repo` so generated previews now include `approval-request.json` and `review-checklist.md`
- added `approve-addon-preview` to `src/aicodereviewer/main.py` so a maintainer must explicitly approve or reject a generated preview before it is installed
- added `src/aicodereviewer/addon_approval.py` to load generated previews, validate them again, persist `approval-decision.json`, and install approved addons into the default discovered addon directory or a caller-provided override
- added `src/aicodereviewer/addon_validation.py` and `tools/validate_generated_addons.py` to validate heuristics against a curated external repository catalog and compare generated bundle relevance against the default bundle
- added the initial catalog at `benchmarks/addon_generation/external_repo_catalog.json`

## Validation

- focused pytest run passed:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_addon_generator.py tests/test_addon_approval.py tests/test_addon_validation.py tests/test_cli_tool_mode.py -k "addon_generator or addon_approval or addon_validation or approve_addon_preview or analyze_repo"
```

- editor diagnostics reported no errors in the new approval, validation, CLI, and test modules

## Outcome

- generated addons now have a real maintainer-facing approval gate instead of relying on manual file copying alone
- Milestone 16 now has the first repeatable external validation path outside this repository and synthetic fixtures
- relevance measurement has started with a concrete baseline: compare the generated review bundle against the default `best_practices + maintainability + testing` bundle on a curated external sample set