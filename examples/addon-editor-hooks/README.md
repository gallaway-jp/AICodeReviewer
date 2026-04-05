# Editor Hook Addon Example

This example shows the expected shape for an addon that contributes editor hooks.

## What It Demonstrates

- `entry_points.editor_hooks` manifest registration
- a code-backed hook module with `build_editor_hooks()`
- popup editor lifecycle handling through `on_editor_event(...)`
- popup editor and diff-preview diagnostics through `collect_diagnostics(...)`
- patch-written notifications through `on_patch_applied(...)`

## Hook Events Used By The Example

The current AICodeReviewer popup surfaces emit these event names:

- `buffer_opened`
- `buffer_switched`
- `buffer_saved`
- `buffer_closed`
- `staged_preview_opened`
- `change_navigation`
- `preview_staged`

## Notes

- The hook payload is a plain Python dictionary so addon code can stay lightweight.
- Diagnostics should be concise because they are rendered inline in the popup editor or diff preview.
- Hook failures are isolated and logged by AICodeReviewer so an addon should not assume it owns the UI flow.
