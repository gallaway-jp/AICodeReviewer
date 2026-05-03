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
| S4 | Tool mode and report artifacts | run with local backend first | not started | pending |
| S5 | GUI core review workflow | run with local backend first | not started | pending |
| S6 | GUI detach, restore, desktop ergonomics | backend-agnostic after startup | not started | pending |
| S7 | Addons and generated addon review | mostly backend-agnostic; use local only if generation path is exercised | not started | pending |
| S8 | Benchmarks and quality tooling | local preferred; others blocked unless setup changes | not started | pending |
| S9 | Local HTTP and shared scheduler | local backend path is the primary runnable slice | not started | pending |
| S10 | Recovery, security, localization, polish | local fully runnable; other backends doc-only unless setup changes | not started | pending |

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
- compare-run workflow in the GUI Benchmarks tab
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