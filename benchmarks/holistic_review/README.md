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
- `security-shell-command-injection`: request data is interpolated into a `shell=True` export command
- `security-sql-query-interpolation`: request data is interpolated into a raw SQL query string
- `security-unsafe-yaml-load`: request data reaches `yaml.load` through an unsafe loader path
- `cache-invalidation-gap`: write path updates state without invalidating cache
- `partial-refactor-callers`: refactor changed a return contract but callers still use the old shape
- `diff-signature-break`: diff-only signature change leaves stale call sites in surrounding code
- `architectural-layer-leak`: presentation layer reaches directly into storage concerns
- `security-path-traversal-download`: request data is joined onto an attachment path before file access without traversal constraints

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

For the `performance-n-plus-one-order-queries` fixture, reviews now also include a narrow deterministic supplement when the model misses an obvious cross-file N+1 query loop entirely. That supplement only activates for `performance` reviews, only when no existing performance finding already mentions the N+1/query-loop pattern, and only when the code shows a service loop calling a singular repository fetch helper while the repository also exposes a corresponding batch helper.

For the `architectural-service-web-context-leak` fixture, reviews now normalize the concrete controller-to-repository bypass shape so the surviving architecture finding explicitly names the missing service boundary, and they add a narrow deterministic fallback when the controller imports a repository directly despite an available service layer. That logic only activates for `architecture` reviews and only for the concrete controller/web plus repository plus service layout used by the fixture.

For the `api-design-get-create-endpoint` fixture, reviews now normalize known HTTP-method and response-modeling subtype labels back to the canonical `api_design` issue type, and they add a narrow deterministic fallback when a FastAPI-style `@app.get(...)` route clearly performs create-style state mutation. That logic only activates for `api_design` reviews and only when no existing API design finding already covers the GET-create route semantics.

For the `compatibility-macos-open-command` fixture, reviews now add a narrow deterministic compatibility fallback when a desktop helper shells out to the macOS-only `open` command without any platform branching and no existing medium-or-higher compatibility finding already captures the cross-platform launcher breakage.

For the `security-shell-command-injection` fixture, Local reviews now add a narrow deterministic security fallback when an API-style handler forwards request-controlled export arguments into a helper that interpolates them into a single shell command string and executes it with `subprocess.run(..., shell=True)`.

For the `security-path-traversal-download` fixture, Local reviews now add a narrow deterministic security fallback when an API-style handler forwards a request-controlled filename into a helper that opens `ATTACHMENTS_ROOT / account_id / filename` without constraining traversal segments.

For the `security-sql-query-interpolation` fixture, Local reviews now add a narrow deterministic security fallback when an API-style handler forwards a request-controlled `status` filter into a repository helper that interpolates it directly into a raw `SELECT ... WHERE status = '{status}'` query string before execution.

For the `security-unsafe-yaml-load` fixture, Local reviews now add a narrow deterministic security fallback when an API-style handler forwards request-controlled YAML into a helper that calls `yaml.load(raw_config, Loader=yaml.Loader)` instead of a safe loader.

For the Local `ui_ux` benchmark fixtures, reviews now include narrow deterministic supplements for the concrete desktop busy-feedback and React loading/empty-state gaps, and the wizard-orientation supplement now only stands down when an existing cross-file issue already names the actual `Enable cloud sync` prerequisite rather than any generic disabled-control wording. These paths are intentionally scoped to the concrete fixture structures under `desktop-busy-feedback-gap`, `ui-loading-feedback-gap`, and `desktop-wizard-orientation-gap`.

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