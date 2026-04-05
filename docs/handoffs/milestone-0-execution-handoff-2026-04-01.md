# Milestone 0 Execution Handoff

Date: 2026-04-01
Repository: AICodeReviewer
Scope: Platform-extensibility Milestone 0 core extraction and compatibility migration

Companion chronology:

- `docs/handoffs/milestone-0-execution-chronology-2026-04-01.md`

## Resume Intent

Continue the Milestone 0 execution-core migration from the current compatibility-first state.

If you want a more literal transcript-style narrative of the recent work instead of this engineering summary, read:

- `docs/handoffs/milestone-0-execution-chronology-2026-04-01.md`

Standing user directive during this work:

- Continue with what you think is correct.

Primary architectural goal:

- move orchestration behavior out of `AppRunner` into typed execution abstractions while preserving current CLI and GUI behavior.

## Current State

The repository now has a typed execution core and registry layer in place, with `AppRunner` acting as a compatibility facade.

Typed execution pieces already added:

- `src/aicodereviewer/execution/models.py`
- `src/aicodereviewer/execution/events.py`
- `src/aicodereviewer/execution/service.py`
- `src/aicodereviewer/execution/__init__.py`

Registry pieces already added:

- `src/aicodereviewer/registries/backend_registry.py`
- `src/aicodereviewer/registries/review_registry.py`
- `src/aicodereviewer/registries/__init__.py`

Key behavior already migrated into `ReviewExecutionService`:

- semantic request validation
- job creation
- scan and issue collection
- typed event emission
- deferred report generation
- interactive CLI completion
- accurate job lifecycle transitions

`AppRunner` currently exposes both typed and compatibility state:

- `last_execution`
- `last_job`
- `execution_summary`
- `serialized_report_context`
- `pending_issues`

The old private compatibility mirrors have now been removed because the repo no longer has production callers that depend on them.

## Completed Work In This Session

Earlier completed work in this branch of the refactor:

1. Added platform-extensibility spec and Milestone 0 design docs.
2. Added backend and review registries.
3. Added typed execution models, typed execution events, and `ReviewExecutionService`.
4. Refactored `AppRunner` into a compatibility wrapper over the execution service.
5. Moved GUI review execution to typed event sinks for Tk-safe progress updates.
6. Moved CLI tool-mode to prefer typed `last_execution` when available.
7. Moved report generation through the execution service.
8. Moved semantic request validation into the execution layer.
9. Moved interactive CLI resolution into the execution service.
10. Corrected typed lifecycle semantics so `issues_found` no longer marks a job completed too early.
11. Stabilized GUI workflow tests by suppressing leaked popup-local Tk callbacks in testing mode.
12. Restored typed pending execution state when reloading GUI sessions that include saved issues.
13. Fixed stale AppRunner state when pending report metadata is restored without an issue list.
14. Migrated in-repo GUI and session tests to the public `serialized_report_context` surface.
15. Migrated CLI tool mode off direct `private execution-summary mirror` reads onto the public `execution_summary` surface.
16. Removed the direct `private report-context mirror` fallback from GUI results handling now that in-repo callers use the public property.
17. Made `AppRunner` public compatibility properties prefer typed state and pending context over the private compatibility mirrors.
18. Made `AppRunner.pending_issues` prefer typed execution or typed pending context over the private `_pending_issues` mirror.
19. Centralized AppRunner compatibility mirror synchronization into one helper.
20. Removed the now-unused `private execution-summary helper` helper after compatibility sync was centralized.
21. Extracted pending-context replacement into one helper so metadata restore clears active execution state through a single path.
22. Extracted restored-session execution rebuilding into one helper so metadata restore with saved issues reconstructs typed execution state through a single path.
23. Moved legacy pending-report metadata translation onto `PendingReportContext` and reset GUI-test logging state so the targeted slice stays stable after CLI capture tests.
24. Moved restored-session request and result reconstruction further into the execution models so `AppRunner` no longer hand-builds those typed objects.
25. Moved restored-session `ReviewJob` reconstruction into the execution models so `AppRunner` no longer hand-builds the synthetic GUI-finalize job either.
26. Moved request-to-pending-context translation onto `ReviewRequest` so the execution service no longer hand-builds deferred report metadata either.
27. Moved the report-written result transition onto `ReviewExecutionResult` so the execution service no longer hand-builds updated report results either.
28. Centralized typed-first report-context resolution inside `AppRunner` and moved `ReviewJob` terminal mutations onto the model so orchestration and service code keep shedding compatibility-specific branching and field mutation.
29. Moved the remaining `ReviewJob` lifecycle transition and pending-result mechanics onto the model, and stopped `AppRunner` public compatibility properties from reading stale private mirrors when no typed state exists.
30. Removed the now-unused private compatibility mirrors from `AppRunner` entirely and collapsed restored-session reconstruction into a single `ReviewJob.from_pending_context(...)` model helper.
31. Routed the remaining deferred-context report build/write fallback in `AppRunner` through a synthetic typed job and `ReviewExecutionService`, removing the last direct report-writing branch from orchestration.
32. Extracted deferred report staging into a typed `DeferredReportState` model so `AppRunner` no longer stores raw pending report metadata as a special-case execution concept.
33. Added a typed `deferred_report_state` AppRunner surface and moved the in-repo GUI session-restore path onto that typed API instead of the legacy metadata setter.
34. Added a typed `ReviewSessionState` model so GUI save/load now round-trips session payloads through execution models instead of ad hoc JSON parsing and assembly in the GUI mixin.
35. Collapsed the remaining AppRunner pending staging branch onto `ReviewSessionState` so the facade now carries one typed session staging abstraction internally instead of a separate `_pending_report_state` slot.
36. Moved live execution-to-session conversion onto `ReviewExecutionResult` so `AppRunner` no longer rebuilds typed session state from `last_execution` inline.
37. Removed the redundant AppRunner report-context preflight helper so pending report building now relies directly on typed pending-job reconstruction.
38. Moved session-state backend lookup and empty-state checks onto `ReviewSessionState` so callers no longer have to unwrap nested deferred-report fields for those decisions.
39. Moved legacy `report_context + issues` session assembly onto `ReviewSessionState` so callers no longer rebuild typed session wrappers from raw metadata.
40. Moved restored pending execution-result reconstruction onto typed deferred/session models so `AppRunner` no longer reassembles that result shape itself during session restore.
41. Moved active-versus-pending precedence and compatibility-surface derivation into a typed runner-state model so `AppRunner` no longer owns that merge logic directly.
42. Moved restore entry-point branching for legacy report metadata, deferred report state, and full session state onto the typed runner-state model so `AppRunner` now forwards those restore inputs instead of deciding the reconstruction path itself.
43. Reassessed `AppRunner.run()` and stopped extracting at that boundary; the remaining body is now primarily top-level orchestration and public compatibility shape rather than duplicated state reconstruction.
44. Normalized Milestone 0 naming and current-state docs around `ReviewRunnerState.staged_session_state`, leaving old `_pending_session_state` wording only in chronology entries where it is historically accurate.

## Most Recent Work

The latest concrete fixes were compatibility-surface cleanup steps around pending report metadata, legacy run state, deferred issues, public-property source of truth, and the internal synchronization of compatibility mirrors.

Problems that were found:

- test scaffolding and one remaining GUI helper still reached into `private report-context mirror` directly even though the public `serialized_report_context` property existed.
- CLI tool mode still had a direct fallback to `private execution-summary mirror` instead of stopping at the public `execution_summary` surface.
- `AppRunner` public compatibility properties still returned private mirror state directly even when newer typed execution or pending-context state existed.
- `pending_issues` could still fall through to a stale `_pending_issues` mirror when typed pending context existed without a live execution result.
- compatibility mirror writes were still duplicated across multiple branches, which made future cleanup riskier and easier to drift.
- `private execution-summary helper` remained as a dead helper after mirror synchronization had been centralized.
- `restore_serialized_report_context(...)` still open-coded the same pending-context replacement and active-execution clearing sequence in more than one branch.
- `restore_serialized_report_context(...)` still open-coded the synthetic restored execution rebuild when saved issues were present.
- legacy pending-report metadata translation still lived inline in `AppRunner` instead of beside `PendingReportContext.to_legacy_dict()`.
- GUI workflow tests could inherit closed root logging streams from earlier CLI `capsys` coverage, which destabilized the combined targeted slice.
- restored-session `ReviewRequest` and `ReviewExecutionResult` assembly still lived inline in `AppRunner` instead of beside the execution models that own those types.
- restored-session `ReviewJob` assembly still lived inline in `AppRunner` instead of beside the execution models that own that typed state.
- request-to-pending-context translation still lived inline in `ReviewExecutionService` instead of beside the `ReviewRequest` model that owns that source data.
- report-written result reconstruction still lived inline in `ReviewExecutionService` instead of beside the `ReviewExecutionResult` model that owns that state shape.
- `AppRunner` still had multiple report-context read paths instead of one typed-first helper, which left room for stale pending-context drift in compatibility reads.
- `ReviewExecutionService` still open-coded `ReviewJob` completion and failure field mutations instead of letting the job model own those terminal state updates.
- `ReviewExecutionService` still owned the non-terminal `ReviewJob` state and start-timestamp mutation path, so the lifecycle boundary between service and model was still split.
- `AppRunner` public compatibility properties still fell back to private mirror reads when no typed state was present, which left stale mirror data observable through the public facade.
- `AppRunner` still retained three private mirror fields and a dedicated synchronization helper even though in-repo production code no longer consumed those compatibility copies.
- restored-session reconstruction in `AppRunner` still required a two-step result-plus-job rebuild even after the underlying pieces had moved into the execution models.
- `AppRunner.build_report(...)` and `generate_report(...)` still bypassed the execution service when only deferred pending context was present, leaving one report-generation branch outside the typed service path.
- `AppRunner` still owned the remaining deferred-report staging concept as a raw `_pending_report_context` field instead of a typed execution model.
- in-repo session restore still depended on the legacy `restore_serialized_report_context(...)` compatibility wrapper even after deferred staging had moved into a typed model.
- GUI session save/load still treated the full session payload as loose JSON and open-coded issue serialization / datetime parsing in `results_mixin` instead of using a typed execution/session model.

Fixes applied:

- GUI workflow and results-session tests were updated to expose and assert `serialized_report_context` through the public property.
- CLI tool mode in `main.py` was updated to prefer `last_execution`, then `execution_summary`, without reading `private execution-summary mirror` directly.
- `ResultsTabMixin._get_runner_report_context()` was simplified to read only `serialized_report_context`.
- `AppRunner.execution_summary` now derives from `last_execution` first, and `serialized_report_context` now derives from the typed pending report context first.
- new orchestration tests were added to prove stale private mirrors do not override typed public state.
- `AppRunner.pending_issues` now resolves from `last_execution` first and otherwise returns `[]` when only typed pending context exists, instead of leaking stale `_pending_issues` data.
- another orchestration test was added to prove stale deferred-issue mirrors do not override typed pending context.
- compatibility mirror writes are now centralized in `_sync_compatibility_mirrors()`, so `restore_serialized_report_context(...)` and `_set_execution_result(...)` update typed state first and then synchronize the legacy copies in one place.
- another orchestration test was added to prove the private compatibility mirrors remain aligned after restoring pending metadata without issues.
- the obsolete `private execution-summary helper` helper was removed once `_sync_compatibility_mirrors()` became the only mirror-update path.
- pending-context replacement is now routed through `_replace_pending_context(...)`, so metadata restore no longer open-codes active-execution clearing.
- another orchestration test was added to prove clearing pending metadata also clears the private mirrors after pending context had been set.
- restored-session execution rebuilding is now routed through `_restore_execution_from_pending_context(...)`, so metadata restore with saved issues no longer open-codes synthetic request/result/job reconstruction.
- another orchestration test was added to prove restoring pending metadata with saved issues rebuilds typed execution and job state correctly.
- `PendingReportContext.from_legacy_dict(...)` was added so legacy metadata translation now lives beside `to_legacy_dict()`, and `AppRunner.restore_serialized_report_context(...)` now uses that model helper.
- direct execution-model coverage was added to prove pending report metadata round-trips through the new model helper.
- the GUI app fixture now resets root logging before each app instance so GUI workflow tests do not inherit closed CLI capture streams during the targeted slice.
- `PendingReportContext.to_review_request()` was added so restored-session request reconstruction now lives with the pending metadata model.
- `ReviewExecutionResult.from_pending_context(...)` was added so restored-session result reconstruction now lives with the execution result model.
- `AppRunner._restore_execution_from_pending_context(...)` now coordinates the restore path instead of rebuilding those typed objects field by field.
- direct execution-model coverage was added for the new request/result restore helpers.
- `ReviewJob.from_pending_context_result(...)` was added so restored-session job reconstruction now also lives in the execution models.
- `AppRunner._restore_execution_from_pending_context(...)` now coordinates the full restored-session typed state without hand-building any of the synthetic request/result/job objects.
- direct execution-model coverage was added for the restored-session job helper.
- `ReviewRequest.to_pending_report_context(...)` was added so issues-found report-context reconstruction now also lives on the request model.
- `ReviewExecutionService.execute_job(...)` now uses that helper instead of hand-building `PendingReportContext` inline.
- direct execution-model coverage was added for the new request helper.
- `ReviewExecutionResult.with_report_output(...)` was added so report-written result reconstruction now also lives on the execution result model.
- `ReviewExecutionService.generate_report(...)` now uses that helper instead of hand-building the updated report result inline.
- direct execution-model coverage was added for the new report-output helper.
- `AppRunner` now routes report-context reads and mirror synchronization through `_current_report_context()`, so typed execution report context wins over stale pending context inside the facade.
- `ReviewJob.complete_with_result(...)` and `ReviewJob.fail_with_error(...)` were added so terminal job mutations now live on the job model.
- `ReviewExecutionService._complete_job(...)` and `_fail_job(...)` now use those helpers instead of mutating job fields inline.
- new execution-model and orchestration regression coverage was added for the typed-first report-context helper and the job completion/failure helpers.
- `ReviewJob.transition_to(...)` and `ReviewJob.set_pending_result(...)` were added so job state changes, start-time stamping, and the awaiting-GUI-finalize result handoff now live on the model too.
- `ReviewExecutionService` now delegates all job lifecycle mutation to `ReviewJob`, emitting events from the returned state transitions instead of mutating `state`, `started_at`, or pending results inline.
- `AppRunner.execution_summary`, `serialized_report_context`, and `pending_issues` now return only typed-derived public state.
- the unused private mirror fields and `_sync_compatibility_mirrors()` were removed from `AppRunner` once the repo-level caller audit showed nothing outside tests still depended on them.
- `ReviewJob.from_pending_context(...)` was added so restored-session GUI-finalize reconstruction now lives in one model helper instead of being coordinated as separate result and job rebuild steps inside `AppRunner`.
- new regression coverage was added for the one-step restored-session job helper and for the absence of the removed private mirrors.
- `AppRunner.build_report(...)` and `generate_report(...)` now synthesize a typed pending job through `_job_from_pending_context(...)` and route deferred-context report generation through `ReviewExecutionService` instead of calling the reporter directly.
- new orchestration regression coverage was added for generating a report from restored pending metadata without a pre-existing job.
- `DeferredReportState` was added to the execution models so deferred report metadata now has a typed home instead of living as a raw orchestration-only context field.
- `AppRunner` now stores `_pending_report_state` and derives synthetic pending jobs from that typed model via `_job_from_pending_state(...)`.
- direct execution-model coverage was added for the new deferred-state round-trip and job-rebuild helper.
- `AppRunner.deferred_report_state` and `AppRunner.restore_deferred_report_state(...)` were added as typed restore/finalize surfaces, while `restore_serialized_report_context(...)` remains as a thin legacy wrapper.
- `ResultsTabMixin._restore_session_report_context(...)` now restores deferred session state through the typed AppRunner surface instead of the legacy metadata wrapper.
- new orchestration regression coverage was added for the typed AppRunner restore API.
- `ReviewSessionState` was added to the execution models so saved GUI sessions now have a typed home that owns issue serialization, `resolved_at` parsing, and deferred-report metadata round-tripping.
- `AppRunner.restore_session_state(...)` was added so saved GUI sessions can be restored through a typed execution/session abstraction instead of loose `issues + meta` arguments.
- `ResultsTabMixin._save_session()` and `_load_session()` now serialize and parse sessions through `ReviewSessionState` while preserving the existing JSON structure on disk.
- new execution-model and orchestration coverage was added for the new typed session-state model and restore surface.
- `AppRunner.session_state` was added so the facade now exposes the current typed saved-session state directly instead of forcing callers to rebuild it from legacy compatibility metadata.
- `ResultsTabMixin._get_session_state()` now prefers `runner.session_state`, and `_load_session()` restores parsed sessions through a new `_restore_session_state(...)` helper instead of converting typed state back through legacy report context payloads.
- new orchestration and session regression coverage was added for the typed session-state facade surface and the updated in-repo caller behavior.
- `ReviewSessionState.with_issues(...)` and `ReviewSessionState.to_review_job(...)` were added so saved-session issue replacement and synthetic GUI-finalize job reconstruction now live on the typed session model too.
- `DeferredReportState.to_session_state(...)` was added so deferred report state can wrap itself as a saved-session abstraction instead of relying on ad hoc callers to assemble `ReviewSessionState` manually.
- `AppRunner.restore_session_state(...)` and `restore_deferred_report_state(...)` now delegate through those model helpers instead of coordinating restored execution rebuilds through a facade-owned `_restore_execution_from_pending_context(...)` helper.
- `ResultsTabMixin` now uses the new typed session helpers when saving or restoring session state instead of rebuilding typed session wrappers inline.
- new execution-model and orchestration regression coverage was added for the model-owned session restore path and for clearing runner state when a session restore no longer carries deferred report state.
- Non-live restore/finalize state first collapsed into one typed saved-session abstraction, and that seam now lives behind `ReviewRunnerState` as staged deferred-session state rather than facade-owned pending-state branching.
- orchestration coverage was updated to prove live execution state still outranks stale staged session state when the public compatibility properties are read.
- `ReviewExecutionResult.to_session_state()` was added so live deferred execution state converts to typed saved-session state in the model layer instead of in facade-owned session-state reconstruction logic.
- direct execution-model coverage was added for the new execution-to-session helper.
- `AppRunner.build_report()` now trusts `_job_from_pending_state(...)` directly instead of separately preflighting deferred report context through `_current_report_context()`, and the redundant helper has been removed.
- orchestration coverage now includes a direct guard that `build_report()` returns `None` when no pending finalize state exists.
- `ReviewSessionState.backend_name` and `ReviewSessionState.is_empty()` were added so the session model now owns backend resolution and empty-state checks.
- `AppRunner` and `ResultsTabMixin` now use those helpers instead of reaching into `session_state.deferred_report_state.context.backend` or open-coding empty-session checks.
- `ReviewSessionState.from_report_context(...)` was added so legacy deferred report context plus issue lists now convert to typed session state in one model-owned helper.
- `AppRunner.restore_serialized_report_context(...)`, `ResultsTabMixin`, and session-test scaffolding now use that helper instead of rebuilding `DeferredReportState` and then wrapping it manually.
- `DeferredReportState.to_execution_result(...)` and `ReviewSessionState.to_execution_result()` were added so restored GUI session state can rebuild a typed pending execution result directly from model-owned helpers.
- `ReviewSessionState.to_review_job()` now reuses that typed execution result, and `AppRunner.restore_session_state(...)` now restores active execution state directly from the reconstructed job result instead of owning that result assembly logic.
- `ReviewRunnerState` was added so the typed layer now owns active execution state, staged deferred-session state, precedence resolution, and compatibility-surface derivation (`execution_summary`, pending report metadata, deferred state, pending issues, and synthetic pending jobs).
- `AppRunner` now delegates execution/session state transitions and compatibility-property reads through `ReviewRunnerState` instead of maintaining parallel `_last_execution`, `_last_job`, and older facade-era session merge logic itself.
- `ReviewRunnerState.from_report_context(...)`, `ReviewRunnerState.from_deferred_report_state(...)`, and `ReviewRunnerState.from_session_state(...)` now own restore-time branching from legacy report context, typed deferred state, and saved session state.
- `AppRunner.restore_serialized_report_context(...)`, `restore_deferred_report_state(...)`, and `restore_session_state(...)` now forward directly into those typed runner-state constructors instead of choosing the reconstruction path in the facade.
- The remaining `AppRunner.run()` body was re-audited and left in place because it now primarily handles backup cleanup, localized logging, sink wiring, and top-level interactive/non-interactive orchestration.
- The now-unused `_replace_pending_session_state(...)` helper was removed as follow-up dead-path cleanup after `ReviewRunnerState` took over restore branching.
- `ReviewRunnerState` now uses `staged_session_state` / `with_staged_session_state(...)` so the typed layer no longer carries the old pending-session staging vocabulary forward.
- Current-state handoff summaries were updated to describe the modern `ReviewRunnerState` boundary, while older `_pending_session_state` and `_current_session_state()` references remain only where chronology accuracy requires them.

Files changed for that latest step:

- `src/aicodereviewer/main.py`
- `src/aicodereviewer/gui/results_mixin.py`
- `src/aicodereviewer/orchestration.py`
- `src/aicodereviewer/execution/models.py`
- `tests/test_cli_tool_mode.py`
- `tests/test_execution_service.py`
- `tests/test_gui_workflows.py`
- `tests/test_results_session.py`
- `tests/test_orchestration.py`

Files changed for the latest follow-up step:

- `src/aicodereviewer/gui/results_mixin.py`
- `src/aicodereviewer/orchestration.py`
- `tests/test_results_session.py`
- `tests/test_orchestration.py`

Files changed for the latest session-restore ownership step:

- `src/aicodereviewer/execution/models.py`
- `src/aicodereviewer/gui/results_mixin.py`
- `src/aicodereviewer/orchestration.py`
- `tests/test_execution_service.py`
- `tests/test_results_session.py`
- `tests/test_orchestration.py`

Files changed for the latest session-centric staging cleanup:

- `src/aicodereviewer/orchestration.py`
- `tests/test_orchestration.py`

Files changed for the latest execution-to-session helper extraction:

- `src/aicodereviewer/execution/models.py`
- `src/aicodereviewer/orchestration.py`
- `tests/test_execution_service.py`

Files changed for the latest report-context helper removal:

- `src/aicodereviewer/orchestration.py`
- `tests/test_orchestration.py`

Files changed for the latest session-state helper extraction:

- `src/aicodereviewer/execution/models.py`
- `src/aicodereviewer/orchestration.py`
- `src/aicodereviewer/gui/results_mixin.py`
- `tests/test_execution_service.py`

Files changed for the latest session-state factory extraction:

- `src/aicodereviewer/execution/models.py`
- `src/aicodereviewer/orchestration.py`
- `src/aicodereviewer/gui/results_mixin.py`
- `tests/test_execution_service.py`
- `tests/test_results_session.py`

Files changed for the latest restored execution-result extraction:

- `src/aicodereviewer/execution/models.py`
- `src/aicodereviewer/orchestration.py`
- `tests/test_execution_service.py`

Files changed for the latest runner-state extraction:

- `src/aicodereviewer/execution/models.py`
- `src/aicodereviewer/execution/__init__.py`
- `src/aicodereviewer/orchestration.py`
- `tests/test_execution_service.py`
- `tests/test_orchestration.py`

Files changed for the latest runner-state restore-constructor extraction:

- `src/aicodereviewer/execution/models.py`
- `src/aicodereviewer/orchestration.py`
- `tests/test_execution_service.py`

Files changed for the latest AppRunner reassessment and dead-path cleanup:

- `src/aicodereviewer/orchestration.py`

Files changed for the Milestone 0 naming/docs consistency pass:

- `src/aicodereviewer/execution/models.py`
- `tests/test_execution_service.py`
- `tests/test_orchestration.py`
- `docs/handoffs/milestone-0-execution-handoff-2026-04-01.md`
- `docs/handoffs/milestone-0-execution-chronology-2026-04-01.md`

## Recent Chat / Work History

This is the latest sequence that matters for resuming:

1. Restored-session typed state was implemented so saved GUI sessions now rebuild:
   - `last_execution.status == "issues_found"`
   - `last_job.state == "awaiting_gui_finalize"`
2. That change was validated with focused session and GUI workflow tests.
3. After that, another AppRunner consistency seam was identified:
   - restoring metadata without issues left stale typed state from earlier runs.
4. `AppRunner.restore_serialized_report_context(...)` was patched to clear stale execution and pending issue state when no issue list is provided.
5. Regression coverage was added in `tests/test_orchestration.py`.
6. Focused and broader targeted regression slices both passed after the fix.
7. GUI workflow and session tests were migrated to `serialized_report_context`.
8. CLI tool mode was migrated off direct `private execution-summary mirror` reads.
9. The remaining direct GUI fallback to `private report-context mirror` was removed from `results_mixin`.
10. Focused and broader targeted regression slices both passed again after those compatibility cleanup steps.
11. `AppRunner` public compatibility properties were updated to prefer typed state over private mirrors.
12. Source-of-truth regression coverage was added in `tests/test_orchestration.py`.
13. Focused orchestration validation and the broader targeted slice both passed after that change.
14. `pending_issues` was updated to prefer typed execution or typed pending context over the legacy mirror.
15. Additional orchestration regression coverage was added for stale `_pending_issues` data.
16. Focused orchestration validation and the broader targeted slice both passed again after that change.
17. Legacy mirror writes were centralized through `_sync_compatibility_mirrors()`.
18. Additional orchestration regression coverage was added for mirror alignment after metadata restore.
19. Focused orchestration validation and the broader targeted slice both passed again after that refactor.
20. The dead `private execution-summary helper` helper was removed.
21. The broader targeted slice stayed green after that dead-code cleanup.
22. Pending-context replacement was extracted into `_replace_pending_context(...)`.
23. Additional orchestration regression coverage was added for private-mirror clearing after pending-context reset.
24. Focused orchestration validation and the broader targeted slice both passed again after that helper extraction.
25. Restored-session execution rebuilding was extracted into `_restore_execution_from_pending_context(...)`.
26. Additional orchestration regression coverage was added for restored typed execution and job state after metadata reload with saved issues.
27. Focused orchestration validation and the broader targeted slice both passed again after that helper extraction.
28. Legacy pending-report metadata translation was moved onto `PendingReportContext.from_legacy_dict(...)`, and `AppRunner` stopped open-coding that compatibility mapping.
29. Direct execution-model regression coverage was added for the legacy metadata round trip.
30. A cross-module targeted-slice failure then surfaced in GUI workflows because earlier CLI tests left root logging bound to closed capture streams.
31. The GUI app fixture was updated to reset root logging before each app instance, which eliminated that cross-module instability.
32. The targeted regression slice passed again after the model-layer cleanup and GUI fixture stabilization.
33. Restored-session request reconstruction was moved into `PendingReportContext.to_review_request()`.
34. Restored-session result reconstruction was moved into `ReviewExecutionResult.from_pending_context(...)`.
35. Direct execution-model coverage was added for those helpers, and `AppRunner` stopped hand-building the restored typed request/result pair.
36. Focused execution/orchestration validation and the broader targeted slice both passed again after that model-layer extraction.
37. Restored-session job reconstruction was moved into `ReviewJob.from_pending_context_result(...)`.
38. Direct execution-model coverage was added for that helper, and `AppRunner` stopped hand-building the restored synthetic GUI-finalize job.
39. Focused execution/orchestration validation and the broader targeted slice both passed again after that model-layer extraction.
40. Request-to-pending-context translation was moved into `ReviewRequest.to_pending_report_context(...)`.
41. Direct execution-model coverage was added for that helper, and `ReviewExecutionService` stopped hand-building `PendingReportContext` inline.
42. Focused execution/orchestration validation and the broader targeted slice both passed again after that model-layer extraction.
43. Report-written result reconstruction was moved into `ReviewExecutionResult.with_report_output(...)`.
44. Direct execution-model coverage was added for that helper, and `ReviewExecutionService.generate_report(...)` stopped hand-building the updated report result inline.
45. Focused execution/orchestration validation and the broader targeted slice both passed again after that model-layer extraction.
46. `AppRunner` report-context resolution was centralized into `_current_report_context()` so public compatibility reads and mirror sync now follow one typed-first path.
47. `ReviewJob` terminal state mutations were moved into `complete_with_result(...)` and `fail_with_error(...)`.
48. Additional regression coverage was added for both changes, including a guard that `serialized_report_context` prefers `last_execution.report_context` over stale pending context.
49. Focused execution/orchestration validation and the broader targeted slice both passed again after those refactors.
50. `ReviewJob.transition_to(...)` was added so state transitions and start-time stamping now live on the model instead of inside `ReviewExecutionService._set_job_state(...)`.
51. `ReviewJob.set_pending_result(...)` was added so the issues-found handoff into `awaiting_gui_finalize` now lives on the model too.
52. `ReviewExecutionService` was updated to emit job state events from model-owned transitions for the issues-found, completed, and failed paths.
53. `AppRunner.execution_summary`, `serialized_report_context`, and `pending_issues` were tightened further so the public compatibility facade never reads stale private mirrors when typed state is absent.
54. Additional regression coverage was added for the new `ReviewJob` transition helpers and for the stricter public-property contract that ignores stale private mirrors without typed state.
55. Focused execution/orchestration validation and the broader targeted slice both passed again after those refactors.
56. A repo-wide caller audit then confirmed the old private mirrors were no longer used by production code outside `AppRunner` itself.
57. `AppRunner` dropped `private execution-summary mirror`, `private report-context mirror`, `_pending_issues`, and `_sync_compatibility_mirrors()` entirely because those compatibility copies no longer had in-repo consumers.
58. `ReviewJob.from_pending_context(...)` was added so restored-session reconstruction now happens through one execution-model helper instead of separate result and job rebuild steps.
59. `AppRunner._restore_execution_from_pending_context(...)` now delegates that reconstruction to the new single helper and only persists the returned typed job/result state.
60. Additional regression coverage was added for the one-step restored-session helper and for the removed private-mirror attributes.
61. Focused execution/orchestration validation and the broader targeted slice both passed again after those refactors.
62. The last orchestration-only report-generation branch was then removed:
   - `AppRunner.build_report(...)` now synthesizes a pending typed job and delegates to `ReviewExecutionService.build_report(...)` when only deferred context exists
   - `AppRunner.generate_report(...)` now does the same for `ReviewExecutionService.generate_report(...)`
   - the direct `generate_review_report(...)` fallback in orchestration is gone
63. Additional orchestration regression coverage was added for generating a report from restored pending metadata without an already-restored job.
64. Focused execution/orchestration validation and the broader targeted slice both passed again after that service-path unification.
65. The remaining deferred staging concept was then moved into the execution models:
   - `DeferredReportState` was added as a typed wrapper around `PendingReportContext`
   - `AppRunner` now stores `_pending_report_state` instead of `_pending_report_context`
   - `DeferredReportState.from_legacy_dict(...)`, `to_legacy_dict(...)`, and `to_review_job(...)` now own the deferred restore/finalize mapping
66. Direct execution-model coverage was added for the new deferred-state helper, and orchestration regression coverage was updated to use the typed deferred state instead of mutating raw pending context.
67. Focused execution/orchestration validation and the broader targeted slice both passed again after the deferred-state extraction.
68. The next cleanup added a typed AppRunner restore surface on top of that model:
   - `deferred_report_state` now exposes the current typed deferred state
   - `restore_deferred_report_state(...)` now restores deferred session state directly from that typed model
   - `restore_serialized_report_context(...)` remains only as a legacy wrapper that converts dict metadata into `DeferredReportState`
69. The in-repo GUI session restore path in `results_mixin` was moved to the new typed AppRunner surface.
70. Additional orchestration coverage was added for the typed AppRunner restore API.
71. Focused execution/orchestration/session validation and the broader targeted slice both passed again after that typed-surface migration.
72. The next cleanup moved the full saved-session payload into the execution models:
   - `ReviewSessionState` was added as a typed wrapper around `issues + DeferredReportState`
   - the model now owns issue serialization, `resolved_at` parsing, and legacy session-payload round-tripping
   - `AppRunner.restore_session_state(...)` was added so typed session restore now has a dedicated facade entry point
73. `ResultsTabMixin._save_session()` and `_load_session()` were updated to use `ReviewSessionState` while keeping the on-disk JSON shape unchanged.
74. Additional execution-model and orchestration coverage was added for the typed session-state model and restore API.
75. Focused execution/orchestration/session validation and the broader targeted slice both passed again after the typed session-state extraction.
76. `AppRunner.session_state` was added so callers can read the current typed saved-session state directly from the compatibility facade.
77. `ResultsTabMixin._get_session_state()` was updated to prefer that typed facade surface, and `_load_session()` now restores parsed `ReviewSessionState` instances through `_restore_session_state(...)` instead of converting them back into legacy report context payloads first.
78. Additional orchestration and results-session regression coverage was added for the new `session_state` surface and for the updated dummy runner/session restore path.
79. Focused execution/orchestration/session validation and the broader targeted slice both passed again after that typed-session follow-up cleanup.
80. The next follow-up moved the last synthetic session-restore rebuild behavior further onto the typed models:
   - `ReviewSessionState.with_issues(...)` now owns replacing the active issue list on a saved-session payload
   - `ReviewSessionState.to_review_job(...)` now owns rebuilding the synthetic GUI-finalize job from saved session state
   - `DeferredReportState.to_session_state(...)` now owns wrapping deferred report state as a `ReviewSessionState`
81. `AppRunner.restore_session_state(...)` and `restore_deferred_report_state(...)` were then simplified to delegate through those model helpers instead of using a facade-owned `_restore_execution_from_pending_context(...)` rebuild step.
82. `ResultsTabMixin` was tightened around the same typed helpers:
   - `_get_session_state()` now uses `session_state.with_issues(...)` when the runner already exposes typed session state
   - the fallback paths now use `DeferredReportState.to_session_state(...)` instead of rebuilding `ReviewSessionState` inline
83. Additional execution-model and orchestration coverage was added for the model-owned session-restore helpers, including a guard that restoring a session without deferred report state clears runner state.
84. Focused execution/orchestration/session validation and the broader targeted slice both passed again after that session-restore ownership cleanup.
85. The next internal cleanup removed the last separate AppRunner pending-report staging slot:
   - `_pending_report_state` was replaced with `_pending_session_state`
   - `AppRunner.session_state`, `deferred_report_state`, `pending_issues`, and `_job_from_pending_state(...)` now all resolve through `_current_session_state()`
   - non-live restore/finalize state is now represented by one typed session abstraction instead of parallel deferred/session branches inside the facade
86. Orchestration coverage was updated for that cleanup:
   - the stale-fallback guard now seeds `_pending_session_state` instead of `_pending_report_state`
87. Validation after the session-centric staging cleanup was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `42 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `119 passed`
88. The next internal cleanup moved the live execution-to-session conversion onto the execution result model:
   - `ReviewExecutionResult.to_session_state()` was added
   - `AppRunner._current_session_state()` now delegates the `last_execution` conversion instead of rebuilding `ReviewSessionState` inline
89. Direct execution-model coverage was added for that helper:
   - one test verifies deferred execution state preserves issues and report context when converted into typed session state
90. Validation after the execution-to-session helper extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `43 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `120 passed`
91. The next internal cleanup removed the last redundant report-context preflight from the facade:
   - `AppRunner.build_report()` now relies directly on `_job_from_pending_state(...)` to determine whether deferred finalize state exists
   - the now-unused `_current_report_context()` helper was removed
92. Orchestration coverage was expanded for that cleanup:
   - one test verifies `build_report()` returns `None` when there is no pending finalize state at all
93. Validation after the report-context helper removal was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `44 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `121 passed`
94. The next internal cleanup moved simple session-state queries onto the model:
   - `ReviewSessionState.backend_name` was added so callers no longer need to unwrap `deferred_report_state.context.backend`
   - `ReviewSessionState.is_empty()` was added so callers no longer need to duplicate the empty-session check
95. `AppRunner` and the GUI restore path were simplified around those helpers:
   - `AppRunner.restore_session_state(...)` now uses `session_state.backend_name`
   - `AppRunner._current_session_state()` now uses `session_state.is_empty()`
   - `ResultsTabMixin._restore_session_state(...)` now uses `session_state.backend_name`
96. Direct execution-model coverage was added for the new session helpers.
97. Validation after the session-state helper extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `45 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `122 passed`
98. The next internal cleanup moved legacy report-context wrapping onto the session model:
   - `ReviewSessionState.from_report_context(...)` was added
   - `ReviewSessionState.from_legacy_dict(...)` now delegates its report-context reconstruction through that helper after parsing issues
99. The callers were then simplified around that helper:
   - `AppRunner.restore_serialized_report_context(...)` now builds typed session staging through `ReviewSessionState.from_report_context(...)`
   - `ResultsTabMixin._get_session_state()` and `_restore_session_report_context(...)` now use the same model-owned factory instead of rebuilding `DeferredReportState` and then wrapping it manually
   - session test scaffolding now seeds `session_state` through the same helper
100. Direct execution-model coverage was added for the new session-state factory.
101. Validation after the session-state factory extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `46 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `123 passed`
102. The next internal cleanup moved restored pending execution-result reconstruction onto typed deferred/session models:
   - `DeferredReportState.to_execution_result(...)` was added
   - `ReviewSessionState.to_execution_result()` was added and now owns pending execution-result reconstruction from saved-session state
103. The restore path then narrowed further:
   - `ReviewSessionState.to_review_job()` now reuses the typed execution result instead of rebuilding pending context inline
   - `AppRunner.restore_session_state(...)` now restores active execution state from the reconstructed job result instead of reassembling that result shape in the facade
104. Direct execution-model coverage was added for the new session-state execution-result helper.
105. Validation after the restored execution-result extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `47 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `124 passed`
106. The next internal cleanup moved active-versus-pending runner precedence into a typed runner-state model:
   - `ReviewRunnerState` was added to own `last_execution`, `last_job`, staged deferred-session state, and precedence resolution between active execution state and restored staged session state
   - the model now also owns compatibility-surface derivation for `execution_summary`, deferred report metadata, deferred report state, pending issues, and synthetic pending jobs
107. `AppRunner` was then narrowed to facade-only orchestration:
   - `AppRunner` now stores one `_runner_state` instead of maintaining parallel execution-versus-staged-session merge logic directly
   - execution/session transitions now run through `ReviewRunnerState.with_execution(...)` and `ReviewRunnerState.with_staged_session_state(...)`
   - `generate_report()` and `build_report()` now ask the typed runner state for synthetic pending jobs instead of rebuilding that lookup locally
108. Direct execution-model coverage was added for active-execution precedence over stale pending session state.
109. Validation after the runner-state extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `48 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `125 passed`
110. The next internal cleanup moved restore entry-point branching onto the typed runner-state model:
   - `ReviewRunnerState.from_report_context(...)` was added for legacy deferred report context restore inputs
   - `ReviewRunnerState.from_deferred_report_state(...)` was added for typed deferred restore inputs
   - `ReviewRunnerState.from_session_state(...)` was added for full saved-session restore inputs
111. `AppRunner` was then narrowed further around those typed constructors:
   - `restore_serialized_report_context(...)`, `restore_deferred_report_state(...)`, and `restore_session_state(...)` now forward directly into `ReviewRunnerState` constructors
   - empty-session normalization now also lives in the typed runner-state model instead of in facade restore helpers
112. Direct execution-model coverage was added for runner-state restore construction from legacy report metadata and full session state.
113. Validation after the runner-state restore-constructor extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `50 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `127 passed`
114. `AppRunner.run()` was then re-audited for one more non-cosmetic extraction seam.
115. That reassessment concluded the remaining body is now the intended Milestone 0 boundary:
   - backup cleanup remains orchestration-only
   - localized logging and dry-run/user-facing messaging remain facade concerns
   - sink wiring and the interactive versus GUI-finalize split remain top-level flow control rather than misplaced typed state reconstruction
116. Follow-up dead-path cleanup removed the now-unused `_replace_pending_session_state(...)` helper after `ReviewRunnerState` absorbed restore branching.
117. Validation after the AppRunner boundary reassessment and dead-path cleanup was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `50 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `127 passed`
118. A Milestone 0 naming/docs consistency pass then normalized the current typed runner-state terminology:
   - `ReviewRunnerState.pending_session_state` was renamed to `staged_session_state`
   - `ReviewRunnerState.with_pending_session_state(...)` was renamed to `with_staged_session_state(...)`
119. Current-state documentation was aligned with that rename:
   - current summaries now describe `ReviewRunnerState` as the source of staged deferred-session state
   - obsolete `_pending_session_state` wording was removed from current-state summaries and retained only in chronology/history entries where it remains historically accurate
120. Validation after the naming/docs consistency pass was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `50 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `127 passed`

## Latest Validation Results

Focused validation after the stale-state fix:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_orchestration.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `44 passed in 110.04s`

Broader targeted regression after the stale-state fix:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `93 passed, 1 skipped in 105.67s`

The skip is an existing GUI/Tk environment skip guard and not a new regression.

Latest focused validation after the public-surface cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_orchestration.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `44 passed in 99.22s`

Latest broader targeted regression after the public-surface cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `94 passed in 99.46s`

Latest focused validation after the model-owned transition and stale-mirror-read cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py
```

Result:

- `33 passed in 0.34s`

Latest broader targeted regression after the model-owned transition and stale-mirror-read cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `112 passed in 98.70s`

Latest focused validation after the mirror removal and one-step restore-helper cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py
```

Result:

- `32 passed in 0.32s`

Latest broader targeted regression after the mirror removal and one-step restore-helper cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `111 passed in 99.03s`

Latest focused validation after the deferred-context service-path unification:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_orchestration.py tests/test_execution_service.py
```

Result:

- `33 passed in 0.27s`

Latest broader targeted regression after the deferred-context service-path unification:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `112 passed in 98.71s`

Latest focused validation after the deferred-state model extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py
```

Result:

- `34 passed in 0.24s`

Latest broader targeted regression after the deferred-state model extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `113 passed in 98.80s`

Latest focused validation after the typed AppRunner deferred-state API migration:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_results_session.py
```

Result:

- `37 passed in 0.38s`

Latest broader targeted regression after the typed AppRunner deferred-state API migration:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `114 passed in 98.62s`

Latest focused validation after the typed session-state extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_results_session.py
```

Result:

- `39 passed in 0.30s`

Latest broader targeted regression after the typed session-state extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `116 passed in 99.01s`

Latest focused validation after the typed `session_state` facade follow-up:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_results_session.py
```

Result:

- `40 passed in 0.39s`

Latest broader targeted regression after the typed `session_state` facade follow-up:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `117 passed in 98.76s`

Latest focused validation after the model-owned session-restore follow-up:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_results_session.py
```

Result:

- `42 passed in 0.39s`

Latest broader targeted regression after the model-owned session-restore follow-up:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `119 passed in 98.84s`

Latest focused validation after the AppRunner source-of-truth cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_orchestration.py
```

Result:

- `10 passed in 0.19s`

Latest broader targeted regression after the AppRunner source-of-truth cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `96 passed in 99.66s`

Latest focused validation after the deferred-issues source-of-truth cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_orchestration.py
```

Result:

- `11 passed in 0.20s`

Latest broader targeted regression after the deferred-issues source-of-truth cleanup:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `97 passed in 99.95s`

Latest focused validation after the mirror-sync refactor:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_orchestration.py
```

Result:

- `12 passed in 0.20s`

Latest broader targeted regression after the mirror-sync refactor:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `98 passed in 99.43s`

Latest broader targeted regression after the dead-helper removal:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `98 passed in 99.44s`

Latest focused validation after the pending-context helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_orchestration.py
```

Result:

- `13 passed in 0.18s`

Latest broader targeted regression after the pending-context helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `99 passed in 101.43s`

Latest focused validation after the restored-session rebuild helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_orchestration.py
```

Result:

- `14 passed in 0.21s`

Latest broader targeted regression after the restored-session rebuild helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `100 passed in 101.85s`

Latest focused validation after the model-layer metadata conversion:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py
```

Result:

- `22 passed in 0.23s`

Latest broader targeted regression after the model-layer metadata conversion and GUI fixture logging reset:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `101 passed in 101.28s`

Latest focused validation after the restored-session model-helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py
```

Result:

- `24 passed in 0.26s`

Latest broader targeted regression after the restored-session model-helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `103 passed in 99.13s`

Latest focused validation after the restored-session job-helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py
```

Result:

- `25 passed in 0.25s`

Latest broader targeted regression after the restored-session job-helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `104 passed in 98.36s`

Latest focused validation after the request-to-pending-context helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py
```

Result:

- `26 passed in 0.28s`

Latest broader targeted regression after the request-to-pending-context helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `105 passed in 98.02s`

Latest focused validation after the report-output helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py
```

Result:

- `27 passed in 0.26s`

Latest broader targeted regression after the report-output helper extraction:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `106 passed in 98.58s`

Latest focused validation after the typed-first report-context and ReviewJob helper extractions:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py
```

Result:

- `30 passed in 0.28s`

Latest broader targeted regression after the typed-first report-context and ReviewJob helper extractions:

Command:

```powershell
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_execution_service.py tests/test_orchestration.py tests/test_cli_tool_mode.py tests/test_main_cli.py tests/test_results_session.py tests/test_gui_workflows.py
```

Result:

- `109 passed in 99.18s`

## Important Constraints Learned

1. Remove private compatibility scaffolding once a repo-wide caller audit shows that production code no longer depends on it.
2. `ReviewJob.state` must remain `awaiting_gui_finalize` after `issues_found`; only report-writing paths should end in `completed`.
3. GUI progress updates should continue to flow through typed execution events marshalled onto the Tk thread.
4. Popup-local Tk `after(...)` callbacks must be test-aware, or GUI workflow tests can fail later with stale Tcl callback errors.
5. `restore_serialized_report_context(...)` must clear stale typed state when restoring metadata without issues.
6. Public compatibility properties should stay typed-derived only; once typed state is the sole source of truth, private mirrors should not be reintroduced.
7. Deferred issue access should continue deriving from typed execution state only.
8. GUI workflow fixtures need to reset root logging after CLI `capsys` coverage, or combined slices can inherit closed capture streams and fail nondeterministically.
9. Restored-session reconstruction should stay in the execution models rather than regrowing field-by-field assembly inside `AppRunner`.
10. Request-to-pending-context translation should stay on typed models so execution services and facades do not rebuild compatibility payloads inline.
11. Report-written result reconstruction should stay on `ReviewExecutionResult` so the service coordinates transitions instead of reconstructing payloads inline.
12. Typed-first report-context reads inside `AppRunner` should flow through one helper so stale pending context cannot outrank live execution state in compatibility surfaces.
13. All `ReviewJob` lifecycle mutation should stay on the model so service code focuses on orchestration and event emission.

## Files Most Relevant To Continue From

- `src/aicodereviewer/orchestration.py`
- `src/aicodereviewer/execution/service.py`
- `src/aicodereviewer/gui/results_mixin.py`
- `src/aicodereviewer/gui/review_mixin.py`
- `tests/test_orchestration.py`
- `tests/test_results_session.py`
- `tests/test_gui_workflows.py`
- `tests/test_cli_tool_mode.py`

## Recommended Next Steps

Milestone 0 execution/session extraction is complete enough to stop thinning the facade further without a new behavior seam.

Recommended follow-on work:

1. Start a new milestone or a behavior-driven cleanup pass instead of continuing facade-thinning work.
2. If a future change touches execution/session restore behavior, treat `ReviewRunnerState` as the primary state boundary and validate on the standard targeted regression slice.

## Suggested Resume Prompt

Use this after restart if needed:

```text
Resume from docs/handoffs/milestone-0-execution-handoff-2026-04-01.md. Milestone 0 execution/session extraction is at a defensible stopping point in AICodeReviewer. The private AppRunner compatibility mirrors have been removed, public compatibility properties are typed-derived only, restored-session reconstruction now flows through typed session/job/result helpers, deferred-context report build/write routes through `ReviewExecutionService`, GUI session save/load round-trips through typed `ReviewSessionState`, active-versus-staged-session precedence plus restore construction now live on typed `ReviewRunnerState`, current-state terminology has been normalized around `staged_session_state`, and the remaining `AppRunner.run()` body has been re-audited and kept as the top-level orchestration boundary. Next work should be a new milestone or a behavior-driven cleanup, not more facade thinning for its own sake.
```

