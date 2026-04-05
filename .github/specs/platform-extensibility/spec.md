# Platform Extensibility Spec

## Purpose

Turn AICodeReviewer from a single-session desktop/CLI application into a platform with:

- queued multi-review execution with configurable concurrent session limits
- custom review types and sub-review types
- addon support for backends, review types, UI, integrations, and behavior hooks
- a shared core that can later support HTTP and web-server workflows
- a structured quality-improvement program across every built-in review type

## Goals

- support queueing multiple reviews and running a bounded number simultaneously
- decouple core review execution from CLI and GUI concerns
- move hard-coded backends and review-type definitions onto registries
- allow user-defined and addon-defined review types without editing core files
- define a stable addon capability model instead of ad hoc monkey-patching
- make future API and web-server support a thin frontend over the same execution core
- institutionalize review-quality evaluation and improvement across all built-in review types

## Non-Goals

- shipping a full remote multi-user SaaS platform in the first iteration
- promising strong sandboxing for arbitrary in-process Python addons
- replacing the current report format wholesale before the registry refactor lands
- auto-applying all review findings without explicit adjudication
- exposing every internal helper as public addon API surface

## Current Constraints

- GUI review execution is still modeled as a single active job via `_running` in `gui/review_mixin.py` and `gui/results_mixin.py`.
- `AppRunner` in `orchestration.py` coordinates one review session at a time and is tightly coupled to current CLI/GUI flows.
- Backend creation is hard-coded in `backends/__init__.py`.
- Review-type definitions are hard-coded in `backends/base.py`.
- The review engine already performs internal batch parallelism in `reviewer.py`, so session-level concurrency must be added above that layer instead of inside it.
- Existing cancellation semantics for Bedrock, Kiro, and Local backends must remain honest and backend-aware.

## Architectural Direction

The target architecture has five layers:

1. Core execution service
- a headless review service that accepts job requests and emits structured progress/state events

2. Session scheduler
- a persistent queue and dispatcher that controls how many review sessions run at once

3. Registries
- backend registry, review-definition registry, preset registry, UI contribution registry, and hook registry

4. Extension host
- trusted in-process addons plus optional isolated subprocess extensions for heavier or riskier integrations

5. Frontends
- CLI, GUI, and future HTTP/web server implemented as clients of the same core service and scheduler

## Core Design Decisions

1. Persist job state
- queue state, progress, result metadata, and job history should be stored locally instead of living only in GUI memory
- SQLite is the default persistence choice for the first implementation

2. Separate session concurrency from internal review batching
- session-level scheduling decides how many reviews run concurrently
- per-review batching in `reviewer.py` remains an internal optimization governed separately

3. Use registries instead of hard-coded switch statements
- built-ins register through the same mechanism addons will use

4. Keep the execution core headless
- GUI and CLI should submit jobs and observe state instead of owning orchestration logic

5. Treat addon compatibility as a real contract
- version addon APIs, validate manifests, and fail closed on incompatible extensions

## Milestones

### Milestone 0: Core Extraction

Detailed class and interface design for this milestone lives in `milestone-0-design.md` beside this spec.

#### Scope

- introduce explicit job/session domain objects
- extract core review execution from the current GUI and CLI paths
- prepare registries for backends and review definitions

#### Deliverables

- `ReviewJob` model for queued/running/completed review sessions
- `ReviewExecutionService` that runs one job headlessly
- event model for progress, logs, state, and result notifications
- backend registry abstraction replacing direct hard-coded factory branching
- review-definition registry abstraction replacing hard-coded review-type metadata storage

#### Acceptance Criteria

1. CLI and GUI both invoke the same execution service for running a review.
2. Existing single-review behavior remains functionally unchanged.
3. Cancellation still respects backend-specific constraints.
4. Existing report generation still works through the new service boundary.

### Milestone 1: Queue And Concurrent Session Execution

#### Scope

- add a persistent job queue
- allow multiple reviews to be queued
- allow a configurable maximum number of simultaneous review sessions

#### Deliverables

- `ReviewScheduler` with persistent queue store
- configurable global `max_concurrent_reviews`
- optional per-backend concurrency caps
- per-job cancel, retry, and status inspection
- GUI queue manager with running/queued/completed views
- CLI job submission and status commands

#### Acceptance Criteria

1. Multiple review jobs can be enqueued from GUI or CLI.
2. Only the configured number of jobs run simultaneously.
3. Each running job has isolated backend instance, cancel token, logs, and progress.
4. Cancelling one job does not cancel unrelated jobs.
5. GUI remains responsive during concurrent execution.

#### Implementation Notes

- do not reuse the current single `_running` app flag as the scheduler primitive
- move to per-job state plus app-level queue state
- preserve `after(...)` boundaries for all Tk updates

### Milestone 2: Custom Review Types And Sub-Review Types

#### Scope

- move review definitions out of `backends/base.py`
- support hierarchical user-defined review lenses

#### Deliverables

- `ReviewDefinition` schema with:
	- key
	- parent key
	- label and summary metadata
	- prompt supplements
	- context augmentation rules
	- category aliases
	- validation rules
	- optional benchmark metadata
- loader for built-in and user-defined review packs
- subtype-aware GUI selection model
- subtype-aware CLI parsing and help output
- preset support over built-in and custom types

#### Acceptance Criteria

1. A new review type can be added without editing core Python switch logic.
2. A subtype can inherit prompt and metadata from a parent type.
3. GUI and CLI both display built-in and custom review definitions.
4. Invalid definitions fail with explicit diagnostics.
5. Reports and filters continue to work with canonical type keys.

#### Implementation Notes

- distinguish selectable subtype granularity from emitted finding taxonomy
- avoid uncontrolled taxonomy explosion in reports and filters

### Milestone 3: Addon Platform

#### Scope

- define a stable extension model for customization

#### Deliverables

- addon manifest schema with id, version, compatibility, permissions, and entry points
- addon discovery from configured local paths
- capability registration for:
	- backend providers
	- review-definition providers
	- preset providers
	- menu and UI contributors
	- context providers
	- behavior hooks
	- report transformers
	- API route contributors
- trusted in-process extension mode
- optional subprocess extension mode for higher isolation

#### Acceptance Criteria

1. An addon can register a backend without core edits.
2. An addon can register a review type or subtype visible in CLI and GUI.
3. An addon can contribute at least one menu or settings surface in the GUI.
4. Addon load failures are isolated and diagnosable.
5. Incompatible addons are rejected before partial activation.

#### Implementation Notes

- do not claim hard security isolation for in-process Python addons
- keep the first SDK intentionally small and versioned

#### Current Status

- completed in the current repository baseline with manifest-driven review-pack contributions, backend-provider registration, surfaced addon diagnostics, and constrained Settings-surface contributions
- subprocess extension mode and broader hook families remain future-expansion work, but the milestone acceptance criteria are now satisfied without widening the trusted in-process SDK prematurely

### Milestone 4: HTTP API And Web Server Support

#### Scope

- expose the queue and review engine over HTTP after the scheduler and registries are stable

#### Deliverables

- local HTTP service built on the shared scheduler and execution service
- endpoints for:
	- create job
	- list jobs
	- get job detail
	- cancel job
	- list backends
	- list review types and presets
	- fetch reports and artifacts
- event streaming via SSE or WebSocket
- optional addon-provided API routes

#### Acceptance Criteria

1. HTTP-submitted jobs appear in the same scheduler as CLI and GUI jobs.
2. Job state is consistent across frontends.
3. No separate web-only orchestration path is introduced.
4. Local-only mode is the safe default unless explicitly configured otherwise.

#### Implementation Notes

- the canonical Milestone 4 path is the runtime-backed scheduler boundary used by the GUI and local HTTP service, with both frontends observing the same in-process `ReviewExecutionRuntime` when they run in the same desktop session
- `ReviewExecutionScheduler` now keeps a narrow compatibility mode only for legacy GUI workflow seams that do not inject a runtime; this preserves older queue and cancellation tests without reintroducing a second HTTP or GUI orchestration stack
- `gui/review_mixin.py` must continue to support both the typed `AppRunner.execution_service` path and older `AppRunner.run(...)` doubles used by workflow tests while the migration to the shared execution model remains in flight

#### Current Status

- completed in the current repository baseline with a local HTTP service over the shared runtime, registry-backed job and metadata endpoints, report and artifact fetch endpoints, SSE event streaming, GUI embedding of the local HTTP server, and desktop Settings discovery controls for the local API
- the runtime-backed scheduler remains the production boundary for GUI and HTTP integration; the compatibility mode above is explicitly transitional and should not be expanded into a second frontend-owned scheduler implementation
- validated after the compatibility-boundary update with a clean no-profile workflow run: `powershell -NoProfile -Command "& 'd:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe' -m pytest tests/test_gui_workflows.py"` -> `71 passed, 1 skipped`

### Milestone 5: Review Recommendation Workflow

#### Scope

- use AI to recommend a focused review-type set for the current project before running a full review

#### Deliverables

- GUI Review-tab recommendation action that proposes a review-type bundle for the selected path or diff scope
- CLI command or flag that prints recommended review types with rationale
- recommendation prompt/context assembly that summarizes project signals such as language mix, framework hints, dependency manifests, and changed files
- clear rationale for why each recommended review type was selected, including fallback heuristics when AI output is weak or unavailable
- controls to accept, edit, or pin recommended review sets before review execution
- user-visible rationale explaining why each suggested review type was included

#### Acceptance Criteria

1. GUI users can request recommended review types without manually selecting a full matrix first.
2. CLI users can request recommended review types for a target path or diff.
3. Recommendations are grounded in observable project signals rather than a static default list.
4. Users can accept or override the recommendation before review execution.
5. Recommendation output explains why a given bundle was suggested and falls back transparently when model output is weak or unavailable.

#### Current Status

- initial slice implemented in the current repository baseline:
  - shared recommendation service that summarizes observable project signals and falls back to signal-based heuristics when backend recommendation output is unavailable or invalid
  - CLI `--recommend-types` flow in both standard and tool-mode review entry points
  - GUI Review-tab recommendation action that applies the proposed bundle onto the existing review-type selection surface and keeps the result overridable before execution
  - local HTTP API recommendation endpoint so GUI, CLI, and API consumers now share the same Milestone 5 recommendation service boundary
- current rationale is grounded in project signals such as detected frameworks, manifests, richer dependency summaries, diff hunk summaries, changed files, and focused file selections
- direct unit coverage now exercises fallback scoring and AI-response parsing in addition to the entry-point integration tests

### Milestone 6: UX Audit And Improvement Program

#### Scope

- analyze current desktop and CLI UX, document recommended improvements with diagrams, and execute approved changes
- harden the embedded code editor and read-only viewer windows used throughout the GUI for large repositories and long-lived sessions
- make the editor and viewer feel feature-complete, comparison-friendly, and visually polished, with the kind of rich navigation and editing affordances users expect from WinMerge- or VSCode-class tools
- improve crash-resilience, memory usage, file-encoding handling, large-file performance, undo/redo correctness, and diff rendering

#### Deliverables

- UX audit covering navigation, discoverability, feedback states, multi-step flows, and error handling
- diagrams for current-state and target-state flows across key GUI and CLI journeys
- prioritized UX improvement backlog with implementation notes and tradeoffs
- executed improvements for the highest-value friction points identified by the audit
- robust in-app code editor component with configurable buffer limits and streaming file-load strategies
- viewer improvements for syntax highlighting fallbacks and paginated or virtualized large-file rendering
- rich compare/editor affordances such as split panes, synchronized scrolling, line numbers, folding, search and replace, go-to-line, bookmarks, and tabbed or multi-buffer navigation
- diff-review helpers for inline change inspection, next/previous change navigation, copy/paste or apply/revert actions where appropriate, and clear change markers across long files
- consistent visual language for spacing, typography, color, iconography, and state feedback across editor and viewer surfaces
- complete controls and affordances for common editor/viewer tasks such as search, replace, navigation, diff inspection, and copy/export flows
- keyboard-accessible navigation and accessibility improvements for the primary editor and viewer workflows
- polished empty states, loading states, and error states so the surfaces feel intentional rather than purely functional
- command-palette-style actions, context menus, and discoverable shortcuts for frequent editor and viewer operations
- recovery behaviors for save/restore editor state, reopen of unsaved buffers after a crash, and per-buffer memory pressure signals
- test harness and regression fixtures for large-file scenarios, mixed encodings, and long-lived editing sessions
- documentation for editor integration points for addons and hooks

#### Acceptance Criteria

1. UX findings are documented with concrete diagrams and an execution plan.
2. Opening very large files does not freeze the UI; files load with progressive streaming or a clear progress indicator.
3. Syntax-highlighting failures fall back gracefully without crashing the viewer/editor.
4. Undo/redo remains consistent across save/restore cycles and when applying tentative AI fixes programmatically.
5. Editor and viewer components recover state after an unexpected app exit and preserve unsaved changes when possible.
6. Editor and viewer windows expose a rich feature set for daily use, including compare-oriented navigation and editing helpers, and present a cohesive, visually deliberate interface.
7. Core editor/viewer workflows are usable with keyboard navigation and accessible state feedback.

#### Implementation Notes

- prefer virtualized rendering and incremental parsing for syntax highlighting to reduce peak memory usage
- keep heavy processing off the main Tk/UI thread; use worker threads or background tasks with well-defined concurrency limits and cancellation tokens
- provide a simple editor API surface in the addon registry so plugins can attach to buffer events, diagnostics, and patch application routines without needing to know internal buffer representations
- add integration tests that simulate large-file opens, rapid edits, and automated tentative-fix application to catch regressions early

### Milestone 7: Tool-Aware File Acquisition

#### Scope

- allow supported AI backends to read files directly through tool capability when the selected model can do so

#### Deliverables

- capability detection for tool-using models and backends
- prompt/runtime path that lets eligible models request file reads instead of forcing all code through one giant static prompt
- safety and audit logging around tool-driven file access
- fallback behavior for models or backends that do not support tool use
- permission prompts or policy controls for sensitive file paths when tool access is enabled
- per-run audit details that record which files were requested and why

#### Acceptance Criteria

1. Supported backends can read repository files through a tool-mediated path during review generation.
2. Unsupported backends continue to work through the existing non-tool fallback.
3. File-access events are logged clearly enough to debug prompt/tool behavior.
4. Tool use improves review quality or efficiency on representative repository scenarios.
5. Sensitive file access can be constrained and explained to the user before tool-mediated reads occur.

### Milestone 8: Tooling Robustness And Permission Handling

#### Scope

- harden external tool integration and properly handle permissions, authentication, and transport failures

#### Deliverables

- normalized error handling for file servers, authenticated services, and CLI tools
- explicit credential/authentication diagnostics for permission-related failures
- retry/backoff or recovery guidance where appropriate
- regression coverage for authentication, authorization, and availability failure paths
- secure credential-referencing mechanism that allows tooling and addons to reference user-configured credentials without exposing them in plain text
- credential lifecycle guidance for storage, rotation, revocation, and masking
- failure categorization that distinguishes auth, transport, timeout, and provider-side errors

#### Acceptance Criteria

1. Permission and authentication failures surface actionable diagnostics instead of generic tool errors.
2. Tool integrations fail safely without corrupting review state.
3. Common authenticated-tool failure cases are covered by automated tests.
4. Users can tell whether a failure is caused by credentials, permissions, transport, or tool compatibility.
5. Users can configure credentials that are referenced securely by the application (not displayed or stored in plain text), and tooling/addons may reference these credentials via audited, access-controlled references.
6. Credential usage can be audited, rotated, and revoked without exposing secret values.

### Milestone 9: Security Validation And Hardening

#### Scope

- perform a proper security vulnerability analysis, testing pass, and reporting cycle on the application itself

#### Deliverables

- structured threat review covering local execution, addons, HTTP surfaces, file handling, and credential storage
- security-focused test plan with automated and manual checks where needed
- vulnerability report with severity, exploitability, mitigation, and remediation status
- approved hardening changes for confirmed issues
- explicit threat model artifact for trust boundaries and attacker assumptions
- remediation tracking that records accepted, deferred, and fixed findings

#### Acceptance Criteria

1. The application has a current security assessment artifact, not just ad hoc issue notes.
2. Confirmed vulnerabilities are tracked with explicit remediation decisions.
3. Security-sensitive paths have targeted automated coverage where practical.
4. The final report distinguishes confirmed vulnerabilities from speculative concerns.
5. The threat model captures addon, tool, file-access, and local-API trust boundaries.

### Milestone 10: Multi-Window Desktop Workflow

#### Scope

- allow detachable desktop windows for non-Review pages that can be snapped back into the main application

#### Deliverables

- drag-out workflow for detachable tabs other than the Review page
- snap-back or redock workflow preserving page state
- window-management rules for focus, close behavior, and shared application state
- regression coverage for detach, redock, and state preservation paths
- persisted layout restoration after restart or crash
- keyboard shortcuts or gestures for docking and redocking

#### Acceptance Criteria

1. Results, queue, benchmark, settings, or other approved pages can open in detached windows.
2. The Review page remains anchored in the main window.
3. Detached pages preserve relevant state when redocked.
4. The multi-window workflow does not break existing single-window operation.
5. Detached window layouts can be restored after a restart.

### Milestone 11: Program Documentation Completion

#### Scope

- complete the program’s technical and reference documentation set

#### Deliverables

- finished reference documentation for architecture, configuration, reports, addons, HTTP API, and web server support
- documentation coverage review identifying and closing remaining gaps
- updated diagrams and examples that match the shipped behavior
- updated screenshots for any UI changes and key workflows
- report-generation and report-rendering code changes that persist fix provenance end to end, including AI suggestions, user edits, and final applied resolutions
- report documentation that explains report sections, fix provenance, confidence, and how to interpret AI-suggested versus user-applied changes
- quick-reference pages for contributor workflows, addon authoring, and local API usage

#### Acceptance Criteria

1. Core technical surfaces have current documentation in the main docs set.
2. Examples and reference docs match actual program behavior.
3. Major newly added platform features are documented before milestone close.
4. Screenshots and diagrams stay in sync with the current UI and workflow flow.
5. Reports clearly show which fixes were suggested by AI, which were manually edited or applied by a user, and which changes were ultimately committed into the final artifact.
6. The underlying code paths store, carry, and render fix provenance so the report output is accurate rather than documentation-only.

### Milestone 12: User Manual Completion

#### Scope

- produce a complete end-user manual for GUI, CLI, tool usage, addon creation and usage, and HTTP/web workflows

#### Deliverables

- task-oriented manual covering GUI usage
- task-oriented manual covering CLI usage
- tool-usage guidance for supported models and backends
- addon authoring and operation guidance
- HTTP API and web server user workflows
- screenshots and annotated UI captures included where appropriate to illustrate steps and flows
- troubleshooting and recovery guidance for common setup, credential, and workflow failures

#### Acceptance Criteria

1. A new user can follow the manual to complete the major GUI and CLI workflows.
2. Addon authors can build and load a basic addon from the manual alone.
3. HTTP and web-server usage is documented at a user-workflow level, not only as API reference.
4. The manual reflects the shipped UX rather than an aspirational design.
5. Users can find help for common failures without reading source code.

### Milestone 13: Review Quality Program

#### Scope

- systematically evaluate and improve each built-in review type on this repository

#### Deliverables

- self-review workflow for this repository
- adjudication rubric for findings:
	- correct and actionable
	- correct but weakly phrased
	- false positive
	- false negative
	- taxonomy drift
	- evidence weakness
- per-type improvement log capturing prompt, parser, scorer, context, and code-fix decisions
- additional benchmark fixtures where this repository reveals missing coverage
- recurring benchmark runs so improvements can be measured over time rather than only once

#### Acceptance Criteria

1. Every built-in review type has at least one evaluated run on this repository.
2. Every evaluated run is adjudicated and recorded.
3. Prompt or scorer changes are justified by observed failure modes.
4. Code fixes are applied only after explicit adjudication.
5. Benchmark and scoring changes can be compared against a baseline across repeated runs.

### Milestone 14: Repository Maintenance And Standardization

#### Scope

- standardize commit and branching workflows (e.g., `main`, `milestone/*`, `feature/*`, `release/*`) and document merge policies
- standardize versioning policy and release cadence (versions should only be incremented as part of the release flow and prior to merging into `main`; treat historical releases up to now as beta and establish a first official release tag)
- repository cleanup: remove or archive stale branches, consolidate or document legacy artifacts, and enforce a minimal repository layout and ownership

#### Deliverables

- documented branching and commit guidelines with examples and CI gating rules
- versioning guidelines and a one-time plan to normalize the current versioning to an official initial release
- repository cleanup plan and a set of scripted or manual cleanup tasks to execute the plan
- release tagging and branch-naming policy for `main`, `milestone/*`, `feature/*`, and `release/*`

#### Acceptance Criteria

1. A documented branching and merge workflow is present in the repository (contributor guide) and enforced by CI where reasonable.
2. A versioning policy exists and the repository records a plan for aligning to the first official release.
3. Legacy/stale branches and artifacts are identified and a cleanup execution plan is in place.
4. Release and branch naming conventions are explicit enough for contributors to follow without ambiguity.

### Milestone 15: Windows Installer And Uninstaller

#### Scope

- provide a native Windows installer and uninstaller for the desktop application that bundles the runtime and dependencies where appropriate

#### Deliverables

- an installer trade-off analysis (MSI vs NSIS vs Inno Setup vs MSIX) with chosen approach and rationale
- a build script or CI job that produces a signed installer/uninstaller package for Windows
- installation and uninstallation instructions added to the user manual
- update/rollback guidance and a clean first-run validation step after installation

#### Acceptance Criteria

1. A reproducible Windows installer build produces a working installer and uninstaller for the current release on a supported Windows environment.
2. Installer supports clean uninstall and removes user-level artifacts unless opted to preserve by the user.
3. Installation and uninstallation instructions are present in the documentation.
4. Updates and rollbacks preserve user data according to documented policy.

### Milestone 16: Adaptive Review Addon Generator

#### Scope

- analyze an input codebase to infer language mix, frameworks, test harnesses, dependency manifests, and stylistic conventions
- generate a tailored addon (review-pack + manifest + prompt templates) that adapts review prompts, context augmentation rules, and prioritization to the target repository
- provide a Human-in-the-Loop (HITL) review/edit step so maintainers can accept, tweak, or reject generated prompt and configuration artifacts before activation

#### Deliverables

- an analysis tool that scans a repository and emits a structured capability profile (languages, frameworks, notable files, coding style indicators)
- a generator that produces an addon scaffold containing review definitions, prompt templates, presets, and manifest metadata tuned to the profile
- a CLI or GUI flow that walks a user through reviewing and accepting generated artifacts (HITL), with diffs and previewed sample findings
- tests and benchmark fixtures showing that the generated addon improves review relevance on the target repository (example: precision/recall-ish heuristics or judged improvements)
- a conservative preview mode that proposes prompt and preset changes without altering core rule behavior
- a diff-first review experience so maintainers can inspect generated artifacts before activation

#### Acceptance Criteria

1. The analyzer correctly identifies the primary languages and at least the top framework or build system for a target repository in >90% of sampled test cases.
2. The generator produces a valid addon scaffold that can be installed and exercised by the app without modification.
3. The HITL flow allows a maintainer to accept or edit generated prompts and definitions before the addon becomes active.
4. In representative sample runs, the generated addon improves review relevance or reduces obviously irrelevant findings compared to a baseline (measured by developer adjudication or benchmark fixtures).
5. The generated addon path remains conservative and reversible, with preview and approval before activation.

#### Implementation Notes

- start with heuristics over common files (`package.json`, `pyproject.toml`, `requirements.txt`, `pom.xml`, `go.mod`, `.csproj`, `Cargo.toml`) and common directory structures
- keep generation conservative: prefer adding presets, prompt supplements, and non-destructive filters rather than removing core checks
- always require author approval before enabling generated rules in active review runs

### Milestone 17: Notifications And Scheduled Reviews

#### Scope

- Notifications can be enabled or disabled for Windows notifications, mobile push notifications, and email notifications for both scheduled reviews and ad hoc/manual reviews.
- Scheduled reviews are set per codebase in the Scheduled Review Settings and accept frequency expressions (cron-like) that, when triggered, check for local changes to the codebase; checks can be configured to look at files modified/added/removed or new commits.
- Scheduled review runs execute silently in the background as a service and send notifications when completed.
- Users can configure how far a scheduled run proceeds automatically - from showing results only, to performing tentative AI fixes, to fully completing the review and producing output artifacts.
- Reviewers and reviewees can receive start-of-review and end-of-review notifications from another user's AICodeReviewer instance through Windows notifications, push notifications, and email, with recipient settings controlled per schedule for scheduled reviews or per invocation for ad hoc reviews.

#### Deliverables

- Settings UI (and equivalent CLI/config) for Scheduled Review Settings per codebase including:
	- target path or repository root
	- recurrence expression (cron-like)
	- file/commit-based trigger filters (modified/added/removed files, commit ranges)
	- notification channels and enable/disable toggles (Windows, mobile push, email)
	- automation level selector (preview-only, tentative-fixes, auto-complete)
- Background scheduled review service that detects local changes and triggers runs according to schedule and filters
- Notification adapters for Windows notifications, mobile push (pluggable delivery hooks), and email, including cross-user delivery for reviewer and reviewee notifications
- Safety controls and audit trail for automatically-applied changes when automation levels permit fixes
- API surface for schedule management (`GET/POST/DELETE /api/schedules`) and an events/SSE feed for schedule-triggered job lifecycle

#### Acceptance Criteria

1. A scheduled review can be created for a codebase with a recurrence expression and filter rules.
2. On scheduled trigger, the system checks for local changes (file diffs/new commits) and only runs when filter criteria are satisfied.
3. Scheduled runs execute in the background without blocking foreground GUI/CLI operations and emit a `job_id` and lifecycle events on start and completion.
4. Notification channels can be toggled per-schedule and deliver a completion notice with a short summary and link to the detailed report when enabled.
5. Reviewer and reviewee recipients can receive start and end notifications through Windows, push, and email channels, even when they originate from another user's AICodeReviewer instance.
6. Automation level is respected: preview-only stops after showing results; tentative-fixes applies non-committal fixes (e.g., draft patches); auto-complete runs through to producing final output artifacts and optional auto-application only when explicitly opted in.
7. Audit logs record scheduled triggers, matched-change criteria, actions taken, recipient targeting, and notification deliveries.

#### Implementation Notes

- Reuse the existing `ReviewScheduler` and `ReviewExecutionService`; add a lightweight `ScheduleManager` mapping recurrence expressions to schedule entries and triggering jobs against the scheduler.
- Prefer an index-based local-change detection (tracked file hashes and head commit) to avoid full-diff costs; provide an option for exhaustive diff scans when requested by a schedule's filters.
- Make notification adapters pluggable through the addon registry to allow platform-specific implementations (Windows toast, push providers, SMTP/email, webhook bridge).
- Require explicit user opt-in for automation levels that apply changes automatically; tentative or auto-apply runs must produce clear audit trails and undo guidance.
- The HTTP API should expose schedule management endpoints and an events feed for schedule-triggered job lifecycle monitoring.
- Consider OS service integration (Windows Service, macOS LaunchAgent, systemd timers) for durable background operation; default to an in-process scheduler when the desktop app is running and persist schedules to SQLite to survive restarts.

## Data Model Plan

### Job Model

Each queued review job should track:

- job id
- created at / started at / completed at
- requested scope and target path
- diff source or selected files
- requested review types
- spec content or spec file reference
- backend selection
- requested language
- programmers / reviewers metadata
- current state
- progress counters
- per-job log channel
- artifact and report paths
- retry count
- failure metadata

### Review Report Model

Each report should track:

- report id
- originating job id
- report version or schema version
- summary metadata and execution context
- finding list with severity, evidence, and affected files
- AI-suggested fix text, patch, or action for each finding when available
- user edits to suggested fixes, including what changed and when
- final applied fix or resolution state
- fix provenance indicating whether a change was AI-suggested, user-edited, user-applied, or auto-applied
- confidence or rationale metadata for suggested fixes
- report timestamps, export paths, and artifact references
- audit trail for review, edit, approve, reject, and commit steps

### Review Definition Model

Each review definition should track:

- canonical key
- optional parent key
- display labels and summaries
- group classification
- prompt fragments
- framework supplements or references
- response normalization aliases
- context augmentation rules
- severity hints
- benchmark hooks or fixture metadata
- visibility and selection flags

### Addon Manifest Model

Each addon manifest should track:

- addon id
- version
- compatible core version range
- human-readable name and description
- entry points by capability
- requested permissions
- load order or priority hints
- optional subprocess mode declaration

## Frontend Work Breakdown

### GUI

- replace single active review assumption with queue-aware state
- add jobs panel showing queued/running/completed sessions
- show per-job progress, logs, cancel, retry, and open-report actions
- add settings for max concurrent sessions and addon management
- support addon-contributed menus, tabs, or panels through a constrained UI contribution API

### CLI

- add commands or flags for enqueue, status, list-jobs, cancel, retry, and wait
- surface custom review types and addon-provided backends in help output
- keep a synchronous foreground path for simple single-run use cases

### Web/API

- reuse scheduler state and execution events
- avoid creating HTTP-only domain models

## Validation Matrix

### Queueing And Concurrency

- enqueue multiple jobs from GUI
- enqueue multiple jobs from CLI
- mix dry-run and full-review jobs
- cancel a queued job before start
- cancel one running job while others continue
- verify per-backend concurrency caps
- verify scheduler recovery after restart

### Custom Review Types

- load valid custom type
- load valid subtype inheriting parent metadata
- reject invalid prompt schema
- reject duplicate keys
- verify GUI and CLI selection visibility
- verify reports preserve canonical type metadata

### Addons

- load addon-provided backend
- load addon-provided review type
- load addon-provided menu contribution
- reject incompatible addon version
- isolate addon startup failure from core startup

### HTTP/Web

- create and monitor jobs through API
- stream progress events
- cancel via API and observe same state in GUI/CLI
- verify auth/local-only defaults

### Quality Program

- run each built-in type on this repository
- record adjudication and improvement notes
- add or update fixtures when systematic misses appear

## Review Quality Tranche Plan

Evaluate built-in review types in the following order:

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

For each tranche:

- run reviews on this repository
- adjudicate findings
- improve prompts, parser normalization, or context augmentation when justified
- apply approved code fixes separately from prompt/scorer changes

## Suggested Backlog

1. extract headless execution service from current review flows
2. add persistent job store and scheduler
3. refactor GUI around per-job state instead of one active review
4. add CLI job lifecycle commands
5. introduce backend registry and migrate built-ins
6. introduce review-definition registry and migrate built-ins
7. add custom review pack loader and schema validation
8. add subtype-capable selection UI and CLI help
9. define addon manifest and discovery flow
10. implement first hook/capability registry set
11. add constrained GUI contribution API
12. add HTTP service on top of scheduler
13. add AI-powered review recommendation flow
14. audit UX with diagrams and execute approved improvements
15. enable tool-aware file acquisition for supported models
16. harden tooling permissions and authentication handling
17. complete security validation and remediation reporting
18. add detachable non-review desktop windows with redocking
19. finish technical documentation coverage
20. finish the end-user manual
21. implement repository self-review adjudication workflow
22. execute tranche-by-tranche review-quality improvement work

## Risks

- oversubscribing external backends when session-level and intra-review parallelism interact poorly
- GUI instability if worker threads bypass main-thread UI updates
- addon API drift if the first SDK surface is too broad
- report/filter churn if subtype taxonomy is not normalized carefully
- configuration races when multiple queued jobs read changing runtime settings

## Exit Criteria For This Spec

This spec is complete enough to start implementation when:

1. the core extraction milestone has concrete class and storage designs
2. the scheduler persistence choice is finalized
3. the first backend and review-definition registry APIs are defined
4. the addon manifest schema is drafted and versioned
5. the self-review adjudication template is created for tranche execution