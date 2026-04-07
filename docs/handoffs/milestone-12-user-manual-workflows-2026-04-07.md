# Milestone 12 User Manual Workflows

## What changed

- Expanded `docs/user-manual.md` with a task-oriented diff-review workflow.
- Added a project-scope partial-review workflow covering selected files, diff filtering, and the intersection behavior when both are used together.
- Added a concrete repository example that follows a selected-file plus diff-filter review from dry run through final report generation.
- Added a specification-review workflow with the required `--spec-file` path.
- Added user-level GUI walkthroughs for AI Fix mode and session restore plus final report generation.
- Added a benchmark-runner workflow so users can generate saved summary runs before loading them in the desktop comparison browser.
- Added a benchmark-authoring workflow so fixture contributors can create or tighten `fixture.json`, sample projects or diffs, and targeted runner validation without leaving the manual.
- Added a benchmark compare-run workflow with triage guidance for sorting fixture churn and inspecting primary/comparison diffs.
- Added a concrete local HTTP example showing job submission, event streaming, and report fetch as one end-user flow.
- Expanded the manual with backend-specific recovery guidance plus credential-refresh and logging examples so common Bedrock, Kiro, Copilot, and Local LLM failures can often be resolved from the manual itself.
- Added worked recovery examples with shipped Copilot and Local failure text so users can see the expected before/after signal when auth or Local model-mode issues are fixed and rerun.
- Added reproducible annotated captures for the selected-file plus diff-filter workflow and the benchmark load-and-triage workflow, with screenshot tooling updated so those assets can be regenerated.
- Updated the Milestone 12 baseline in the platform-extensibility spec to reflect the broader manual coverage.

## Why this slice matters

- The manual now covers several of the highest-value workflows that users would otherwise piece together from multiple reference pages.
- The local HTTP section is now user-workflow oriented instead of only pointing at the route reference.
- GUI users now have an explicit manual path for AI Fix and restored-session finalization instead of only tab descriptions.
- Partial-project narrowing and benchmark compare-run triage are now documented as real user workflows instead of implicit GUI capabilities.
- The manual now absorbs more common backend recovery steps instead of immediately sending users into the reference troubleshooting guide.
- The manual now shows both how to generate benchmark artifacts and how to compare them later, which closes the gap between runner documentation and the desktop browser workflow.
- The manual now also covers fixture authoring, which closes the last major benchmark workflow gap between the runner reference and practical day-to-day benchmark maintenance.
- The worked recovery examples give users exact failure text and rerun outcomes instead of only high-level checklists, which reduces the need for source dives when a backend or benchmark run fails.
- Annotated captures are now limited to the workflows where they clarify stateful UI setup; they were not added broadly across the manual.

## Files updated

- `docs/user-manual.md`
- `.github/specs/platform-extensibility/spec.md`

## Remaining Milestone 12 gaps

- only incremental manual polish is still justified from the current baseline; a further broad coverage pass is not needed unless a new user-facing workflow lands
- possible small follow-ups are wording cleanup, command-example freshness checks, and any future annotated capture added for a newly shipped flow rather than for current baseline coverage