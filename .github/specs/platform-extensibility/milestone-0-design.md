# Milestone 0 Design

## Purpose

Define the first concrete refactor step for the platform extensibility roadmap:

- extract a headless execution core from the existing GUI and CLI paths
- introduce explicit job and event models
- establish backend and review-definition registries
- preserve current behavior while creating stable seams for queueing, addons, and web support

## Current Behavior To Preserve

Milestone 0 must preserve the observable behavior of the current product:

1. CLI still supports dry-run, project/diff scope, multiple review types, interactive confirmation, and report generation.
2. GUI still supports running a review in the background, cancellation, previewing issues, verifying changes, and finalizing reports.
3. Existing backend-specific cancellation limitations remain accurate and unchanged.
4. Existing report schema and artifact flow remain backward compatible.

## Refactor Strategy

Do not replace the current orchestration in one step.

Instead:

1. introduce new domain models and service interfaces beside the current flow
2. adapt `AppRunner` to delegate into the new core
3. adapt GUI and CLI to depend on the new core through thin adapters
4. only then remove obsolete orchestration duplication

## Proposed Module Layout

New modules to introduce in Milestone 0:

- `src/aicodereviewer/execution/models.py`
- `src/aicodereviewer/execution/events.py`
- `src/aicodereviewer/execution/service.py`
- `src/aicodereviewer/execution/context.py`
- `src/aicodereviewer/execution/adapters.py`
- `src/aicodereviewer/registries/backend_registry.py`
- `src/aicodereviewer/registries/review_registry.py`

Existing modules to adapt rather than replace immediately:

- `src/aicodereviewer/orchestration.py`
- `src/aicodereviewer/main.py`
- `src/aicodereviewer/gui/review_mixin.py`
- `src/aicodereviewer/backends/__init__.py`
- `src/aicodereviewer/backends/base.py`

## Domain Model Design

### ReviewRequest

Represents one requested review execution.

Fields:

- `path: str | None`
- `scope: Literal["project", "diff"]`
- `diff_file: str | None`
- `commits: str | None`
- `review_types: list[str]`
- `spec_content: str | None`
- `target_lang: str`
- `programmers: list[str]`
- `reviewers: list[str]`
- `dry_run: bool`
- `output_file: str | None`
- `backend_name: str`
- `selected_files: list[str] | None`
- `diff_filter_file: str | None`
- `diff_filter_commits: str | None`
- `interactive_mode: Literal["cli", "gui", "none"]`

Notes:

- this is the normalized request after CLI and GUI specific parsing is complete
- frontends own argument/widget parsing; the execution core owns normalized validation

### ReviewJob

Represents one executable unit that later Milestone 1 can queue persistently.

Fields:

- `job_id: str`
- `request: ReviewRequest`
- `state: JobState`
- `created_at: datetime`
- `started_at: datetime | None`
- `completed_at: datetime | None`
- `result: ReviewExecutionResult | None`
- `error_message: str | None`

### ReviewExecutionResult

Captures the structured outcome of one executed request.

Fields:

- `status: Literal["dry_run", "no_files", "no_issues", "issues_found", "report_written", "cancelled", "error"]`
- `backend_name: str`
- `review_types: list[str]`
- `scope: str`
- `project_path: str | None`
- `diff_source: str | None`
- `files_scanned: int`
- `target_paths: list[str]`
- `issues: list[ReviewIssue]`
- `report: ReviewReport | None`
- `report_path: str | None`
- `dry_run_summary: list[str] | None`

Notes:

- this supersedes the current loose compatibility summary dict in `AppRunner`
- GUI can still use the raw issue list when interactive finalization is deferred

### JobState

Use an explicit enum-like state set:

- `created`
- `validating`
- `scanning`
- `reviewing`
- `awaiting_interactive_resolution`
- `awaiting_gui_finalize`
- `reporting`
- `completed`
- `cancelled`
- `failed`

## Event Model Design

Milestone 0 needs a typed event channel so the GUI stops depending on ad hoc callbacks and logs.

### Base Event

Each event includes:

- `job_id: str`
- `timestamp: datetime`
- `kind: str`

### Event Types

#### JobStateChanged

Fields:

- `previous_state: JobState | None`
- `new_state: JobState`
- `message: str | None`

#### JobProgressUpdated

Fields:

- `current: int`
- `total: int`
- `message: str`

#### JobLogEmitted

Fields:

- `levelno: int`
- `message: str`

#### JobStreamingToken

Fields:

- `token: str`

#### JobResultAvailable

Fields:

- `result: ReviewExecutionResult`

#### JobFailed

Fields:

- `error_message: str`
- `exception_type: str | None`

## Service Interface Design

### ExecutionDependencies

Bundle injectable dependencies so tests and future schedulers can supply alternatives.

Fields:

- `backend_registry: BackendRegistry`
- `review_registry: ReviewRegistry`
- `scan_fn: ScanFunction`
- `issue_collector: IssueCollector`
- `interactive_resolver: InteractiveResolver`
- `report_writer: ReportWriter`
- `backup_cleaner: BackupCleaner`

### ReviewExecutionService

Primary Milestone 0 service.

Methods:

- `validate_request(request: ReviewRequest) -> None`
- `create_job(request: ReviewRequest) -> ReviewJob`
- `execute_job(job: ReviewJob, sink: ExecutionEventSink, cancel_check: CancelCheck | None = None) -> ReviewExecutionResult`
- `generate_report(job: ReviewJob, issues: list[ReviewIssue] | None = None, output_file: str | None = None) -> ReviewExecutionResult`

Responsibilities:

- normalize state transitions
- resolve backend through registry
- run scan / collect / interactive / report flow
- emit typed events rather than mutating frontend widgets directly
- return structured results instead of dict fragments

Non-responsibilities:

- queue persistence
- job prioritization
- frontend widget management
- long-term artifact storage policy

### ExecutionEventSink

Protocol-like interface:

- `emit(event: ExecutionEvent) -> None`

Concrete sink implementations for Milestone 0:

- `LoggingEventSink`
- `CallbackEventSink`
- `CompositeEventSink`
- GUI adapter sink that marshals updates through `after(...)`

## Registry Design

### BackendRegistry

Purpose:

- replace the hard-coded backend factory branching in `backends/__init__.py`
- prepare for addon-provided backend registration later

Core types:

- `BackendDescriptor`
  - `key`
  - `aliases`
  - `factory`
  - `display_name`
  - `capabilities`

Methods:

- `register(descriptor: BackendDescriptor) -> None`
- `resolve(name: str | None) -> BackendDescriptor`
- `create(name: str | None, **kwargs: Any) -> AIBackend`
- `list_descriptors() -> list[BackendDescriptor]`

Migration plan:

- existing Bedrock, Kiro, Copilot, and Local backends register at import time
- `create_backend()` becomes a thin compatibility wrapper over the registry

### ReviewRegistry

Purpose:

- separate built-in review metadata from the backend base module
- establish the same registration path built-ins and later custom definitions will use

Core types:

- `ReviewDefinition`
  - `key`
  - `group`
  - `label`
  - `summary_key`
  - `prompt_rules`
  - `framework_supplements`
  - `ui_visible`

Methods:

- `register(definition: ReviewDefinition) -> None`
- `get(key: str) -> ReviewDefinition`
- `list_visible() -> list[ReviewDefinition]`
- `canonical_keys() -> list[str]`

Migration plan:

- first move metadata only
- keep prompt assembly in `backends/base.py` temporarily, but drive it from registry data
- later Milestone 2 can externalize definitions fully

## Adapter Design

### CLI Adapter

Purpose:

- convert `argparse.Namespace` into `ReviewRequest`
- invoke `ReviewExecutionService`
- optionally route through interactive CLI resolution

Notes:

- CLI remains synchronous in Milestone 0
- tool-mode still consumes structured results

### GUI Adapter

Purpose:

- convert form state into `ReviewRequest`
- run `execute_job()` in a worker thread
- adapt execution events into Tk-safe UI updates

Notes:

- GUI still runs one session at a time in Milestone 0
- the adapter must own the bridge from typed events to widgets, status bar, and issue/result views
- the existing `_running` flag stays temporarily but becomes UI state, not core execution state

### Legacy AppRunner Adapter

Purpose:

- preserve the existing `AppRunner` public surface while delegating into `ReviewExecutionService`

Plan:

- `AppRunner.run()` constructs a `ReviewRequest`
- calls into the execution service
- maps the structured result into the current return types until callers are migrated

This allows staged migration rather than a flag day rewrite.

## Responsibility Mapping

### What Leaves AppRunner

- request validation
- lifecycle state management
- structured result generation
- backend resolution

### What Stays In AppRunner Temporarily

- compatibility facade for older callers
- deferred report generation bridge used by the GUI until the GUI moves fully to the new result model

### What Leaves GUI ReviewTabMixin

- direct orchestration ownership
- direct backend factory usage beyond adapter boundaries
- direct dependence on `AppRunner` construction details

### What Stays In GUI ReviewTabMixin Temporarily

- worker-thread startup
- Tk widget updates
- selected-file and diff-filter normalization

## Validation Rules Placement

Request validation must be split deliberately:

### Frontend-Level Validation

Keep only UI/CLI parsing errors at the edge:

- missing required widget values
- malformed CLI combinations before request creation

### Core-Level Validation

Move normalized semantic checks into `ReviewExecutionService.validate_request()`:

- diff scope requires diff source
- project scope requires path
- specification requires spec content or spec file materialized to content
- unknown review types rejected after registry resolution
- unknown backend rejected after backend registry resolution

## Logging Strategy

Milestone 0 should keep Python logging, but augment it with typed execution events.

Rule:

- logging remains for diagnostics and existing Output Log support
- all user-relevant state/progress transitions also emit typed events

That lets the GUI migrate incrementally without losing current log behavior.

## Test Plan

### Unit Tests

- request validation for normalized execution requests
- backend registry resolution and alias handling
- review registry visibility and lookup
- execution service dry-run result shape
- execution service no-files / no-issues / issues-found flows
- event emission order and state transitions

### Integration Tests

- CLI path still produces the same behavior for a representative project review
- GUI path still updates progress and result views using the adapter sink
- cancellation propagates through the new service boundary
- deferred report generation still works for GUI finalize flow

### Compatibility Tests

- existing `AppRunner` tests continue to pass while internally delegating
- `create_backend()` remains backward compatible
- current review-type CLI help and GUI type pickers still show built-ins correctly

## Migration Sequence

1. add domain models and event types
2. add backend registry and reimplement `create_backend()` on top of it
3. add review registry and expose current built-in metadata through it
4. implement `ReviewExecutionService` using current scanner, reviewer, and reporter pieces
5. refactor `AppRunner` into a compatibility wrapper over the new service
6. refactor CLI path to build `ReviewRequest` explicitly
7. refactor GUI path to use a GUI execution adapter and event sink
8. remove duplicated validation and state handling once callers are migrated

## Open Decisions

1. Whether `ReviewJob` ids should be UUIDs immediately in Milestone 0 or only once queue persistence arrives.
2. Whether `ReviewExecutionResult` should embed raw dry-run display strings or only structured paths/counts.
3. Whether GUI finalize should continue to keep a live runner-like object or switch immediately to result-driven report generation state.

## Recommendation

For Milestone 0, prefer compatibility over purity:

- keep `AppRunner` as a facade
- keep `create_backend()` as a facade
- keep existing report schema intact

The milestone succeeds if the new service and registries exist and current behavior routes through them, even if some legacy wrappers remain in place.