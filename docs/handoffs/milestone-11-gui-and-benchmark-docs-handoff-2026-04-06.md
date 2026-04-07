# Milestone 11 GUI And Benchmark Docs Handoff

## What changed

- Updated the maintained GUI guide to match the shipped desktop app instead of the older four-tab description.
- Documented the Benchmarks tab as a first-class GUI surface, including saved-run comparison, fixture diff triage, report preview/diff actions, and detached-window support.
- Documented the shared detachable-window workflow for Benchmarks, Settings, and Output Log, including `Open In Window`, `Redock`, `Ctrl+Shift+O`, `Ctrl+W`, and restart restore behavior.
- Added a short desktop benchmark-browser section to `docs/benchmarks.md` so the benchmark docs cover both CLI execution and the shipped GUI browsing flow.
- Refreshed the screenshot capture tooling and generated new checked-in images for the Benchmarks tab and detached benchmark workflow.
- Added a maintained addon guide that documents the shipped manifest/runtime contract, discovery rules, supported entry points, diagnostics workflow, and example addon paths.
- Clarified the reports guide so restored GUI-finalize sessions are explicitly tied back to the typed deferred-report/session-state model used by the runtime.

## Files updated

- `docs/gui.md`
- `docs/benchmarks.md`
- `docs/addons.md`
- `docs/configuration.md`
- `docs/architecture.md`
- `docs/http-api.md`
- `docs/README.md`
- `docs/contributing.md`
- `docs/reports.md`
- `tools/gui_screenshot_state.py`
- `tools/capture_gui_screenshots.ps1`
- `docs/images/gui-benchmarks-tab.png`
- `docs/images/gui-detached-benchmark-window.png`

## Notes

- The detached-workflow screenshot currently shows the shipped placeholder/redock state in the main app while the benchmark browser is detached; that still matches the documented workflow even though it is not a separate cropped toplevel-only capture.
- This slice included a small tooling change so `tools/capture_gui_screenshots.ps1` can regenerate the benchmark and detached-workflow images in future doc refreshes.
- The addon guide is intentionally limited to the currently shipped extension surface: review-pack manifests, backend providers, Settings-surface UI contributors, and popup-editor hooks.
- No automated tests were required beyond error checks and visual verification because the functional behavior was already covered in earlier GUI test slices.

## Next logical documentation slices

- continue Milestone 11 by checking the remaining reference docs for report/output or addon drift against recently shipped platform-extensibility work
- add more GUI screenshots only if a future slice needs additional visual coverage for queue, local HTTP discovery, or settings-specific detached flows