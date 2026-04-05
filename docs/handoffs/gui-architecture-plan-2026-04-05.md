# GUI Architecture Plan

Date: 2026-04-05

## Objective

Reduce GUI complexity without destabilizing the working desktop surface, the shared review-execution runtime, or the addon platform that now contributes review packs, backend providers, Settings-surface cards, and editor hook behavior.

This plan is intentionally incremental. The current GUI is already functionally broad and well covered. The goal is not a rewrite. The goal is to keep the current user-visible behavior while making ownership boundaries clearer, test seams narrower, and addon-facing surfaces more explicit.

## Current Baseline

The GUI has reached a practical stable point:

- `App` is the composition root in `src/aicodereviewer/gui/app.py`
- tab behavior is split across mixins:
  - `review_mixin.py`
  - `results_mixin.py`
  - `settings_mixin.py`
  - `health_mixin.py`
  - `benchmark_mixin.py`
- review execution already has meaningful seams below the mixin layer:
  - `review_runtime.py`
  - `review_execution_coordinator.py`
  - `review_execution_facade.py`
  - `review_execution_scheduler.py`
  - `review_queue_presenter.py`
  - `review_queue_coordinator.py`
  - `review_queue_actions.py`
  - `review_queue_panel.py`
- popup/editor behavior already has a dedicated subsystem in `popup_surfaces.py`
- addon GUI support is deliberately narrow and working:
  - Settings-surface UI contributors from addon manifests
  - editor hook events and diagnostics
  - patch-applied events emitted from Results workflows

That means the right next move is not “replace mixins with a brand new architecture”. The right move is to continue extracting stable feature seams from the existing mixin host while preserving the current runtime and addon contracts.

## Constraints

Any GUI cleanup must preserve these constraints:

1. `App` remains the only Tk root and composition root.
2. GUI and HTTP continue to share `ReviewExecutionRuntime` and the scheduler boundary rather than growing separate orchestration stacks.
3. All widget updates still cross the Tk thread boundary through app-owned scheduling helpers.
4. The addon model stays manifest-driven and intentionally narrow.
5. Existing GUI tests keep driving real widgets through `tests/gui_test_utils.py` rather than being replaced by mock-heavy unit tests.

## Non-Goals

This plan does not propose:

- a framework rewrite away from CustomTkinter
- generic arbitrary addon widget injection
- replacing the scheduler/runtime stack that already exists
- moving core review/business logic back into the GUI layer
- large visual redesign work

## Main Problems To Solve

### 1. `App` still owns too many cross-feature responsibilities

Even after the recent queue/runtime cleanup, the app shell still bootstraps config, addon/runtime installation, HTTP startup, UI-thread scheduling, logging, popup lifecycle, tab layout, and multiple feature controllers.

### 2. Mixins remain both builders and behavior owners

The mixins are smaller than before, but some files still mix together:

- widget construction
- layout responsiveness
- workflow orchestration
- persistent settings logic
- status/toast updates
- popup launch behavior

That makes future changes harder to place cleanly.

### 3. Popup/editor logic is better isolated than before but still hosted from Results behavior

The popup surface controller is already real architecture. The remaining problem is that popup ownership, results actions, and addon editor events are still coupled closely enough that changes in one area can ripple into the others.

### 4. Addon GUI support is implemented, but not yet modeled as a first-class GUI integration seam

Today the addon GUI contract is correct, but its handling is spread across the app bootstrap, Settings rendering, and popup/editor event emission. The plan should make that integration seam explicit instead of letting it stay incidental.

## Target Architecture

The target architecture keeps the current application shape but narrows responsibilities into five layers.

### Layer 1: App Shell

Owned by `app.py`.

Responsibilities:

- create the Tk root
- load config and locale
- install addon runtime and review registry
- create shared services and feature controllers
- assemble tabs and shared chrome
- own UI-thread scheduling and shutdown

The app shell should not grow new feature-specific workflow logic.

### Layer 2: Feature Modules

Each major GUI feature should move toward a dedicated module boundary that owns only one surface area:

- Review feature
- Results feature
- Settings feature
- Health feature
- Benchmark feature
- Shared status/log surface

Inside each feature, split three concerns clearly:

- view building
- view-state projection and layout application
- workflow actions

The current queue presenter/coordinator split is the model to continue using.

### Layer 3: Workflow Services

These are non-widget helpers used by one or more features:

- review execution scheduler/facade/coordinator stack
- popup/editor surface controller
- model refresh and health-check helpers
- session persistence helpers
- HTTP server bootstrap/status helpers

These services may call back into the app shell for UI-thread scheduling, status updates, and lifecycle hooks, but they should not construct tab widgets directly.

### Layer 4: Shared GUI Infrastructure

This layer should hold infrastructure that multiple features depend on:

- app-owned `after(...)` scheduling and callback cleanup
- status/toast helpers
- log queue plumbing
- responsive layout helpers
- common dialog launch helpers
- shared widget factories or builder helpers where the widgets are not feature-specific

This is where current duplicated or ad hoc layout/scheduling helpers should continue to move.

### Layer 5: Addon Integration Surface

Addon support should stay narrow and explicit.

It should be treated as a dedicated integration layer with two supported GUI paths:

- manifest-declared Settings contributions
- editor/popup events emitted to addon hooks

This layer should not become a generic plugin widget API.

## Addon-Safe Design Rules

The architecture plan must preserve these addon-specific rules:

1. `AddonUIContributorSpec.surface == "settings_section"` remains supported as-is.
2. Settings-addon rendering stays declarative and read-only from the addon perspective.
3. Editor hook events remain event-driven, best-effort, and non-fatal.
4. Addon failures continue to surface as diagnostics instead of breaking GUI startup or popup workflows.
5. GUI cleanup must not inline or bypass addon event emission from popup/editor and patch-application flows.

Practical implication:

- if Settings layout is refactored, addon contribution rendering needs its own stable renderer or presenter rather than disappearing into a larger Settings rewrite
- if popup/editor behavior is split further, addon event emission must move with the popup controller boundary rather than getting stranded in Results-specific code

## Recommended Module Direction

This is the preferred medium-term direction, not an all-at-once move.

### Keep Stable

- `app.py` as composition root
- `review_execution_*` stack
- `review_runtime.py`
- `popup_surfaces.py`
- `review_queue_*` helpers
- `addons.py` as manifest/runtime source of truth

### Gradually Extract From Mixins

- Review tab widget construction into a dedicated builder/helper module
- Review tab responsive layout mapping into an explicit view-state helper
- Results issue-list and action wiring into smaller action/presenter helpers
- Settings addon diagnostics and contribution rendering into dedicated Settings-side renderer helpers
- benchmark layout and artifact-view mapping into presentation helpers parallel to the queue presenter pattern

### Avoid

- another generic compatibility layer that mirrors app state under new names
- a second scheduler path for GUI-only behavior
- direct addon code execution from widget builders beyond the already-validated manifest and hook boundaries

## Incremental Execution Plan

### Phase 0: Lock Boundaries And Vocabulary

Goal:

- document which GUI seams are stable enough to build on

Work:

- treat the scheduler/runtime/popup/addon boundaries as architecture, not temporary cleanup artifacts
- define a short list of app-shell services the feature modules may depend on
- keep test harness access pointed at visible widget surfaces and dedicated helpers rather than app internals

Exit criteria:

- no new feature work adds raw widget-local `after(...)` scheduling without the app-owned helper path
- no new addon GUI behavior bypasses manifest parsing or event emission helpers

### Phase 1: Settings And Addon Extraction

Goal:

- make Settings the first fully structured feature because it already has a constrained addon surface

Work:

- split `settings_mixin.py` into:
  - settings view builder
  - settings persistence/actions
  - settings layout helper
  - addon diagnostics/contribution renderer
- create one explicit renderer/helper that turns addon runtime manifests into Settings cards
- keep the current addon cards visually and behaviorally unchanged

Exit criteria:

- addon summary, diagnostics, refresh, and contribution rendering can be changed without touching unrelated Settings persistence code
- GUI smoke coverage for addon Settings cards still passes unchanged

### Phase 2: Review Tab Builder And Layout Cleanup

Goal:

- reduce `review_mixin.py` to workflow orchestration plus explicit view updates

Work:

- extract review tab widget construction from workflow logic
- isolate responsive layout decisions into view-state helpers similar to the queue presenter pattern
- keep scheduler submission, queue refresh, and cancellation on the current scheduler/coordinator path

Exit criteria:

- layout fixes no longer require editing submission logic
- queue behavior remains driven by scheduler snapshots and coordinators rather than direct widget mutation across the mixin

### Phase 3: Results And Popup Boundary Cleanup

Goal:

- formalize the boundary between Results workflows and popup/editor workflows

Work:

- continue moving popup-specific behavior into `popup_surfaces.py` or closely related helpers
- keep issue-card actions in Results, but move preview/edit/apply flow state ownership to popup-oriented helpers where possible
- keep addon editor event and patch-applied event emission inside popup/editor or apply-action boundaries, not in ad hoc widget callbacks

Exit criteria:

- popup lifecycle and recovery changes no longer require broad edits in `results_mixin.py`
- addon hook behavior remains covered by focused workflow tests

### Phase 4: App Shell Consolidation

Goal:

- leave `App` as composition root, but make it noticeably smaller and more declarative

Work:

- centralize startup/bootstrap helpers for:
  - addon installation
  - registry install
  - local HTTP startup
  - background startup actions
  - shutdown cleanup
- keep the shell as the place where services are wired together, not where feature logic lives

Exit criteria:

- `App.__init__` reads as composition and startup sequencing rather than mixed feature logic
- shutdown still cleans up app-owned timers, popup surfaces, runtime state, and addon-safe diagnostics paths

## Validation Strategy

Every phase should keep three test layers green:

1. focused unit tests for new presenters/coordinators/renderers
2. existing GUI smoke and workflow tests
3. addon regression tests whenever Settings rendering, popup/editor hooks, or patch-application flows change

Minimum regression slices to keep rerunning during this plan:

- `tests/test_gui_smoke.py`
- `tests/test_gui_workflows.py`
- `tests/test_addons.py`
- `tests/test_main_cli.py`
- `tests/test_review_execution_scheduler.py`
- `tests/test_review_queue_actions.py`
- `tests/test_review_queue_coordinator.py`
- `tests/test_review_queue_presenter.py`

When popup/editor behavior changes, also rerun addon-hook and results workflow coverage.

## Sequencing Recommendation

Recommended order:

1. Settings and addon renderer extraction
2. Review tab builder/layout extraction
3. Results and popup boundary cleanup
4. App shell consolidation

This order is deliberate:

- Settings has the narrowest feature surface and the clearest addon contract
- Review already has good scheduler and queue seams to build around
- Results and popup flows are the riskiest and should move only after the surrounding architecture vocabulary is settled
- App shell cleanup should happen last so it reflects the extracted boundaries instead of guessing them early

## Acceptance Criteria For This Plan

The GUI architecture cleanup should be considered successful when:

1. `App` is clearly a shell plus service composition root.
2. Each major tab has a cleaner split between build, layout, and actions.
3. Scheduler/runtime boundaries remain the only production review-execution path.
4. Popup/editor behavior has an explicit ownership boundary separate from general Results rendering.
5. Addon Settings contributions and editor hook events remain supported without widening the addon SDK.
6. GUI smoke/workflow coverage stays green throughout the migration.

## Immediate Next Slice

Start with Settings and addon extraction.

That is the safest architecture slice because it:

- preserves current user-visible behavior
- hardens the only existing addon GUI contribution surface
- provides a repeatable pattern for later feature extraction
- avoids destabilizing the already-working scheduler/runtime and popup/editor boundaries