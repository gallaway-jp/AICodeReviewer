# Milestone 13 Product Surface Tranche

## What changed

- Extended `tools/run_benchmark_tranche.py` with `ui_ux`, `accessibility`, and `localization` so the product-surface tranche could use the same short command path and `--evaluate-existing` recovery flow.
- Executed the full product-surface tranche on Copilot and Local.
- Reconstructed both `ui_ux` summaries from populated report directories with `--evaluate-existing` after the runner left the per-fixture report files behind without persisting final summary JSON.
- Recorded `ui_ux`, `accessibility`, and `localization` in `docs/review-quality-log.md`.
- Updated the Milestone 13 status block in the roadmap spec so it reflects completion of the product-surface tranche.

## Baseline outcomes

- `ui_ux`
  - Copilot: `5/7`, `overall_score = 0.7143`
  - Local: `4/7`, `overall_score = 0.5714`
- `accessibility`
  - Copilot: `3/3`, `overall_score = 1.0`
  - Local: `2/3`, `overall_score = 0.6667`
- `localization`
  - Copilot: `3/3`, `overall_score = 1.0`
  - Local: `1/3`, `overall_score = 0.3333`

## Key observations

- `ui_ux` is the only product-surface slice that still shows the broader Local transport/runtime pattern: the Local `desktop-busy-feedback-gap` and `desktop-confirmation-gap` artifacts are timeout envelopes after `HTTP 400 {"error":"Context size has been exceeded."}` failures during combined review.
- `accessibility` and `localization` are materially cleaner Local baselines than the transport-heavy runtime-safety and engineering-confidence slices.
- Copilot product-surface misses are all near-miss quality problems rather than transport failures: two anchor misses in `ui_ux` and no misses in `accessibility` or `localization`.

## Files updated

- `tools/run_benchmark_tranche.py`
- `docs/review-quality-log.md`
- `.github/specs/platform-extensibility/spec.md`

## Next steps

- continue Milestone 13 into the platform-and-scale tranche using the tranche wrapper and `--evaluate-existing` as the default execution path
- keep separating transport-heavy Local slices from cleaner Local baselines so prompt work is only driven by trustworthy failures