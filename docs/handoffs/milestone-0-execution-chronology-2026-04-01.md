# Milestone 0 Execution Chronology

Date: 2026-04-01
Repository: AICodeReviewer
Purpose: More literal transcript-style chronology of the recent Milestone 0 execution-core work, intended as a restart companion to the engineering handoff.

## Chronological History

1. The work continued under the standing instruction: Continue with what you think is correct.

2. The main objective for this phase was to keep advancing the platform-extensibility Milestone 0 refactor by moving orchestration behavior out of `AppRunner` and into typed execution abstractions without breaking the existing CLI and GUI flows.

3. Before the latest sequence, the branch had already accumulated the following major changes:
   - platform-extensibility spec and Milestone 0 design docs were created
   - backend registry and review registry were introduced
   - typed execution models, events, and `ReviewExecutionService` were added
   - `AppRunner` had been converted into a compatibility facade over the execution service
   - GUI review execution had moved to typed event sinks for Tk-safe progress updates
   - CLI tool-mode had been updated to prefer `last_execution`
   - report generation had been moved behind the execution service

4. After those pieces were in place, semantic validation was moved into the execution core:
   - `ReviewRequest` gained `backend_name`
   - unknown backends were rejected through the backend registry
   - unknown review types were rejected through the review registry
   - this validation happened before any real scan or backend work

5. The next step extracted the interactive CLI completion flow into the execution service:
   - `ReviewExecutionService.complete_interactive_review(...)` was added
   - `AppRunner.run()` stopped directly owning the interactive confirmation path
   - an early default-argument binding problem prevented tests from patching the resolver cleanly, so the injected resolver was changed to bind at runtime instead of function-definition time

6. Wider test runs then surfaced Tk suite-order instability:
   - popup windows were scheduling local `after(...)` callbacks that outlived the windows in tests
   - fixes were applied in Results, dialogs, and health popup flows so nonessential titlebar-fix and popup-local callbacks are skipped in testing mode
   - additional Tk bootstrap failures involving `tk.tcl` and `init.tcl` were treated as environment skips instead of hard suite failures

7. After that, the typed job lifecycle was corrected:
   - jobs with `issues_found` were no longer marked `completed` immediately
   - GUI-style runs now remain in `awaiting_gui_finalize`
   - interactive CLI runs transition through `awaiting_interactive_resolution`
   - actual report writing transitions through `reporting` and only then reaches `completed`
   - tests were updated to match the corrected lifecycle

8. A malformed patch briefly corrupted `_complete_job(...)` in `src/aicodereviewer/execution/service.py` during that lifecycle work:
   - the method was manually repaired
   - the lingering premature completion call in the `issues_found` path was removed
   - focused lifecycle tests and the broader targeted slice both passed afterward

9. Once live execution flows were in better shape, attention shifted to restored GUI sessions:
   - saved sessions already contained both issues and deferred report metadata
   - however, session restore only reconstructed legacy `private report-context mirror`
   - restored sessions did not rebuild typed pending execution state such as `last_execution` and `last_job`

10. The restore path was then updated:
   - `AppRunner.restore_serialized_report_context(...)` was extended to accept optional restored issues
   - when issues are provided, it now synthesizes:
     - a `ReviewRequest`
     - a `ReviewExecutionResult` with status `issues_found`
     - a `ReviewJob` in state `awaiting_gui_finalize`
   - `results_mixin._restore_session_report_context(...)` was updated to pass restored issues through
   - `_load_session()` was updated accordingly
   - tests in `tests/test_results_session.py` and `tests/test_gui_workflows.py` were updated to assert restored typed state exists

11. During validation of the restored-session path, a real syntax problem surfaced:
   - `src/aicodereviewer/gui/results_mixin.py` had a malformed indentation in `_restore_session_report_context(...)`
   - that indentation was corrected
   - after the fix, the focused restore/session and GUI workflow slice passed

12. The broader targeted regression slice was then rerun around:
   - execution service
   - orchestration
   - CLI tool mode
   - main CLI
   - results session handling
   - GUI workflows
   - that slice passed as well

13. After the restored-session typed-state change was green, another narrower consistency issue was identified in `AppRunner`:
   - `restore_serialized_report_context(meta, issues=None)` could leave stale typed state from a previous run attached to newly restored pending report metadata
   - this meant `last_execution`, `last_job`, `private execution-summary mirror`, and deferred issues could remain populated even when the new metadata did not correspond to a real typed execution result

14. That AppRunner stale-state seam was fixed:
   - `restore_serialized_report_context(...)` now clears stale typed state and mirrored pending state before returning when only metadata is restored
   - a public `pending_issues` property was added
   - `build_report(...)` was updated to read from `pending_issues` instead of reaching directly into `_pending_issues`

15. Regression coverage was added for that latest fix in `tests/test_orchestration.py`:
   - one test verifies restoring pending metadata without issues after a prior run clears stale execution state
   - another test verifies clearing pending metadata clears pending state entirely

16. Validation after the stale-state fix was then run in two stages:
   - focused slice:
     - `tests/test_orchestration.py`
     - `tests/test_results_session.py`
     - `tests/test_gui_workflows.py`
     - result: `44 passed`
   - broader targeted slice:
     - `tests/test_execution_service.py`
     - `tests/test_orchestration.py`
     - `tests/test_cli_tool_mode.py`
     - `tests/test_main_cli.py`
     - `tests/test_results_session.py`
     - `tests/test_gui_workflows.py`
     - result: `93 passed, 1 skipped`

17. The one skip in the broader slice was a GUI/Tk environment skip and not treated as a new regression.

18. A durable engineering handoff file was then created so the work could survive a restart:
   - `docs/handoffs/milestone-0-execution-handoff-2026-04-01.md`
   - a shorter repo-memory checkpoint was also saved under `/memories/repo/milestone-0-execution-handoff.md`

19. The recommended next step after restart remained:
   - continue migrating remaining GUI and tests away from direct `private report-context mirror` access toward `serialized_report_context`
   - keep compatibility mirrors until the remaining callers are migrated
   - continue validating with the standard targeted regression slice after each step

20. After restart, the next compatibility step migrated the remaining in-repo GUI and test scaffolding away from direct private pending report metadata access:
   - GUI workflow and session tests were updated to provide `serialized_report_context` on runner stubs instead of `private report-context mirror`
   - restored-session and runtime-action assertions were updated to read the public property
   - the production GUI compatibility helper in `results_mixin` was left unchanged during that first migration step

21. Validation after the test-side/public-surface migration was rerun in two stages:
   - focused slice:
     - `tests/test_orchestration.py`
     - `tests/test_results_session.py`
     - `tests/test_gui_workflows.py`
     - result: `44 passed`
   - broader targeted slice:
     - `tests/test_execution_service.py`
     - `tests/test_orchestration.py`
     - `tests/test_cli_tool_mode.py`
     - `tests/test_main_cli.py`
     - `tests/test_results_session.py`
     - `tests/test_gui_workflows.py`
     - result: `94 passed`

22. The next safe compatibility cut then moved CLI tool mode off the direct `private execution-summary mirror` fallback:
   - `main.py` was updated to use `last_execution` first and `execution_summary` second, without reading `private execution-summary mirror` directly
   - `tests/test_cli_tool_mode.py` fake runners were updated to expose `execution_summary` instead of `private execution-summary mirror`
   - CLI tool-mode coverage passed, followed by another green targeted regression rerun

23. With in-repo GUI and test callers now using the public pending-report surface, the direct private fallback in `src/aicodereviewer/gui/results_mixin.py` was removed:
   - `_get_runner_report_context()` now reads only `serialized_report_context`
   - compatibility mirrors still remain inside `AppRunner`, but GUI consumers no longer reach into `private report-context mirror` directly
   - focused GUI/session validation passed, followed by another green targeted regression rerun

24. The next compatibility cut then tightened `AppRunner` itself so public compatibility properties now prefer typed state over private mirrors:
   - `execution_summary` now derives from `last_execution` when typed execution state is present
   - `serialized_report_context` now derives from `PendingReportContext` when typed pending context is present
   - private compatibility fields remain updated, but they are no longer treated as the primary source of truth for the public properties

25. Regression coverage was added in `tests/test_orchestration.py` for the new property contract:
   - one test verifies `serialized_report_context` ignores a stale `private report-context mirror` mirror when typed pending context exists
   - one test verifies `execution_summary` ignores a stale `private execution-summary mirror` mirror when `last_execution` exists

26. Validation after the AppRunner source-of-truth cleanup was rerun in two stages:
   - focused slice:
     - `tests/test_orchestration.py`
     - result: `10 passed`
   - broader targeted slice:
     - `tests/test_execution_service.py`
     - `tests/test_orchestration.py`
     - `tests/test_cli_tool_mode.py`
     - `tests/test_main_cli.py`
     - `tests/test_results_session.py`
     - `tests/test_gui_workflows.py`
     - result: `96 passed`

27. The next AppRunner cleanup extended the same source-of-truth rule to deferred issues:
    - `pending_issues` now derives from `last_execution` when typed execution exists
    - when only typed pending report context exists, `pending_issues` now resolves to an empty list instead of falling through to a stale `_pending_issues` mirror
    - the private `_pending_issues` field still exists as a compatibility copy, but it no longer overrides typed state

28. Regression coverage was added in `tests/test_orchestration.py` for the new deferred-issues contract:
    - one test verifies `pending_issues` ignores a stale `_pending_issues` mirror when only typed pending context exists

29. Validation after the deferred-issues source-of-truth cleanup was rerun in two stages:
    - focused slice:
       - `tests/test_orchestration.py`
       - result: `11 passed`
    - broader targeted slice:
       - `tests/test_execution_service.py`
       - `tests/test_orchestration.py`
       - `tests/test_cli_tool_mode.py`
       - `tests/test_main_cli.py`
       - `tests/test_results_session.py`
       - `tests/test_gui_workflows.py`
       - result: `97 passed`

30. The next AppRunner cleanup then centralized compatibility mirror synchronization:
   - mirror writes for `private report-context mirror`, `_pending_issues`, and `private execution-summary mirror` were consolidated into one `_sync_compatibility_mirrors()` helper
   - `restore_serialized_report_context(...)` now clears or repopulates legacy mirrors through that single sync path instead of hand-maintaining each field in multiple branches
   - `_set_execution_result(...)` now updates typed state first and then syncs the compatibility mirrors from that typed state

31. Regression coverage was added in `tests/test_orchestration.py` for the centralized mirror-sync behavior:
   - one test verifies restoring pending metadata without issues still keeps the private compatibility mirrors aligned with the public state

32. Validation after the mirror-sync refactor was rerun in two stages:
   - focused slice:
      - `tests/test_orchestration.py`
      - result: `12 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `98 passed`

33. After the mirror-sync refactor, the now-unused `private execution-summary helper` helper in `AppRunner` was removed:
   - the compatibility mirror path now runs entirely through `_sync_compatibility_mirrors()`
   - no behavior change was intended; this was dead-code cleanup after the earlier source-of-truth consolidation

34. Validation after the dead-helper removal reran the standard targeted slice:
   - `tests/test_execution_service.py`
   - `tests/test_orchestration.py`
   - `tests/test_cli_tool_mode.py`
   - `tests/test_main_cli.py`
   - `tests/test_results_session.py`
   - `tests/test_gui_workflows.py`
   - result: `98 passed`

35. The next internal cleanup extracted pending-context replacement into one helper:
   - `restore_serialized_report_context(...)` now uses `_replace_pending_context(...)` to replace deferred pending metadata while clearing active execution state
   - this removed another small open-coded reset sequence and kept pending-context restore logic aligned with the centralized compatibility-sync path

36. Regression coverage was added in `tests/test_orchestration.py` for the new helper-driven behavior:
   - one test verifies clearing pending metadata also clears the private compatibility mirrors after pending context had been set

37. Validation after the pending-context helper extraction was rerun in two stages:
   - focused slice:
      - `tests/test_orchestration.py`
      - result: `13 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `99 passed`

38. The next internal cleanup extracted restored-session execution rebuilding into one helper:
   - `restore_serialized_report_context(...)` now uses `_restore_execution_from_pending_context(...)` when saved issues are available
   - this removed another open-coded synthetic restore path for `ReviewRequest`, `ReviewExecutionResult`, and `ReviewJob`
   - the refactor kept restored-session behavior centralized beside the pending-context replacement helper

39. Regression coverage was added in `tests/test_orchestration.py` for the restore helper:
   - one test verifies restoring pending metadata with saved issues rebuilds `last_execution`, `last_job`, and deferred issues from the restored metadata

40. Validation after the restored-session rebuild helper extraction was rerun in two stages:
   - focused slice:
      - `tests/test_orchestration.py`
      - result: `14 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `100 passed`

41. The next internal cleanup moved legacy pending-report metadata translation onto the model layer:
   - `PendingReportContext.from_legacy_dict(...)` was added beside `to_legacy_dict()`
   - `AppRunner.restore_serialized_report_context(...)` stopped open-coding the legacy dict-to-context mapping
   - direct execution-model coverage was added to prove pending metadata round-trips through the new helper

42. Validation after the model-layer metadata conversion was rerun on the focused execution/orchestration slice:
   - `tests/test_execution_service.py`
   - `tests/test_orchestration.py`
   - result: `22 passed`

43. The first broader rerun after that refactor exposed a cross-module GUI workflow failure:
   - the minimal reproducer turned out to be `tests/test_cli_tool_mode.py`, `tests/test_main_cli.py`, and `tests/test_gui_workflows.py`
   - earlier CLI tests were leaving root logging bound to closed pytest capture streams, which polluted later GUI workflow runs

44. The GUI app fixture was then stabilized for combined slices:
   - `tests/test_gui_workflows.py` now resets root logging before each app instance
   - that ensures GUI workflow tests start with a live stderr-backed root handler instead of inheriting closed capture streams from prior CLI modules

45. Validation after the model-layer cleanup and GUI fixture stabilization was rerun in two stages:
   - minimal reproducer:
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_gui_workflows.py`
      - result: `77 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `101 passed`

46. The next internal cleanup moved restored-session request reconstruction into the pending metadata model:
   - `PendingReportContext.to_review_request()` was added
   - `AppRunner` no longer rebuilds restored `ReviewRequest` objects field by field

47. The same cleanup moved restored-session execution result reconstruction into the execution result model:
   - `ReviewExecutionResult.from_pending_context(...)` was added
   - `AppRunner._restore_execution_from_pending_context(...)` now coordinates restore state instead of constructing the synthetic result inline

48. Direct execution-model coverage was added for the new restore helpers:
   - one test verifies `PendingReportContext.to_review_request()` preserves restored metadata
   - one test verifies `ReviewExecutionResult.from_pending_context(...)` recreates the expected `issues_found` result shape

49. Validation after the restored-session model-helper extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - result: `24 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `103 passed`

50. The next internal cleanup moved restored-session job reconstruction into the execution models:
   - `ReviewJob.from_pending_context_result(...)` was added
   - `AppRunner._restore_execution_from_pending_context(...)` stopped constructing the synthetic GUI-finalize job inline

51. Direct execution-model coverage was added for the new job helper:
   - one test verifies restored job reconstruction preserves the expected `job-restored-session` identity, `awaiting_gui_finalize` state, and attached result

52. Validation after the restored-session job-helper extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - result: `25 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `104 passed`

53. The next internal cleanup moved request-to-pending-context translation onto the request model:
   - `ReviewRequest.to_pending_report_context(...)` was added
   - `ReviewExecutionService.execute_job(...)` stopped constructing `PendingReportContext` inline in the issues-found path

54. Direct execution-model coverage was added for the new request helper:
   - one test verifies a `ReviewRequest` rebuilds the expected deferred report metadata, including diff source, participants, backend, and scanned-file count

55. Validation after the request-to-pending-context helper extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - result: `26 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `105 passed`

56. The next internal cleanup moved report-written result reconstruction onto the execution result model:
   - `ReviewExecutionResult.with_report_output(...)` was added
   - `ReviewExecutionService.generate_report(...)` stopped constructing the updated `report_written` result inline

57. Direct execution-model coverage was added for the new report-output helper:
   - one test verifies the updated result preserves request identity, files scanned, issues, report context, and generated report path while switching status to `report_written`

58. Validation after the report-output helper extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - result: `27 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `106 passed`

59. The next internal cleanup centralized typed-first report-context resolution inside `AppRunner`:
   - `_current_report_context()` was added
   - `build_report(...)`, `serialized_report_context`, `_restore_execution_from_pending_context(...)`, and `_sync_compatibility_mirrors()` now all use that one typed-first path

60. Regression coverage was added for the new orchestration helper:
   - one test verifies `serialized_report_context` prefers `last_execution.report_context` over a stale `_pending_report_context`

61. The same round of cleanup moved terminal `ReviewJob` field mutations onto the model:
   - `ReviewJob.complete_with_result(...)` and `ReviewJob.fail_with_error(...)` were added
   - `ReviewExecutionService._complete_job(...)` and `_fail_job(...)` stopped mutating job fields inline

62. Direct execution-model coverage was added for the new job helpers:
   - one test verifies successful completion stores the result and completion timestamp
   - one test verifies failure stores the error message and completion timestamp

63. Validation after the typed-first report-context and ReviewJob helper extractions was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - result: `30 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `109 passed`

64. The next internal cleanup moved the remaining non-terminal job transition mechanics onto the model:
   - `ReviewJob.transition_to(...)` was added
   - `ReviewExecutionService._set_job_state(...)` stopped mutating `job.state` and `job.started_at` directly
   - the service now emits state-change events from model-owned transitions instead

65. The same cleanup moved the issues-found pending-result handoff onto the model:
   - `ReviewJob.set_pending_result(...)` was added
   - `ReviewExecutionService.execute_job(...)` stopped setting `job.result` inline before the `awaiting_gui_finalize` transition

66. The AppRunner compatibility facade was tightened further in the same round:
   - `execution_summary`, `serialized_report_context`, and `pending_issues` no longer read private mirror state at all
   - private compatibility mirrors still remain and are still synchronized through `_sync_compatibility_mirrors()` as legacy output copies
   - this means stale mirror writes no longer leak through the public properties when no typed state exists

67. Regression coverage was added for the latest boundary cleanup:
   - execution-model tests now verify `ReviewJob.transition_to(...)` preserves the initial start timestamp and `ReviewJob.set_pending_result(...)` stores the result while transitioning to `awaiting_gui_finalize`
   - orchestration coverage now verifies public compatibility properties ignore stale private mirrors when no typed execution or pending context exists

68. Validation after the model-owned transition and stale-mirror-read cleanup was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - result: `33 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `112 passed`

## Latest State At Save Time

- `AppRunner` is still intentionally a compatibility facade
- typed execution state exists and is the main direction of travel
- restored sessions now rebuild typed pending state when saved issues exist
- restoring metadata without issues now clears stale typed state correctly
- in-repo GUI, CLI tool mode, and tests now consume public `serialized_report_context` / `execution_summary` surfaces instead of reaching into private compatibility mirrors
- `AppRunner` public compatibility properties now read typed execution/pending context state first, with private mirrors retained only as compatibility copies
- `pending_issues` now also follows typed state and typed pending context before consulting the legacy mirror
- private compatibility mirrors are now synchronized through one central helper instead of multiple hand-maintained branches
- the obsolete `private execution-summary helper` helper is gone; compatibility sync now has a single implementation path
- pending-context replacement now also runs through one helper rather than open-coding execution-state clearing in multiple branches
- restored-session execution rebuilding now also runs through one helper rather than open-coding synthetic typed-state reconstruction in `restore_serialized_report_context(...)`
- legacy pending-report metadata translation now lives on `PendingReportContext`, not inline in `AppRunner`
- GUI workflow tests now reset root logging before app creation so combined CLI+GUI slices do not inherit closed capture streams
- restored-session synthetic `ReviewRequest` and `ReviewExecutionResult` assembly now lives in the execution models instead of `AppRunner`
- restored-session synthetic `ReviewJob` assembly now also lives in the execution models instead of `AppRunner`
- request-to-pending-context translation now lives on `ReviewRequest` instead of inside `ReviewExecutionService`
- report-written result reconstruction now lives on `ReviewExecutionResult` instead of inside `ReviewExecutionService`
- typed-first report-context resolution inside `AppRunner` now flows through one helper instead of multiple ad hoc branches
- terminal `ReviewJob` mutations now live on the model instead of inside `ReviewExecutionService`
- the current targeted regression slice is green

69. A final repo-wide caller audit then showed the old private AppRunner mirrors no longer had in-repo production consumers:
   - `private execution-summary mirror`
   - `private report-context mirror`
   - `_pending_issues`

70. With that caller audit in hand, the private mirrors were removed from `AppRunner` entirely:
   - `_sync_compatibility_mirrors()` was deleted
   - public compatibility properties stayed typed-derived only
   - orchestration coverage was updated to assert those private attributes are no longer present

71. The restored-session path was also collapsed one step further in the same round:
   - `ReviewJob.from_pending_context(...)` was added
   - `AppRunner._restore_execution_from_pending_context(...)` now uses that one helper instead of rebuilding a result and then a job in separate steps

72. Validation after the mirror removal and one-step restore-helper cleanup was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - result: `32 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `111 passed`

73. Latest saved state after that cleanup:
   - `AppRunner` remains a compatibility facade, but the legacy private mirrors are gone
   - `_pending_report_context` is now the remaining AppRunner-side staging field for deferred report finalization and restored sessions
   - restored-session job reconstruction now lives in one execution-model helper rather than a two-step facade rebuild

74. The next cleanup removed the last orchestration-only deferred-report branch:
   - `AppRunner.build_report(...)` now synthesizes a typed pending job through `_job_from_pending_context(...)` and delegates to `ReviewExecutionService.build_report(...)`
   - `AppRunner.generate_report(...)` now does the same for `ReviewExecutionService.generate_report(...)`
   - orchestration no longer calls the reporter directly when only deferred pending context exists

75. Regression coverage was added for that path:
   - one test now restores pending metadata without a pre-existing job, calls `runner.generate_report([issue])`, and verifies the typed service path produces a completed `report_written` result

76. Validation after the deferred-context service-path unification was rerun in two stages:
   - focused slice:
      - `tests/test_orchestration.py`
      - `tests/test_execution_service.py`
      - result: `33 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `112 passed`

77. The next cleanup moved the last raw deferred-report staging concept into the execution models:
   - `DeferredReportState` was added as a typed wrapper around `PendingReportContext`
   - `AppRunner` now stores `_pending_report_state` instead of `_pending_report_context`
   - deferred legacy metadata restore and synthetic pending-job reconstruction now flow through that typed model

78. Coverage was expanded for that extraction:
   - execution-model tests now verify `DeferredReportState.from_legacy_dict(...)` round-trips metadata and rebuilds a synthetic GUI-finalize job
   - orchestration regression coverage now mutates the typed deferred state instead of the old raw pending context field

79. Validation after the deferred-state extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - result: `34 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `113 passed`

80. The next cleanup added a typed AppRunner surface for that deferred state:
   - `deferred_report_state` now exposes the current typed deferred report state
   - `restore_deferred_report_state(...)` now restores deferred session state directly from `DeferredReportState`
   - `restore_serialized_report_context(...)` remains only as a legacy wrapper around that typed path

81. The in-repo GUI session restore path in `results_mixin` was moved to the typed AppRunner surface:
   - `ResultsTabMixin._restore_session_report_context(...)` now constructs `DeferredReportState` and calls `runner.restore_deferred_report_state(...)`

82. Coverage was expanded for that migration:
   - orchestration coverage now verifies the typed AppRunner restore API rebuilds the expected `issues_found` / `awaiting_gui_finalize` state
   - focused validation also included `tests/test_results_session.py` because the in-repo restore caller changed

83. Validation after the typed AppRunner deferred-state API migration was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `37 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `114 passed`

84. The next cleanup moved the saved-session payload itself into the execution models:
   - `ReviewSessionState` was added as a typed wrapper around `issues + DeferredReportState`
   - the model now owns issue serialization, `resolved_at` parsing, and legacy GUI session-payload round-tripping
   - `AppRunner.restore_session_state(...)` was added as a typed restore entry point for the full session abstraction

85. The GUI save/load path in `results_mixin` was then updated to use `ReviewSessionState`:
   - `_save_session()` now serializes through `ReviewSessionState.to_legacy_dict(...)`
   - `_load_session()` now parses through `ReviewSessionState.from_legacy_dict(...)`
   - the on-disk JSON structure remains unchanged

86. Coverage was expanded for that migration:
   - execution-model tests now verify `ReviewSessionState` round-trips a legacy payload including `resolved_at`
   - orchestration coverage now verifies `restore_session_state(...)` rebuilds the expected typed execution/job state

87. Validation after the typed session-state extraction was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `39 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `116 passed`

88. The next follow-up exposed the current typed saved-session state directly on the compatibility facade:
   - `AppRunner.session_state` now returns `ReviewSessionState | None` for the current typed restore state
   - this keeps in-repo callers on the typed session path instead of rebuilding state from compatibility metadata

89. The GUI session caller in `results_mixin` was then tightened around that typed surface:
   - `_get_session_state()` now prefers `runner.session_state` when available
   - `_load_session()` now restores parsed `ReviewSessionState` instances through `_restore_session_state(...)` directly instead of converting them back through legacy report context payloads
   - the existing `_restore_session_report_context(...)` path now delegates through the new typed session restore helper

90. Coverage was expanded for that follow-up:
   - orchestration coverage now verifies `session_state` exposes the current typed restore state
   - session tests now use a dummy runner that exposes `session_state` as well as `serialized_report_context`

91. Validation after the typed `session_state` facade follow-up was rerun in two stages:
   - focused slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_results_session.py`
      - result: `40 passed`
   - broader targeted slice:
      - `tests/test_execution_service.py`
      - `tests/test_orchestration.py`
      - `tests/test_cli_tool_mode.py`
      - `tests/test_main_cli.py`
      - `tests/test_results_session.py`
      - `tests/test_gui_workflows.py`
      - result: `117 passed`

92. The next follow-up moved the last saved-session reconstruction behavior further onto the typed models:
   - `ReviewSessionState.with_issues(...)` was added so callers can replace the issue list on a typed saved-session payload without rebuilding the wrapper inline
   - `ReviewSessionState.to_review_job(...)` was added so synthetic GUI-finalize job reconstruction now lives on the saved-session model itself
   - `DeferredReportState.to_session_state(...)` was added so deferred report state can wrap itself as a typed saved-session payload

93. `AppRunner` and the GUI session caller were then simplified around those model helpers:
   - `AppRunner.restore_session_state(...)` now restores typed execution state through `ReviewSessionState.to_review_job(...)`
   - `AppRunner.restore_deferred_report_state(...)` now delegates through `DeferredReportState.to_session_state(...)` when issues are provided
   - the old facade-owned `_restore_execution_from_pending_context(...)` helper was removed
   - `ResultsTabMixin._get_session_state()` now uses `session_state.with_issues(...)` when the runner already exposes typed session state, and the fallback paths now use `DeferredReportState.to_session_state(...)`

94. Coverage was expanded for that follow-up:
   - execution-model tests now verify typed session state can replace issues and rebuild a synthetic GUI-finalize job
   - orchestration coverage now verifies restoring a session without deferred report state clears runner state cleanly

95. Validation after the model-owned session-restore follow-up was rerun in two stages:
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

96. The next internal cleanup collapsed the remaining AppRunner staging split:
   - `_pending_report_state` was replaced with `_pending_session_state`
   - `session_state`, `deferred_report_state`, `pending_issues`, and synthetic pending-job reconstruction now all resolve through one `_current_session_state()` helper
   - this means non-live restore/finalize state inside the facade is now represented by one typed saved-session abstraction instead of separate deferred/session branches

97. Regression coverage was updated for that cleanup:
   - the stale-fallback orchestration guard now seeds `_pending_session_state` instead of `_pending_report_state`

98. Validation after the session-centric staging cleanup was rerun in two stages:
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

99. The next internal cleanup moved live deferred execution-to-session conversion onto the execution result model:
   - `ReviewExecutionResult.to_session_state()` was added
   - `AppRunner._current_session_state()` now delegates the `last_execution` conversion to that model helper instead of rebuilding `ReviewSessionState` inline

100. Direct execution-model coverage was added for that helper:
   - one test verifies a deferred execution result preserves issues and pending report context when converted into typed saved-session state

101. Validation after the execution-to-session helper extraction was rerun in two stages:
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

102. The next internal cleanup removed the last redundant report-context preflight from `AppRunner`:
   - `build_report()` now relies directly on `_job_from_pending_state(...)` to determine whether deferred finalize state exists
   - the now-unused `_current_report_context()` helper was deleted

103. Orchestration coverage was expanded for that cleanup:
   - one test now verifies `build_report()` returns `None` when the facade holds no pending finalize state

104. Validation after the report-context helper removal was rerun in two stages:
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

105. The next internal cleanup moved simple session-state queries onto the model:
   - `ReviewSessionState.backend_name` was added so callers no longer need to unwrap `deferred_report_state.context.backend`
   - `ReviewSessionState.is_empty()` was added so callers no longer need to duplicate the empty-session check

106. The callers were then simplified around those helpers:
   - `AppRunner.restore_session_state(...)` now uses `session_state.backend_name`
   - `AppRunner._current_session_state()` now uses `session_state.is_empty()`
   - `ResultsTabMixin._restore_session_state(...)` now uses `session_state.backend_name`

107. Direct execution-model coverage was added for the new session helpers.

108. Validation after the session-state helper extraction was rerun in two stages:
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

109. The next internal cleanup moved legacy report-context wrapping onto the session model:
   - `ReviewSessionState.from_report_context(...)` was added
   - `ReviewSessionState.from_legacy_dict(...)` now delegates its metadata reconstruction through that helper after parsing issues

110. The callers were then simplified around that factory:
   - `AppRunner.restore_serialized_report_context(...)` now builds typed session staging through `ReviewSessionState.from_report_context(...)`
   - `ResultsTabMixin._get_session_state()` and `_restore_session_report_context(...)` now use the same helper instead of rebuilding `DeferredReportState` and then wrapping it manually
   - session test scaffolding now seeds `session_state` through the same model-owned factory

111. Direct execution-model coverage was added for the new session-state factory.

112. Validation after the session-state factory extraction was rerun in two stages:
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

113. The next internal cleanup moved restored pending execution-result reconstruction onto typed deferred/session models:
   - `DeferredReportState.to_execution_result(...)` was added
   - `ReviewSessionState.to_execution_result()` was added and now owns pending execution-result reconstruction from saved-session state

114. The restore path then narrowed further:
   - `ReviewSessionState.to_review_job()` now reuses the typed execution result instead of rebuilding pending context inline
   - `AppRunner.restore_session_state(...)` now restores active execution state from the reconstructed job result instead of reassembling that result shape in the facade

115. Direct execution-model coverage was added for the new session-state execution-result helper.

116. Validation after the restored execution-result extraction was rerun in two stages:
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

117. The next internal cleanup moved active-versus-pending runner precedence into a typed runner-state model:
   - `ReviewRunnerState` was added to own `last_execution`, `last_job`, staged deferred-session state, and precedence resolution between active execution state and restored staged session state
   - the model now also owns compatibility-surface derivation for `execution_summary`, deferred report metadata, deferred report state, pending issues, and synthetic pending jobs

118. `AppRunner` was then narrowed to facade-only orchestration:
   - `AppRunner` now stores one `_runner_state` instead of maintaining `_last_execution`, `_last_job`, and `_pending_session_state` merge logic directly
   - execution/session transitions now run through `ReviewRunnerState.with_execution(...)` and `ReviewRunnerState.with_staged_session_state(...)`
   - `generate_report()` and `build_report()` now ask the typed runner state for synthetic pending jobs instead of rebuilding that lookup locally

119. Direct execution-model coverage was added for active-execution precedence over stale pending session state.

120. Validation after the runner-state extraction was rerun in two stages:
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

121. The next internal cleanup moved restore entry-point branching onto the typed runner-state model:
   - `ReviewRunnerState.from_report_context(...)` was added for legacy deferred report context restore inputs
   - `ReviewRunnerState.from_deferred_report_state(...)` was added for typed deferred restore inputs
   - `ReviewRunnerState.from_session_state(...)` was added for full saved-session restore inputs

122. `AppRunner` was then narrowed further around those typed constructors:
   - `restore_serialized_report_context(...)`, `restore_deferred_report_state(...)`, and `restore_session_state(...)` now forward directly into `ReviewRunnerState` constructors
   - empty-session normalization now also lives in the typed runner-state model instead of in facade restore helpers

123. Direct execution-model coverage was added for runner-state restore construction from legacy report metadata and full session state.

124. Validation after the runner-state restore-constructor extraction was rerun in two stages:
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

125. `AppRunner.run()` was then re-audited for one more non-cosmetic extraction seam.

126. That reassessment concluded the remaining body is now the intended Milestone 0 boundary:
   - backup cleanup remains orchestration-only
   - localized logging and dry-run/user-facing messaging remain facade concerns
   - sink wiring and the interactive versus GUI-finalize split remain top-level flow control rather than misplaced typed state reconstruction

127. Follow-up dead-path cleanup removed the now-unused `_replace_pending_session_state(...)` helper after `ReviewRunnerState` absorbed restore branching.

128. Validation after the AppRunner boundary reassessment and dead-path cleanup was rerun in two stages:
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

129. A Milestone 0 naming/docs consistency pass then normalized the current typed runner-state terminology:
   - `ReviewRunnerState.pending_session_state` was renamed to `staged_session_state`
   - `ReviewRunnerState.with_pending_session_state(...)` was renamed to `with_staged_session_state(...)`

130. Current-state documentation was aligned with that rename:
   - current summaries now describe `ReviewRunnerState` as the source of staged deferred-session state
   - obsolete `_pending_session_state` wording was removed from current-state summaries and retained only in chronology/history entries where it remains historically accurate

131. Validation after the naming/docs consistency pass was rerun in two stages:
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

## Suggested Restart Usage

Use this file when you want a literal narrative of what just happened.

Use `docs/handoffs/milestone-0-execution-handoff-2026-04-01.md` when you want the cleaner engineering summary and next-step guidance.

