# Quality Benchmarks

AICodeReviewer includes a small holistic benchmark suite for review-quality regression checks.

These benchmarks are not unit tests for one helper or parser branch. They model realistic review scenarios, run the tool against known fixture projects, and score whether the resulting findings match the expected issue shape.

Some benchmark categories also rely on narrow reviewer-side normalization or deterministic supplements when a backend drifts into subtype labels or entirely misses an obvious, fixture-specific structural problem. Current examples include cache invalidation, cross-file N+1 query loops, controller-to-repository boundary bypasses, GET-based create routes in `api_design`, macOS-only `open` launch helpers in `compatibility`, stale return-shape caller mismatches, the Local `security` shell-command-injection, SSRF, path-traversal, raw-SQL interpolation, and unsafe-YAML deserialization cases, and the Local `ui_ux` cases for desktop busy feedback, wizard dependency orientation, and blank loading/error/empty-state handling.

## What The Benchmarks Cover

The fixture catalog lives under `benchmarks/holistic_review/fixtures/`.

Current scenarios include:

- accessibility gaps such as icon-only buttons or form controls without an accessible name for screen reader users, or modal panels that lack dialog semantics
- API design gaps such as mutating create endpoints exposed as GET routes instead of using a write-oriented HTTP method, or POST creation routes that never communicate clear `201 Created` semantics to clients
- compatibility gaps such as desktop helpers that hardcode the macOS `open` command instead of using platform-aware report launching, or runtime-version assumptions that break the declared Python support range
- cross-file contract drift
- authorization regressions
- cache invalidation gaps
- concurrency gaps such as threaded workers mutating shared sequence counters or recipient queues without synchronization, or async reservation flows that await between checking shared capacity and decrementing it
- complexity gaps such as helpers that collapse multiple policy dimensions into a deeply nested decision tree or a long branch-heavy rule ladder that is hard to reason about safely
- dependency gaps such as source files that import third-party packages the project metadata never declares, or runtime modules that import packages scoped only to dev/test extras
- license gaps such as projects that declare permissive distribution terms while their generated license inventory shows a copyleft runtime dependency, third-party notices that waive Apache NOTICE obligations even though the packaged dependency is shipped in binaries, or vendored MIT code that ships without the original attribution and permission notice
- data-validation gaps such as validators that coerce fields but never enforce ordering, range, or boundary constraints before invalid data reaches scheduling or persistence code
- dead-code gaps such as always-disabled fallback branches, obsolete compatibility shims that are no longer wired into live flows, and stale feature-flag paths that leave dormant handlers behind
- documentation gaps such as READMEs or operator guides that still describe flags, environment variables, or flows the current implementation no longer supports
- error-handling gaps such as swallowed exceptions that still surface as success to callers or operators, or transient failures that are treated as terminal without a retry or recovery path
- localization gaps such as screens that bypass the translation helper for visible UI labels, or receipts that hardcode US-only date and currency formatting
- maintainability gaps such as duplicated active policy or parser logic split across multiple entry points, or controller classes that accumulate validation, persistence, orchestration, and presentation work in one place
- scalability gaps such as process-local coordination state that breaks once a service scales across workers, or in-memory buffers that grow without backpressure or capacity limits under sustained load
- specification gaps such as implementations that return fields or success states the external requirements file explicitly forbids, or omit response fields and guarantees the spec says clients must receive
- testing gaps such as source code that enforces a boundary contract but test coverage never exercises the edge-case or regression path, or service code that already implements a rollback/failure path that the suite never pins
- transaction boundary splits
- validation drift
- partial refactors and caller mismatch
- architectural layer leaks
- regression diffs such as default-setting changes that silently disable an existing feature path for users who rely on prior behavior, or inverted startup guards that stop a previously enabled workflow from running
- UI/UX gaps such as missing loading, error, and empty states
- UI/UX gaps such as destructive validation flow and weak recovery messaging in forms
- desktop UI/UX gaps such as blocking actions with weak busy-state and completion feedback
- desktop UI/UX gaps such as destructive confirmation flows without preview, cancel context, or undo
- desktop UI/UX gaps such as hidden settings architecture and weak option discoverability
- desktop UI/UX gaps such as multi-step wizard orientation and hidden dependencies between steps
- desktop UI/UX gaps such as cross-tab preference dependencies that silently override another tab's settings

Each fixture contains:

- a `fixture.json` manifest
- a small sample project or diff input
- expected findings with issue-type, severity, scope, and evidence expectations

## Test The Harness

To validate fixture discovery and evaluation logic without calling a live backend:

```bash
pytest tests/test_benchmarking.py tests/test_run_holistic_benchmarks.py -v
```

This verifies:

- fixture discovery
- report evaluation and scoring
- tool-mode runner argument construction
- repeated-run stability summaries

## Run The Benchmarks

To execute the benchmark runner against a configured backend:

```bash
python tools/run_holistic_benchmarks.py --backend local --skip-health-check
```

Typical useful variants:

```bash
python tools/run_holistic_benchmarks.py --backend copilot --fixture ui-loading-feedback-gap --skip-health-check
python tools/run_holistic_benchmarks.py --backend local --runs 3 --skip-health-check
python tools/run_holistic_benchmarks.py --backend bedrock --output-dir artifacts/holistic-benchmarks --summary-out artifacts/holistic-benchmarks/summary.json
```

Important flags:

- `--fixture <id>` limits execution to one or more named fixtures
- `--runs <n>` repeats the full benchmark set to measure stability
- `--output-dir <path>` controls where raw tool-mode reports are written
- `--summary-out <path>` writes a JSON summary file
- `--lang en` keeps benchmark output stable for comparisons
- `--skip-health-check` bypasses the backend readiness preflight when you already know the environment is valid
- `--fixture-timeout-seconds <n>` bounds each fixture subprocess separately so one stalled review does not hang the whole batch

Operational notes:

- `--timeout-seconds` still applies inside tool-mode `review`, but `--fixture-timeout-seconds` protects the outer benchmark runner and persists a JSON error envelope when a fixture exceeds its budget.
- This is especially useful with Local OpenAI-compatible backends, where a single `reasoning_content only` response can otherwise cascade into retries or fallbacks that consume the entire benchmark batch.

## When To Update Benchmarks

Update or add benchmark fixtures when:

- a new review type is introduced
- prompt guidance changes in a way that should improve finding quality
- a deterministic supplement is added to recover missed findings
- parser or scoring behavior changes for issue type, severity, or evidence matching

For example, the `accessibility` suite now includes a single-file toolbar case where an icon-only search button and adjacent input ship without a label or `aria-label`, leaving screen reader users without a stable accessible name for the primary controls, a fieldset-grouping case where related notification controls sit inside `fieldset` elements without a `legend`, so assistive technology does not announce the group label for the options, plus a modal-dialog case where a settings panel is rendered with plain div containers and no `role="dialog"` / `aria-modal` semantics. The `api_design` suite now includes a FastAPI handler that wires `create_invitation` to `@app.get("/api/invitations/create")` even though the route appends a new invitation, creating a direct HTTP-method semantics mismatch, a second creation-route case where `@app.post("/api/invitations")` returns the default 200 response and a raw dict without explicit created-resource semantics, plus a PATCH case where `patch_user_settings` is exposed under `@app.patch(...)` but replaces the stored document with `payload.model_dump()` so omitted fields are cleared instead of preserved as partial updates. The `compatibility` suite now includes a desktop report viewer that shells out to the macOS-only `open` command without any platform branching, leaving the feature broken on Windows and Linux, a runtime-version case where `config_loader.py` imports `tomllib` directly even though `pyproject.toml` still advertises Python 3.9 support, plus a path-handling case where `export_history.py` splits incoming paths on `/` and indexes the expected segments directly, which breaks when Windows supplies native backslash-separated paths. The `complexity` suite now includes one sync-strategy helper that collapses account state, retry mode, network conditions, and feature flags into one deeply nested decision tree, a notification-planning helper that turns channel selection, quiet hours, compliance mode, and account-tier exceptions into one long branch-heavy rule ladder, plus a workflow state-machine case where one transition helper mixes draft, queued, running, paused, and failed states with event, retry, and feature-flag branching in a single function. The `concurrency` suite now includes a threaded dispatcher case where worker threads read and increment `next_sequence` while mutating recipient queues without synchronization, an async reservation case where `reserve_slot` awaits between checking `available_slots` and decrementing it, allowing overlapping requests to double-book the same capacity, plus a topic-snapshot case where worker threads mutate `listeners_by_topic` while another path iterates the same shared map to build a snapshot. The `dependency` suite now includes a project where `config_writer.py` imports the third-party `yaml` module even though `pyproject.toml` never declares `PyYAML`, a second case where `metrics.py` imports `pytest` even though the manifest only lists it in a dev extra, which makes the runtime path depend on a test-only package, plus a vendored-API case where `aws_client.py` imports `botocore.vendored.requests` even though the declared modern botocore version no longer guarantees that runtime surface. The `license` suite now includes one project that ships under MIT while `licenses_check.csv` marks a runtime dependency as AGPL-3.0-only and `THIRD_PARTY_NOTICES.md` still claims every bundled package is permissive and MIT-compatible, a second project where the third-party notice file says a distributed Apache-2.0 dependency's upstream NOTICE does not need to ship with binaries, plus a bundled-source case where `markdown_table.py` is copied from the MIT-licensed tinytable package but the shipped notices say no third-party source is bundled and never preserve tinytable's original notice. The `localization` suite now includes a settings screen that mixes calls to `t(...)` with hardcoded visible labels such as `Sync now`, a receipt formatter that hardcodes `%m/%d/%Y` dates and dollar-prefixed amounts instead of using locale-aware presentation, plus a banner case where `renewal_banner.py` concatenates translation fragments around the customer name and renewal date instead of using one template translators can reorder for other languages. The `maintainability` suite now includes a cross-file case where CLI and GUI settings modules both implement the same `normalize_sync_window` logic, forcing future fixes to stay synchronized across entry points, a second cross-file case where manual and scheduled sync flows each define `parse_sync_selector` and the parser copies have already drifted into different wildcard, alias, and normalization rules, plus a single-file controller case where `SettingsController` mixes configuration loading, validation, persistence, sync orchestration, telemetry, and summary formatting in one class. The `scalability` suite now includes a cross-file rate-limiter case where `app.py` stores quota state in process-local `RATE_LIMIT_STATE` while `gunicorn.conf.py` runs four workers, a connection-pool case where burst export processing fans out 64 workers even though `db_pool.py` only exposes eight connections and each job holds a connection across slow remote work, plus a single-file buffer case where `event_buffer.py` appends every incoming payload into `pending_events` without any capacity limit or backpressure. The `security` suite now also includes a cross-file shell-injection case where `api.py` forwards request-controlled export arguments into `report_export.py`, which interpolates them into a single command string and executes it with `subprocess.run(..., shell=True)`, an IDOR case where `api.py` forwards a request-controlled `invoice_id` into `invoice_service.py`, which loads and returns that invoice without checking ownership against the current account, a JWT-signature-bypass case where `api.py` forwards a bearer token into `token_service.py`, which calls `jwt.decode(..., options={"verify_signature": False})`, an open-redirect case where `api.py` forwards a request-controlled `return_to` value into `redirects.py`, which returns that destination unchanged after login, a predictable-reset-token case where `api.py` forwards an email address into `password_reset.py`, which builds the reset token with `hashlib.sha256(email.encode(...)).hexdigest()`, an SSRF case where `api.py` forwards a request-controlled `avatar_url` into `avatar_fetcher.py`, which fetches it server-side with `requests.get(...)` and no internal-destination restrictions, a path-traversal case where `api.py` forwards a request-controlled download filename into `attachment_store.py`, which joins it onto an attachment root and opens the resulting path without constraining `..` traversal segments, a zip-slip case where `api.py` forwards a request-controlled theme archive path into `theme_importer.py`, which calls `archive.extractall(destination)` without validating archive member paths, a raw-SQL case where `api.py` forwards a request-controlled `status` filter into `user_repository.py`, which interpolates it directly into a `SELECT ... WHERE status = '{status}'` query before calling `db.execute(...)`, and an unsafe-deserialization case where `api.py` forwards request-controlled YAML into `settings_loader.py`, which calls `yaml.load(raw_config, Loader=yaml.Loader)` instead of a safe loader. The `specification` suite now includes a batch handler that returns `partial_success` and persists accepted items even though the requirements document says the batch must be atomic, a profile-response case where `build_profile_response` returns `name` and omits `email_verified` even though the spec says clients must receive `display_name` and `email_verified`, plus an enum-contract case where `build_sync_job_response` returns `sync_mode` as `bool(job.schedule_enabled)` even though the specification requires the string enum values `manual`, `scheduled`, or `disabled`. The `ui_ux` review type now has dedicated framework-aware prompt guidance plus benchmark fixtures that cover blank-screen feedback failures, destructive validation recovery flow, desktop busy-state feedback gaps, unsafe confirmation flows for destructive settings actions, settings discoverability failures in desktop configuration flows, wizard steps that hide prerequisite relationships, and cross-tab preference overrides that happen without clear explanation. The `dead_code` review type now also has benchmark fixtures for always-disabled legacy fallbacks, obsolete compatibility exporters that remain in the tree after the active flow moved elsewhere, and stale feature flags that strand dormant UI handlers. The `documentation` suite now includes a cross-file docs drift case where README.md still advertises a `--dry-run` safety flag even though `cli.py` no longer registers that option on the live command, a deployment-guide case where docs/deployment.md claims the worker is stateless and safe to scale horizontally even though `lease_store.py` keeps job claims in process-local memory, plus an operations-guide case where docs/operations.md still tells operators to export `SYNC_API_TOKEN` even though `config.py` now only reads `SYNC_TOKEN`. The `error_handling` suite now includes a cross-file swallowed-exception scenario where a job reports `completed` after `except Exception`, a context-manager cleanup case where `ExportLease.__exit__` only clears the running marker when no exception occurs, leaving failed exports stuck as already running, plus a retryless transient-timeout scenario where a worker surfaces `TimeoutError` as retryable but the controller disables sync immediately instead of preserving recovery. The `data_validation` suite now includes a cross-file scheduling case where a validator coerces `start_hour` and `end_hour` but never enforces that the end must come after the start, a rollout-percentage case where `rollout_percent` is coerced but never constrained to the valid 0..100 range before deployment batch sizing, plus an enum-constraint case where `delivery_mode` is coerced to a string but never checked against the supported values before workflow scheduling. The `testing` suite now includes a cross-file case where `validation.py` already rejects out-of-range `rollout_percent` values but `tests/test_api.py` never exercises that boundary, an order-service case where `orders.py` already performs `repository.rollback()` on payment failure but `tests/test_orders.py` only pins the success path and never verifies rollback, plus a timeout-retry case where `sync.py` already catches `TimeoutError` and retries once but `tests/test_sync.py` only covers the immediate success path. The `regression` suite now includes a diff-based default-setting change where `sync_enabled` flips from `True` to `False`, silently disabling background sync for users who rely on the prior startup behavior, an inverted startup-guard case where sync remains enabled in defaults but `app_startup.py` only starts the scheduler when `sync_enabled` is false, plus a stale-caller case where a reordered retry-delay helper signature leaves `sync_worker.py` passing the old positional argument order and changes existing retry timing behavior.

## Contributor Guidance

When you add a fixture:

- keep the sample project minimal and readable
- encode the expectation in `fixture.json` rather than in ad hoc test logic
- prefer one clear benchmark scenario over a large mixed example
- update [contributing.md](contributing.md) and [README.md](../README.md) if the workflow changes

If the benchmark catalog meaningfully expands, also update:

- [docs/README.md](README.md)
- [docs/review-types.md](review-types.md) when a benchmark clarifies review-type semantics
