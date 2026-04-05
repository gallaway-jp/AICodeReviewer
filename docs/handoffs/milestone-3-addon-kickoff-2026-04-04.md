# Milestone 3 Addon Kickoff Handoff

Date: 2026-04-04

## Objective

Start Milestone 3 from the platform extensibility roadmap: addon manifests, local addon discovery, and capability registration.

This first slice stays narrow on purpose. It does not try to deliver full backend-provider plugins, GUI addon management, or subprocess isolation yet. It establishes a manifest and discovery layer that can already contribute review packs through the existing review-definition system.

## Why This Slice First

Milestone 2 is at a practical stopping point. The benchmark browser now has persisted comparison view state and semantic issue-level diff summaries, and the remaining benchmark work is optional polish rather than a milestone blocker.

The next roadmap milestone is the Addon Platform. The cleanest live extensibility seam in the current codebase is not backend instantiation or GUI composition, but review-pack installation:

- review definitions and presets already compose from built-ins plus external JSON packs
- CLI and GUI already consume that registry surface
- benchmark metadata and subtype metadata already flow through that registry path

That made the highest-leverage first addon slice:

- add an addon manifest contract
- discover addon manifests from configured local paths
- validate compatibility and duplicate ids
- let addons contribute review packs immediately through manifest entry points

This starts Milestone 3 without inventing a second plugin path beside the registry system that already works.

## Completed In This Slice

- added `src/aicodereviewer/addons.py` as the first addon manifest and discovery module
- added addon config defaults in `src/aicodereviewer/config.py`:
  - `[addons]`
  - `paths = ""`
- introduced addon manifest constants:
  - `ADDON_MANIFEST_FILENAME = "addon.json"`
  - `ADDON_MANIFEST_SCHEMA_VERSION = 1`
- added typed addon manifest models:
  - `AddonCompatibility`
  - `AddonManifest`
- added local addon discovery behavior:
  - default discovery from config-relative `addons/`
  - optional discovery from configured `[addons] paths`
  - path expansion for directories and glob-like entries
- added manifest validation for:
  - `manifest_version`
  - `id`
  - `version`
  - optional `permissions`
  - optional `compatibility.min_app_version`
  - optional `compatibility.max_app_version`
  - `entry_points.review_packs`
- validated addon compatibility against the live app version from `src/aicodereviewer/__init__.py`
- rejected duplicate addon ids across discovered manifests
- rejected addon review-pack entry points that do not resolve to files
- integrated addon review-pack discovery into `src/aicodereviewer/review_definitions.py` by appending addon-provided review packs to `discover_review_pack_paths()` with de-duplication preserved
- added `examples/addon-secure-defaults/addon.json` as a concrete addon manifest example
- added direct addon tests in `tests/test_addons.py`
- added review-definition integration coverage in `tests/test_review_definitions.py`

## Current Addon Contract

The first addon contract is intentionally small:

- addons are discovered from `addon.json`
- the current supported capability surface is `entry_points.review_packs`
- those review packs reuse the existing pack schema and existing registry installation path

Example manifest shape:

```json
{
  "manifest_version": 1,
  "id": "secure-defaults-addon",
  "version": "1.0.0",
  "name": "Secure Defaults Addon",
  "compatibility": {
    "min_app_version": "2.0.0"
  },
  "permissions": [
    "review_definitions"
  ],
  "entry_points": {
    "review_packs": [
      "../review-pack-secure-defaults.json"
    ]
  }
}
```

## Design Constraints Locked In By This Slice

1. Addon discovery is local-path based first.
2. Addon activation currently reuses review-pack composition instead of creating a separate plugin registry.
3. Incompatible addons fail before activation based on app-version checks.
4. Duplicate addon ids fail fast.
5. Missing review-pack files fail fast.
6. The first milestone slice should not broaden into backend loading, subprocess execution, or GUI addon management until the manifest/discovery layer is stable.

## What Is Deliberately Not Done Yet

- no addon backend-provider registration
- no addon-provided GUI contributions
- no addon manager UI or addon diagnostics tab
- no subprocess or sandbox mode
- no CLI addon install/list/inspect commands
- no richer permission enforcement beyond storing and validating declared permissions

This is a Milestone 3 start, not the full addon platform.

## Validation

Focused validation for this slice:

- `tests/test_addons.py tests/test_review_definitions.py tests/test_main_cli.py` -> `40 passed in 0.41s`

Broader regression after the slice:

- `tests/test_execution_service.py tests/test_gui_smoke.py` -> `59 passed in 56.92s`

One focused failure surfaced during development before the passing rerun:

- `tests/test_review_definitions.py::test_compose_review_registry_loads_review_pack_from_discovered_addon`
- cause: the `_write_pack(...)` test helper wrote nested files without creating parent directories first
- fix: `_write_pack(...)` now calls `path.parent.mkdir(parents=True, exist_ok=True)` before writing

No changed-file diagnostics remained after the fix.

## Recommended Next Slice

Continue Milestone 3 by widening addon contribution points only where there is a real downstream consumer.

The highest-leverage next step is:

- define a second addon entry-point capability for backend providers or execution capabilities, but keep it manifest-driven and registry-backed rather than jumping straight to arbitrary code execution

Good follow-on options from here:

1. backend-provider descriptor registration via addon manifests
2. addon diagnostics and surfaced discovery errors in the GUI or CLI
3. a trusted in-process addon loading boundary for code-backed capabilities once the manifest contract is stable

## Resume Prompt

Resume from `docs/handoffs/milestone-3-addon-kickoff-2026-04-04.md`. Milestone 3 has started in AICodeReviewer with a narrow addon-manifest foundation: local addon discovery now loads `addon.json` manifests from the default `addons/` directory and configured addon paths, validates manifest version, duplicate ids, compatibility bounds, and review-pack entry points, and feeds addon-provided review packs into the existing review-definition composition path. The next slice should build on this manifest-driven seam rather than inventing a parallel plugin system.