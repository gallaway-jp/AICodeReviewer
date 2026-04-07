# Milestone 13 Runtime Safety Tranche

## What changed

- Investigated the Local invalid-payload path on the previously failing `security` fixtures instead of assuming prompt or scorer regressions.
- Rebuilt the Local `security` summary against the stabilized report directory, which corrected the Local baseline from `5/12` to `6/12` passed.
- Confirmed the Local `security` invalid-payload path is not one thing: some fixtures time out after the optional cross-issue interaction-analysis pass begins, while others fail earlier because the Local backend cannot connect or returns `HTTP 400` context-size errors before a valid tool-mode report envelope is written.
- Extended `tools/run_benchmark_tranche.py` with `error_handling`, `data_validation`, and `regression` tranches.
- Executed the remaining runtime-safety tranches on Copilot and Local using the tranche wrapper.
- Reconstructed missing summary files with the wrapper's `--evaluate-existing` mode where the report directories existed but the outer runner did not persist a final summary.
- Updated `docs/review-quality-log.md` and the Milestone 13 roadmap status block in the spec to reflect the full runtime-safety tranche.

## Runtime-safety baseline

- `security`
  - Copilot: `9/12`, `overall_score = 0.75`
  - Local: `6/12`, `overall_score = 0.5`
- `error_handling`
  - Copilot: `3/3`, `overall_score = 1.0`
  - Local: `0/3`, `overall_score = 0.0`
- `data_validation`
  - Copilot: `3/3`, `overall_score = 1.0`
  - Local: `0/3`, `overall_score = 0.0`
- `regression`
  - Copilot: `2/3`, `overall_score = 0.6667`
  - Local: `2/3`, `overall_score = 0.6667`

## Key observations

- Local runtime-safety misses are still not ready for prompt tuning in most slices because the dominant failure mode is upstream of scorer judgment: timeout envelopes, backend connectivity failures, or `Context size has been exceeded` responses.
- Copilot runtime-safety misses are narrower and more benchmark-shaped: `security` near-misses on evidence/scope anchors and a `regression` stale-caller near-miss on evidence wording.
- The tranche wrapper is now the safer default path for long benchmark slices, and `--evaluate-existing` is the correct recovery when the per-fixture reports exist but the final summary file does not.

## Files updated

- `tools/run_benchmark_tranche.py`
- `docs/review-quality-log.md`
- `.github/specs/platform-extensibility/spec.md`

## Next steps

- investigate Local interaction-analysis timeout pressure and context-size failures before changing runtime-safety prompts or expectations
- move from runtime safety into the next Milestone 13 tranche family using the same wrapper and recovery workflow