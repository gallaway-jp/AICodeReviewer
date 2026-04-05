# Milestone 3 Addon Completion Handoff

Date: 2026-04-04

## Objective

Finish the remaining Milestone 3 acceptance gap so the roadmap can move from the Addon Platform to HTTP and web-server work.

The open gap after the earlier addon slices was the GUI contribution acceptance criterion:

- an addon could already register review packs
- an addon could already register backend providers
- addon failures were already isolated and diagnosable
- incompatible addons were already rejected before activation
- but addons still could not contribute any GUI surface

## Completed In This Slice

- extended `src/aicodereviewer/addons.py` with manifest-backed `entry_points.ui_contributors`
- added a constrained `AddonUIContributorSpec` model with the first supported surface:
  - `settings_section`
- kept the UI contribution contract manifest-driven and intentionally narrow:
  - title
  - optional description
  - optional informational lines
- avoided widening the SDK into arbitrary in-process widget injection before the HTTP milestone
- updated CLI addon diagnostics in `src/aicodereviewer/main.py` to list UI contributor counts and entries
- updated Settings-tab addon rendering in `src/aicodereviewer/gui/settings_mixin.py` to show addon-contributed settings cards
- fixed the latent translation placeholder collision in the Settings addon backend summary path by renaming `{key}` to `{backend_key}`
- updated locale strings in:
  - `src/aicodereviewer/lang/en.py`
  - `src/aicodereviewer/lang/ja.py`
- extended the checked-in example addon in `examples/addon-echo-backend/addon.json` so it now contributes:
  - backend provider registration
  - a Settings-surface contribution
- updated `examples/README.md` to describe the expanded example addon
- extended tests to cover:
  - UI contributor parsing in `tests/test_addons.py`
  - config-driven CLI addon listing output in `tests/test_main_cli.py`
  - Settings-surface rendering in `tests/test_gui_smoke.py`
- updated `.github/specs/platform-extensibility/spec.md` to:
  - mark Milestone 3 ready to move on
  - insert the newly requested milestones before the review quality program
  - renumber the review quality milestone accordingly

## Why This Completes Milestone 3

Milestone 3 acceptance criteria are now satisfied in the repository baseline:

1. an addon can register a backend without core edits
2. an addon can register a review type or subtype visible in CLI and GUI
3. an addon can contribute at least one menu or settings surface in the GUI
4. addon load failures are isolated and diagnosable
5. incompatible addons are rejected before partial activation

This does not claim the full long-tail deliverable list is exhausted. In particular:

- subprocess extension mode is still future work
- broader hook families remain future expansion work
- API route contributions belong naturally with the HTTP milestone

Those remaining areas are roadmap growth, not blockers for leaving Milestone 3.

## Validation

Focused validation after the GUI contribution slice:

- `tests/test_addons.py tests/test_main_cli.py tests/test_gui_smoke.py` -> `69 passed in 58.12s`

Broader addon-related regression after the milestone-close changes:

- `tests/test_addons.py tests/test_main_cli.py tests/test_review_definitions.py tests/test_gui_smoke.py tests/test_gui_workflows.py` -> `145 passed in 258.63s (0:04:18)`

No changed-file errors remained after the final rerun.

## Recommended Next Milestone

Move on to Milestone 4: HTTP API And Web Server Support.

The immediate implementation path should stay aligned with the existing architecture work already in place:

- reuse the scheduler and execution service rather than introducing a parallel web orchestration path
- expose registry-backed backends and review definitions through HTTP
- keep local-only defaults and additive API route design

## Resume Prompt

Resume from `docs/handoffs/milestone-3-addon-completion-2026-04-04.md`. Milestone 3 is now functionally complete in AICodeReviewer: manifest-driven addon discovery supports review-pack contributions, backend-provider registration, surfaced CLI and GUI diagnostics, and constrained Settings-surface GUI contributions. The roadmap spec has also been updated to insert the new milestones ahead of the review quality program. The next implementation milestone should be HTTP API and web-server support on top of the shared scheduler and execution service, without introducing a separate web-only orchestration path.