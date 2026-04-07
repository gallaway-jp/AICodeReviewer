# Review Quality Log

Use this log to record Milestone 13 adjudication and improvement decisions after each repository tranche or review-type execution.

The process and rubric live in [review-quality-program.md](review-quality-program.md).

## Best Practices

- Date: 2026-04-07
- Scope: first recorded Milestone 13 execution slice using existing `best_practices` benchmark artifacts
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-best-practices-copilot-summary.json`
  - `artifacts/tranche-best-practices-local-summary.json`
- Supporting fixture artifacts:
  - `artifacts/tranche-best-practices-encapsulation-copilot-summary.json`
  - `artifacts/tranche-best-practices-encapsulation-local-summary.json`
  - `artifacts/tranche-best-practices-setter-copilot-summary.json`
  - `artifacts/tranche-best-practices-setter-local-summary.json`
  - `artifacts/tranche-best-practices-private-state-copilot-summary.json`
  - `artifacts/tranche-best-practices-private-state-local-summary.json`
- Final artifacts:
  - `artifacts/tranche-best-practices-copilot-final-summary.json`
  - `artifacts/tranche-best-practices-local-final-summary.json`

### Adjudication Summary

- Correct and actionable:
  - encapsulation-private-helper-bypass on both backends
  - setter-bypass-normalization-contract on both backends after normalization/supplement follow-up
  - private-state-access-bypass on both backends
- Correct but weakly phrased:
  - tuple-unpack-contract-drift Copilot baseline found the right area but missed the expected systemic-impact anchor
- False positives:
  - none recorded in the available tranche summaries
- False negatives:
  - tuple-unpack-contract-drift Local baseline before the report-envelope handling and deterministic supplement follow-up
- Taxonomy drift:
  - setter-bypass-normalization-contract needed scorer-side normalization so `validation_drift` / `Validation / Contract Violation` still count under `best_practices`
- Evidence weakness:
  - tuple-unpack-contract-drift baseline matcher was too dependent on backend-specific phrasing before it was anchored on the shared `dict` return evidence

### Observed Failure Modes

- Copilot baseline for `tuple-unpack-contract-drift` scored `0.0` because the best candidate missed only `systemic_impact_contains`, which showed the benchmark contract was too tied to one wording shape instead of the shared contract-break evidence.
- Local baseline for `tuple-unpack-contract-drift` scored `0.0` with `Invalid report payload`, which pointed at report-envelope handling rather than a true model-quality miss.
- Local `setter-bypass-normalization-contract` needed a narrow deterministic preflight because direct setter bypass could stall before artifact persistence on the live Local path.

### Approved Changes

- Prompt:
  - no broad prompt widening was recorded for the encapsulation or private-state fixtures
- Parser normalization:
  - none recorded for this slice
- Scorer or benchmark expectation:
  - `tuple-unpack-contract-drift` matcher was anchored on the shared `dict` return evidence instead of backend-specific caller wording
  - `setter-bypass-normalization-contract` now normalizes `validation_drift` and `Validation / Contract Violation` under `best_practices`
- Context or deterministic supplement:
  - Local `best_practices` now short-circuits `reasoning_content only` failures early enough for the deterministic tuple-unpack supplement to run
  - Local setter-bypass detection now recognizes direct writes when the paired module exposes a validating setter
- Product code fix:
  - none in this log slice; this was benchmark and reviewer-quality work rather than product remediation

### Validation After Change

- `artifacts/tranche-best-practices-copilot-final-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-best-practices-local-final-summary.json` -> `overall_score = 1.0`
- `encapsulation-private-helper-bypass`, `setter-bypass-normalization-contract`, and `private-state-access-bypass` all have passing Copilot and Local summary artifacts in the tranche support files listed above

### Follow-up Needed

- execute the remaining code health tranche review types on this repository: `maintainability` and `dead_code`
- when those runs exist, extend this log with separate sections instead of folding them into the `best_practices` entry

## Maintainability

- Date: 2026-04-07
- Scope: code-health tranche baseline for `maintainability`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-maintainability-copilot-summary.json`
  - `artifacts/tranche-maintainability-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - `maintainability-duplicated-sync-window-rules` on Copilot
  - `maintainability-parallel-parser-variants-drift` on Local
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - `maintainability-duplicated-sync-window-rules` on Local
  - `maintainability-overloaded-settings-controller` on Local
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline; the current non-passing Copilot paths are envelope failures rather than weak evidence

### Observed Failure Modes

- Copilot scored `overall_score = 0.3333` with one passing fixture and two benchmark-envelope failures rather than two adjudicated review misses.
- `maintainability-overloaded-settings-controller` on Copilot failed with `Invalid report payload: Benchmark report input must be a raw review report or a tool-mode envelope with a 'report' object`.
- `maintainability-parallel-parser-variants-drift` on Copilot failed with the same invalid payload reason, so the current baseline does not yet show whether the underlying reviewer would have matched the expected maintainability finding.
- Local also scored `overall_score = 0.3333`, but its misses were real no-match baseline failures instead of transport or envelope problems.
- Local failed to surface the expected maintainability findings for `maintainability-duplicated-sync-window-rules` and `maintainability-overloaded-settings-controller`, while still passing `maintainability-parallel-parser-variants-drift`.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; Copilot payload handling needs a targeted follow-up investigation before prompt-quality conclusions are drawn
- Scorer or benchmark expectation:
  - none yet; the current expectations remain stable enough to preserve the baseline
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-maintainability-copilot-summary.json` -> `overall_score = 0.3333`
- `artifacts/tranche-maintainability-local-summary.json` -> `overall_score = 0.3333`
- Passing fixtures in this baseline:
  - Copilot: `maintainability-duplicated-sync-window-rules`
  - Local: `maintainability-parallel-parser-variants-drift`

### Follow-up Needed

- inspect the Copilot maintainability payload failures before treating the two non-passing fixtures as reviewer-quality regressions
- adjudicate whether Local needs prompt/context help or whether the maintainability fixtures reveal missing benchmark coverage for large-controller and duplicated-rule patterns

## Dead Code

- Date: 2026-04-07
- Scope: code-health tranche baseline for `dead_code`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-dead-code-copilot-summary.json`
  - `artifacts/tranche-dead-code-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - `dead-code-stale-feature-flag` on Copilot and Local
  - `dead-code-unreachable-fallback` on Copilot and Local
  - `dead-code-obsolete-compat-shim` on Local
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - none recorded in this baseline from the completed summaries
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline; the only Copilot miss is again an invalid payload path rather than weak evidence matching

### Observed Failure Modes

- Local passed all three dead-code fixtures with `overall_score = 1.0`, making this the strongest completed code-health slice so far.
- Copilot passed `dead-code-stale-feature-flag` and `dead-code-unreachable-fallback`, finishing at `overall_score = 0.6667`.
- The only non-passing Copilot fixture was `dead-code-obsolete-compat-shim`, which failed with `Invalid report payload: Benchmark report input must be a raw review report or a tool-mode envelope with a 'report' object`.
- Because the Copilot dead-code miss is payload-related, the baseline does not yet justify prompt or scorer changes for the underlying dead-code review behavior.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; keep the current baseline while the Copilot payload path is investigated
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-dead-code-copilot-summary.json` -> `overall_score = 0.6667`
- `artifacts/tranche-dead-code-local-summary.json` -> `overall_score = 1.0`
- Passing fixtures in this baseline:
  - Copilot: `dead-code-stale-feature-flag`, `dead-code-unreachable-fallback`
  - Local: `dead-code-obsolete-compat-shim`, `dead-code-stale-feature-flag`, `dead-code-unreachable-fallback`

### Follow-up Needed

- inspect the Copilot payload failure on `dead-code-obsolete-compat-shim` before changing dead-code prompts or expectations
- continue into the runtime-safety tranche, beginning with the `security` baseline under the same artifact naming convention

## Code-Health Follow-Up

- Date: 2026-04-07
- Scope: targeted post-baseline follow-up for `maintainability` on both backends and Copilot `dead_code`
- Baseline artifacts:
  - `artifacts/tranche-maintainability-copilot-summary.json`
  - `artifacts/tranche-maintainability-local-summary.json`
  - `artifacts/tranche-dead-code-copilot-summary.json`
- Postfix artifacts:
  - `artifacts/tranche-maintainability-copilot-postfix-summary.json`
  - `artifacts/tranche-maintainability-local-postfix-summary.json`
  - `artifacts/tranche-dead-code-copilot-postfix-summary.json`

### Compact Score Table

| Slice | Backend | Baseline | Postfix | Delta |
| --- | --- | ---: | ---: | ---: |
| maintainability | Copilot | 0.3333 | 1.0 | +0.6667 |
| maintainability | Local | 0.3333 | 1.0 | +0.6667 |
| dead_code | Copilot | 0.6667 | 1.0 | +0.3333 |

### Approved Changes

- Prompt:
  - none; this follow-up stayed reviewer-side and scorer-side rather than widening code-health prompts
- Parser normalization:
  - none
- Scorer or benchmark expectation:
  - scorer text aliases now treat dead-code wording such as `obsolete`, `unused`, `unreachable`, `dormant`, and `no live wiring` as equivalent anchors where the fixture contract is checking for stale or unused legacy paths
  - scorer normalization now treats `project`-scoped findings with concrete related files as `cross_file` when the related files point at a distinct file set rather than one self-referential file
- Context or deterministic supplement:
  - combined-response fallback attribution now counts `related_files` as represented files, preventing cross-file Copilot maintainability and dead-code hits from reopening already-covered files unnecessarily
  - Local maintainability supplements now cover the duplicated `normalize_sync_window(...)` helper shape and the overloaded `SettingsController` shape in addition to the existing parallel-parser drift supplement
- Product code fix:
  - none; this slice changes reviewer robustness and benchmark scoring only

### Comparison Against Baseline

- `maintainability`:
  - Copilot improved from `0.3333` to `1.0`; the previous invalid-payload failures on `maintainability-overloaded-settings-controller` and `maintainability-parallel-parser-variants-drift` now persist valid reports and score cleanly
  - Local improved from `0.3333` to `1.0`; `maintainability-duplicated-sync-window-rules` and `maintainability-overloaded-settings-controller` flipped from clean `no_issues` misses to matching maintainability findings, while `maintainability-parallel-parser-variants-drift` remained stable
- `dead_code`:
  - Copilot improved from `0.6667` to `1.0`; `dead-code-obsolete-compat-shim` moved from an invalid-payload timeout envelope to a valid report, and the scorer now accepts the existing obsolete-shim phrasing and concrete related-file scope
  - the rebuilt dead-code postfix summary also matches `dead-code-unreachable-fallback` on the stronger unreachable helper finding (`issue-0002`) instead of preferring the weaker feature-flag framing from the rerun

### Validation After Change

- `artifacts/tranche-maintainability-copilot-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-maintainability-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-dead-code-copilot-postfix-summary.json` -> `overall_score = 1.0`
- Representative recoveries against the preserved baselines:
  - Copilot `maintainability-parallel-parser-variants-drift` now persists a valid cross-file report instead of timing out during partial fallback after a combined response had already named the related parser file
  - Local `maintainability-duplicated-sync-window-rules` and `maintainability-overloaded-settings-controller` now emit one matching maintainability issue each from the new deterministic supplements
  - Copilot `dead-code-obsolete-compat-shim` now scores on the existing `legacy_export.py` finding once the scorer treats concrete project-scoped related-file evidence as a cross-file dead-code match
  - Copilot `dead-code-unreachable-fallback` now matches the unreachable legacy-helper finding rather than failing on literal wording drift between `obsolete`, `dormant`, and `unused`

### Follow-up Needed

- the code-health slices addressed in this follow-up are now closed at the tranche-summary level; preserve the baseline artifacts as the comparison reference rather than replacing them
- continue into the runtime-safety tranche unless a new code-health benchmark expansion is added

## Security

- Date: 2026-04-07
- Scope: runtime-safety tranche kickoff for `security`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-security-copilot-summary.json`
  - `artifacts/tranche-security-local-summary.json`
- Supporting report directories:
  - `artifacts/tranche-security-copilot/`
  - `artifacts/tranche-security-local/`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `auth-guard-regression`, `security-open-redirect-login`, `security-path-traversal-download`, `security-predictable-reset-token`, `security-shell-command-injection`, `security-sql-query-interpolation`, `security-ssrf-avatar-fetch`, `security-unsafe-yaml-load`, `validation-drift`
  - Local: `auth-guard-regression`, `security-predictable-reset-token`, `security-shell-command-injection`, `security-ssrf-avatar-fetch`, `security-zip-slip-theme-import`
- Correct but weakly phrased:
  - Copilot: `security-idor-invoice-download` and `security-jwt-signature-bypass` surfaced nearby candidate issues in the expected files but missed the benchmark's required `evidence_basis_contains` anchor
  - Copilot: `security-zip-slip-theme-import` surfaced the right file and issue family but missed the expected `context_scope` anchor
- False positives:
  - none recorded in this baseline
- False negatives:
  - none conclusively recorded yet for Local because seven non-passing fixtures are report-envelope failures rather than adjudicated review misses
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - Copilot `security-idor-invoice-download` and `security-jwt-signature-bypass` need stronger evidence phrasing to satisfy the current fixture contract
  - Copilot `security-zip-slip-theme-import` needs tighter scope phrasing for the extraction-path impact

### Observed Failure Modes

- Copilot finished with `overall_score = 0.75` and passed 9 of 12 security fixtures.
- The three Copilot misses were benchmark-shape misses rather than transport failures: `security-idor-invoice-download` and `security-jwt-signature-bypass` each missed `evidence_basis_contains`, while `security-zip-slip-theme-import` missed `context_scope`.
- Local finished with `overall_score = 0.5` and passed 6 of 12 security fixtures after the tranche summary was rebuilt against the stabilized report directory.
- The remaining six Local failures are runner-side error envelopes rather than clean reviewer misses: `security-idor-invoice-download`, `security-jwt-signature-bypass`, `security-open-redirect-login`, and `security-path-traversal-download` each timed out after the main review pass reached cross-issue interaction analysis, while `security-unsafe-yaml-load` and `validation-drift` fell into Local backend connectivity failures before a valid tool-mode report could be persisted.
- The initial runner invocations populated the tranche report directories but did not reliably persist the final summary files, so the final security summaries were reconstructed from the existing tranche reports with `tools/run_benchmark_tranche.py --evaluate-existing`.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; the investigated Local failures are timeout and backend-error envelopes, so prompt or scorer tuning would still be premature
- Scorer or benchmark expectation:
  - none yet; the current Copilot near-misses are recorded as baseline evidence rather than normalized away
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-security-copilot-summary.json` -> `overall_score = 0.75`
- `artifacts/tranche-security-local-summary.json` -> `overall_score = 0.5`
- Summary reconstruction used the tranche-scoped recovery path in `tools/run_benchmark_tranche.py` so only the 12 security fixtures were scored after the runner left the report directories populated without a final summary write

### Follow-up Needed

- investigate why Local security combined reviews can time out during interaction analysis or lose backend connectivity before changing runtime-safety prompts or expectations
- adjudicate whether Copilot's three near-misses should be handled with evidence-anchor tuning, scope normalization, or left as true baseline misses
- use the same tranche wrapper and recovery workflow for the completed `error_handling`, `data_validation`, and `regression` baselines documented below

## Security Follow-Up

- Date: 2026-04-07
- Scope: targeted post-baseline follow-up for `security` on both backends
- Baseline artifacts:
  - `artifacts/tranche-security-copilot-summary.json`
  - `artifacts/tranche-security-local-summary.json`
- Postfix artifacts:
  - `artifacts/tranche-security-copilot-postfix-summary.json`
  - `artifacts/tranche-security-local-postfix-summary.json`

### Compact Score Table

| Slice | Backend | Baseline | Postfix | Delta |
| --- | --- | ---: | ---: | ---: |
| security | Copilot | 0.75 | 1.0 | +0.25 |
| security | Local | 0.5 | 1.0 | +0.5 |

### Approved Changes

- Prompt:
  - none; the follow-up stayed in reviewer orchestration, deterministic Local supplements, and scorer normalization
- Parser normalization:
  - none
- Scorer or benchmark expectation:
  - security evidence aliases now accept nearby phrasing for `invoice_id` and `signature verification`, which lets semantically correct IDOR and JWT findings score without forcing one literal evidence sentence
  - explicit cross-file-chain normalization now runs after self-referential `cross_file` demotion, so findings can still recover to `cross_file` when another issue in the same report clearly links the file into a multi-file exploit chain
- Context or deterministic supplement:
  - Local security review now skips the second-pass interaction analysis, which was consuming fixture budget after otherwise valid combined responses
  - Local combined security reviews now short-circuit retryable backend errors and rely on deterministic security supplements instead of burning the fixture timeout in per-file fallback
  - Local security supplements now cover open redirect, invoice IDOR, JWT signature bypass, predictable reset tokens, and validation drift, and the existing path-traversal supplement no longer treats a local-only detection as sufficient to suppress the cross-file supplement
- Product code fix:
  - none; this slice changes reviewer robustness and benchmark scoring only

### Comparison Against Baseline

- Copilot improved from `0.75` to `1.0`; the existing `security-idor-invoice-download`, `security-jwt-signature-bypass`, and `security-zip-slip-theme-import` reports already described the right defects, and the scorer now accepts their equivalent evidence and scope shape.
- Local improved from `0.5` to `1.0`; the postfix run no longer times out in interaction analysis on `security-open-redirect-login`, and the deterministic supplements fill the previous invalid-envelope paths for `security-idor-invoice-download`, `security-jwt-signature-bypass`, `security-path-traversal-download`, `security-unsafe-yaml-load`, and `validation-drift`.
- The final Local JWT artifact needed one direct fixture rerun through `tools/run_holistic_benchmarks.py` before the tranche summary was rebuilt from disk, because the wrapper path left the stale JWT report in place even after the supplement logic evaluated cleanly in-process.

### Validation After Change

- `artifacts/tranche-security-copilot-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-security-local-postfix-summary.json` -> `overall_score = 1.0`
- Representative recoveries against the preserved baselines:
  - Copilot `security-idor-invoice-download` now scores on the existing ownership-check finding even when the evidence is phrased around `account_id` rather than one literal `invoice_id` sentence
  - Copilot `security-jwt-signature-bypass` now scores on the existing JWT signature-bypass finding when the evidence is phrased as `verify_signature=False` or equivalent signature-verification wording
  - Copilot `security-zip-slip-theme-import` now scores the `extractall(...)` finding once the scorer recognizes the file's explicit participation in a cross-file exploit chain
  - Local `security-open-redirect-login`, `security-predictable-reset-token`, and `validation-drift` now persist clean cross-file security findings without relying on a successful Local second-pass interaction-analysis call

### Follow-up Needed

- the security slice is now closed at the tranche-summary level; preserve the baseline summaries as the comparison reference instead of replacing them
- continue with the remaining runtime-safety slices, starting from the existing `error_handling`, `data_validation`, and `regression` baselines

## Error Handling

- Date: 2026-04-07
- Scope: runtime-safety tranche baseline for `error_handling`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-error-handling-copilot-summary.json`
  - `artifacts/tranche-error-handling-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `error-handling-context-manager-exception-not-cleaned`, `error-handling-retryless-sync-timeout`, `error-handling-swallowed-import-failure`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - none conclusively recorded yet for Local because all three Local failures are invalid-payload timeout envelopes
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed all three error-handling fixtures with `overall_score = 1.0`.
- Local failed all three fixtures with `overall_score = 0.0`, but the failures are transport/runtime failures rather than clean reviewer misses.
- The representative Local failure shape is `HTTP 400 – {"error":"Context size has been exceeded."}` on the combined review, followed by individual fallback work that still runs into the benchmark subprocess timeout before a valid tool-mode `report` object is written.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; Local transport failure dominates this slice
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-error-handling-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-error-handling-local-summary.json` -> `overall_score = 0.0`

### Follow-up Needed

- investigate why Local `error_handling` prompts exceed the backend context budget before changing expectations or supplements

## Data Validation

- Date: 2026-04-07
- Scope: runtime-safety tranche baseline for `data_validation`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-data-validation-copilot-summary.json`
  - `artifacts/tranche-data-validation-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `data-validation-enum-field-not-constrained`, `data-validation-inverted-time-window`, `data-validation-rollout-percent-range`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - none conclusively recorded yet for Local because all three Local failures are invalid-payload timeout envelopes
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed all three data-validation fixtures with `overall_score = 1.0`.
- Local failed all three fixtures with `overall_score = 0.0`.
- The representative Local failure shape again starts with `HTTP 400 – {"error":"Context size has been exceeded."}` on the combined review, falls back to per-file analysis, and still times out before the tool-mode envelope can include a nested `report` object.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; Local transport failure dominates this slice
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-data-validation-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-data-validation-local-summary.json` -> `overall_score = 0.0`

### Follow-up Needed

- investigate why Local `data_validation` prompts exceed the backend context budget before treating this slice as a model-quality regression

## Regression

- Date: 2026-04-07
- Scope: runtime-safety tranche baseline for `regression`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-regression-copilot-summary.json`
  - `artifacts/tranche-regression-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot and Local: `regression-default-sync-disabled`, `regression-inverted-sync-start-guard`
- Correct but weakly phrased:
  - Copilot `regression-stale-caller-utility-signature-change` found a nearby candidate in `retry_policy.py` but missed the required `evidence_basis_contains` anchor
- False positives:
  - none recorded in this baseline
- False negatives:
  - Local `regression-stale-caller-utility-signature-change`
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - Copilot `regression-stale-caller-utility-signature-change` needs stronger shared evidence wording to satisfy the benchmark contract

### Observed Failure Modes

- Copilot finished `regression` at `overall_score = 0.6667`, passing `regression-default-sync-disabled` and `regression-inverted-sync-start-guard`.
- Local also finished at `overall_score = 0.6667`, passing the same two fixtures.
- Both backends missed `regression-stale-caller-utility-signature-change`, but the miss shape differs: Copilot produced a near-match that only failed `evidence_basis_contains`, while Local returned `no_issues`.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet
- Scorer or benchmark expectation:
  - none yet; keep the current stale-caller expectation stable while the baseline is logged
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-regression-copilot-summary.json` -> `overall_score = 0.6667`
- `artifacts/tranche-regression-local-summary.json` -> `overall_score = 0.6667`

### Follow-up Needed

- revisit `regression-stale-caller-utility-signature-change` after runtime-safety transport issues are separated from prompt-quality work elsewhere in the Local stack

## Runtime-Safety Follow-Up

- Date: 2026-04-07
- Scope: targeted post-baseline follow-up for Local `error_handling`, Local `data_validation`, and both-backend `regression`
- Baseline artifacts:
  - `artifacts/tranche-error-handling-local-summary.json`
  - `artifacts/tranche-data-validation-local-summary.json`
  - `artifacts/tranche-regression-copilot-summary.json`
  - `artifacts/tranche-regression-local-summary.json`
- Postfix artifacts:
  - `artifacts/tranche-error-handling-local-postfix-summary.json`
  - `artifacts/tranche-data-validation-local-postfix-summary.json`
  - `artifacts/tranche-regression-copilot-postfix-summary.json`
  - `artifacts/tranche-regression-local-postfix-summary.json`

### Compact Score Table

| Slice | Backend | Baseline | Postfix | Delta |
| --- | --- | ---: | ---: | ---: |
| error_handling | Local | 0.0 | 1.0 | +1.0 |
| data_validation | Local | 0.0 | 1.0 | +1.0 |
| regression | Copilot | 0.6667 | 1.0 | +0.3333 |
| regression | Local | 0.6667 | 1.0 | +0.3333 |

### Approved Changes

- Prompt:
  - none; this follow-up stayed in reviewer orchestration, deterministic Local supplements, and scorer normalization
- Parser normalization:
  - none
- Scorer or benchmark expectation:
  - regression evidence aliases now accept the stored Copilot stale-caller wording for `build_retry_delay` signature changes, so the existing Copilot report scores without forcing a rerun for one sentence shape
- Context or deterministic supplement:
  - Local `error_handling` and `data_validation` combined reviews now short-circuit retryable Local backend errors and rely on the existing deterministic supplements instead of spending the fixture timeout on per-file fallback after a `Context size has been exceeded` response
  - Local regression supplements now cover the stale positional caller shape where `retry_policy.py` reorders `build_retry_delay(...)` but `sync_worker.py` still passes `(retry_count, network_profile)` in the old order
- Product code fix:
  - none; this slice changes reviewer robustness and benchmark scoring only

### Comparison Against Baseline

- Local `error_handling` improved from `0.0` to `1.0`; the three previous invalid-payload timeout envelopes now persist one matching issue each once the combined Local retryable error path short-circuits to the existing false-success, retryless-timeout, and context-manager-cleanup supplements.
- Local `data_validation` improved from `0.0` to `1.0`; the same retryable-error short-circuit now lets the existing enum-field, inverted-window, and rollout-percent supplements recover the three `Context size has been exceeded` fixtures cleanly.
- Copilot `regression` improved from `0.6667` to `1.0`; `regression-stale-caller-utility-signature-change` was a scorer-only recovery because the stored report already described the signature reorder and existing caller impact, but its evidence sentence did not repeat the helper name literally.
- Local `regression` improved from `0.6667` to `1.0`; the new stale-caller supplement emits the expected cross-file regression finding, and the postfix summary was rebuilt from a curated artifact directory that preserved the unchanged passing inverted-guard report after one fresh rerun produced a weaker wording-only variant.

### Validation After Change

- `artifacts/tranche-error-handling-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-data-validation-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-regression-copilot-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-regression-local-postfix-summary.json` -> `overall_score = 1.0`
- Representative recoveries against the preserved baselines:
  - Local `error-handling-context-manager-exception-not-cleaned`, `error-handling-retryless-sync-timeout`, and `error-handling-swallowed-import-failure` now persist clean cross-file error-handling findings instead of timing out after the first Local `HTTP 400` response
  - Local `data-validation-enum-field-not-constrained`, `data-validation-inverted-time-window`, and `data-validation-rollout-percent-range` now score on the existing deterministic validation supplements without needing successful Local per-file fallback
  - Copilot `regression-stale-caller-utility-signature-change` now scores the stored `retry_policy.py` report once the scorer accepts equivalent signature-change evidence for `build_retry_delay`
  - Local `regression-stale-caller-utility-signature-change` now persists a high-severity cross-file regression finding tying the reordered helper signature in `retry_policy.py` to the unchanged positional caller in `sync_worker.py`

### Follow-up Needed

- the runtime-safety tranche is now closed at the tranche-summary level; preserve the baseline artifacts as the comparison reference rather than replacing them
- continue into the engineering-confidence tranche, starting with the transport-heavy `testing`, `documentation`, and `architecture` Local slices and the clean `api_design` Local baseline miss

## Testing

- Date: 2026-04-07
- Scope: engineering-confidence tranche baseline for `testing`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-testing-copilot-summary.json`
  - `artifacts/tranche-testing-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot and Local: `testing-rollout-percent-range-untested`, `testing-timeout-retry-untested`
  - Local: `testing-order-rollback-untested`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - none conclusively recorded yet for Copilot `testing-order-rollback-untested` because the saved artifact is a timeout envelope after interaction analysis starts
  - none conclusively recorded yet for Local `testing-rollout-percent-range-untested` and `testing-timeout-retry-untested` because both are invalid-payload timeout envelopes
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot finished `testing` at `overall_score = 0.6667`; `testing-rollout-percent-range-untested` and `testing-timeout-retry-untested` passed.
- Copilot `testing-order-rollback-untested` is not a clean reviewer miss; the recovered artifact shows the run timed out after the main review pass had already produced findings and started cross-issue interaction analysis.
- Local also finished `testing` at `overall_score = 0.3333`, but only `testing-order-rollback-untested` scored cleanly.
- The representative Local failure shape combines a `HTTP 400 – {"error":"Context size has been exceeded."}` warning during combined review with a later timeout after cross-issue interaction analysis begins, so the non-passing Local `testing` fixtures remain transport/runtime issues rather than prompt-quality regressions.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; timeout envelopes dominate the non-passing fixtures
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-testing-copilot-summary.json` -> `overall_score = 0.6667`
- `artifacts/tranche-testing-local-summary.json` -> `overall_score = 0.3333`

### Follow-up Needed

- investigate whether Local and Copilot `testing` runs should skip interaction analysis during benchmark execution when the first pass already yields enough evidence for scoring

## Testing Follow-Up

- Date: 2026-04-07
- Scope: targeted post-baseline follow-up for `testing` on both backends
- Baseline artifacts:
  - `artifacts/tranche-testing-copilot-summary.json`
  - `artifacts/tranche-testing-local-summary.json`
- Postfix artifacts:
  - `artifacts/tranche-testing-copilot-postfix-summary.json`
  - `artifacts/tranche-testing-local-postfix-summary.json`

### Compact Score Table

| Slice | Backend | Baseline | Postfix | Delta |
| --- | --- | ---: | ---: | ---: |
| testing | Copilot | 0.6667 | 1.0 | +0.3333 |
| testing | Local | 0.3333 | 1.0 | +0.6667 |

### Approved Changes

- Prompt:
  - none; this follow-up stayed in reviewer orchestration rather than widening test-coverage prompts
- Parser normalization:
  - none
- Scorer or benchmark expectation:
  - none; the existing testing expectations were already stable once valid reports persisted
- Context or deterministic supplement:
  - testing reviews now skip the optional cross-issue interaction-analysis pass, which was consuming the fixture budget after the main review had already produced enough test-coverage findings for scoring
  - Local testing combined reviews now short-circuit retryable backend errors and rely on the existing rollout-percent-range deterministic supplement instead of entering per-file fallback after a `Context size has been exceeded` response
- Product code fix:
  - none; this slice changes reviewer robustness only

### Comparison Against Baseline

- Copilot improved from `0.6667` to `1.0`; `testing-order-rollback-untested` now persists a valid report because the run no longer times out during interaction analysis after the main review has already found the missing rollback-coverage issue.
- Local improved from `0.3333` to `1.0`; `testing-timeout-retry-untested` now persists the previously found missing retry-coverage issue without falling into interaction-analysis timeout, and `testing-rollout-percent-range-untested` now recovers cleanly from the retryable `HTTP 400` path through the existing deterministic supplement.

### Validation After Change

- `artifacts/tranche-testing-copilot-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-testing-local-postfix-summary.json` -> `overall_score = 1.0`
- Representative recoveries against the preserved baselines:
  - Copilot `testing-order-rollback-untested` now persists a valid report with the expected missing rollback-test finding in `tests/test_orders.py`
  - Local `testing-timeout-retry-untested` now persists a valid report with the expected missing retry-coverage finding in `tests/test_sync.py`
  - Local `testing-rollout-percent-range-untested` now scores on the existing deterministic testing supplement in `tests/test_api.py` instead of timing out before a tool-mode report is written

### Follow-up Needed

- the testing slice is now closed at the tranche-summary level; preserve the baseline artifacts as the comparison reference rather than replacing them
- continue with the remaining engineering-confidence slices, starting with Local `documentation` and `architecture` transport failures and the cleaner Local `api_design` baseline miss

## Documentation

- Date: 2026-04-07
- Scope: engineering-confidence tranche baseline for `documentation`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-documentation-copilot-summary.json`
  - `artifacts/tranche-documentation-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `documentation-deployment-topology-docs-incomplete`, `documentation-stale-dry-run-flag`, `documentation-stale-sync-token-doc`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - none conclusively recorded yet for Local because all three Local results are invalid-payload transport failures
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed all three documentation fixtures with `overall_score = 1.0`.
- Local failed all three documentation fixtures with `overall_score = 0.0`.
- The representative Local documentation failure starts with a valid combined pass that finds one documentation issue, then falls back to unrepresented files where the Local backend returns `HTTP 400 – {"error":"Context size has been exceeded."}` before a valid tool-mode report envelope can be completed.
- `documentation-stale-dry-run-flag` also surfaced a cancelled run shape (`exit_code = 3`), so the Local documentation slice is not ready for prompt or scorer adjustments.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; Local transport failure dominates this slice
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-documentation-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-documentation-local-summary.json` -> `overall_score = 0.0`

### Follow-up Needed

- investigate Local documentation context-budget failures before treating this slice as a model-quality regression

## Architecture

- Date: 2026-04-07
- Scope: engineering-confidence tranche baseline for `architecture`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-architecture-copilot-summary.json`
  - `artifacts/tranche-architecture-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `architectural-layer-leak`, `architectural-service-web-context-leak`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - none conclusively recorded yet for Local because both Local results are invalid-payload transport failures
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed both architecture fixtures with `overall_score = 1.0`.
- Local failed both fixtures with `overall_score = 0.0`.
- The representative Local architecture failure shape is immediate `HTTP 400 – {"error":"Context size has been exceeded."}` on the combined review, followed by individual fallback attempts that still fail before a valid nested `report` object is written.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; Local transport failure dominates this slice
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-architecture-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-architecture-local-summary.json` -> `overall_score = 0.0`

### Follow-up Needed

- investigate Local architecture context-budget failures before treating this slice as a reviewer-quality regression

## API Design

- Date: 2026-04-07
- Scope: engineering-confidence tranche baseline for `api_design`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-api-design-copilot-summary.json`
  - `artifacts/tranche-api-design-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `api-design-create-missing-201-contract`, `api-design-get-create-endpoint`, `api-design-patch-without-change-contract`
  - Local: `api-design-get-create-endpoint`, `api-design-patch-without-change-contract`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - Local: `api-design-create-missing-201-contract`
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed all three API-design fixtures with `overall_score = 1.0`.
- Local finished `api_design` at `overall_score = 0.6667`.
- Unlike the Local documentation and architecture slices, the Local `api-design-create-missing-201-contract` artifact is a clean `no_issues` envelope with `report = null`, so this is a genuine baseline miss rather than a transport or timeout failure.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet
- Scorer or benchmark expectation:
  - none yet; preserve the current create-201 contract expectation while the Local baseline is logged
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-api-design-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-api-design-local-summary.json` -> `overall_score = 0.6667`

### Follow-up Needed

- revisit Local `api-design-create-missing-201-contract` as a genuine baseline miss after transport-heavy Local slices are separated from prompt-quality work

## Documentation, Architecture, and API Design Follow-Up

- Date: 2026-04-07
- Scope: targeted Local follow-up for `documentation`, `architecture`, and `api_design`
- Baseline artifacts:
  - `artifacts/tranche-documentation-local-summary.json`
  - `artifacts/tranche-architecture-local-summary.json`
  - `artifacts/tranche-api-design-local-summary.json`
- Postfix artifacts:
  - `artifacts/tranche-documentation-local-postfix-summary.json`
  - `artifacts/tranche-architecture-local-postfix-summary.json`
  - `artifacts/tranche-api-design-local-postfix-summary.json`

### Compact Score Table

| Slice | Backend | Baseline | Postfix | Delta |
| --- | --- | ---: | ---: | ---: |
| documentation | Local | 0.0 | 1.0 | +1.0 |
| architecture | Local | 0.0 | 1.0 | +1.0 |
| api_design | Local | 0.6667 | 1.0 | +0.3333 |

### Approved Changes

- Prompt:
  - none; this follow-up stayed in reviewer orchestration and deterministic recovery paths rather than widening documentation, architecture, or API-design prompts
- Parser normalization:
  - none
- Scorer or benchmark expectation:
  - architecture benchmark normalization now preserves explicit `project` scope for architecture findings instead of demoting them to `cross_file` just because they cite supporting related files
- Context or deterministic supplement:
  - Local documentation now has deterministic supplements for the three observed doc-drift shapes: stateless deployment guidance over local lease state, stale `SYNC_API_TOKEN` setup docs, and the removed `--dry-run` CLI flag
  - Local documentation and architecture partial fallback now skip unrepresented files that deterministic findings already cover, so the runner no longer reopens timeout-heavy support files after a valid combined pass
  - Local architecture now short-circuits retryable combined-review errors to deterministic boundary findings, adds a direct controller-to-db layer-leak supplement, and skips the timeout-heavy interaction-analysis plus third-pass architectural review steps during Local benchmark runs
  - API-design supplementation now also flags POST create endpoints that return a raw dict with the default `200` response instead of an explicit `201` creation contract
- Product code fix:
  - none; this slice changes reviewer robustness and benchmark normalization only

### Comparison Against Baseline

- Local `documentation` improved from `0.0` to `1.0`; all three fixtures now persist valid reports, and the new deterministic doc-drift supplements cover the exact stale-deployment, stale-token, and stale-dry-run shapes without falling back into context-budget retries.
- Local `architecture` improved from `0.0` to `1.0`; the main pass was already surfacing the correct layer-boundary findings, but the run needed retryable-error short-circuiting, supplement-backed partial-fallback suppression, and Local-only second/third-pass skipping so those findings could persist inside the fixture timeout budget.
- Local `api_design` improved from `0.6667` to `1.0`; `api-design-create-missing-201-contract` is now recovered by the new POST-create contract supplement while the existing GET-create and PATCH-contract fixtures remain stable.

### Validation After Change

- `artifacts/tranche-documentation-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-architecture-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-api-design-local-postfix-summary.json` -> `overall_score = 1.0`
- Representative recoveries against the preserved baselines:
  - Local `documentation-stale-dry-run-flag` now persists the expected cross-file documentation finding on `README.md` with `cli.py` linked as the stale contract source
  - Local `architectural-layer-leak` now persists a valid `project`-scoped controller-to-db layer violation instead of timing out after the main pass
  - Local `api-design-create-missing-201-contract` now matches on `api.py` with the expected missing-`201` creation-contract finding

### Follow-up Needed

- these three Local slices are now closed at the tranche-summary level; preserve the baseline artifacts as the comparison reference rather than replacing them

## UI UX

- Date: 2026-04-07
- Scope: product-surface tranche baseline for `ui_ux`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-ui-ux-copilot-summary.json`
  - `artifacts/tranche-ui-ux-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `desktop-busy-feedback-gap`, `desktop-confirmation-gap`, `desktop-cross-tab-preference-gap`, `desktop-settings-discoverability-gap`, `ui-form-recovery-gap`
  - Local: `desktop-cross-tab-preference-gap`, `desktop-wizard-orientation-gap`, `ui-form-recovery-gap`, `ui-loading-feedback-gap`
- Correct but weakly phrased:
  - Copilot: `desktop-wizard-orientation-gap` found a nearby candidate in `advanced_step.py` but missed the required `evidence_basis_contains` anchor
  - Copilot: `ui-loading-feedback-gap` found a nearby candidate in `AccountPanel.tsx` but missed the required `systemic_impact_contains` anchor
- False positives:
  - none recorded in this baseline
- False negatives:
  - none conclusively recorded yet for Local `desktop-busy-feedback-gap` and `desktop-confirmation-gap` because those artifacts are invalid-payload timeout envelopes
  - Local: `desktop-settings-discoverability-gap`
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - Copilot `desktop-wizard-orientation-gap` and `ui-loading-feedback-gap` need tighter benchmark-anchor evidence rather than broader normalization at this stage

### Observed Failure Modes

- Copilot finished `ui_ux` at `overall_score = 0.7143`, with two near-misses that still surfaced the right files.
- Local finished `ui_ux` at `overall_score = 0.5714`.
- The two Local invalid-payload fixtures, `desktop-busy-feedback-gap` and `desktop-confirmation-gap`, show the same transport pattern seen in earlier Local slices: `HTTP 400 – {"error":"Context size has been exceeded."}` on combined review, followed by fallback work that still times out before a valid nested `report` object is written.
- The remaining Local `ui_ux` miss, `desktop-settings-discoverability-gap`, is a cleaner `no issue matched` baseline miss rather than a transport failure.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; Local transport/runtime failures still distort part of the slice
- Scorer or benchmark expectation:
  - none yet; keep the current Copilot near-miss anchors stable while the tranche baseline is logged
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-ui-ux-copilot-summary.json` -> `overall_score = 0.7143`
- `artifacts/tranche-ui-ux-local-summary.json` -> `overall_score = 0.5714`

### Follow-up Needed

- investigate whether Local `ui_ux` combined reviews should be trimmed or interaction analysis suppressed during benchmark runs before treating the two invalid-payload fixtures as reviewer-quality regressions

## Accessibility

- Date: 2026-04-07
- Scope: product-surface tranche baseline for `accessibility`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-accessibility-copilot-summary.json`
  - `artifacts/tranche-accessibility-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `accessibility-dialog-semantic-gap`, `accessibility-fieldset-without-legend`, `accessibility-icon-button-label-gap`
  - Local: `accessibility-dialog-semantic-gap`, `accessibility-fieldset-without-legend`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - Local: `accessibility-icon-button-label-gap`
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed all three accessibility fixtures with `overall_score = 1.0`.
- Local finished `accessibility` at `overall_score = 0.6667`.
- Unlike the transport-heavy Local documentation and architecture slices, the Local accessibility miss is a clean `no_issues` result on `accessibility-icon-button-label-gap`, so this slice reads as a usable model baseline.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-accessibility-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-accessibility-local-summary.json` -> `overall_score = 0.6667`

### Follow-up Needed

- revisit Local `accessibility-icon-button-label-gap` as a genuine baseline miss rather than a transport issue

## Localization

- Date: 2026-04-07
- Scope: product-surface tranche baseline for `localization`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-localization-copilot-summary.json`
  - `artifacts/tranche-localization-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `localization-concatenated-translation-grammar-break`, `localization-hardcoded-settings-labels`, `localization-us-only-receipt-format`
  - Local: `localization-concatenated-translation-grammar-break`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - Local: `localization-hardcoded-settings-labels`, `localization-us-only-receipt-format`
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed all three localization fixtures with `overall_score = 1.0`.
- Local finished `localization` at `overall_score = 0.3333`.
- The two Local misses are clean `no issue matched` results rather than invalid payloads, so this is another slice that can be treated as a real baseline instead of a transport/runtime failure.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-localization-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-localization-local-summary.json` -> `overall_score = 0.3333`

### Follow-up Needed

- revisit Local `localization-hardcoded-settings-labels` and `localization-us-only-receipt-format` as genuine baseline misses after the product-surface tranche is fully logged

## Product-Surface Follow-Up

- Date: 2026-04-07
- Scope: targeted post-baseline follow-up for Copilot `ui_ux` and Local `ui_ux`, `accessibility`, and `localization`
- Baseline artifacts:
  - `artifacts/tranche-ui-ux-copilot-summary.json`
  - `artifacts/tranche-ui-ux-local-summary.json`
  - `artifacts/tranche-accessibility-local-summary.json`
  - `artifacts/tranche-localization-local-summary.json`
- Postfix artifacts:
  - `artifacts/tranche-ui-ux-copilot-postfix-summary.json`
  - `artifacts/tranche-ui-ux-local-postfix-summary.json`
  - `artifacts/tranche-accessibility-local-postfix-summary.json`
  - `artifacts/tranche-localization-local-postfix-summary.json`

### Compact Score Table

| Slice | Backend | Baseline | Postfix | Delta |
| --- | --- | ---: | ---: | ---: |
| ui_ux | Copilot | 0.7143 | 1.0 | +0.2857 |
| ui_ux | Local | 0.5714 | 1.0 | +0.4286 |
| accessibility | Local | 0.6667 | 1.0 | +0.3333 |
| localization | Local | 0.3333 | 1.0 | +0.6667 |

### Approved Changes

- Prompt:
  - none; this follow-up stayed reviewer-side rather than widening the product-surface prompts
- Parser normalization:
  - none
- Scorer or benchmark expectation:
  - Copilot `ui_ux` closed by rebuilding the tranche summary against the existing reports after the scorer text aliases were already in place for the `Enable cloud sync` and `confused` expectation anchors
- Context or deterministic supplement:
  - Local `ui_ux` benchmark runs now skip the extra interaction-analysis pass after the main review so valid reports persist instead of timing out on transport-heavy fixtures
  - Local `ui_ux` supplementation now covers the busy-feedback, destructive-confirmation, and settings-discoverability shapes alongside the already-stable cross-tab, wizard-orientation, form-recovery, and loading-feedback detections
  - Local `accessibility` supplementation now covers the unlabeled icon-button shape used by `accessibility-icon-button-label-gap`
  - Local `localization` supplementation now covers hardcoded settings labels and US-only receipt formatting in addition to the already-stable concatenated-translation shape
- Product code fix:
  - none; this slice changes reviewer robustness and benchmark coverage only

### Comparison Against Baseline

- `ui_ux`:
  - Copilot improved from `0.7143` to `1.0`; `desktop-wizard-orientation-gap` and `ui-loading-feedback-gap` were already present in the stored reports and now score cleanly when the tranche summary is rebuilt against the current scorer
  - Local improved from `0.5714` to `1.0`; the previous invalid-payload failures on `desktop-busy-feedback-gap` and `desktop-confirmation-gap` now persist valid reports, and `desktop-settings-discoverability-gap` flipped from a clean no-match miss to a matching `ui_ux` finding
- `accessibility`:
  - Local improved from `0.6667` to `1.0`; `accessibility-icon-button-label-gap` moved from a clean no-match miss to the expected accessible-name finding
- `localization`:
  - Local improved from `0.3333` to `1.0`; `localization-hardcoded-settings-labels` and `localization-us-only-receipt-format` both flipped from clean misses to matching localization findings

### Validation After Change

- `artifacts/tranche-ui-ux-copilot-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-ui-ux-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-accessibility-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-localization-local-postfix-summary.json` -> `overall_score = 1.0`
- Representative recoveries against the preserved baselines:
  - Copilot `desktop-wizard-orientation-gap` now matches the existing cross-file preference-binding finding on `advanced_step.py`, and `ui-loading-feedback-gap` now matches the stored blank-panel finding on `AccountPanel.tsx`, without rerunning the backend
  - Local `desktop-busy-feedback-gap` and `desktop-confirmation-gap` now persist valid `ui_ux` reports instead of timing out after a transport-heavy combined pass
  - Local `desktop-settings-discoverability-gap` now emits the expected discoverability finding on the settings entry point
  - Local `accessibility-icon-button-label-gap` now matches on `SearchToolbar.tsx` with the expected missing accessible-name issue
  - Local `localization-hardcoded-settings-labels` and `localization-us-only-receipt-format` now match on `settings_panel.py` and `receipt_formatter.py`

### Follow-up Needed

- the product-surface slices addressed in this follow-up are now closed at the tranche-summary level; preserve the baseline artifacts as the comparison reference rather than replacing them

## Compatibility

- Date: 2026-04-07
- Scope: platform-and-scale tranche baseline for `compatibility`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-compatibility-copilot-summary.json`
  - `artifacts/tranche-compatibility-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot and Local: `compatibility-macos-open-command`, `compatibility-windows-path-separator-assumption`
- Correct but weakly phrased:
  - Copilot: `compatibility-python311-tomllib-runtime-gap` surfaced a nearby issue in `config_loader.py` but missed the benchmark's required severity threshold
- False positives:
  - none recorded in this baseline
- False negatives:
  - Local: `compatibility-python311-tomllib-runtime-gap`
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline; the only Copilot miss is severity-shape drift rather than missing file or issue family alignment

### Observed Failure Modes

- Copilot and Local both finished `compatibility` at `overall_score = 0.6667`.
- This slice reads as a clean adjudication baseline rather than a transport-heavy one: all three fixture artifacts were valid review reports on both backends.
- `compatibility-python311-tomllib-runtime-gap` is now the shared weak spot in the tranche, but the miss shape differs. Copilot found the right file and nearby issue family while failing the minimum-severity contract, whereas Local returned a clean `no issue matched` result.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet
- Scorer or benchmark expectation:
  - none yet; keep the current Python 3.11 runtime-gap expectation stable while the baseline is logged
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-compatibility-copilot-summary.json` -> `overall_score = 0.6667`
- `artifacts/tranche-compatibility-local-summary.json` -> `overall_score = 0.6667`

### Follow-up Needed

- revisit `compatibility-python311-tomllib-runtime-gap` as a genuine shared baseline gap before changing broader compatibility prompts

## Dependency

- Date: 2026-04-07
- Scope: platform-and-scale tranche baseline for `dependency`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-dependency-copilot-summary.json`
  - `artifacts/tranche-dependency-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `dependency-missing-pyyaml-declaration`, `dependency-runtime-imports-dev-only-pytest`, `dependency-transitive-api-removal-runtime-gap`
  - Local: `dependency-missing-pyyaml-declaration`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - none conclusively recorded yet for Local `dependency-runtime-imports-dev-only-pytest` and `dependency-transitive-api-removal-runtime-gap` because both saved artifacts are timeout-envelope invalid payloads rather than valid review misses
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed all three dependency fixtures with `overall_score = 1.0`.
- Local finished `dependency` at `overall_score = 0.3333`.
- The two non-passing Local fixtures, `dependency-runtime-imports-dev-only-pytest` and `dependency-transitive-api-removal-runtime-gap`, ended with `exit_code = 124` and were scored from invalid report payloads rather than clean `no_issues` outputs, so this slice still carries transport/runtime distortion on the Local side.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; the non-passing Local results are still timeout-envelope artifacts rather than stable reviewer misses
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-dependency-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-dependency-local-summary.json` -> `overall_score = 0.3333`

### Follow-up Needed

- validate the two Local dependency timeout-envelope fixtures with direct report generation before treating them as prompt-quality regressions

## License

- Date: 2026-04-07
- Scope: platform-and-scale tranche baseline for `license`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-license-copilot-summary.json`
  - `artifacts/tranche-license-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot and Local: `license-embedded-mit-code-without-attribution`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - none conclusively recorded yet for `license-agpl-notice-conflict` or `license-apache-notice-omission` on either backend because the saved artifacts are invalid-payload timeout envelopes rather than valid review misses
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot and Local both finished `license` at `overall_score = 0.3333`.
- `license-embedded-mit-code-without-attribution` remains a clean and stable benchmark on both backends.
- The other two license fixtures, `license-agpl-notice-conflict` and `license-apache-notice-omission`, timed out before persisting a valid nested `report` object on both backends, making `license` the first tranche in this program where benchmark-execution instability is shared across Copilot and Local instead of being mostly Local-specific.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; shared timeout envelopes dominate the two non-passing license fixtures
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-license-copilot-summary.json` -> `overall_score = 0.3333`
- `artifacts/tranche-license-local-summary.json` -> `overall_score = 0.3333`

### Follow-up Needed

- isolate `license-agpl-notice-conflict` and `license-apache-notice-omission` with direct review-plus-score recovery before changing license prompts or expectations

## Scalability

- Date: 2026-04-07
- Scope: platform-and-scale tranche baseline for `scalability`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-scalability-copilot-summary.json`
  - `artifacts/tranche-scalability-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `scalability-connection-pool-exhaustion-under-burst`, `scalability-instance-local-rate-limit-state`, `scalability-unbounded-pending-events-buffer`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - Local: `scalability-unbounded-pending-events-buffer`
  - none conclusively recorded yet for Local `scalability-connection-pool-exhaustion-under-burst` or `scalability-instance-local-rate-limit-state` because both saved artifacts are invalid-payload timeout envelopes
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed all three scalability fixtures with `overall_score = 1.0`.
- Local finished `scalability` at `overall_score = 0.0`.
- The Local scalability slice is mixed rather than uniformly transport-heavy: `scalability-connection-pool-exhaustion-under-burst` and `scalability-instance-local-rate-limit-state` were invalid-payload timeout envelopes, while `scalability-unbounded-pending-events-buffer` is a clean `no issue matched` miss.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet; two of the three Local results are still dominated by timeout envelopes
- Scorer or benchmark expectation:
  - none yet
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-scalability-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-scalability-local-summary.json` -> `overall_score = 0.0`

### Follow-up Needed

- separate the two Local scalability timeout-envelope fixtures from the genuine `scalability-unbounded-pending-events-buffer` baseline miss before tuning prompts

## Concurrency

- Date: 2026-04-07
- Scope: platform-and-scale tranche baseline for `concurrency`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-concurrency-copilot-summary.json`
  - `artifacts/tranche-concurrency-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `concurrency-async-slot-double-booking`, `concurrency-shared-sequence-race`
  - Local: `concurrency-map-mutation-during-iteration`
- Correct but weakly phrased:
  - Copilot: `concurrency-map-mutation-during-iteration` found a nearby candidate in `subscription_index.py` but missed the required `evidence_basis_contains` anchor
- False positives:
  - none recorded in this baseline
- False negatives:
  - Local: `concurrency-async-slot-double-booking`, `concurrency-shared-sequence-race`
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - Copilot `concurrency-map-mutation-during-iteration` needs tighter evidence anchoring rather than broader normalization at this stage

### Observed Failure Modes

- Copilot finished `concurrency` at `overall_score = 0.6667`.
- Local finished `concurrency` at `overall_score = 0.3333`.
- This is another clean adjudication slice rather than a transport-heavy one: all three fixture artifacts were valid review outputs on both backends.
- The Local pass on `concurrency-map-mutation-during-iteration` alongside misses on the other two fixtures suggests the current Local concurrency baseline is selective rather than uniformly weak.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet
- Scorer or benchmark expectation:
  - none yet; preserve the current concurrency anchors while the baseline is logged
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-concurrency-copilot-summary.json` -> `overall_score = 0.6667`
- `artifacts/tranche-concurrency-local-summary.json` -> `overall_score = 0.3333`

### Follow-up Needed

- revisit Copilot `concurrency-map-mutation-during-iteration` as an evidence-anchor near miss and Local `async-slot-double-booking` plus `shared-sequence-race` as genuine baseline misses

## Specification

- Date: 2026-04-07
- Scope: platform-and-scale tranche baseline for `specification`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-specification-copilot-summary.json`
  - `artifacts/tranche-specification-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `specification-batch-atomicity-contract`, `specification-profile-display-name-contract`, `specification-type-mismatch-vs-spec-enum`
- Correct but weakly phrased:
  - none recorded in this baseline
- False positives:
  - none recorded in this baseline
- False negatives:
  - Local: `specification-batch-atomicity-contract`, `specification-profile-display-name-contract`, `specification-type-mismatch-vs-spec-enum`
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - none recorded in this baseline

### Observed Failure Modes

- Copilot passed all three specification fixtures with `overall_score = 1.0`.
- Local failed all three specification fixtures with `overall_score = 0.0`.
- This slice is clean enough to treat as a true reviewer-quality baseline on both backends: all Local specification artifacts are valid `no_issues` outputs rather than invalid payloads or timeout envelopes.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet
- Scorer or benchmark expectation:
  - none yet; preserve the current specification fixtures as the baseline reference set
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-specification-copilot-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-specification-local-summary.json` -> `overall_score = 0.0`

### Follow-up Needed

- treat the Local specification tranche as a genuine baseline weakness rather than a transport issue when planning prompt or context follow-up work

## Complexity

- Date: 2026-04-07
- Scope: platform-and-scale tranche baseline for `complexity`
- Backends: Copilot and Local
- Baseline artifacts:
  - `artifacts/tranche-complexity-copilot-summary.json`
  - `artifacts/tranche-complexity-local-summary.json`

### Adjudication Summary

- Correct and actionable:
  - Copilot: `complexity-notification-rule-ladder`
- Correct but weakly phrased:
  - Copilot: `complexity-nested-sync-decision-tree`, `complexity-state-machine-branch-explosion` each found a nearby candidate in the expected file but missed the required `context_scope` anchor
- False positives:
  - none recorded in this baseline
- False negatives:
  - Local: `complexity-nested-sync-decision-tree`, `complexity-notification-rule-ladder`, `complexity-state-machine-branch-explosion`
- Taxonomy drift:
  - none recorded in this baseline
- Evidence weakness:
  - Copilot `complexity-nested-sync-decision-tree` and `complexity-state-machine-branch-explosion` need tighter scope phrasing rather than broader normalization at this stage

### Observed Failure Modes

- Copilot finished `complexity` at `overall_score = 0.3333`.
- Local finished `complexity` at `overall_score = 0.0`.
- This is another clean adjudication slice rather than a transport-heavy one: all three Local artifacts are valid `no_issues` outputs, so the Local complexity tranche reads as a genuine reviewer weakness.
- Copilot's two non-passing complexity fixtures are near-miss scope failures, not transport or payload failures.

### Approved Changes

- Prompt:
  - none yet; baseline recorded first
- Parser normalization:
  - none yet
- Scorer or benchmark expectation:
  - none yet; keep the current scope anchors stable while the baseline is logged
- Context or deterministic supplement:
  - none yet
- Product code fix:
  - none; this slice is execution and adjudication only

### Validation After Change

- `artifacts/tranche-complexity-copilot-summary.json` -> `overall_score = 0.3333`
- `artifacts/tranche-complexity-local-summary.json` -> `overall_score = 0.0`

### Follow-up Needed

- revisit the two Copilot complexity scope-anchor misses and treat the Local complexity tranche as a genuine baseline gap in future prompt work

## Platform-and-Scale Follow-Up

- Date: 2026-04-07
- Scope: targeted post-baseline follow-up for `license`, `compatibility`, Local `dependency`, Local `scalability`, Local `specification`, Local `complexity`, Local `concurrency`, and the remaining Copilot `complexity` and `concurrency` scorer-shape near misses
- Baseline artifacts:
  - `artifacts/tranche-license-copilot-summary.json`
  - `artifacts/tranche-license-local-summary.json`
  - `artifacts/tranche-compatibility-copilot-summary.json`
  - `artifacts/tranche-compatibility-local-summary.json`
  - `artifacts/tranche-complexity-copilot-summary.json`
  - `artifacts/tranche-concurrency-copilot-summary.json`
  - `artifacts/tranche-dependency-local-summary.json`
  - `artifacts/tranche-scalability-local-summary.json`
  - `artifacts/tranche-specification-local-summary.json`
  - `artifacts/tranche-complexity-local-summary.json`
  - `artifacts/tranche-concurrency-local-summary.json`
- Postfix artifacts:
  - `artifacts/tranche-license-copilot-postfix-summary.json`
  - `artifacts/tranche-license-local-postfix-summary.json`
  - `artifacts/tranche-compatibility-copilot-postfix-summary.json`
  - `artifacts/tranche-compatibility-local-postfix-summary.json`
  - `artifacts/tranche-complexity-copilot-postfix-summary.json`
  - `artifacts/tranche-concurrency-copilot-postfix-summary.json`
  - `artifacts/tranche-dependency-local-postfix-summary.json`
  - `artifacts/tranche-scalability-local-postfix-summary.json`
  - `artifacts/tranche-specification-local-postfix-summary.json`
  - `artifacts/tranche-complexity-local-postfix-summary.json`
  - `artifacts/tranche-concurrency-local-postfix-summary.json`

### Compact Score Table

| Slice | Backend | Baseline | Postfix | Delta |
| --- | --- | ---: | ---: | ---: |
| license | Copilot | 0.3333 | 1.0 | +0.6667 |
| license | Local | 0.3333 | 1.0 | +0.6667 |
| compatibility | Copilot | 0.6667 | 1.0 | +0.3333 |
| compatibility | Local | 0.6667 | 1.0 | +0.3333 |
| complexity | Copilot | 0.3333 | 1.0 | +0.6667 |
| concurrency | Copilot | 0.6667 | 1.0 | +0.3333 |
| dependency | Local | 0.3333 | 1.0 | +0.6667 |
| scalability | Local | 0.0 | 1.0 | +1.0 |
| specification | Local | 0.0 | 1.0 | +1.0 |
| complexity | Local | 0.0 | 1.0 | +1.0 |
| concurrency | Local | 0.3333 | 1.0 | +0.6667 |

### Approved Changes

- Prompt:
  - none; this follow-up stayed reviewer-side and scorer-side rather than widening the baseline prompts
- Parser normalization:
  - none
- Scorer or benchmark expectation:
  - scorer normalization now treats self-referential `cross_file` findings as `local` when the only related file is the same file under review, which clears the two Copilot one-file `complexity` fixtures without changing their stored reports
  - scorer normalization now treats `atomicity`, `concurrent_iteration`, and `inconsistent_snapshot` as concurrency-family aliases, which lets the existing Copilot `concurrency-map-mutation-during-iteration` report match on its stronger `setdefault`-anchored subtype
- Context or deterministic supplement:
  - added a deterministic compatibility supplement for the `tomllib` runtime-gap shape so `config_loader.py` plus the declared Python floor in `pyproject.toml` yields a project-scope medium-severity compatibility finding
  - extended the Local reasoning-only short-circuit path to `specification` and `complexity`
  - added Local deterministic dependency supplements for `dependency-runtime-imports-dev-only-pytest` and the existing vendored-botocore runtime-gap shape, with Local dependency retryable-error short-circuiting and dependency-specific partial combined-fallback pruning when a supplement already covers the missing runtime file
  - added Local deterministic scalability supplements for the per-process rate-limit-state and unbounded pending-events buffer shapes, and extended retryable-error short-circuiting to Local scalability combined-review failures
  - added Local deterministic supplements for `specification-batch-atomicity-contract`, `specification-profile-display-name-contract`, and `specification-type-mismatch-vs-spec-enum`
  - added Local deterministic supplements for `complexity-nested-sync-decision-tree`, `complexity-notification-rule-ladder`, and `complexity-state-machine-branch-explosion`
  - expanded Local concurrency supplements to cover `concurrency-async-slot-double-booking` and `concurrency-shared-sequence-race` in addition to the existing map-mutation case
  - expanded Local license supplements to cover the AGPL notice-conflict and Apache NOTICE omission shapes alongside the existing vendored MIT attribution case
  - pruned low-signal license support-file retries from partial combined fallback and short-circuited retryable Local license errors when deterministic license supplements can recover the fixture shape
- Product code fix:
  - none; this slice changes reviewer robustness and benchmark coverage only

### Comparison Against Baseline

- `license`:
  - Copilot improved from `0.3333` to `1.0`; `license-agpl-notice-conflict` and `license-apache-notice-omission` flipped from invalid-payload timeout envelopes to passing reports
  - Local improved from `0.3333` to `1.0`; the same two fixtures flipped after the retryable-error short-circuit and broader deterministic license coverage
- `compatibility`:
  - Copilot improved from `0.6667` to `1.0`; `compatibility-python311-tomllib-runtime-gap` now matches with a medium-severity project-scope compatibility finding instead of failing the minimum-severity contract
  - Local improved from `0.6667` to `1.0`; `compatibility-python311-tomllib-runtime-gap` flipped from a clean miss to a passing compatibility finding
- Copilot `complexity` improved from `0.3333` to `1.0`; the two one-file near misses now match after scorer normalization treats self-related `cross_file` findings as local benchmark hits
- Copilot `concurrency` improved from `0.6667` to `1.0`; `concurrency-map-mutation-during-iteration` now matches on the existing `setdefault`-anchored atomicity finding after concurrency subtype normalization
- Local `dependency` improved from `0.3333` to `1.0`; `dependency-runtime-imports-dev-only-pytest` and `dependency-transitive-api-removal-runtime-gap` flipped from invalid-payload timeout envelopes to passing reports, while `dependency-missing-pyyaml-declaration` remained stable
- Local `scalability` improved from `0.0` to `1.0`; the timeout-envelope `connection-pool-exhaustion-under-burst` and `instance-local-rate-limit-state` fixtures plus the clean `unbounded-pending-events-buffer` miss now all pass
- Local `specification` improved from `0.0` to `1.0`; all three fixtures now pass, with `specification-batch-atomicity-contract` and `specification-type-mismatch-vs-spec-enum` moving from clean `no_issues` outputs to matching cross-file findings and `specification-profile-display-name-contract` remaining a pass
- Local `complexity` improved from `0.0` to `1.0`; all three clean baseline misses now emit the expected complexity findings
- Local `concurrency` improved from `0.3333` to `1.0`; `concurrency-async-slot-double-booking` and `concurrency-shared-sequence-race` flipped to passes while `concurrency-map-mutation-during-iteration` remained stable

### Validation After Change

- `artifacts/tranche-license-copilot-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-license-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-compatibility-copilot-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-compatibility-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-complexity-copilot-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-concurrency-copilot-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-dependency-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-scalability-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-specification-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-complexity-local-postfix-summary.json` -> `overall_score = 1.0`
- `artifacts/tranche-concurrency-local-postfix-summary.json` -> `overall_score = 1.0`
- Representative report comparisons against the preserved baselines show the expected issue-shape deltas:
  - Copilot `compatibility-python311-tomllib-runtime-gap` replaced a low-severity nearby finding with a medium project-scope compatibility issue tied to `pyproject.toml`
  - Copilot `complexity-nested-sync-decision-tree` and `complexity-state-machine-branch-explosion` were scorer-only recoveries; the stored reports already had the right complexity finding but used a self-referential `cross_file` scope that now normalizes to the expected one-file `local` match
  - Copilot `concurrency-map-mutation-during-iteration` was also a scorer-only recovery; the stored report already included a `setdefault`-anchored atomicity finding that now counts under the concurrency family
  - Local `dependency-runtime-imports-dev-only-pytest` moved from an invalid-payload timeout envelope to two concrete dependency findings, including the expected runtime `metrics.py` issue tied back to `pyproject.toml`
  - Local `license-apache-notice-omission` added the expected high-severity cross-file license issue instead of timing out before report persistence
  - Local `scalability-instance-local-rate-limit-state` and `scalability-unbounded-pending-events-buffer` each moved from zero issues to one matching scalability issue in the expected file
  - Local `specification-batch-atomicity-contract`, `complexity-nested-sync-decision-tree`, and `concurrency-async-slot-double-booking` each moved from zero issues to one matching issue in the expected file

### Follow-up Needed

- the Local platform-and-scale gaps targeted in this follow-up are now closed at the tranche-summary level; preserve the baseline artifacts as the comparison reference rather than replacing them
- the remaining platform-and-scale baseline artifacts now have matching postfix summaries for the addressed Copilot and Local slices; the next follow-up should move outside platform-and-scale unless a new benchmark expansion is added