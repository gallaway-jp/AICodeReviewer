# Milestone 13 Platform And Scale Tranche

## What changed

- Extended `tools/run_benchmark_tranche.py` with the final platform-and-scale review types: `compatibility`, `dependency`, `license`, `scalability`, `concurrency`, `specification`, and `complexity`.
- Executed the full platform-and-scale tranche on Copilot and Local.
- Recorded all seven review types in `docs/review-quality-log.md`.
- Updated the roadmap spec so Milestone 13 now reflects baseline coverage across every built-in review type.

## Baseline outcomes

- `compatibility`
  - Copilot: `2/3`, `overall_score = 0.6667`
  - Local: `2/3`, `overall_score = 0.6667`
- `dependency`
  - Copilot: `3/3`, `overall_score = 1.0`
  - Local: `1/3`, `overall_score = 0.3333`
- `license`
  - Copilot: `1/3`, `overall_score = 0.3333`
  - Local: `1/3`, `overall_score = 0.3333`
- `scalability`
  - Copilot: `3/3`, `overall_score = 1.0`
  - Local: `0/3`, `overall_score = 0.0`
- `concurrency`
  - Copilot: `2/3`, `overall_score = 0.6667`
  - Local: `1/3`, `overall_score = 0.3333`
- `specification`
  - Copilot: `3/3`, `overall_score = 1.0`
  - Local: `0/3`, `overall_score = 0.0`
- `complexity`
  - Copilot: `1/3`, `overall_score = 0.3333`
  - Local: `0/3`, `overall_score = 0.0`

## Key observations

- `compatibility`, `concurrency`, `specification`, and `complexity` mostly produced clean adjudication artifacts rather than transport-heavy invalid payloads, so those slices are useful for direct prompt-quality analysis.
- `dependency` and especially `license` still show timeout-envelope distortion; the `license` slice is notable because the invalid-payload behavior hit both Copilot and Local instead of being mostly Local-specific.
- `scalability` remains mixed: Copilot is clean at `3/3`, while Local split between two invalid-payload timeout envelopes and one true `no issue matched` miss.
- With platform-and-scale recorded, Milestone 13 now has at least one evaluated and adjudicated run for every built-in review type.

## Files updated

- `docs/review-quality-log.md`
- `.github/specs/platform-extensibility/spec.md`

## Next steps

- prioritize transport-path investigation for the shared timeout-envelope slices in `license` and the Local timeout-envelope slices in `dependency` and `scalability`
- use the cleaner baselines in `compatibility`, `concurrency`, `specification`, and `complexity` for the next prompt or scorer follow-up cycle
- keep using tranche-level reruns so future improvement work stays comparable against the Milestone 13 baseline