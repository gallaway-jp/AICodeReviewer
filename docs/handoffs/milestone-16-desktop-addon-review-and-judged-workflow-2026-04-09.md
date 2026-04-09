# Milestone 16: Desktop Addon Review And Judged Workflow

## Summary

- moved the generated-addon preview review flow out of Settings into a dedicated desktop Addon Review page with a detachable window path
- added `src/aicodereviewer/gui/addon_review_builder.py` and `src/aicodereviewer/gui/addon_review_mixin.py` so the GUI now treats Addon Review as a first-class top-level surface alongside Benchmarks, Settings, and Output Log
- reduced the Settings Addons section back to addon diagnostics plus a launcher button that opens the dedicated Addon Review page
- extended `tools/evaluate_generated_addon_review_quality.py` so judged runs now append backend-specific history, compute trend deltas against the previous run, and emit a markdown summary suitable for workflow publishing
- added `.github/workflows/generated-addon-judged-quality.yml` so the repository can restore the latest backend history artifact, rerun the judged fixture catalog on a provisioned runner, append the new history entry, and upload the updated artifact set

## Validation

- targeted pytest coverage passed:

```bash
d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_addon_review_quality.py tests/test_gui_smoke.py::TestAppCreation::test_settings_addon_diagnostics_widgets tests/test_gui_smoke.py::TestAppCreation::test_addon_review_widgets tests/test_gui_smoke.py::TestAppCreation::test_addon_review_surface_loads_preview tests/test_gui_workflows.py::test_addon_review_can_approve_preview tests/test_gui_workflows.py::test_addon_review_tab_detach_and_redock_preserves_loaded_state tests/test_gui_workflows.py::test_detachable_pages_support_keyboard_shortcuts_for_open_and_redock tests/test_gui_workflows.py::test_four_detached_pages_restore_after_restart -q
```

- result: `13 passed`

## Outcome

- maintainers now have a real desktop review surface for generated addon previews instead of a temporary Settings-hosted subsection
- the detachable-window baseline now includes Addon Review in addition to Output Log, Settings, and Benchmarks
- judged generated-addon relevance evidence is no longer only per-run JSON; the repository now has backend-specific history continuity and a scheduled markdown trend summary path for repeatable regression tracking