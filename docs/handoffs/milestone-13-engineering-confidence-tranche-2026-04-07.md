# Milestone 13 Engineering Confidence Tranche

## What changed

- Extended `tools/run_benchmark_tranche.py` with `testing`, `documentation`, `architecture`, and `api_design` tranches so the next Milestone 13 family could be executed through the same short command path and `--evaluate-existing` recovery workflow.
- Executed the full engineering-confidence tranche on Copilot and Local.
- Reconstructed the missing Copilot `testing` summary from the report directory with `--evaluate-existing` after the run populated per-fixture reports without persisting the final summary file.
- Recorded all four tranche slices in `docs/review-quality-log.md`.
- Updated the Milestone 13 status block in the roadmap spec so it reflects both the completed runtime-safety tranche and the completed engineering-confidence tranche.

## Baseline outcomes

- `testing`
  - Copilot: `2/3`, `overall_score = 0.6667`
  - Local: `1/3`, `overall_score = 0.3333`
- `documentation`
  - Copilot: `3/3`, `overall_score = 1.0`
  - Local: `0/3`, `overall_score = 0.0`
- `architecture`
  - Copilot: `2/2`, `overall_score = 1.0`
  - Local: `0/2`, `overall_score = 0.0`
- `api_design`
  - Copilot: `3/3`, `overall_score = 1.0`
  - Local: `2/3`, `overall_score = 0.6667`

## Key observations

- The Local transport/runtime problem now clearly extends beyond runtime safety.
- `documentation` and `architecture` are dominated by `Context size has been exceeded` failures and timeout envelopes before a valid tool-mode report is written.
- `testing` is mixed: one Local fixture passes cleanly, while the other two fall into context-budget plus interaction-analysis timeout envelopes; Copilot also has one timeout-envelope outlier on `testing-order-rollback-untested`.
- `api_design` is the first post-runtime-safety family where Local mostly behaves like a true model baseline instead of a transport failure path; `api-design-create-missing-201-contract` is a clean `no_issues` miss rather than an invalid payload.

## Files updated

- `tools/run_benchmark_tranche.py`
- `docs/review-quality-log.md`
- `.github/specs/platform-extensibility/spec.md`

## Next steps

- stabilize the Local transport/runtime path before changing prompts or expectations for the transport-heavy slices
- continue Milestone 13 into the product-surface tranche using the tranche wrapper and `--evaluate-existing` recovery flow as the default execution path