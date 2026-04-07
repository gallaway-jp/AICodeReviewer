# Addons Guide

AICodeReviewer supports a small, explicit addon model for extending review packs, backends, selected GUI surfaces, and popup-editor hooks without editing core files.

This guide documents the currently shipped addon contract.

## What Addons Can Contribute Today

Supported manifest entry points in the current repository baseline:

- `entry_points.review_packs`
- `entry_points.backend_providers`
- `entry_points.ui_contributors`
- `entry_points.editor_hooks`

Current surface limits:

- review packs add review definitions through JSON packs discovered from addon manifests
- backend providers register new backend keys and aliases at startup
- UI contributors are currently limited to the desktop Settings surface through `surface = "settings_section"`
- editor hooks currently target the popup editor and staged diff-preview flows

The runtime is intentionally narrow. If an addon needs capabilities outside this list, treat that as new product work instead of assuming undocumented extension points are stable.

## Discovery

Addon manifests are discovered from:

- the default `addons/` directory beside `config.ini`
- any extra locations listed in `addons.paths`

Configured paths may point to either:

- an addon directory containing `addon.json`
- a manifest file directly

Relative paths are resolved from the directory containing `config.ini`.

Example:

```ini
[addons]
paths = examples/addon-echo-backend
```

Addon-provided review packs are loaded from the manifest and then merged into the normal review-definition discovery flow. Standalone review-pack search paths configured through `review_packs.paths` continue to work separately.

## Manifest Shape

Each addon is rooted by an `addon.json` manifest.

Required fields:

- `manifest_version`
- `id`
- `version`
- `entry_points`

Common optional fields:

- `name`
- `compatibility.min_app_version`
- `compatibility.max_app_version`
- `permissions`

Minimal manifest-only review-pack addon:

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

Notes:

- `manifest_version` must match the current supported schema version
- addon IDs are normalized to lowercase and must be unique across discovery results
- compatibility bounds are validated before activation
- `permissions` are declared metadata, not a sandbox boundary

## Entry Point Reference

### `review_packs`

Use `entry_points.review_packs` for manifest-only addons that only add review definitions.

Each value must resolve to a file within the addon root.

Use this path when you want to:

- add review types or presets without Python code
- ship opinionated project defaults
- keep an addon entirely data-driven

Reference example:

- [examples/addon-secure-defaults/addon.json](../examples/addon-secure-defaults/addon.json)

### `backend_providers`

Use `entry_points.backend_providers` to register a new backend implementation.

Each backend provider entry declares:

- `key`
- `display_name`
- `module`
- `factory`
- optional `aliases`
- optional `capabilities`

The referenced factory is imported during addon runtime composition and probed immediately so broken providers fail during startup instead of on first review execution.

Reference example:

- [examples/addon-echo-backend/addon.json](../examples/addon-echo-backend/addon.json)

### `ui_contributors`

Use `entry_points.ui_contributors` for small informational GUI contributions.

The currently supported surface is:

- `settings_section`

Each contributor can provide:

- `surface`
- `title`
- optional `description`
- `lines`

This is intended for compact addon-specific status or configuration notes inside Settings, not arbitrary Tk widget injection.

Reference example:

- [examples/addon-echo-backend/addon.json](../examples/addon-echo-backend/addon.json)

### `editor_hooks`

Use `entry_points.editor_hooks` to attach lightweight behavior to popup-editor and staged-preview flows.

Each hook entry declares:

- `module`
- `factory`

The built hook object may implement any supported subset of these methods:

- `on_editor_event`
- `on_buffer_event`
- `on_buffer_opened`
- `on_buffer_switched`
- `on_buffer_saved`
- `on_buffer_closed`
- `on_staged_preview_opened`
- `on_change_navigation`
- `on_preview_staged`
- `collect_diagnostics`
- `get_diagnostics`
- `on_patch_applied`

Hook payloads are plain dictionaries and failures are isolated into addon diagnostics instead of taking over the UI flow.

Reference example:

- [examples/addon-editor-hooks/addon.json](../examples/addon-editor-hooks/addon.json)
- [examples/addon-editor-hooks/README.md](../examples/addon-editor-hooks/README.md)

## Validation And Safety Rules

The current runtime validates several failure modes early:

- invalid JSON or wrong manifest shape
- unsupported `manifest_version`
- incompatible app-version bounds
- duplicate addon IDs
- missing review-pack or module files
- backend factories that fail to import or build
- unsupported UI contributor surfaces

Path handling is intentionally strict:

- addon entry-point file references are resolved relative to the addon root
- review-pack and Python module paths must remain inside that addon root
- entries that escape the addon root or point to missing files are rejected

This protects discovery from accidental path traversal and keeps manifests self-contained.

## Diagnostics And Inspection

Use the CLI to inspect the currently discovered addon runtime:

```bash
aicodereviewer --list-addons
```

The command reports:

- each discovered manifest
- review-pack counts
- backend providers and display names
- UI contributors and their target surfaces
- addon diagnostics when loading or registration fails

Use this command first when an addon is not appearing in the GUI or a backend key is not available.

## Choosing Between Addons And Direct Configuration

Prefer direct configuration when you only need:

- backend selection
- prompt or runtime tuning
- standalone review-pack file loading through `review_packs.paths`

Prefer an addon when you need:

- a redistributable review-pack bundle with its own manifest
- a new backend implementation
- Settings-surface documentation for an extension
- popup editor or staged-preview hook behavior

## Related Guides

- [Configuration Reference](configuration.md)
- [Backend Guide](backends.md)
- [Review Types Reference](review-types.md)
- [Contributing](contributing.md)
- [Architecture](architecture.md)