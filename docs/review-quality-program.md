# Review Quality Program

Use this guide when running Milestone 13 self-review work on AICodeReviewer.

It is the execution baseline for repository review-quality improvement, not a replacement for the benchmark reference in [benchmarks.md](benchmarks.md).

## Purpose

The Milestone 13 goal is to evaluate every built-in review type on this repository, adjudicate the results, and improve prompts, parser behavior, scorer behavior, context shaping, or benchmark coverage only when the observed failure mode justifies it.

This guide standardizes:

- how to run tranche reviews on this repository
- how to classify findings and misses
- how to record prompt, parser, scorer, context, and code-fix decisions
- how to keep repeated benchmark runs comparable over time

The running record for completed slices lives in [review-quality-log.md](review-quality-log.md).

## Tranche Order

Run built-in review types in this order so closely related findings are adjudicated together:

1. Code health tranche

- `best_practices`
- `maintainability`
- `dead_code`

2. Runtime safety tranche

- `security`
- `error_handling`
- `data_validation`
- `regression`

3. Engineering confidence tranche

- `testing`
- `documentation`
- `architecture`
- `api_design`

4. Product surface tranche

- `ui_ux`
- `accessibility`
- `localization`

5. Platform and scale tranche

- `compatibility`
- `dependency`
- `license`
- `scalability`
- `concurrency`
- `specification`
- `complexity`

## Repository Self-Review Workflow

Use the same workflow for each tranche.

### 1. Establish the run scope

- use project scope for repository-wide behavior
- use diff scope only when testing a specific regression or prompt change
- keep `--lang en` fixed when runs will be compared later
- pass `--backend` explicitly so the artifact is reproducible

Example repository review run:

```bash
aicodereviewer . --type best_practices,maintainability,dead_code --backend copilot --lang en --output artifacts/tranche-code-health-copilot-report.json
```

Example benchmark comparison run:

```bash
python tools/run_holistic_benchmarks.py --backend local --lang en --output-dir artifacts/tranche-code-health-local --summary-out artifacts/tranche-code-health-local-summary.json --skip-health-check
```

### 2. Capture the baseline before changing anything

For the first run in a tranche, record:

- backend
- selected review types
- command used
- saved report path
- saved benchmark summary path if benchmark reruns are involved
- notable environment overrides such as `--local-enable-web-search` or `--model`

Do not change prompts, parser logic, scoring logic, or code before this baseline is written down.

### 3. Adjudicate findings explicitly

Review every material finding and every known miss against the rubric below.

Record whether the problem is:

- a correct and actionable finding
- a correct but weakly phrased finding
- a false positive
- a false negative
- taxonomy drift
- evidence weakness

### 4. Choose the smallest justified intervention

Only make the narrowest change that addresses the observed failure mode:

- prompt change when the model had the right code evidence available but framed it poorly or ignored a clear instruction
- parser normalization when the model found the right issue under a stable alternate label
- scorer or expectation change when the benchmark contract is too brittle for a correct finding shape
- context or deterministic supplement change when the model repeatedly misses a concrete repository shape that should be recovered narrowly
- code fix only after the finding itself is adjudicated as correct and worth fixing in the product

### 5. Re-run and compare

After every change:

- repeat the focused repository run or fixture run
- preserve the new output artifact separately from the baseline
- compare score or finding deltas before concluding that the change helped

## Adjudication Rubric

Use these labels exactly in tranche notes and follow-up handoffs.

### Correct and actionable

Use this when the finding identifies a real problem, uses the right review type, cites enough evidence, and suggests a realistic next step.

### Correct but weakly phrased

Use this when the underlying concern is real but the wording is vague, the suggested fix is weak, the severity is off, or the systemic impact is underspecified.

### False positive

Use this when the finding is not supported by the repository code, misreads intended behavior, or treats an acceptable design choice as a defect.

### False negative

Use this when a meaningful repository problem should have been found but was missed.

### Taxonomy drift

Use this when the finding points at a real issue but lands under the wrong canonical review type or subtype label.

### Evidence weakness

Use this when the finding category is reasonable but the cited proof is incomplete, overly generic, or does not actually support the conclusion strongly enough.

## Improvement Log Template

Create one log section per review type or tranche execution.

Use this template verbatim when starting a new record:

```md
## <review type or tranche name>

- Date:
- Backend:
- Command:
- Baseline artifacts:
- Benchmark artifacts:
- Repository areas reviewed:

### Adjudication Summary

- Correct and actionable:
- Correct but weakly phrased:
- False positives:
- False negatives:
- Taxonomy drift:
- Evidence weakness:

### Observed Failure Modes

-

### Approved Changes

- Prompt:
- Parser normalization:
- Scorer or benchmark expectation:
- Context or deterministic supplement:
- Product code fix:

### Validation After Change

-

### Follow-up Needed

-
```

## Artifact Naming Guidance

Use stable artifact names so repeated runs can be compared without guesswork.

Recommended pattern:

- repository tranche report: `artifacts/tranche-<name>-<backend>-report.json`
- benchmark directory: `artifacts/tranche-<name>-<backend>/`
- benchmark summary: `artifacts/tranche-<name>-<backend>-summary.json`
- rerun after a change: add a suffix such as `-postfix`, `-rerun`, or `-baseline`

When a run is interrupted after report files are written but before summary persistence, reconstruct the score with `tools/evaluate_holistic_benchmarks.py` instead of discarding the run.

## Guardrails

- do not apply product code fixes before explicit adjudication
- do not widen prompt or supplement logic when a narrow repository shape is enough
- do not tighten benchmark expectations around one backend's exact prose when the defect can be anchored on file, type, scope, and evidence instead
- do not compare runs with mixed language or backend settings unless the purpose of the run is precisely that comparison

## Completion Criteria For Milestone 13 Execution

This milestone is effectively complete when:

- every built-in review type has at least one evaluated repository run
- every evaluated run has a recorded adjudication outcome
- every prompt, parser, scorer, or supplement change is tied to an observed failure mode
- repeated benchmark runs can be compared against an earlier baseline without reconstructing process history from memory

Use [benchmarks.md](benchmarks.md) for fixture-catalog details and runner flags.