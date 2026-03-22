# Holistic Review Benchmarks

This benchmark set measures whether AICodeReviewer surfaces broader-impact findings when the evidence supports them.

Each fixture contains:
- `fixture.json`: the scenario contract and expected finding characteristics
- `project/`: a minimal code sample that reproduces the scenario
- optional `changes.diff`: a diff-scope input for changed-lines review benchmarks

The evaluator accepts either:
- a raw review report JSON containing `issues_found`
- a tool-mode `review` envelope containing a nested `report`

When a fixture fails, the score output includes the closest candidate issue and the specific expectation checks that did not match, such as `issue_type`, `context_scope`, `related_files_contains`, or evidence-text requirements.

The scorer also normalizes semantically equivalent issue types for broad benchmark categories. For example, a `best_practices` fixture can match `contract_mismatch`, and an `architecture` fixture can match `layer-leakage`.

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
For reproducible benchmark scoring, the runner defaults to `--lang en`; override it explicitly if you want to measure another output language.

To measure backend stability instead of a single noisy sample, run the suite multiple times:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/run_holistic_benchmarks.py --runs 5 --output-dir artifacts/holistic-benchmark-reports-copilot --summary-out artifacts/holistic-benchmark-stability-copilot.json
```

With `--runs > 1`, the runner writes reports into `run-001/`, `run-002/`, and so on, and the summary output becomes a stability summary with per-fixture pass rates and average scores across runs.

To compare the Local LLM web-guidance path on the same fixture without editing `config.ini`, use the tool-mode runtime overrides:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/run_holistic_benchmarks.py --backend local --skip-health-check --lang en --fixture validation-drift --local-disable-web-search --output-dir artifacts/holistic-benchmark-reports-local-validation-off --summary-out artifacts/holistic-benchmark-score-local-validation-off.json

d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/run_holistic_benchmarks.py --backend local --skip-health-check --lang en --fixture validation-drift --local-enable-web-search --output-dir artifacts/holistic-benchmark-reports-local-validation-on --summary-out artifacts/holistic-benchmark-score-local-validation-on.json
```

These flags are forwarded to tool-mode `review` so a benchmark run can compare prompt enrichment on and off without mutating the saved Local LLM settings.

For the `cache-invalidation-gap` fixture, Local LLM reviews now include a narrow deterministic supplement when the model misses an obvious stale-cache read/write split entirely. The supplement only activates for `performance` reviews, only when no cache/state finding was produced, and only when the fixture code shows a concrete cache accessor pair plus a separate write path for the same entity without invalidation.

For the `partial-refactor-callers` fixture, Local LLM reviews also include a narrow deterministic supplement when the model misses an obvious return-shape contract break entirely. That supplement only activates for `best_practices` reviews, only when no contract-style finding was produced, and only when the code shows an imported function returning a literal dict shape while a caller still reads a missing legacy key from that result.

The broader Local LLM web-enabled benchmark reports under `artifacts/holistic-benchmark-reports-local-web-broader-runs1-postshape/` currently reevaluate to `8/8` passed with `overall_score = 1.0`.

If the tool-mode runner emits all report files but does not persist the final summary file, you can reconstruct the final score by re-evaluating that report directory with `tools/evaluate_holistic_benchmarks.py` or the benchmarking helpers directly.

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/evaluate_holistic_benchmarks.py --report-dir artifacts/holistic-benchmark-reports-local-web-broader-runs1-postshape
```

This is useful when long Local LLM interaction-analysis calls complete successfully enough to write reports but the outer runner summary write is interrupted.

Evaluate a directory of reports named by fixture id:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/evaluate_holistic_benchmarks.py --report-dir artifacts/holistic-benchmark-reports
```

Evaluate a single fixture against one report:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/evaluate_holistic_benchmarks.py --fixture field-rename-contract --report-file artifacts/field-rename-contract.json
```

Compare two generated review artifacts to see how issue shape changed between runs:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/compare_review_reports.py artifacts/holistic-benchmark-reports-local-auth-flag-off/auth-guard-regression.json artifacts/holistic-benchmark-reports-local-auth-flag-on/auth-guard-regression.json --json-out artifacts/compare-auth-web-search.json
```

This comparison tool accepts either raw review reports or tool-mode `review` envelopes and summarizes issue-count, severity, type, and scope deltas.

List available fixtures:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe tools/evaluate_holistic_benchmarks.py --list-fixtures
```

## Naming Convention

For directory evaluation, the expected report file name is `<fixture-id>.json`.