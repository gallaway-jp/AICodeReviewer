# Holistic Review Benchmarks

This benchmark set measures whether AICodeReviewer surfaces broader-impact findings when the evidence supports them.

Each fixture contains:
- `fixture.json`: the scenario contract and expected finding characteristics
- `project/`: a minimal code sample that reproduces the scenario
- optional `changes.diff`: a diff-scope input for changed-lines review benchmarks

The evaluator accepts either:
- a raw review report JSON containing `issues_found`
- a tool-mode `review` envelope containing a nested `report`

## Fixture Catalog

- `field-rename-contract`: renamed producer field with stale consumers
- `validation-drift`: endpoint and validator disagree on required fields
- `transaction-split`: transaction boundary removed across service and repository
- `auth-guard-regression`: admin path no longer enforces the expected guard
- `cache-invalidation-gap`: write path updates state without invalidating cache
- `partial-refactor-callers`: refactor changed a return contract but callers still use the old shape
- `diff-signature-break`: diff-only signature change leaves stale call sites in surrounding code
- `architectural-layer-leak`: presentation layer reaches directly into storage concerns

## Evaluating Reports

Generate benchmark reports and score them in one step:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/run_holistic_benchmarks.py --output-dir artifacts/holistic-benchmark-reports --summary-out artifacts/holistic-benchmark-score.json
```

The runner uses the configured backend by default, performs a health check first, writes one tool-mode review envelope per fixture, and then scores the resulting directory.

Evaluate a directory of reports named by fixture id:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/evaluate_holistic_benchmarks.py --report-dir artifacts/holistic-benchmark-reports
```

Evaluate a single fixture against one report:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/evaluate_holistic_benchmarks.py --fixture field-rename-contract --report-file artifacts/field-rename-contract.json
```

List available fixtures:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/evaluate_holistic_benchmarks.py --list-fixtures
```

## Naming Convention

For directory evaluation, the expected report file name is `<fixture-id>.json`.