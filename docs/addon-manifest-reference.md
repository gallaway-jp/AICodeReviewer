# Addon Manifest Reference

Use this page when you need the field-level contract for `addon.json` and the supported entry-point payload shapes.

Use [Addons Guide](addons.md) when you want the broader addon model, discovery flow, generated-preview workflow, and addon runtime behavior.

## Manifest Root

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

## Root Field Rules

### `manifest_version`

- must match the current supported schema version
- the current supported value is `1`
- unsupported values are rejected during manifest loading

### `id`

- required string
- normalized to lowercase during loading
- must be unique across discovered addons

### `version`

- required string
- treated as addon metadata and surfaced in discovery output

### `name`

- optional string
- defaults to the addon id when omitted or blank

### `permissions`

- optional string list
- declared metadata, not a sandbox boundary
- use it to communicate intent such as review definitions, backend providers, or UI contributions

### `compatibility`

Optional object with these keys:

- `min_app_version`
- `max_app_version`

If present, compatibility bounds are validated before activation.

### `entry_points`

- required object
- contains the supported addon contribution lists
- unknown shapes are rejected when the loader validates the specific supported keys

## Supported Entry Point Families

### `entry_points.review_packs`

Type:

- list of strings

Rules:

- each value is resolved relative to the addon root
- each resolved path must stay inside the addon root
- each resolved path must point to a file

Example:

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

### `entry_points.backend_providers`

Type:

- list of objects

Required fields per provider:

- `key`
- `module`
- `factory`

Common optional fields:

- `display_name`
- `aliases`
- `capabilities`

Rules:

- `key` is normalized to lowercase during load
- `display_name` falls back to `key` when omitted
- `module` is resolved relative to the addon root and must stay inside it
- `module` must resolve to a file
- the referenced factory is imported and built during runtime composition

Example:

```json
{
  "manifest_version": 1,
  "id": "echo-backend-addon",
  "version": "1.0.0",
  "name": "Echo Backend Addon",
  "compatibility": {
    "min_app_version": "2.0.0"
  },
  "permissions": [
    "backend_providers",
    "ui_contributors"
  ],
  "entry_points": {
    "backend_providers": [
      {
        "key": "echo-addon",
        "display_name": "Echo Addon Backend",
        "module": "backend_provider.py",
        "factory": "build_backend",
        "aliases": [
          "echo-addon-example"
        ],
        "capabilities": [
          "example",
          "offline"
        ]
      }
    ]
  }
}
```

### `entry_points.ui_contributors`

Type:

- list of objects

Required fields per contributor:

- `surface`
- `title`
- `lines`

Common optional fields:

- `description`

Current supported surface values:

- `settings_section`

Rules:

- unsupported surfaces are rejected during manifest loading
- this is intended for compact addon-specific status or configuration notes inside Settings

Example:

```json
{
  "surface": "settings_section",
  "title": "Echo Backend Addon",
  "description": "This addon installs a deterministic example backend for testing addon discovery and GUI contribution rendering.",
  "lines": [
    "Backend key: echo-addon",
    "Alias: echo-addon-example",
    "Capabilities: example, offline"
  ]
}
```

### `entry_points.editor_hooks`

Type:

- list of objects

Required fields per hook:

- `module`
- `factory`

Rules:

- `module` is resolved relative to the addon root and must stay inside it
- `module` must resolve to a file
- the built hook object may implement only a supported subset of editor and staged-preview callbacks

Supported callback names currently include:

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

Example:

```json
{
  "manifest_version": 1,
  "id": "editor-hook-addon",
  "version": "1.0.0",
  "name": "Editor Hook Addon",
  "compatibility": {
    "min_app_version": "2.0.0"
  },
  "permissions": [
    "ui_contributors"
  ],
  "entry_points": {
    "editor_hooks": [
      {
        "module": "editor_hooks.py",
        "factory": "build_editor_hooks"
      }
    ]
  }
}
```

## Path And Validation Constraints

The addon loader validates these failure modes early:

- invalid JSON or non-object manifest payloads
- unsupported `manifest_version`
- missing required string fields
- invalid compatibility bounds
- missing files for review packs or Python modules
- paths that escape the addon root
- unsupported UI contributor surfaces

These checks happen during manifest loading so broken addons fail at discovery time instead of failing later during a review run.

## Practical Examples In The Repository

- [Secure defaults example](../examples/addon-secure-defaults/addon.json)
- [Echo backend example](../examples/addon-echo-backend/addon.json)
- [Editor hooks example](../examples/addon-editor-hooks/addon.json)

## Related Guides

- [Addons Guide](addons.md)
- [GUI Guide](gui.md)
- [Configuration Reference](configuration.md)
- [Contributing](contributing.md)