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
| `local` | configured in `config.ini`; OpenAI-compatible endpoint at `http://localhost:1234` responded with HTTP 200 | `ready=true` | fully runnable now; use as the default backend for this milestone's manual execution |
| `bedrock` | AWS CLI installed | `ready=false` because credentials are missing | keep in scope for docs review, but classify execution steps as blocked by environment until AWS auth is configured |
| `kiro` | WSL installed and healthy | `ready=false` because Kiro CLI is not installed in WSL | keep in scope for docs review, but defer execution unless Kiro CLI is installed |
| `copilot` | Copilot CLI stub is present on disk | `ready=false` because the CLI did not respond during health checks | treat as blocked until the local Copilot CLI installation is repaired or replaced |

Backend-specific execution rule for this milestone:

1. Run backend-dependent manual sessions against `local` first.
2. Keep `bedrock`, `kiro`, and `copilot` in the checklist so documentation and workflow claims are still audited.
3. Record those three as `blocked by environment` unless we deliberately repair their prerequisites during the milestone.
4. Do not weaken the docs just because this machine lacks a prerequisite; only update docs when the product claim itself is wrong, incomplete, or misleading.

## Live Session Tracker

| Session | Focus | Backend scope on this machine | Status | Latest result |
|---|---|---|---|---|
| S1 | Install and startup baseline | no backend dependency; local path available for smoke checks | in progress | source install passed; CLI help passed; GUI visible confirmation pending; startup logged Copilot model-discovery failure; packaged installer artifact not present locally |
| S2 | Backend configuration and health | local runnable; bedrock/kiro/copilot blocked by environment | not started | pending |
| S3 | Core CLI review flows | run with local backend first | not started | pending |
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

Current status: in progress

Observed so far on 2026-05-03:

- Source install step succeeded with `python -m pip install -e ".[gui]"` from the milestone worktree.
- The install step replaced an older preexisting editable install that still reported `aicodereviewer 0.1.0` in this environment; after reinstall, the imported package version is `0.3.0`.
- The installed console entrypoint launched successfully with `aicodereviewer.exe --help`.
- No packaged `AICodeReviewer-Setup-<version>.exe` artifact is present in the current workspace, so the packaged-installer slice cannot be executed from local artifacts yet.
- The GUI launch command started from the same editable install without an immediate process crash.
- GUI startup emitted `SDK Copilot model discovery failed: Missing required fields in ModelCapabilities: supports=None, limits=None` even though Copilot is not a runnable backend on this machine right now.
- Visible confirmation from the active desktop session is still required to decide whether that startup diagnostic is only noisy logging or a user-visible Session 1 defect.

Pending Session 1 confirmations:

- confirm the GUI window opened normally
- confirm the initial startup surface matches the current docs closely enough for a `pass` or identify the first visible drift
- decide whether to fetch or build a packaged installer artifact later in the milestone or record that slice as pending-artifact for now