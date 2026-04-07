# Milestone 13 Code Health And Security Baselines

## What changed

- Executed and recorded fresh `maintainability` tranche baselines for Copilot and Local.
- Executed and recorded fresh `dead_code` tranche baselines for Copilot and Local.
- Extended `docs/review-quality-log.md` with dedicated `Maintainability`, `Dead Code`, and `Security` sections instead of leaving code-health and runtime-safety progress implicit in artifact directories.
- Added `tools/run_benchmark_tranche.py` so tranche runs can be launched with a short command like `--tranche security` instead of spelling every fixture on the CLI.
- Added a tranche-scoped `--evaluate-existing` recovery path to that wrapper so populated report directories can still be converted into correct tranche summaries when the outer runner does not persist the final summary file.
- Reconstructed the `security` tranche summaries from the generated report directories and recorded the results in the log.
- Updated the Milestone 13 status block in the roadmap spec to reflect completed code-health logging, recorded `security` runtime-safety kickoff results, and the new tranche wrapper workflow.

## Baseline outcomes

- `maintainability`
  - Copilot: `1/3` passed, `overall_score = 0.3333`
  - Local: `1/3` passed, `overall_score = 0.3333`
- `dead_code`
  - Copilot: `2/3` passed, `overall_score = 0.6667`
  - Local: `3/3` passed, `overall_score = 1.0`
- `security`
  - Copilot: `9/12` passed, `overall_score = 0.75`
  - Local: `5/12` passed, `overall_score = 0.4167`

## Key observations

- Copilot `maintainability` and `dead_code` still show payload-path failures that need investigation before they should drive prompt or scorer changes.
- Copilot `security` is materially stronger than Local in this baseline, but its three misses are near-misses tied to evidence or scope anchors rather than transport failures.
- Local `security` has seven invalid-payload failures, so runtime-safety follow-up should start with report-envelope stability before prompt tuning.
- The benchmark docs guidance about reconstructing summaries from populated report directories was necessary in practice for the long security runs.

## Files updated

- `docs/review-quality-log.md`
- `.github/specs/platform-extensibility/spec.md`
- `tools/run_benchmark_tranche.py`

## Next steps

- investigate Local payload-envelope instability on the `security` tranche
- continue runtime-safety with `error_handling`, `data_validation`, and `regression`
- use `tools/run_benchmark_tranche.py` for future tranche runs and `--evaluate-existing` whenever report directories are complete but the summary file is missing