# Milestone 1 Queue Kickoff Handoff

Date: 2026-04-03

## Objective

Start Milestone 1 from the platform extensibility roadmap: queue and concurrent session execution.

Milestone 0 is now at a deliberate stop point. The execution core, typed session restore/finalize path, and `AppRunner` compatibility facade are all in place. The next work should introduce a real session-scheduling seam instead of continuing facade-thinning cleanup.

## Current Status

The first Milestone 1 slice is now in place.

Completed in this slice:

- added a GUI-side `ActiveReviewController` in `src/aicodereviewer/gui/review_runtime.py`
- moved review start/cancel/client/runner ownership in `gui/review_mixin.py` onto that controller
- kept `_running`, `_review_runner`, `_review_client`, and `_cancel_event` as synchronized compatibility mirrors so existing GUI flows and tests stay stable while the boundary changes underneath
- updated `gui/results_mixin.py` to resolve finalize/session state through runner helper methods instead of reaching only for the ambient runner field
- added focused GUI regression assertions that the controller retains the finalize-capable runner after a completed review and clears active client/cancel state when execution ends
- split GUI busy-state ownership so review execution, review-changes verification, and health checks now each have dedicated source-of-truth state while `_running` remains only as a synchronized compatibility mirror
- removed the remaining review-path decision-making dependence on `_running`; review execution cancellation now keys off the controller-backed execution state instead of the legacy mirror
- tightened Review Changes semantics so the workflow no longer advertises global cancellation it does not actually honor
- stabilized Review Changes workflow coverage to assert durable outcomes instead of transient entry into the short-lived `_review_changes_running` state
- migrated the remaining GUI smoke coverage that simulated a running review from direct `_running` mutation to the active review controller
- centralized shared cancel-button availability behind the review runtime helpers so review execution and backend health checks now use one cancel-capable boundary instead of ad hoc widget toggles
- kept Review Changes outside that shared cancel path and added focused assertions that the global cancel button is enabled only while a genuinely cancel-capable review or health-check workflow is active
- introduced an explicit AI Fix runtime controller so AI Fix generation no longer relies only on mixin-local `_ai_fix_running` / `_ai_fix_cancel_event` fields and ambient client ownership
- folded AI Fix into the shared busy-state helpers so app-wide review-start gating now treats AI Fix as active background work instead of depending only on local button disabling
- kept the existing AI Fix UX intact by preserving `_ai_fix_running`, `_ai_fix_cancel_event`, and `_review_client` as compatibility mirrors while tests now also assert the controller-backed runtime state
- introduced an explicit health-check runtime controller so backend identity and timeout timer ownership no longer live only in ambient `_health_check_backend` / `_health_check_timer` fields
- routed health-check start, timeout, completion, and cancellation through that controller while preserving the old fields as compatibility mirrors
- closed a cross-workflow overlap bug by preventing health checks from starting while AI Fix is running, and added focused regression coverage for that interaction
- extracted the duplicated begin/bind-client/request-cancel/finish behavior for review execution and AI Fix into a shared cancelable runtime helper in `gui/review_runtime.py`
- switched AI Fix behavior-dependent backend-context and client lookup over to runtime helpers instead of reading the `_review_client` compatibility mirror directly
- converted the remaining behavior-dependent review-side compatibility reads in global-cancel, AI Fix cancel, and Review Changes verification flows to helper methods instead of direct `_review_client` / `_cancel_event` / `_ai_fix_cancel_event` reads
- extended `App.destroy()` to clean up AI Fix clients and active health-check timers/runtime state instead of only releasing the review-side client
- added smoke coverage for AI Fix client shutdown and health-check timer shutdown
- migrated focused GUI smoke/workflow assertions away from direct compatibility-mirror reads so the tests now prefer runtime helpers and controller-owned state for review clients, AI Fix cancellation, and health-check identity
- migrated the remaining focused review-runner test setup and assertions onto `_bind_review_runner()` / `_current_review_runner()` so the GUI/session tests no longer need `_review_runner` as their primary observation or setup surface
- removed the duplicate review-runner helper implementation from `gui/results_mixin.py` so production Results-tab session/finalize flows now rely on the runtime-aware runner helpers provided by `gui/review_mixin.py`, while the standalone results-session test double carries its own minimal shim
- converted `_review_runner` from a separately synchronized app field into a compatibility proxy backed by the active review controller, leaving only `_legacy_review_runner` as fallback storage for controller-less test doubles or mixin-only use
- converted `_review_client` from a separately synchronized app field into a compatibility proxy backed by the active review and AI Fix controllers, leaving only `_legacy_review_client` as fallback storage for transient review-side compatibility and controller-less cases
- converted `_cancel_event` from a separately synchronized app field into a compatibility proxy backed by the active review controller, leaving only `_legacy_cancel_event` as fallback storage for controller-less cases
- converted `_ai_fix_running` and `_ai_fix_cancel_event` from separately synchronized app fields into compatibility proxies backed by the active AI Fix controller, leaving only `_legacy_ai_fix_running` and `_legacy_ai_fix_cancel_event` as controller-less fallback storage
- converted `_health_check_backend` and `_health_check_timer` from separately synchronized app fields into compatibility proxies backed by the active health-check controller, leaving only `_legacy_health_check_backend` and `_legacy_health_check_timer` as controller-less fallback storage
- converted `_running` from a separately synchronized app field into a compatibility proxy backed by the helper-defined busy state, leaving only `_legacy_running` as fallback storage for controller-less or direct-compatibility writes
- stopped eagerly materializing most `_legacy_*` fallback slots in `App.__init__`; production code now creates them only if a compatibility write actually occurs, while proxy getters continue to tolerate absence via `getattr`
- collapsed the remaining `_legacy_*` fallback slots inside `gui/review_mixin.py` into one internal `_legacy_compat_state` map, so production code no longer carries a family of pseudo-fields for controller-less compatibility paths
- removed `_legacy_compat_state` from `gui/review_mixin.py` entirely; Review Changes now binds its recreated backend client onto the active review controller, so real `App` paths no longer depend on any controller-less compatibility store
- added focused GUI assertions that production `App` flows do not materialize `_legacy_compat_state` during startup, destroy cleanup, or Review Changes verification
- removed the dead `_running` compatibility property and the no-op `_sync_*_compatibility()` shim layer from `gui/review_mixin.py`, so production code now talks directly to controller helpers instead of routing through empty compatibility hooks
- removed leftover AI Fix initialization writes and Review Changes busy-sync calls that no longer carried state, and updated the smoke coverage to assert the `App` class no longer exposes `_running`
- removed the remaining class-level GUI compatibility properties (`_review_runner`, `_review_client`, `_cancel_event`, `_ai_fix_running`, `_ai_fix_cancel_event`, `_health_check_backend`, `_health_check_timer`) from `gui/review_mixin.py`; the runtime now reaches controller state only through explicit helper methods
- renamed the last production review-client rebinding helper away from `compatibility` wording and extended smoke coverage to assert those legacy property names no longer exist on the `App` class
- renamed the remaining GUI helper API away from old mirror vocabulary so production code now uses controller/session-oriented helpers like `_current_session_runner()`, `_bind_session_runner()`, `_active_review_client()`, and `_active_ai_fix_cancel_event()`
- renamed the typed execution/session serialization helpers in `execution/models.py` away from `legacy` terminology (`from_serialized_dict()`, `to_serialized_dict()`, `to_summary_dict()`), and updated GUI session save/load plus focused execution/orchestration tests to use the new API names without changing payload shape
- added primary `AppRunner` names for the remaining compatibility-facing runner surface so production code can use `execution_summary`, `serialized_report_context`, and `restore_serialized_report_context()`
- moved `main.py`, `gui/results_mixin.py`, and the focused runner/session test stubs onto the new runner-facing names so the active production path no longer depends on the older compatibility vocabulary
- migrated the remaining general orchestration and CLI tool-mode tests to the new runner-facing names so old runner vocabulary no longer appears in routine test setup
- removed incidental retired-alias fields from the broad GUI workflow and results-session test stubs
- removed the retired runner aliases from `AppRunner` and `ReviewRunnerState`, and deleted the guarded old-name fallbacks from `main.py` and `gui/results_mixin.py`, so the live runtime and focused tests now use only `execution_summary`, `serialized_report_context`, and `restore_serialized_report_context()`
- rewrote the archival Milestone 0 handoff/chronology docs and the active design note so the repository text no longer preserves the retired runner vocabulary either
- renamed the saved-session payload/report metadata vocabulary to `report_context`, started writing `format_version: 2` session payloads, and made that versioned shape the only supported session-file contract
- moved review-progress snapshot and elapsed-timer bookkeeping off the ambient `App` object and onto `ActiveReviewController`, so the active review handle now owns more of the execution progress wiring needed for future scheduling work
- moved Review Changes running-state ownership off the ambient `App` object and onto a dedicated `ActiveReviewChangesController`, so busy-state coordination no longer depends on the `_review_changes_running` app field
- moved health-check countdown bookkeeping off the ambient `App` object and onto `ActiveHealthCheckController`, so the last visible health-check timer state now lives with the active health-check runtime owner too
- moved backend model-refresh deduplication off the ambient `App` object and onto `ActiveModelRefreshController`, so combobox refresh coordination no longer depends on the `_model_refresh_in_progress` app set
- moved backend-client stream callback management and release cleanup for review execution and AI Fix into the shared `CancelableRuntimeController`, so the mixins no longer duplicate backend resource teardown logic
- moved review progress-event application and formatted progress-status text into `ActiveReviewController`, so `gui/review_mixin.py` now only schedules Tk updates while the controller owns the review progress snapshot semantics
- moved review stream-preview accumulation and formatted preview publishing behind `ActiveReviewController`, so `gui/review_mixin.py` no longer keeps its own token buffer while the review runtime owner now resets preview state when a new run begins
- moved review event-sink construction behind `ActiveReviewController`, so `gui/review_mixin.py` no longer interprets execution events directly and now only schedules the widget updates published by the controller
- moved review backend-client creation, binding, and stream setup behind `ActiveReviewController`, so `gui/review_mixin.py` no longer performs inline backend activation for the non-dry-run review path
- pivoted the extracted review execution behavior onto a new `ReviewExecutionCoordinator`, so `ActiveReviewController` returns to owning live review state while the coordinator now owns review stream handling, event-sink construction, and backend activation above it
- moved review run outcome classification onto `ReviewExecutionCoordinator`, so `gui/review_mixin.py` no longer decides cancel/dry-run/issues/no-report result branches inline and now only applies the UI effect of the coordinator-classified outcome
- introduced a higher-level `ReviewExecutionFacade` above the coordinator, so `gui/review_mixin.py` now routes review event-sink creation and the main review-run setup/execution path through one façade instead of coordinating scan assembly, runner construction, and run execution itself
- introduced a final scheduler-facing `ReviewExecutionScheduler` above the façade stack, so `gui/review_mixin.py` no longer owns the background worker function and now delegates review execution lifecycle dispatch to the scheduler boundary
- moved active-review begin/finish/client-release ownership into `ReviewExecutionScheduler.submit_run()`, so `gui/review_mixin.py` now keeps only GUI-specific widget effects while the scheduler owns review submission ids, cancel-event handoff, and runtime lifecycle cleanup
- expanded scheduler-focused workflow coverage to assert accepted submission handles plus success, error, and cancellation callback ordering, including backend-client release on scheduler-managed failure paths
- evolved `ReviewExecutionSubmission` into a queued submission record with `queued` / `running` / terminal status transitions, while `ReviewExecutionScheduler` now keeps an internal pending-submission queue and auto-dispatches the next accepted review after the active one finishes without changing the current single-active-review GUI behavior
- moved elapsed-timer start ownership onto a scheduler `on_started` callback, keeping the timer itself GUI-owned but ensuring it begins only when a submission actually dispatches rather than merely being accepted into the scheduler boundary
- added `ReviewExecutionScheduler.cancel_submission(submission_id)` so the scheduler can now drop a queued review before dispatch or forward a cancel request to the active submission's cancel event, with focused coverage locking in queued-cancel callback ordering and active-cancel signaling
- added immutable scheduler query APIs (`get_active_submission_snapshot()`, `get_submission_snapshot(...)`, `list_submission_snapshots()`) so a later queue UI can consume full submission snapshots without inspecting mutable internal scheduler state directly
- added a GUI-side `ReviewSubmissionSelectionController` plus a minimal review-queue panel on the Review tab, so visible queue behavior now targets a selected submission through GUI-owned selection state while the panel itself consumes only scheduler snapshots and routes cancellation only through `ReviewExecutionScheduler.cancel_submission(...)`
- relaxed review submission gating so the Review tab can accept another review while one is already active, allowing the minimal queue panel to surface active-plus-queued submissions without changing the rest of the app's non-review busy-state rules
- moved the queue panel's labels, detail text, summary text, and queued-cancellation status behind i18n keys, and added an explicit submission kind (`review` vs `dry_run`) to scheduler submissions/snapshots so dry runs stay in the same queue panel but are clearly labeled instead of being mixed in invisibly
- localized the remaining review-tab submission-path strings around file selection, diff filtering, invalid project-path validation, and testing-mode review start so the queue-enabled review flow no longer falls back to raw English outside the queue panel
- refined queue-panel presentation so visible submissions are display-sorted as active first, then queued reviews, then queued dry runs, and each entry now carries a localized badge-like kind prefix for easier scanning when both submission types share one queue
- rerouted the bottom cancel button's active-review path through `ReviewExecutionScheduler.cancel_submission(...)` while preserving its existing active-only UX, and moved the active backend-cancel hop behind the scheduler so visible queue behavior now has one cancellation boundary for both targeted queue actions and active review cancellation
- kept a narrow controller-level fallback when no scheduler snapshot is present so testing-mode/controller-only review state still reports cancellation correctly without weakening the production scheduler-first path
- split the queue panel's selected-submission detail copy into explicit localized active-versus-queued variants, so the visible queue UX no longer relies only on the role label to communicate whether the current selection is running or pending
- hardened `ReviewExecutionScheduler` so an exception raised after cancellation has already been requested now resolves as a cancelled submission rather than surfacing a failure, preserving the expected terminal ordering for active-cancel/error races now that all review cancellation paths converge on the scheduler
- extracted queue-panel ordering and localized label/detail formatting into a small `ReviewSubmissionQueuePresenter`, so `gui/review_mixin.py` now keeps queue widget wiring and selection state while the presenter owns the scheduler-snapshot-to-UI presentation mapping
- pinned the remaining late active-cancel ordering edge with focused scheduler coverage: if cancel is requested after the backend has already returned an outcome but before finish callbacks complete, the scheduler now ignores that late cancel request instead of mutating the already-decided completed outcome
- moved the remaining queue-panel empty-versus-populated widget application behind a tiny mixin helper, so `gui/review_mixin.py` no longer assembles the queue panel's disabled/enabled widget state inline during refresh and instead applies one computed view state surface
- added focused scheduler coverage for the queue handoff edge where a late cancel is attempted during the first submission's finish cleanup while a second submission is already queued, locking in that the late cancel is ignored and the next queued dispatch still starts in order
- extracted queue-panel widget creation itself into a dedicated builder helper, so `gui/review_mixin.py` no longer owns both queue widget construction and queue refresh logic while the Review tab still exposes the same queue widget attributes to the rest of the app/tests
- added scheduler coverage for the transition window where the next queued submission has already been promoted to the active slot but its `on_started` callback has not fired yet, locking in that cancellation is rejected in that reserved-active state and the dispatch proceeds normally into `running`
- moved the queue-panel widget binding behind a tiny helper in `gui/review_queue_panel.py`, so `gui/review_mixin.py` no longer depends on the builder return field names while preserving the existing queue widget attribute surface
- added focused scheduler coverage for the dispatch-start edge where active cancellation is requested during `on_started` side effects, locking in that the submission is already `running`, cancellation succeeds through the scheduler, and the worker exits through the normal `cancelled` outcome without executing the review body
- moved the remaining queue-selection orchestration behind the existing `ReviewSubmissionSelectionController`, so `gui/review_mixin.py` no longer owns label-to-submission mapping or snapshot-selection synchronization and now limits itself to queue refresh, view application, and cancel/status side effects
- added focused scheduler coverage for re-entrant queue refresh during `on_finished` side effects, locking in that a finish-time snapshot query sees the next submission in the reserved-active window (`is_active`, still `queued`, no thread attached) and that dispatch still proceeds normally into `running`
- moved the remaining queue-cancel outcome branching behind a tiny `gui/review_queue_actions.py` helper, so `gui/review_mixin.py` no longer interprets queue-targeted cancellation results directly and now only applies the returned UI effects
- added focused scheduler coverage for re-entrant cancel attempted from the second submission's own `on_finished` side effects, locking in that the submission is already cleaned up, no snapshots remain, and the late self-cancel is rejected without mutating the completed outcome
- moved the remaining queue refresh timing behind a small `ReviewSubmissionQueueCoordinator`, so `gui/review_mixin.py` no longer scatters direct queue refresh calls across review lifecycle callbacks and now emits queue-related events into one helper that owns selection sync plus refresh application
- added presenter-level unit coverage for the queue empty and stale-selection cases, so the queue presentation fallback behavior is now pinned below the mixin layer as the Review tab becomes mostly orchestration around presenter and helper outputs
- moved the final queue widget-application branch behind `ReviewSubmissionQueueCoordinator` as well, so `gui/review_mixin.py` no longer owns queue view-state application and now only forwards queue events plus applies status/cancel side effects outside the coordinator seam
- added a small coordinator unit-test slice for selection-change refresh and cancel-effect refresh behavior, so the newly introduced queue coordination seam is now covered directly instead of only through GUI workflow tests
- added a direct unit-test file for `gui/review_queue_actions.py`, so the remaining queue-targeted cancellation decision tree now has explicit coverage for no-selection, stale-selection, cancel-rejected, active-cancel, and queued-cancel outcomes below the mixin layer
- considered collapsing the `_submission_queue_*` compatibility surface in `gui/review_mixin.py`, but kept it in place because current smoke/workflow coverage still reaches those attributes directly for queue-panel assertions and button invocation
- introduced a small queue test helper in `tests/gui_test_utils.py` so GUI smoke/workflow tests can drive the queue panel through one helper surface instead of reaching through app-owned `_submission_queue_*` internals directly
- removed the mixin-facing `_submission_queue_*` widget compatibility surface from production after migrating those tests, leaving queue widget ownership inside the builder/coordinator path while preserving the same queue-panel coverage and regression baseline
- routed `QueuePanelHarness` selection through the actual queue option-menu widget callback path instead of calling the app selection handler directly, so the queue GUI tests now better match user-driven widget behavior
- added a small status-bar helper on `GuiTestHarness` and moved queue/cancel status assertions onto that helper, further reducing direct test reads of raw app UI state without changing behavior
- moved the remaining `QueuePanelHarness` label mapping off selection-controller state and onto widget-visible labels plus ordered scheduler snapshots, so the queue test helper now leans more on visible widget state and less on internal controller storage
- formalized the status helper as a dedicated `StatusBarHarness` inside `tests/gui_test_utils.py`, leaving `GuiTestHarness` to delegate status reads/waits instead of exposing only ad hoc wrapper methods

Focused validation after this slice:

- `tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` -> `56 passed`
- `tests/test_gui_smoke.py` -> `21 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` -> `77 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after AI Fix runtime extraction -> `77 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after health-check runtime extraction -> `78 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after shared cancelable runtime helper extraction -> `78 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after helper-driven mirror cleanup and destroy cleanup -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py` after migrating focused GUI assertions off compatibility mirrors -> `58 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py` after migrating runner setup/assertions to helper methods -> `60 passed`
- `tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after removing duplicate Results-tab runner helpers -> `57 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after converting `_review_runner` into a controller-backed compatibility proxy -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after converting `_review_client` into a controller-backed compatibility proxy -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after converting `_cancel_event` into a controller-backed compatibility proxy -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after converting AI Fix and health-check compatibility fields into controller-backed proxies -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after converting `_running` into a compatibility proxy and removing eager legacy-slot initialization -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after consolidating fallback compatibility storage into `_legacy_compat_state` -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after removing `_legacy_compat_state` from production `App` paths -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after removing `_running` and the no-op compatibility sync shims -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after removing the remaining class-level legacy properties from `ReviewTabMixin` -> `80 passed`
- `tests/test_execution_service.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after renaming the execution/session serialization helpers away from `legacy` terminology -> `108 passed`
- `tests/test_execution_service.py tests/test_orchestration.py tests/test_results_session.py tests/test_gui_workflows.py tests/test_gui_smoke.py tests/test_cli_tool_mode.py` after adding primary runner API names for execution summaries and serialized report context -> `127 passed`
- `tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_execution_service.py tests/test_results_session.py tests/test_gui_workflows.py tests/test_gui_smoke.py` after migrating the remaining general tests to the primary runner API names -> `127 passed`
- `tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_execution_service.py tests/test_results_session.py tests/test_gui_workflows.py tests/test_gui_smoke.py` after removing incidental old alias usage from broad GUI test stubs -> `127 passed`
- `tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_execution_service.py tests/test_results_session.py tests/test_gui_workflows.py tests/test_gui_smoke.py` after removing the retired runner vocabulary from runtime code, focused tests, archival handoffs, and the active design note -> `127 passed`
- `tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_execution_service.py tests/test_results_session.py tests/test_gui_workflows.py tests/test_gui_smoke.py` after removing the remaining old runner vocabulary from runtime code and focused tests -> `127 passed`
- `tests/test_execution_service.py tests/test_results_session.py tests/test_gui_workflows.py tests/test_orchestration.py` after versioning saved-session payloads, renaming persisted report context fields, and removing the backward-compatibility session-key reader -> `85 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving review progress/timer state onto `ActiveReviewController` -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving Review Changes running state onto `ActiveReviewChangesController` -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving health-check countdown state onto `ActiveHealthCheckController` -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving model-refresh state onto `ActiveModelRefreshController` -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after centralizing review/AI Fix backend client lifecycle on `CancelableRuntimeController` -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving review progress-event application into `ActiveReviewController` -> `80 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving review stream preview buffering into `ActiveReviewController` and adding focused coverage -> `81 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving review event-sink construction into `ActiveReviewController` and adding focused coverage -> `82 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving review backend activation into `ActiveReviewController` and adding focused coverage -> `83 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after pivoting review execution behavior onto `ReviewExecutionCoordinator` -> `83 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving review outcome classification into `ReviewExecutionCoordinator` -> `84 passed, 1 skipped`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after introducing `ReviewExecutionFacade` above the coordinator and routing the review path through it -> `86 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after introducing `ReviewExecutionScheduler` above the façade stack and routing `_run_review(...)` through it -> `87 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after promoting `ReviewExecutionScheduler` into the review-submission/runtime-lifecycle boundary and adding scheduler ordering coverage -> `89 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after evolving `ReviewExecutionScheduler` into a queued submission boundary and moving elapsed-timer start onto scheduler start callbacks -> `90 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after adding scheduler-side queued submission cancellation and active-cancel forwarding -> `92 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after adding immutable scheduler submission snapshot queries and snapshot-focused workflow coverage -> `94 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after adding the GUI submission-selection abstraction, minimal review-queue panel, and queue-capable review submission path -> `95 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after localizing the queue panel and labeling scheduler snapshots with submission kinds -> `96 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after localizing the remaining queue-adjacent review-tab strings and adding queue entry badge/order refinement -> `98 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after routing active-review cancellation through the scheduler boundary and covering the controller fallback path -> `100 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after making selected queue detail copy explicit and collapsing post-cancel exceptions into cancelled scheduler outcomes -> `101 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after extracting queue presentation into a helper and pinning the late active-cancel ordering case -> `102 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving queue widget application behind an apply-view-state helper and pinning queued dispatch after late cancel during finish cleanup -> `103 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after extracting queue widget construction into a builder and pinning reserved-active cancellation before `on_started` -> `104 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving queue widget binding behind a helper and pinning active cancellation during `on_started` side effects -> `105 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving queue-selection orchestration behind the selection controller and pinning re-entrant finish-time refresh -> `106 passed`
- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving queue-cancel outcome branching behind a helper and pinning late self-cancel during second `on_finished` cleanup -> `107 passed`
- `tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving queue refresh timing behind a coordinator and adding presenter-level empty/stale-selection coverage -> `109 passed`
- `tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after moving final queue widget application behind the coordinator and adding coordinator unit coverage -> `111 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after adding direct action-helper unit coverage and keeping the still-used queue widget compatibility surface -> `116 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after introducing a queue test helper and removing the mixin-facing queue widget compatibility surface -> `116 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after routing queue selection through the option-menu path and adding a status-bar test helper -> `116 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after shifting queue harness mapping toward widget state and formalizing `StatusBarHarness` -> `116 passed`
- added a small `ResultsTabHarness` in `tests/gui_test_utils.py` for Results-tab issue-list and tab-state assertions, covering current tab label, issue counts/descriptions, visible-card counts, finalize/save button state, and filter controls without widening production surface area
- migrated the first Results-tab GUI workflow assertions off raw `app._issues`, `app._issue_cards`, `tabs.get()`, `finalize_btn`, `save_session_btn`, and filter widget reads, keeping direct card-level access only where the workflow still needs to invoke per-card actions
- `tests/test_gui_workflows.py -k "displays_results_and_releases_backend or save_session_round_trip_restores_results_and_report_context or skip_and_undo_workflow_updates_results_actions or review_changes_recreates_backend_and_auto_finalizes or finalize_workflow_saves_report_and_clears_results or results_filters_match_visible_issue_cards or restored_session_review_changes_recreates_backend_and_finalizes"` after adding `ResultsTabHarness` -> `6 passed, 56 deselected`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after adding `ResultsTabHarness` and migrating the first Results assertions -> `116 passed`
- expanded `ResultsTabHarness` so the remaining AI Fix and batch-fix workflow setup now goes through helper methods for `show_issues(...)`, card lookup, selected-card collection, and batch-fix popup launch instead of rebuilding selections from raw `_issue_cards` in each test
- migrated the remaining per-card selection and batch-fix setup in `tests/test_gui_workflows.py` behind the Results harness, leaving direct app access only for widgets or runtime state that still lack a dedicated helper surface
- removed the dead queue presenter accessor and the remaining queue-selection/coordinator forwarding helpers from `gui/review_mixin.py`; the mixin now calls the app-owned `_review_submission_queue` coordinator and `_selected_review_submission` state directly at the queue boundary
- `tests/test_gui_smoke.py tests/test_gui_workflows.py` after expanding `ResultsTabHarness` and thinning queue helpers in `review_mixin.py` -> `85 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after expanding the Results harness and removing the remaining queue helper accessors -> `116 passed`
- added small AI Fix mode/button helpers on `ResultsTabHarness` for entering mode, starting and cancelling generation, checking mode/button visibility/state, checking AI Fix runtime state, and waiting for AI Fix shutdown so the Results workflows no longer need to reach through raw AI Fix widgets for those assertions
- migrated the remaining AI Fix mode/button state checks in `tests/test_gui_workflows.py` onto the Results harness while leaving broader runtime assertions on shared app state only where no dedicated helper exists yet
- collapsed `_on_submission_queue_selected(...)` in `gui/review_mixin.py` by binding the queue option-menu callback directly to `self._review_submission_queue.on_queue_selection_changed`, removing one more queue-only pass-through from the mixin surface
- `tests/test_gui_smoke.py tests/test_gui_workflows.py` after adding AI Fix Results helpers and collapsing direct queue selection binding -> `85 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after adding AI Fix Results helpers and removing `_on_submission_queue_selected(...)` -> `116 passed`
- added a small `ResultsTabHarness.active_review_client()` helper and migrated the remaining Results/runtime assertions in `tests/test_gui_workflows.py` off direct `app._active_review_client()` reads
- moved the remaining queue-cancel glue beside the existing queue action seam in `gui/review_queue_actions.py` with `apply_review_submission_cancel_effect(...)` and `cancel_selected_review_submission_and_apply(...)`, then bound the Review-tab queue cancel button directly to that action-module helper instead of a mixin-local `_cancel_selected_submission()` pass-through
- added direct queue-action tests for effect application and combined cancel-and-apply behavior, increasing the milestone baseline by two tests
- `tests/test_review_queue_actions.py tests/test_gui_smoke.py tests/test_gui_workflows.py` after adding the active-review-client helper and collapsing queue cancel binding -> `92 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after migrating the remaining Results runtime assertions and removing `_cancel_selected_submission()` -> `118 passed`
- added `ResultsTabHarness.is_busy()` and migrated the remaining Results/AI Fix workflow assertion off direct `app._is_busy()` reads so the last shared busy-state check in that path now goes through the harness surface too
- replaced the inline queue-cancel lambda in `gui/review_mixin.py` with a named queue callback factory, `make_cancel_selected_review_submission_callback(...)`, in `gui/review_queue_actions.py`, keeping the Review tab builder call cleaner while preserving the existing queue action seam
- added direct queue-action coverage for the named callback factory and updated the focused/baseline counts accordingly
- `tests/test_review_queue_actions.py tests/test_gui_smoke.py tests/test_gui_workflows.py` after adding the busy-state helper and named queue cancel callback factory -> `93 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after replacing the queue cancel lambda and migrating the last busy-state assertion -> `119 passed`
- added `ResultsTabHarness.status_text()` and migrated the remaining direct status-bar reads in the Results/AI Fix workflow path onto that helper, leaving the remaining raw status assertions only in unrelated dry-run and health-check coverage
- bundled the Review-tab queue callbacks behind a small `ReviewSubmissionQueueCallbacks` object plus `make_review_submission_queue_callbacks(...)` in `gui/review_queue_actions.py`, so `gui/review_mixin.py` now binds one queue callback bundle instead of spelling out cancel binding arguments inline
- added direct queue-action coverage for the callback bundle factory and updated the focused/baseline counts accordingly
- `tests/test_review_queue_actions.py tests/test_gui_smoke.py tests/test_gui_workflows.py` after adding the Results status helper and queue callback bundle -> `94 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after bundling queue callbacks and finishing Results/AI Fix status cleanup -> `120 passed`
- removed `ResultsTabHarness.status_text()` again and moved the remaining dry-run, health-check, and shared AI Fix status assertions in `tests/test_gui_workflows.py` onto the existing `StatusBarHarness` / `GuiTestHarness.status_text()` path, so status-bar observation is now centralized on one shared harness instead of split across queue and Results helpers
- moved `ReviewSubmissionQueueCallbacks` plus `make_review_submission_queue_callbacks(...)` from `gui/review_queue_actions.py` into `gui/review_queue_panel.py`, keeping queue action semantics in the action helper module while making the queue callback bundle live beside the queue panel builder contract that consumes it
- `tests/test_review_queue_actions.py tests/test_gui_smoke.py tests/test_gui_workflows.py` after centralizing status-bar assertions on the shared status harness and moving the queue callback bundle to the panel module -> `94 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after centralizing status-bar assertions and moving the queue callback bundle beside the panel builder -> `120 passed`
- added a dedicated `ReviewRuntimeHarness` in `tests/gui_test_utils.py` plus a few queue-observation helpers on `QueuePanelHarness`, so GUI smoke/workflow tests can now observe active review runtime state, current session runner state, queue snapshots, and selected queue submission state without reaching through `App` internals directly
- migrated the remaining GUI-facing review-runtime and queue assertions in `tests/test_gui_workflows.py` off direct `_active_review`, `_current_session_runner()`, `_is_review_execution_running()`, `_is_review_changes_running()`, queue snapshot, and queue-selection reads; the remaining direct accesses in that file are now the intentional lower-level scheduler/facade monkeypatch seams rather than GUI-state observation
- moved the remaining smoke status assertion in `tests/test_gui_smoke.py` onto `StatusBarHarness` and switched the review-client destroy assertion to the new review runtime harness, leaving only one direct `_active_review.begin()` setup call as an intentional low-level test setup step
- `tests/test_gui_smoke.py tests/test_gui_workflows.py` after adding the review runtime harness and migrating the remaining GUI-facing runtime assertions -> `85 passed`
- `tests/test_review_queue_actions.py tests/test_review_queue_coordinator.py tests/test_review_queue_presenter.py tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_results_session.py tests/test_orchestration.py` after closing the remaining GUI-facing runtime/queue observation leaks -> `120 passed`

## Recommended First Behavior Seam

Introduce an explicit GUI-side active review control boundary in front of the execution core.

Concretely, the first seam to work on is:

- stop treating GUI review execution as one ambient `_running` boolean plus one ambient `_review_runner`
- replace that global in-flight assumption with a single active-review handle/controller abstraction that owns:
  - the current review job identity
  - cancel signaling
  - progress/event subscription
  - the runner or execution-state reference needed for Results-tab finalize behavior

This is the narrowest behavior seam that moves the codebase toward queueing without prematurely building persistence, multi-job UI, or scheduler policy.

## Why This Seam First

The current codebase already has the headless execution pieces Milestone 1 needs underneath it:

- `ReviewExecutionService` runs one job headlessly
- `ReviewJob` and `ReviewExecutionResult` already model execution lifecycle
- `ReviewRunnerState` already owns active-versus-staged session/report state inside the compatibility facade

But the GUI still hard-codes a single active review at the application layer:

- `src/aicodereviewer/gui/app.py` stores one `_running` flag and one `_review_runner`
- `src/aicodereviewer/gui/review_mixin.py` gates Start/Dry Run on `_running`
- `src/aicodereviewer/gui/review_mixin.py` cancellation targets one ambient `_cancel_event` and backend client
- `src/aicodereviewer/gui/results_mixin.py` finalize/report flows still assume one active runner binding for the whole app session

That means the next scheduler-friendly boundary is not inside `AppRunner`; it is between GUI widget state and review execution ownership.

## Scope For The First Milestone 1 Slice

Keep the first slice compatibility-first and behavior-preserving.

In scope:

- introduce one active-review controller/handle abstraction for the GUI
- route review start, progress, cancellation, and completion through that abstraction
- ensure Results-tab finalize continues to bind to the correct active or restored session state
- preserve the existing single-active-review user experience for now

Out of scope for the first slice:

- persistent queue storage
- running multiple reviews at once in the GUI
- queue-management UI
- CLI job submission commands
- per-backend concurrency caps

## Acceptance Criteria For The First Slice

1. The GUI still behaves as a single-active-review application from the user's perspective.
2. `_running` is no longer the only source of truth for an in-flight review.
3. Cancel behavior targets the active review handle instead of a mix of ambient widget fields.
4. Results-tab finalize and session restore still work after the refactor.
5. Existing focused GUI workflow coverage stays green.

Status: complete.

## Candidate Implementation Shape

One pragmatic starting shape:

- add a small GUI-owned review handle/controller object beside the current mixins
- let that object own cancel state, active runner, and execution progress wiring
- make `ReviewTabMixin` submit work through the handle instead of directly toggling `_running`, `_cancel_event`, `_review_client`, and `_review_runner`
- keep the handle singular for now so the GUI behavior does not change yet

This creates a scheduler entry point later without forcing queue persistence into the first slice.

## Next Likely Seam

The next contained follow-up inside Milestone 1 has moved beyond runner API naming.

After the controller extraction, helper rename, test migration, Results-tab runner-helper deduplication, the removal of the class-level compatibility properties (`_review_runner`, `_review_client`, `_cancel_event`, `_ai_fix_running`, `_ai_fix_cancel_event`, `_health_check_backend`, `_health_check_timer`), the removal of `_legacy_compat_state`, the deletion of `_running` plus the empty `_sync_*_compatibility()` layer, the execution-model serialization rename, and the final removal of the old runner aliases and fallbacks, the live GUI/runtime path no longer uses the retired vocabulary.

The next refinement is to continue shrinking `gui/review_mixin.py` by deciding whether any remaining review-start and review-finish widget choreography belongs in a scheduler callback surface or should remain explicitly GUI-owned around the execution stack.

- decide whether the scheduler boundary should remain a thin lifecycle dispatcher for the single-active-review UX or become the first real queue-oriented submission surface for Milestone 1
- decide whether the new scheduler-owned `ReviewExecutionSubmission` ids should evolve into a queued/pending submission model or remain only an accepted-submission tracking seam for the current single-active-review UX

The current answer is now clearer:

- submission acceptance/queue state and actual-dispatch lifecycle belong in the scheduler
- elapsed-timer start belongs on scheduler `on_started` because it must reflect actual dispatch, not mere acceptance
- elapsed-timer rendering and stop/reset remain GUI-owned because they are Tk widget choreography, not scheduler policy
- queued submission state should stay internal until a later Milestone 1 UI slice; the current single-active-review UX still gates review starts via `_is_busy()`, so surfacing queue state now would expose behavior the user cannot actually exercise through the GUI yet

Visible queue behavior is now intentionally exposed in a minimal form:

- the Review tab now shows active and queued submissions through scheduler snapshots only
- queue targeting is owned by a small GUI abstraction instead of widget-local selection state
- cancellation from that panel routes through the scheduler boundary rather than reaching directly into active-review runtime state
- full reviews and dry runs should remain mixed in the same queue panel, but the scheduler snapshot/UI should carry a small type label so the user can distinguish them without fragmenting the queue UX into separate lists too early

The same rule applies to the existing GUI cancel button:

- once visible queue behavior is introduced, the button should route through `ReviewExecutionScheduler.cancel_submission(...)` instead of talking only to the active review controller
- for this slice, keep the bottom cancel button wired to the active review cancel path because its current semantics are still "cancel the active review"
- the queue panel now handles targeted submission cancellation explicitly, which avoids overloading the existing global cancel control before the broader queue UX is redesigned
- a later queue-focused UI slice can either retarget the bottom cancel button to the currently selected submission or keep it as an active-only control, but that should be an explicit UX choice rather than an incidental routing change

That keeps the next step focused on scheduler-facing behavior while treating the versioned session payload as the stable restore boundary.

## Files Likely Involved

- `src/aicodereviewer/gui/app.py`
- `src/aicodereviewer/gui/review_mixin.py`
- `src/aicodereviewer/gui/results_mixin.py`
- possibly a new GUI support module for the handle/controller abstraction
- focused tests in `tests/test_gui_workflows.py` and orchestration-adjacent tests only if behavior surfaces change

## Validation Target

Minimum focused slice after the first Milestone 1 change:

- `tests/test_gui_workflows.py`
- `tests/test_results_session.py`
- `tests/test_orchestration.py`

Broader targeted regression if the slice changes shared execution ownership:

- `tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py`

## Resume Prompt

Resume from `docs/handoffs/milestone-1-queue-kickoff-2026-04-03.md`. Milestone 0 execution/session extraction is complete enough to stop at its current orchestration boundary. Milestone 1 should begin with a narrow GUI-side scheduling seam: replace the app-wide `_running` / `_review_runner` assumption with a single active-review handle/controller that owns cancel state, execution progress wiring, and the runner reference needed for Results-tab finalize behavior, while preserving the existing single-active-review UX and validating on the focused GUI/session/orchestration test slice first.
