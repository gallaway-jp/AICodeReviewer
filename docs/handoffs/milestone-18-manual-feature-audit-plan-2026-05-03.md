# Milestone 18 Manual Feature Audit Plan

Date: 2026-05-03

## Objective

Run a deliberate manual audit over the features AICodeReviewer claims to ship, verify that each one is actually implemented and behaves as documented, and use that pass to tighten the maintained docs wherever the product and docs have drifted.

This milestone is intentionally verification-first:

- confirm the feature exists
- confirm the feature works on the documented path
- confirm the docs describe the actual behavior rather than an earlier milestone snapshot
- log gaps as either product defects, documentation defects, or environment-specific limits

## Current Environment Backend Profile

The audit plan should reflect what this machine can actually exercise right now rather than treating every documented backend as equally available.

Backend status as of 2026-05-03:

| Backend | Local prerequisite status | Product health result | Audit stance |
|---|---|---|---|
| `local` | configured in `config.ini`; OpenAI-compatible endpoint at `http://localhost:1234` responded with HTTP 200; explicit test model pinned to `qwen/qwen3.5-9b` | `ready=true` | fully runnable now; use as the default backend for this milestone's manual execution |
| `bedrock` | AWS CLI installed; SSO profile `colin` refreshed; explicit test model pinned to `amazon.nova-micro-v1:0` | `ready=true` | runnable now; use Nova Micro for low-cost Bedrock validation on this machine |
| `kiro` | native Windows `kiro-cli.exe` installed and authenticated; explicit test model pinned to `minimax-m2.1` | `ready=true` on the native Windows path | runnable now; use native Windows Kiro and keep WSL only as a fallback compatibility path |
| `copilot` | native Copilot CLI installed and authenticated; explicit test model pinned to `gpt-5-mini` | `ready=true` | runnable now; avoid `auto` during testing so premium requests are not consumed |

Backend-specific execution rule for this milestone:

1. Run backend-dependent manual sessions against `local` first.
2. Keep `bedrock`, `kiro`, and `copilot` in the checklist so documentation and workflow claims are still audited.
3. Reclassify a backend from `blocked by environment` to runnable as soon as we verify a real local path, and record any remaining mismatch as product or docs drift rather than keeping a stale environment block.
4. Do not weaken the docs just because this machine lacks a prerequisite; only update docs when the product claim itself is wrong, incomplete, or misleading.

## Live Session Tracker

| Session | Focus | Backend scope on this machine | Status | Latest result |
|---|---|---|---|---|
| S1 | Install and startup baseline | no backend dependency; packaged and source install paths both available now | completed | pass for source install and packaged installer smoke validation; GUI opened on Review tab; earlier Copilot startup noise was traced and reduced |
| S2 | Backend configuration and health | all four configured backends are now runnable on this machine | in progress | local, copilot, kiro, and bedrock health checks all pass with explicit low-cost test models; health surfaces are normalized and the Local LLM Settings save/rotate/revoke path is now covered through the real GUI widgets |
| S3 | Core CLI review flows | run with local backend first | in progress | dry run, preset expansion, patch diff, commit diff, specification-only, and mixed specification review surfaces are now all exercised live; diff-scope widening and mixed-spec prompt loss were both fixed during the audit |
| S4 | Tool mode and report artifacts | run with local backend first | completed | local tool-mode review, health, resume, fix-plan, apply-fixes, and cancellation envelopes are exercised end to end on an isolated fixture; LM Studio model advertisement parsing and specification dry-run spec loading were fixed during the pass |
| S5 | GUI core review workflow | run with local backend first | completed | scheduler-backed queue visibility, queued-cancel behavior, and recent-completed queue entries now have live desktop evidence alongside the earlier Output Log and health-dialog probe |
| S6 | GUI detach, restore, desktop ergonomics | backend-agnostic after startup | in progress | shared status-bar detach behavior and startup presentation with reopened detached windows now have live desktop evidence; mixed-DPI cross-monitor validation is blocked on this machine because only one display is currently available to the probe |
| S7 | Addons and generated addon review | mostly backend-agnostic; use local only if generation path is exercised | completed | live desktop Addon Review probing now covers preview load, diff inspection, approve/reject decisions, and visible English wording on the real GUI surface |
| S8 | Benchmarks and quality tooling | local preferred; others blocked unless setup changes | in progress | live evidence now confirms the Benchmarks tab can start a local run, persist timestamped saved runs, auto-load the generated summary, compare two real saved summary artifacts, compare two real per-fixture report artifacts with `tools/compare_review_reports.py`, and follow the documented fixture-authoring evaluator path on a fresh temp fixture; the probes also flushed out and fixed runner-import, summary-metadata, and zero-count summary rendering defects |
| S9 | Local HTTP and shared scheduler | local backend path is the primary runnable slice | completed | embedded and CLI-started local HTTP startup now both have live evidence on `local`; route discovery, recommendations, job submission, SSE/event reads, report/artifact fetch, shared GUI queue visibility, and dedicated audit-log emission are all exercised end to end |
| S10 | Recovery, security, localization, polish | local and copilot fully runnable on this machine; remaining backend recovery slices only if new gaps surface | in progress | local recovery/localization and Copilot tool-aware sensitive-path handling now both have live evidence; the final reactive docs polish pass has been applied only to verified drift |

## Branch Strategy

This audit is broad enough to justify a `milestone/*` branch rather than mixing the work into unrelated feature branches.

Current branch for the audit:

- `milestone/18-manual-feature-audit`

Execution rules:

1. Keep the milestone branch as the umbrella integration branch for the audit log, checklist updates, and cross-cutting docs changes.
2. If a manual test session exposes a narrow fix that can land independently, cut a short-lived `feature/<slug>` branch from the milestone branch, validate it, and merge it back into the milestone branch.
3. If a fix is tiny and tightly coupled to the checklist or docs entry being updated, it can be committed directly on the milestone branch.
4. Merge the milestone branch into `main` only when the audited slices are documented, validated, and do not leave `main` in a half-audited state.

## Audit Output Expectations

Each audited feature area should produce four outputs:

1. Manual result
   - `pass`
   - `pass with doc drift`
   - `partial`
   - `fail`
   - `blocked by environment`
2. Evidence
   - command used
   - screen or artifact observed
   - output path if relevant
3. Follow-up classification
   - product bug
   - docs bug
   - environment prerequisite gap
   - accepted limitation
4. Landing action
   - no change needed
   - docs update only
   - fix on milestone branch
   - isolated fix on short-lived feature branch

## Recording Rules

For each manual session:

1. Start from the maintained docs page that claims the feature exists.
2. Follow the documented user path without silently correcting the steps.
3. Record the first point where reality diverges from the docs.
4. If the feature works only after undocumented setup or workaround, classify that as at least a docs defect.
5. If the feature exists but is weaker than the docs promise, classify that as `partial` rather than `pass`.
6. When a bug is fixed during the milestone, rerun the same manual path and update the recorded result rather than creating a second disconnected note.

## Session Order

The audit should run in practical user-facing order so the highest-value regressions surface first.

### Session 1: Install And Startup Baseline

Primary docs:

- `README.md`
- `docs/getting-started.md`
- `docs/user-manual.md`
- `docs/windows-installer.md`

Manual scope:

- source install with `pip install -e ".[gui]"`
- CLI help and basic entry-point startup
- GUI launch
- packaged Windows installer path when an installer artifact is available
- uninstall / preserve-data / remove-data flow when installer validation is in scope

Expected evidence:

- successful install command output
- `aicodereviewer --help`
- GUI launch confirmation
- installer artifact name, version, and install result when applicable

### Session 2: Backend Configuration And Health

Primary docs:

- `docs/backends.md`
- `docs/configuration.md`
- `docs/troubleshooting.md`
- `docs/user-manual.md`

Manual scope:

- Local LLM health path
- Bedrock health path as an environment-blocked verification unless AWS auth is added during the milestone
- Kiro health path as an environment-blocked verification unless Kiro CLI is installed during the milestone
- Copilot health path as an environment-blocked verification unless the local CLI install is repaired during the milestone
- Local LLM keyring-backed save / rotate / revoke behavior
- Local LLM web-search toggle behavior
- tool-aware file access enablement and fallback expectations

Expected evidence:

- health or check-connection commands per backend
- GUI Settings save/reload behavior where relevant
- explicit note of which backends are blocked by environment rather than product behavior

### Session 3: Core CLI Review Flows

Primary docs:

- `docs/cli.md`
- `docs/user-manual.md`
- `docs/review-types.md`

Manual scope:

- project review on `local`
- diff review from commits on `local`
- diff review from patch file on `local`
- specification review on `local`
- dry run on `local`
- multi-type review on `local`
- preset-driven review selection on `local`
- legacy interactive flow actions where feasible

Expected evidence:

- command lines used
- output or report artifact paths
- interactive behavior notes for resolve / ignore / AI fix / skip / force-resolve

### Session 4: Tool Mode And Report Artifacts

Primary docs:

- `docs/cli.md`
- `docs/reports.md`
- `docs/user-manual.md`

Manual scope:

- `review` on `local`
- `health` on `local` plus blocked-environment checks for other backends
- `fix-plan` on locally generated artifacts
- `apply-fixes` on locally generated artifacts
- `resume` on locally generated artifacts
- JSON envelope behavior
- report output naming and override behavior
- provenance in JSON/TXT/Markdown outputs
- cancel-file and timeout behavior where feasible

Expected evidence:

- saved JSON envelopes
- generated reports
- provenance fields or examples observed in output

### Session 5: GUI Core Review Workflow

Primary docs:

- `docs/gui.md`
- `docs/user-manual.md`

Manual scope:

- Review tab setup flow
- backend health checks from the GUI, with `local` expected to pass and the other configured backends expected to surface environment-blocked diagnostics
- project vs diff scope
- selected-files and diff-filter behavior
- queue panel visibility and cancellation path when scheduler-backed execution is active
- Results tab cards, filters, and issue inspection
- AI Fix preview/edit/apply flow
- session save/load/finalize flow
- Output Log save/clear/filter behavior

Expected evidence:

- report or session artifact paths
- screenshots only when needed to clarify mismatches
- explicit note when GUI wording differs from docs text

### Session 6: GUI Detach, Restore, And Desktop Ergonomics

Primary docs:

- `docs/gui.md`
- `docs/configuration.md`
- `docs/user-manual.md`

Manual scope:

- detach/redock for Benchmarks
- detach/redock for Addon Review
- detach/redock for Settings
- detach/redock for Output Log
- status-bar detach action behavior
- restart restore for detached windows
- `Ctrl+Shift+O` and `Ctrl+W`
- startup presentation behavior
- mixed-DPI stability mode and `automatic_dpi_awareness` override behavior on Windows when feasible

Expected evidence:

- observed detached-page state
- restored geometry / reopen behavior
- any mismatch between docs and actual labels or keyboard shortcuts

### Session 7: Addons And Generated Addon Review

Primary docs:

- `docs/addons.md`
- `docs/user-manual.md`
- `docs/gui.md`

Manual scope:

- addon discovery from `addons.paths`
- review-pack addon loading
- backend-provider addon loading
- Settings-surface contributor rendering
- editor-hook path if feasible
- `analyze-repo`
- `review-addon-preview`
- `approve-addon-preview`
- GUI Addon Review tab load / diff / approve / reject / detach flow

Expected evidence:

- `--list-addons` output
- generated preview directory contents
- approval decision artifacts
- GUI Addon Review behavior notes

### Session 8: Benchmarks And Quality Regression Tooling

Primary docs:

- `docs/benchmarks.md`
- `docs/review-quality-program.md`
- `docs/review-quality-log.md`
- `docs/user-manual.md`

Manual scope:

- benchmark harness tests
- benchmark runner on at least the `local` backend
- fresh-run and compare-run workflow in the GUI Benchmarks tab
- fixture authoring workflow sanity check
- `tools/compare_review_reports.py`
- generated-addon judged-quality or validation helper paths when environment allows

Expected evidence:

- summary JSON paths
- compare workflow screenshots or notes only when needed
- explicit `blocked by environment` classification when a backend-specific benchmark path cannot be run

### Session 9: Local HTTP And Shared Scheduler Paths

Primary docs:

- `docs/http-api.md`
- `docs/local-http-quick-reference.md`
- `docs/user-manual.md`

Manual scope:

- `serve-api` on `local`
- `/api/backends`
- `/api/review-types`
- `/api/recommendations/review-types`
- job submission
- event streaming
- report fetch
- embedded local HTTP startup from GUI Settings
- shared queue/runtime visibility between GUI and API where feasible

Expected evidence:

- curl or equivalent requests
- returned job ids and report payloads
- note whether scheduler-backed queue state is visible as documented

### Session 10: Recovery, Security, Localization, And Final Polish

Primary docs:

- `docs/troubleshooting.md`
- `docs/security.md`
- `docs/user-manual.md`
- `docs/reports.md`

Manual scope:

- one recovery path per available backend
- English and Japanese UI/output sanity check
- sensitive-path handling for tool-aware file access
- audit-log behavior where applicable
- final pass over any docs that were updated reactively during earlier sessions

Expected evidence:

- before/after failure text when reproduced
- language toggle result
- note of any remaining accepted limitations that should be documented explicitly

## Session Template

Use this template for each manual test slice:

```text
Session:
Feature:
Docs followed:
Environment prerequisites:
Commands / actions performed:
Observed result:
Classification: pass | pass with doc drift | partial | fail | blocked by environment
Evidence:
Follow-up:
Landing branch:
```

## Merge Criteria For The Milestone

Do not merge `milestone/18-manual-feature-audit` into `main` until:

1. every session above has a recorded result
2. every `fail` or `partial` result has either a landed fix or an explicit documented limitation
3. doc changes made during the audit reflect the actual final behavior after reruns
4. at least one focused automated validation or behavior check has been run for each code fix made during the milestone
5. the remaining open items, if any, are narrow enough to leave `main` in a coherent state rather than a half-audited one

## First Recommended Execution Slice

Start with these in order:

1. Session 1: Install And Startup Baseline
2. Session 3: Core CLI Review Flows
3. Session 5: GUI Core Review Workflow
4. Session 6: GUI Detach, Restore, And Desktop Ergonomics

That sequence gives the fastest signal on whether the current docs and user-facing product still match the core promised experience before we spend time on the more specialized addon, benchmark, and local-HTTP paths.

## Session 1 Working Log

Current status: completed for both the source-install baseline and the packaged-installer smoke slice

Observed so far on 2026-05-03:

- Source install step succeeded with `python -m pip install -e ".[gui]"` from the milestone worktree.
- The install step replaced an older preexisting editable install that still reported `aicodereviewer 0.1.0` in this environment; after reinstall, the imported package version is `0.3.0`.
- The installed console entrypoint launched successfully with `aicodereviewer.exe --help`.
- A packaged installer artifact was fetched from CI (`AICodeReviewer-Setup-0.3.1.exe`, run `24192855653`) and passed current-user smoke validation.
- The GUI launch command started from the same editable install without an immediate process crash.
- An earlier Copilot startup warning was traced to eager inactive-backend model refresh plus a stale Copilot SDK minimum; the startup path was quiet on rerun after the fix and SDK upgrade.
- Visible confirmation from the active desktop session showed that the GUI opened normally and landed on the expected Review tab.
- Current Session 1 classification: `pass` for the documented source-install startup path and the packaged-installer smoke path.

Follow-up notes:

- Installer smoke evidence is stored under `artifacts/manual-installer-validation/20260503-181225/summary.md`.
- Session 2 should now record backend-specific outcomes rather than treating Copilot and Kiro as environment-blocked on this machine.

## Session 2 Working Log

Current status: backend readiness repaired; health reporting is normalized; Local LLM credential actions and backend-specific Bedrock, Kiro, and Copilot Settings persistence now have real GUI-surface coverage before broader manual GUI and CLI passes

Observed so far on 2026-05-03:

- Local, Bedrock, Kiro, and Copilot all pass current connection and setup checks on this machine with explicit low-cost test models.
- The GUI health dialog now preserves full remediation sentences when a hint includes a URL and renders the documentation link on its own clickable row.
- The CLI `--check-connection` path now prints one normalized remediation hint from the shared backend/category mapping instead of appending the older extra `conn.hint_*` block.
- Focused regression coverage now exists for the health-dialog helper rendering path and for CLI connection-hint fallback behavior.
- The legacy `conn.hint_*` translation entries were removed after the CLI path stopped referencing them, reducing drift between the CLI and GUI health surfaces.
- The checked-in example addon now advertises a compatible minimum app version again, so the broader CLI addon-discovery suite no longer fails on the example manifest.
- The Local LLM Settings surface now has a restart-style GUI workflow regression covering API key save, rotate, replacement save, and revoke behavior with the same widgets and buttons exposed to users.
- Bedrock model and AWS fields, plus Kiro and Copilot CLI, model, and timeout fields, now also have restart-style GUI workflow coverage that saves in one app instance, reloads `config.ini`, and verifies restored widget state in a fresh app instance.
- Performance and Processing controls now have matching restart-style GUI workflow coverage for request rate, request interval, max file size, batch size, and `combine_files`, including the config layer's typed persistence contract for bytes, floats, ints, and raw boolean strings.
- A real GUI failure-path regression now verifies that an invalid numeric Settings value blocks save and keeps unrelated edits off disk across app restart.
- Real GUI workflow regressions now also cover forced `config.save()` failures and the minimum-one-output-format guard, including confirmation that the on-disk config stays unchanged across restart when either path blocks persistence.
- A live Settings-surface wording check on this machine found hardcoded English output-format and Reset Defaults copy plus refresh-button hover text; those labels and tooltips now flow through the localized string catalog and render correctly in Japanese on the real app surface.
- A live detached-Settings pass on this machine now confirms the detached Settings window opens with the expected localized title, retains the backend sections, redocks successfully, and still exposes the backend-specific hover/help text for Bedrock, Kiro, Copilot, and Local LLM fields on the real GUI surface.
- The focused Session 2 validation baseline has been widened again and remains clean: six Settings GUI workflow regressions, plus `tests/test_settings_actions.py`, `tests/test_config_and_auth.py`, and `tests/test_main_cli.py`, now pass together (`63 passed`).

Follow-up notes:

- Session 2 is now in good shape to hand off; the next active slice is Session 3 core CLI review-flow validation against `examples/sample_project` on the local backend.

## Session 3 Working Log

Current status: Session 3 is underway on the documented sample-project path; the Local backend false-clean path has been fixed, and the security review is being re-exercised on the live CLI flow

Observed so far on 2026-05-03:

- The local backend passes the current CLI connection check on the milestone code path with `qwen/qwen3.5-9b` against `http://localhost:1234`.
- The documented dry-run command against `D:\Development\Python\AICodeReviewer\examples\sample_project` behaves as expected: it lists all five sample-project files, keeps the selected type at `security`, and confirms that no API call is made.
- The preset-discovery CLI surface now has live coverage too: `aicodereviewer --list-type-presets` prints the built-in bundle definitions, and `--type runtime_safety --dry-run` expands to `security, error_handling, data_validation, dependency` on the sample project without spending backend time.
- The first real legacy interactive review run against the same sample project initially ended in a false clean result (`0 issue(s)` / `レビューで問題は見つかりませんでした！`) because the Local `qwen/qwen3.5-9b` path returned reasoning-only output and the reviewer short-circuited to an empty issue list for unsupported files.
- The reviewer now raises `LocalReasoningOnlyResponseError` when a Local reasoning-only response cannot be backed by deterministic supplements for the current files, and the legacy CLI entrypoint catches that path and exits `1` with the actionable non-thinking-model guidance instead of claiming the review was clean.
- Mid-run partial fallback now surfaces the same failure class cleanly too: if a combined batch produced some findings but an unrepresented file hits unsupported Local reasoning-only output during the individual retry pass, the reviewer aborts with a file-specific `LocalReasoningOnlyResponseError` instead of just logging the failed retry and returning an incomplete issue set.
- Focused reviewer validation now passes in the milestone worktree (`tests/test_reviewer.py -k "reasoning_only or partial_fallback_hits_local_reasoning_only_error or shell_command_injection_security_supplement"` → `8 passed`).
- A second live rerun of the sample-project security review showed the Local backend is non-deterministic on this model: that rerun parsed `11` combined findings, then entered partial per-file fallback and parsed `4` more findings for `utils.py` before continuing on `data_processor.py`.
- Local backend health/details now includes an explicit `Reasoning Control` row for LM Studio-native and OpenAI-compatible modes so the app states that per-request reasoning on/off is only available on LM Studio native mode and not on LM Studio's OpenAI-compatible chat-completions path.
- The latest live rerun on the manual-audit config (`api_type=lmstudio`, `reasoning=off`, same `qwen/qwen3.5-9b` model) no longer false-cleans: it parsed `6` issues from the combined batch, entered partial fallback for four unrepresented files, parsed `1` more issue for `data_processor.py`, and then continued on `calculator.py`.
- The first live interactive prompt was reached and exercised on the local sample-project security review. Confirmed branches so far: `コード表示`, `スキップ`, `AI修正` with explicit apply/cancel prompt, `無視` with free-text reason, and `解決済み` with re-analysis plus a force-resolve confirmation when the issue still reproduces.
- The interactive `コード表示` output exposed a real file-mapping defect: security findings whose snippets belonged to `user_auth.py` were displayed under `utils.py`, which only contains maintainability examples in the sample project. The root cause was the JSON response parser defaulting unmatched or unreliable finding filenames to the first file in the batch.
- That path-mapping bug is now patched in the milestone worktree: the parser prefers a unique `code_context` content match across the batch before falling back to the first file, and a focused regression was added in `tests/test_response_parser.py` to cover the `utils.py` versus `user_auth.py` case (`2 passed`).
- A fresh post-fix rerun now verifies the combined review path rebinding in live logs: six combined findings were explicitly reassigned from `<combined>` to `D:\Development\Python\AICodeReviewer\examples\sample_project\user_auth.py`, and `user_auth.py` no longer appeared in the fallback retry list.
- A targeted interactive diff-scope rerun against `examples/sample_project/user_auth.py` now confirms the corrected path on the actual prompt surface too: the first rendered issue showed `ファイル: D:\Development\Python\AICodeReviewer\examples\sample_project\user_auth.py` with the SQL injection snippet from `login()`.
- The documented commit-range diff workflow was also exercised on the milestone branch itself. The dry run correctly narrowed `HEAD~1..HEAD` to `docs/handoffs/milestone-18-manual-feature-audit-plan-2026-05-03.md`, but the first live documentation review widened that same diff to 15 documentation files because the documentation/dependency/license target augmentation path ignored diff-backed scan results. That scope bug is now fixed in the milestone worktree, focused reviewer regressions pass (`2 passed` selected), and a rerun now stays on the single changed handoff file through the interactive prompt surface.
- The specification-only legacy CLI path is now exercised on the minimal `specification-profile-display-name-contract` fixture too. A real Local run reached the interactive prompt and correctly reported that the implementation returns `name` where the requirements document mandates `display_name`, confirming that spec content is being read and applied on the live path.
- A mixed `specification,maintainability` legacy CLI run exposed a second prompt bug: on single-file combined reviews the shared user-message builder only attached the specification document when `review_type == "specification"`, so the live mixed run lost the spec text and inverted the contract, claiming the requirements demanded `name`. That bug is now fixed in the milestone worktree, a focused prompt-builder regression passes, and the rerun again reaches the interactive prompt with the correct `display_name` mismatch on-screen while still reporting `1 ファイル × 2 レビュータイプ`.
- The `AI修正` preview defect was traced to the shared fix prompt path. `get_fix()` was calling `_build_system_prompt("fix", lang)`, but the shared system-prompt builder still appended the review JSON schema even for fix mode. That made the Local backend return a review-style JSON payload and the fixer accepted it as whole-file replacement content.
- The AI-fix root cause is now patched in the milestone worktree: fix mode uses a dedicated full-file code-only system prompt, and `generate_ai_fix_result()` now rejects review-shaped JSON payloads instead of treating them as valid replacement content. Focused regressions now pass in `tests/test_fixer.py` and `tests/test_local_llm.py` (`5 passed` selected).
- A live Local backend fix probe against `examples/sample_project/user_auth.py` now returns code-like full-file content rather than JSON review output (`HAS_RESULT True`, `STARTS_WITH_JSON False`); the preview began with the module docstring and updated imports instead of a review envelope.
- The direct full-file Local fix probe remains semantically mixed: it is syntactically valid and removes MD5 usage, but it over-fixes unrelated vulnerabilities, adds an unused `os` import, changes pickle-backed data loading to JSON semantics, and rewrites `check_admin()` into a placeholder that effectively always returns `False`.
- The interactive `AI修正` preview on the rendered SQL injection finding is materially better than that raw full-file probe. On the same prompt surface it produced a focused patch that parameterized the vulnerable `login()` query and aligned `get_password()` to the same placeholder style without returning review JSON; the preview was declined rather than applied so the sample project stayed unchanged.

Follow-up notes:

- Session 3 now has enough live coverage to fold the verified behaviors back into `docs/cli.md` and `docs/user-manual.md`; the next active slice can move to Session 4 tool-mode/report-artifact coverage.

## Session 4 Working Log

Current status: completed on the isolated local fixture; the main artifact chain, local health path, and cancellation envelopes are exercised live, and both discovered Session 4 product defects were fixed during the pass

Observed so far on 2026-05-04:

- Session 4 artifacts are isolated under `artifacts/manual-session4/` using a copied `specification-profile-display-name-contract` fixture so tool-mode review and apply-fixes can run without mutating checked-in sample or benchmark files.
- Tool-mode `health --backend local --json-out artifacts/manual-session4/health-local.json` initially exposed a real product defect rather than an environment-only limitation. The current LM Studio native `/api/v1/models` response advertises models under `models[].key`, but the milestone worktree still parsed only OpenAI-style `data[].id`, so the configured model `qwen/qwen3.5-9b` was falsely reported as unavailable.
- Tool-mode specification dry run exposed a real bug in the milestone worktree: `review --dry-run --type specification --spec-file ...` failed with `Specification reviews require spec content` because `_load_spec_content(...)` discarded the spec file whenever `dry_run` was set even though tool-mode validation still requires loaded spec content.
- That tool-mode specification dry-run bug is now patched in the milestone worktree, and a focused regression now passes in `tests/test_main_cli.py` (`1 passed` selected). A rerun of the same command now emits a successful dry-run envelope with `status="dry_run"`, `files_scanned=1`, and the expected target path for `artifacts/manual-session4/spec-profile-fixture/src/profile_api.py`.
- The LM Studio model-advertisement false-negative is also now patched in the milestone worktree. A focused backend-health slice now passes (`3 passed` selected), and a rerun of `health --backend local --json-out artifacts/manual-session4/health-local-rerun.json` now returns `ready=true`, confirms `Model Availability`, and completes the live local-health path with a successful connection test.
- Tool-mode `review` is now exercised end to end on the same isolated fixture with both `--json-out` and `--output`. The command wrote `review-envelope.json`, `review-report.json`, `review-report_summary.txt`, and `review-report.md` under `artifacts/manual-session4/`, and the envelope preserved stable `issue_id` values (`issue-0001`, `issue-0002`).
- Tool-mode `resume` now has live coverage for both dry-run and completed review artifacts. The dry-run artifact normalizes to `workflow_stage="dry-run"` with `next_command=null`, while the completed review envelope normalizes to `workflow_stage="reviewed"`, `next_command="fix-plan"`, and respects `--issue-id issue-0001` filtering.
- Tool-mode `fix-plan` is now exercised against the saved review envelope rather than only a raw report file. A selected run for `issue-0001` completed successfully with `generated_count=1`, `failed_count=0`, and a focused `proposed_content` payload.
- Tool-mode `apply-fixes` is now exercised against that fix-plan artifact on the isolated fixture copy. The apply result completed successfully with `applied_count=1`, created `artifacts/manual-session4/spec-profile-fixture/src/profile_api.py.backup`, and rewrote only the copied fixture file.
- Tool-mode `resume` now also has live coverage for both `fix-plan` and `apply-fixes` artifacts. The fix-plan artifact normalizes to `workflow_stage="fix-planned"` with `next_command="apply-fixes"`, and the apply-results artifact normalizes to `workflow_stage="fixes-applied"` with `can_resume=false`.
- Timeout and cancel-file behavior are now both exercised on the tool-mode `review` path. Deterministic runs with `--timeout-seconds 0` and a pre-created `--cancel-file` sentinel both emitted JSON envelopes with `status="cancelled"`, `exit_code=3`, and machine-readable `cancel_reason` values (`timeout` and `cancel_file:...`).

Follow-up notes:

- Session 4 now has enough verified coverage to move forward. Any further tool-mode work should be adjacent polish or cross-backend follow-up rather than core-flow validation.

## Session 5 Working Log

Current status: completed for the planned GUI-core slice on this machine, with both harness-backed and live desktop evidence for the main review/results/session/fix flow including scheduler-backed queue visibility

Observed so far on 2026-05-04:

- The documented Session 5 surfaces in `docs/gui.md` and `docs/user-manual.md` are broadly aligned with the current GUI architecture: Review and Results stay anchored in the main window; session save/load and finalize remain Results-tab actions; selected-file mode and project-scope diff filtering are described as GUI-first workflows.
- Focused GUI workflow coverage for the core review path now passes on the milestone worktree: `tests/test_gui_workflows.py -k "review_workflow_displays_results_and_releases_backend or cancel_review_workflow_reports_requested_then_cancelled or dry_run_workflow_switches_to_log_tab_and_records_output or finalize_workflow_saves_report_and_clears_results or health_check_workflow_shows_report_and_restores_controls or restored_session_review_changes_recreates_backend_and_finalizes"` completed with `5 passed` selected.
- That slice verifies the main Review-tab start flow, cancellation path, dry-run handoff into Output Log, finalize reporting, the health-check dialog lifecycle, and restored-session review actions that recreate the backend before finalization.
- A second focused GUI workflow slice now also passes on the milestone worktree: `tests/test_gui_workflows.py -k "results_filters_match_visible_issue_cards or ai_fix_preview_edit_save_applies_user_edited_fix or ai_fix_preview_save_and_close_stages_edited_content_until_apply or session_can_be_saved_and_loaded_into_a_fresh_app"` completed with `4 passed` selected.
- That slice verifies Results-tab filters, session save/load into a fresh app instance, AI Fix preview/edit/apply for user-edited content, and the staged-edit behavior where `Save and Close` does not write the file until `Apply Selected Fixes` runs.
- Review-tab diff-filter controls also now have a fresh verification pass through the GUI smoke suite: `tests/test_gui_smoke.py -k "diff_filter_frame_exists or browse_diff_filter_noop or enable_diff_filter or disable_diff_filter"` completed with `4 passed` selected.
- Live desktop evidence now exists for the Output Log surface outside the pytest harness. An isolated runtime probe at `artifacts/manual-session5/gui-live-probe.json` exercised real CTk widgets against a temp copy of the current `config.ini`, confirmed log-level filtering (`All` to `WARNING`), main-log save, detached-log save, and clear-log behavior, and left the real GUI config untouched.
- The same isolated runtime probe also captured GUI health-dialog wording for the configured backends on this machine. The local dialog rendered a passing summary; Copilot surfaced a blocked CLI diagnostic against the stale Winget-installed stub path with the expected remediation hint row; Kiro and Bedrock both rendered passing prerequisite dialogs. This closes the earlier Session 5 gap around GUI health wording with actual desktop dialog content rather than CLI output alone.
- Supporting desktop screenshots were captured into `artifacts/manual-session5/live-log-tab.png` and `artifacts/manual-session5/live-benchmark-detached.png`. The log screenshot matches the documented Output Log layout, and the detached benchmark screenshot shows the expected main-window placeholder plus `Focus Window` and `Redock` actions.
- The repository includes a real interactive GUI harness at `tools/manual_test_gui.py`, but on this machine it is still a manual launcher only (`--lang`, `--theme`) rather than a scripted desktop driver, so the remaining GUI-only checks still need explicit human interaction or a dedicated automation shim.
- A new isolated desktop probe at `artifacts/manual-session6/gui-queue-detach-probe.json` now covers the remaining scheduler-backed queue surface on the real GUI widgets. It records one running review plus one queued dry run, confirms the queue summary renders `active=1 / queued=1 / recent=0`, verifies that selecting and cancelling the queued submission updates the summary to `active=1 / queued=0 / recent=1`, and then confirms the finished review remains visible as a recent-completed entry.
- The same probe confirms that the queue panel's visible labels, detail text, and cancel-button enablement all track the scheduler state on the desktop surface rather than only inside the pytest harness.

Follow-up notes:

- Session 5 is complete for the planned local-backend GUI-core audit slice on this machine. Any further Session 5 work would be adjacent wording polish rather than a missing feature-validation path.

## Session 6 Working Log

Current status: underway with focused regression coverage plus live detached-window evidence; shared status-bar detach behavior and startup presentation are now verified, and the only remaining Session 6 gap is mixed-DPI cross-monitor validation on a multi-display setup

Observed so far on 2026-05-04:

- Focused detachable-window coverage now exists for all four supported pages on the milestone worktree: `tests/test_gui_workflows.py -k "log_tab_detach_and_redock_keeps_log_state_synced or settings_tab_detach_and_redock_preserves_unsaved_state or addon_review_tab_detach_and_redock_preserves_loaded_state or benchmark_tab_detach_and_redock_preserves_loaded_state or detachable_pages_support_keyboard_shortcuts_for_open_and_redock or log_tab_detached_window_restores_after_restart or four_detached_pages_restore_after_restart"` completed with `7 passed` selected after the fixes below.
- This Session 6 pass exposed a real restart-restore product defect: detached-window restore ran before lazily built Benchmarks and Addon Review tabs existed, so `restore_detached_windows()` persisted those pages in `gui.detached_pages` but silently failed to recreate their detached windows on the next app start.
- That restart-restore defect is now patched in the milestone worktree. The Benchmarks and Addon Review detached-window open paths now build their lazy tabs on demand before restoring the detached surface, and the originally failing `test_four_detached_pages_restore_after_restart` now passes on rerun.
- Live desktop evidence for the detached-window experience now exists under `artifacts/manual-session5/`. The screenshot `live-benchmark-detached.png` shows the shipped placeholder state in the main window while Benchmarks is detached, including the `Focus Window` and `Redock` actions documented in `docs/gui.md`.
- The isolated runtime probe at `artifacts/manual-session5/gui-live-probe.json` also now exercises detached-page persistence outside the pytest harness. It detached Log, Settings, Benchmarks, and Addon Review on a temp config, recreated the app, and recorded all four restored detached windows under `detach_restore.restored_windows`.
- A second isolated desktop probe at `artifacts/manual-session6/gui-queue-detach-probe.json` now covers the shared status-bar detach action directly. On the live widgets, Review and Results render the shared button disabled with the localized unavailable label, while Log, Settings, Benchmarks, and Addon Review all render the localized `Open In Window` action.
- That same probe also verified the status-bar detach action end to end on the lazy Benchmarks surface: invoking the shared button opened the detached window, changed the shared button label to the localized `Focus Window` action, and after redocking returned the label to `Open In Window`.
- Startup presentation with reopened detached windows now has explicit live evidence too. A non-testing app instance launched against a temp config with all four detachable pages pre-populated in `gui.detached_pages` restored Log, Settings, Benchmarks, and Addon Review, brought the main window back to `state=normal`, and left `_startup_window_hidden` cleared after the restore/finalize sequence.
- Mixed-DPI cross-monitor validation could not be completed on this machine during this pass. Running `tools/gui_perf_probe.py --move-across-monitors ...` detected only one display and skipped the monitor-move loop with the explicit message that a multi-monitor setup is required, so the remaining DPI-specific check is currently environment-limited rather than a reproduced product defect.

Follow-up notes:

- Session 6 still needs one final pass on a real multi-monitor Windows setup to compare cross-screen behavior with and without `gui.automatic_dpi_awareness`. The status-bar detach and startup-presentation slices are now covered.

## Session 7 Working Log

Current status: completed for the intended Session 7 surface. The focused addon baseline, manual CLI artifact slice, and live desktop Addon Review probe are all now recorded.

Observed so far on 2026-05-04:

- Focused addon validation is now green on the milestone worktree. The current targeted slice completed with `10 passed` across CLI addon discovery, generated-preview rendering, approval/install, and the GUI Addon Review approval plus detach/redock coverage.
- That focused slice covered `tests/test_main_cli.py::test_list_addons_prints_runtime_summary`, `tests/test_main_cli.py::test_list_addons_reads_checked_in_example_addon_from_configured_paths`, `tests/test_addon_review_surface.py`, `tests/test_addon_approval.py`, the generated-addon tool-mode nodes in `tests/test_cli_tool_mode.py`, and the Addon Review GUI workflow nodes in `tests/test_gui_workflows.py`.
- A first manual CLI artifact slice now exists under `artifacts/manual-session7/`. `analyze-repo` generated a preview for a minimal FastAPI demo repository and wrote `analyze-repo-output.json`, `generated-preview/capability-profile.json`, `generated-preview/approval-request.json`, `generated-preview/review-checklist.md`, plus the generated addon scaffold.
- The same manual slice exercised `review-addon-preview --diff-only` and captured the rendered bundle diff in `artifacts/manual-session7/review-addon-preview.txt`, including the generated `api_design`, `data_validation`, and `error_handling` additions against the default bundle.
- `approve-addon-preview --decision approve --reviewer Colin --install-dir artifacts/manual-session7/installed-addons` completed successfully on that preview and wrote both the approval decision artifact and the installed addon payload under `artifacts/manual-session7/installed-addons/manual-session7-fastapi`.
- Addon discovery also now has live CLI evidence for the installed preview. Running `--list-addons` against a temp config that pointed `addons.paths` at the installed preview path reported `demo-repo Adaptive Review Addon [manual-session7-fastapi] v0.1.0` with one discovered review pack; the captured output is stored in `artifacts/manual-session7/list-addons.txt`.
- Live desktop Addon Review evidence now exists under `artifacts/manual-session7/gui-addon-review-probe.json`. The isolated GUI probe loaded two generated previews, captured the visible English labels on the Addon Review tab, selected the shipped `Generated Bundle vs Default Bundle` diff, approved one preview, rejected the other, and recorded the corresponding toast messages.
- That live probe confirmed the approve path writes an `approved` decision and installs the reviewed addon payload, while the reject path writes a `rejected` decision without creating an installed addon directory.
- The visible English Addon Review labels captured from the live desktop surface matched the current docs closely enough that no obvious wording drift was observed in this pass.

Follow-up notes:

- Session 7's planned load/diff/approve/reject wording pass is now closed for the current machine and English desktop surface.

## Session 8 Working Log

Current status: the main Session 8 user-facing and contributor-facing seams now have live evidence. The Benchmarks tab no longer requires a user to understand saved summary files before starting a basic benchmark run, real saved summaries round-trip back into both the main-run and comparison views correctly, and the documented fixture-authoring evaluator path now has a direct sanity artifact as well.

Observed so far on 2026-05-04:

- The original Session 8 gap was confirmed in the live code path: the Benchmarks tab could browse fixture catalogs and saved summary artifacts, but it exposed no GUI entry point for starting a benchmark run.
- The milestone worktree now adds a direct `Run Benchmarks` action to the Benchmarks tab. The new flow reuses `tools/run_holistic_benchmarks.py`, writes a timestamped run folder under the configured saved-runs root, refreshes the discovered summary selector, and auto-loads the generated summary as the new main run.
- The first live probe exposed a real import-path defect in that new flow: `aicodereviewer.gui.benchmark_mixin` tried to load the runner via `from tools import run_holistic_benchmarks`, which fails when the repo root is not on `sys.path`. The GUI now loads `tools/run_holistic_benchmarks.py` from its known filesystem path instead, and the new regression slice `tests/test_gui_workflows.py::test_benchmark_runner_loader_does_not_require_tools_package_on_sys_path` locks that seam down.
- The same live probe exposed a second contract mismatch: the runner's generated `summary.json` lacked the `representative_fixtures` metadata the Benchmarks tab expects when it reloads a saved run. `tools/run_holistic_benchmarks.py` now carries `representative_fixture_ids` and `representative_fixtures` into both `summary.json` and `run.json`, and `tests/test_run_holistic_benchmarks.py::test_runner_writes_summary_artifacts_with_representative_fixture_metadata` covers that artifact contract.
- A follow-up comparison probe exposed one more real UI defect in the saved-summary path: `_format_summary_overview(...)` treated zero pass/fail counts as falsey and rendered them as `-`, and `_collect_fixture_snapshots(...)` did not read top-level `results` from the real `summary.json` artifacts. The Benchmarks tab now preserves zero counts correctly and mines fixture snapshots from top-level summary results as well as the richer runner envelope shape.
- Focused validation is green for the full Session 8 fix set. `tests/test_gui_smoke.py::TestAppCreation::test_benchmark_tab_widgets`, `tests/test_gui_workflows.py::test_benchmark_tab_can_run_benchmarks_without_manual_summary_selection`, `tests/test_gui_workflows.py::test_benchmark_runner_loader_does_not_require_tools_package_on_sys_path`, `tests/test_gui_workflows.py::test_benchmark_tab_compares_summary_artifacts_with_top_level_results_and_zero_counts`, and `tests/test_run_holistic_benchmarks.py::test_runner_writes_summary_artifacts_with_representative_fixture_metadata` all passed.
- User-facing docs now describe the simplified desktop benchmark path in `docs/gui.md`, `docs/benchmarks.md`, and `docs/user-manual.md`.
- Live desktop evidence now exists under `artifacts/manual-session8/gui-benchmark-run-probe.json`. That probe launched the real Benchmarks tab in `testing_mode=True`, pointed it at a temp fixture root containing only `auth-guard-regression`, invoked `Run Benchmarks`, and recorded the visible English labels, toast/status text, generated summary paths, and loaded benchmark state.
- The successful local evidence run is `artifacts/manual-session8/holistic-benchmark-runs/20260504-104113-local/summary.json` with companion envelope `artifacts/manual-session8/holistic-benchmark-runs/20260504-104113-local/run.json` and fixture report `artifacts/manual-session8/holistic-benchmark-runs/20260504-104113-local/reports/auth-guard-regression.json`.
- That live run completed in about 29.9 seconds against the local LM Studio backend, reported backend health ready for `qwen/qwen3.5-9b`, auto-selected the new `summary.json` entry in the saved-run selector, updated the source text to `Main run: summary.json`, showed `count=1`, selected `auth-guard-regression - Authorization Guard Regression`, and rendered the generated benchmark summary directly on the desktop surface.
- The captured desktop copy aligned with the current English docs for this flow: the probe recorded the expected `Run Benchmarks` call to action and the success toast `Benchmark run finished and loaded summary.json.` without further wording drift on this screen.
- Live desktop comparison evidence now also exists under `artifacts/manual-session8/gui-benchmark-compare-probe.json`. That probe ran two real local benchmark sessions from the GUI against isolated one-fixture roots (`auth-guard-regression` and `cache-invalidation-gap`), then loaded `artifacts/manual-session8/holistic-benchmark-runs/20260504-104854-local/summary.json` as the main run and `artifacts/manual-session8/holistic-benchmark-runs/20260504-104925-local/summary.json` as the comparison run.
- The corresponding runner envelopes and per-fixture reports were written to `artifacts/manual-session8/holistic-benchmark-runs/20260504-104854-local/run.json`, `artifacts/manual-session8/holistic-benchmark-runs/20260504-104854-local/reports/auth-guard-regression.json`, `artifacts/manual-session8/holistic-benchmark-runs/20260504-104925-local/run.json`, and `artifacts/manual-session8/holistic-benchmark-runs/20260504-104925-local/reports/cache-invalidation-gap.json`.
- That live compare pass confirmed the summary selector discovered both new saved runs, the Benchmarks tab loaded the primary summary with `Fixtures Passed: 0` / `Fixtures Failed: 1`, the comparison summary rendered `Fixtures Passed: 1` / `Fixtures Failed: 0`, and the compare view surfaced the expected primary-only vs compare-only fixture records for the two real saved runs.
- The captured compare surface showed the expected summary-vs-summary behavior on the current English desktop copy: `Loaded benchmark summary artifact (1 fixture(s))` for the main run, `Loaded benchmark comparison artifact (1 representative fixture(s))` for the comparison run, and a compare overview that called out `Only In Primary: auth-guard-regression` plus `Only In Comparison: cache-invalidation-gap`.
- The remaining smaller Session 8 quality-tooling surface now also has live artifact evidence. Running `tools/compare_review_reports.py artifacts/manual-session8/holistic-benchmark-runs/20260504-104854-local/reports/auth-guard-regression.json artifacts/manual-session8/holistic-benchmark-runs/20260504-104925-local/reports/cache-invalidation-gap.json --json-out artifacts/manual-session8/compare-review-reports-probe.json` produced a saved delta report under `artifacts/manual-session8/compare-review-reports-probe.json`.
- That compare-report artifact showed the expected non-overlapping delta between the two real saved benchmark reports: `unchanged_count=0`, `added_count=3`, and `removed_count=3`, with the `cache.py` / `profile_service.py` findings appearing only in the comparison report and the `auth.py` / `admin.py` authorization findings appearing only in the baseline report.
- The last optional contributor-side Session 8 surface now also has a direct sanity artifact. `artifacts/manual-session8/fixture_authoring_sanity_probe.py` built a fresh temp fixture rooted under `benchmarks/holistic_review/fixtures/<fixture-id>/` shape, wrote a matching temp report, then ran `tools/evaluate_holistic_benchmarks.py --list-fixtures`, `--fixture ... --report-file ...`, and `--report-dir ...` against that temp catalog.
- The saved output under `artifacts/manual-session8/fixture-authoring-sanity-probe.json` shows the authoring path stayed valid end to end: the temp fixture was discovered correctly, both evaluation commands exited `0`, and the fixture passed with `overall_score=1.0` in both the single-report and report-directory flows.

Follow-up notes:

- Session 8's benchmark start-and-compare flow, compare-report utility, and documented fixture-authoring evaluator path are now backed by focused automated coverage and real saved-artifact evidence. Remaining Session 8 work, if any, should target broader quality-program surfaces rather than the Benchmarks tab's core saved-run or fixture-authoring workflow.

## Session 9 Working Log

Current status: Session 9 is now complete for the planned local slice. Both startup seams are recorded: the GUI starts the embedded local API from Settings, the CLI `serve-api` path starts the same route surface on `local`, API-submitted jobs share the documented runtime/queue state, and both the embedded and CLI-started paths now have real report, artifact, and audit-log evidence.

Observed so far on 2026-05-04:

- The first live Session 9 diagnostic reproduced a real product defect before any fix landed: API-submitted jobs were present in `app._review_runtime.list_jobs()` immediately, but the Review queue panel still showed `No queued submissions` until `on_submission_sync_requested()` was called manually.
- The fix now in the milestone worktree adds a lightweight Review-surface queue poll that keeps the queue panel synchronized with the shared runtime even when submissions originate from the embedded local HTTP API instead of the GUI-owned review start path.
- Focused validation is green for the repaired slice. `tests/test_gui_workflows.py::test_review_queue_panel_auto_refreshes_for_runtime_jobs_submitted_outside_gui`, `tests/test_gui_workflows.py::test_gui_starts_and_stops_local_http_server_when_enabled`, and `tests/test_gui_workflows.py::test_local_http_settings_persist_across_app_restart` all passed in the current worktree, and the earlier `tests/test_compare_review_reports.py` regression still passed for the remaining Session 8 tool surface.
- Live embedded-API evidence now exists under `artifacts/manual-session9/gui-local-http-shared-queue-probe.json`, generated by `artifacts/manual-session9/gui_local_http_shared_queue_probe.py` against a temp two-file Python project and a temp config that enabled the GUI's embedded local HTTP server on a free localhost port.
- That probe confirmed the GUI-advertised base URL and route quick reference were live on the desktop surface: the embedded server reported `Running in this desktop session on port 55797.`, exposed `http://127.0.0.1:55797`, and the docs excerpt listed `GET /api/backends`, `GET /api/review-types`, `POST /api/recommendations/review-types`, `POST /api/jobs`, `GET /api/jobs/{job_id}/report`, `GET /api/jobs/{job_id}/artifacts`, `GET /api/events`, and `GET /api/jobs/{job_id}/events`.
- The same probe hit the embedded server directly and got successful responses for `/api/backends`, `/api/review-types`, and `POST /api/recommendations/review-types`. The recommendation payload came back with `recommended_preset=code_health`, `recommended_review_types=[best_practices, maintainability]`, and project signals for the tiny Python fixture root.
- Two API job submissions on that same embedded server immediately shared queue state with the GUI: the first job returned `state=reviewing`, the second returned `state=queued`, `GET /api/jobs` listed both job ids, and the Review queue panel rendered `1 active, 1 queued, 0 recent` without any manual sync call.
- The recorded queue snapshot in `artifacts/manual-session9/gui-local-http-shared-queue-probe.json` maps both visible queue labels back to the submitted job ids, confirming that the GUI surface and API route were observing the same runtime-owned jobs rather than separate scheduler state.
- The probe also captured global and per-job event streams from `/api/events` and `/api/jobs/{job_id}/events`, then allowed the deterministic report-writing job to finish and verified `GET /api/jobs/{job_id}/report`, `GET /api/jobs/{job_id}/artifacts`, `GET /api/jobs/{job_id}/artifacts/{artifact_key}`, and `GET /api/jobs/{job_id}/artifacts/{artifact_key}/raw` against the same embedded server.
- The generated report and artifacts were all present for the first job: `api-report.json`, `api-report_summary.txt`, and `api-report.md`, with the report endpoint returning the expected single high-severity authorization issue for `admin.py` in the temp probe project.
- A broader real local-backend run now also exists under `artifacts/manual-session9/gui-local-http-real-local-probe.json`, generated by `artifacts/manual-session9/gui_local_http_real_local_probe.py` against the real embedded local HTTP server, the configured local backend, and a tiny two-file Python project with an authorization flaw.
- That real-backend probe showed the full embedded path working beyond the deterministic harness: `/api/backends`, `/api/review-types`, `/api/review-presets`, and `POST /api/recommendations/review-types` all succeeded; `POST /api/jobs` started a real local `security` review; the active job appeared in the GUI queue with `1 active, 0 queued, 0 recent`; and the job reached `completed` with `status=report_written` after about 17 seconds.
- The report payload from that live run contained one real cross-file authorization issue for `admin.py` with `auth.py` as a related file, and the artifact endpoints returned the expected `report_primary`, `report_summary_txt`, and `report_md` outputs for the generated `api-report.json`.
- That broader run also exposed one concrete docs drift in the shipped route inventory: the API already supported `GET /api/jobs/{job_id}/artifacts/{artifact_key}`, but `docs/http-api.md`, `docs/local-http-quick-reference.md`, and the Settings-surface local API route list omitted it. The milestone worktree now includes that preview route in the docs and in the Settings quick reference, and `tests/test_gui_workflows.py::test_gui_starts_and_stops_local_http_server_when_enabled` locks the GUI copy down.
- The CLI-started `serve-api` seam initially reproduced a second real product defect: `python -m aicodereviewer serve-api --backend local --host 127.0.0.1 --port <port>` crashed before startup because the `serve-api` parser never defined `args.backend` even though the shared runtime-override path expects it.
- That CLI startup defect is now fixed in the milestone worktree by adding the missing `--backend` flag to the `serve-api` parser, and focused CLI validation now covers the path in `tests/test_main_cli.py::test_serve_api_command_accepts_backend_override_and_starts_server`.
- Live CLI-started API evidence now exists under `artifacts/manual-session9/cli-local-http-real-local-probe.json`, generated by `artifacts/manual-session9/cli_local_http_real_local_probe.py` against a temp config, a temp two-file Python project, and a real local backend run launched through `python -m aicodereviewer serve-api --backend local --host 127.0.0.1 --port <free-port>`.
- That CLI probe confirmed the documented parity claim directly on the CLI-started server: `/api/backends`, `/api/review-types`, `/api/review-presets`, and `POST /api/recommendations/review-types` all returned `200`; `POST /api/jobs` created a real `security` review; `/api/events` and `/api/jobs/{job_id}/events` returned SSE payloads; and the same run completed with `report_written`, `report_primary`, `report_summary_txt`, and `report_md` outputs available through report, artifact-preview, and raw-artifact routes.
- The same CLI probe also closed the Session 9 audit-log slice with real retained evidence. The temp `aicodereviewer-audit.log` captured `action=job_submit`, `action=report_fetch`, `action=artifact_list`, and both preview/raw `action=artifact_fetch` entries for the probe job, which confirms the shipped local API audit trail beyond the existing unit tests.
- That audit run exposed a second docs drift in the local HTTP guides: `docs/http-api.md` and `docs/local-http-quick-reference.md` still said sensitive local API actions emitted through the normal application logger even though the current baseline uses the dedicated `aicodereviewer.audit` logger with optional separate retained file logging. The docs now reflect the dedicated audit logger, and the user manual's Local HTTP workflow also now shows the explicit `--backend local` startup form used by the verified CLI probe.

Follow-up notes:

- Session 9 now has both embedded and CLI-started live evidence, plus focused regression coverage for the queue-refresh, route-list, and CLI-startup defects uncovered during the audit.

## Session 10 Working Log

Current status: underway with the first local recovery/localization slice recorded. The current worktree now preserves `python -m aicodereviewer` exit codes correctly, the local failure-and-recovery path has fresh CLI evidence, and English/Japanese CLI plus GUI language surfaces are verified on this machine.

Observed so far on 2026-05-04:

- Session 10 starter evidence now exists under `artifacts/manual-session10/recovery-localization-probe.json`, generated by `artifacts/manual-session10/recovery_localization_probe.py` against a temp config that first pointed the Local backend at `http://127.0.0.1:9` and then restored the working `http://localhost:1234` / `qwen/qwen3.5-9b` / `lmstudio` settings.
- The first run of that probe reproduced a real product defect before the fix landed: `python -m aicodereviewer --check-connection --backend local --lang en` printed a failed connection with remediation text, but the process still exited `0` because `src/aicodereviewer/__main__.py` called `main()` without propagating its return code.
- That module-entry defect is now fixed in the milestone worktree: `src/aicodereviewer/__main__.py` exits with `main()`'s return code, and focused CLI validation now covers the path in `tests/test_main_cli.py::test_module_entrypoint_preserves_main_exit_code` together with the adjacent `serve-api` and `check-connection` regressions.
- The post-fix rerun of the same Session 10 probe now confirms the intended recovery contract for module-based CLI use too: the failing Local health check exits `1`, prints the provider/category remediation details, and the restored Local health check exits `0` with the expected success output for `http://localhost:1234` and `qwen/qwen3.5-9b`.
- The same probe also captured English and Japanese CLI output sanity through `--list-type-presets`: the English run printed `Review Type Presets` with labels such as `Runtime Safety`, while the Japanese run printed `レビュータイププリセット` with translated labels such as `ランタイム安全性` and `リリース安全性`.
- Real GUI localization evidence now also exists in that artifact. Running `App(testing_mode=True)` against temp `gui.language` values showed the Review surface switching from `▶  Start Review` / `Dry Run` / `🩺 Check Setup` / `Ready` to `▶  レビュー開始` / `ドライラン` / `🩺 セットアップ確認` / `準備完了`, and the Settings-surface local HTTP route summary intro also switched between English and Japanese while preserving the same route list.
- Session 10 already has one adjacent security/polish input from the completed Session 9 CLI probe too: the dedicated local API audit logger is now evidenced on a real run and the local HTTP docs no longer describe it as ordinary application logging.
- Fresh Copilot sensitive-path evidence now exists under `artifacts/manual-session10/tool-aware-sensitive-path-probe.json`, generated by `artifacts/manual-session10/tool_aware_sensitive_path_probe.py` against a temp config with `tool_file_access.enabled = true`, `backend_allowlist = copilot`, and explicit sensitive globs including `.env`.
- The deterministic policy portion of that probe confirmed the intended contract directly at the backend seam: a workspace file read was allowed, `.env` was denied with `Sensitive file path denied by policy`, and an out-of-workspace file was denied with `Requested file is outside the workspace root`; the resulting audit recorded one allowed read and two denied requests.
- The live Copilot portion of the same probe also succeeded on this machine without falling back. The review completed in about 129 seconds, read both in-workspace Python files through tool calls, recorded `file_read_count = 2` and `denied_request_count = 0`, and produced four cross-file security findings led by the expected `shell=True` command-injection issue.
- The saved documentation review report was useful only as a hint list. Several claimed regressions were stale or false against the current tree, so the final reactive docs pass was intentionally limited to verified drift in the root README plus the backend, troubleshooting, security, and architecture guides.

Follow-up notes:

- The sensitive-path slice and the reactive docs polish pass are now complete for Session 10.
- Leave `docs/configuration.md` alone for now because the current worktree already has unrelated local edits there; the maintained guide already documents the tool-aware sensitive-path contract accurately.
- Keep Session 10 open only for any additional recovery/security follow-up that later manual probes actually expose.