# Milestone 13 Quality Program Foundation

## What changed

- Added `docs/review-quality-program.md` as the Milestone 13 execution baseline.
- Recorded the tranche order already sketched in the platform-extensibility spec so repository review work can start from one maintained workflow document instead of only the roadmap text.
- Added a repository self-review workflow covering baseline capture, adjudication, smallest-justified intervention, and rerun comparison.
- Added an explicit adjudication rubric for `correct and actionable`, `correct but weakly phrased`, `false positive`, `false negative`, `taxonomy drift`, and `evidence weakness`.
- Added a reusable improvement-log template and artifact naming guidance so repeated tranche runs can be compared without reconstructing process history ad hoc.
- Linked the new guide from `docs/README.md`, `README.md`, and `docs/contributing.md`.
- Updated the Milestone 13 status block in `.github/specs/platform-extensibility/spec.md` to show that the structural baseline now exists and the remaining work is tranche execution.

## Why this slice matters

- The spec already required a self-review adjudication template before tranche execution; this slice creates that missing baseline directly in the maintained docs set.
- Milestone 13 can now advance with one shared vocabulary for adjudication and one shared artifact convention for reruns.
- This keeps review-quality work auditable and comparable instead of relying on scattered artifact names and memory.

## Files updated

- `docs/review-quality-program.md`
- `docs/README.md`
- `README.md`
- `docs/contributing.md`
- `.github/specs/platform-extensibility/spec.md`

## Next steps

- start tranche 1 (`best_practices`, `maintainability`, `dead_code`) on this repository and record the first adjudication log using the new template
- preserve baseline and rerun artifacts under stable tranche names before making prompt or scorer changes
- create follow-up handoffs per tranche rather than reopening the foundation doc for execution details