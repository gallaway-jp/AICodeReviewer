# Build A Basic Addon

Use this guide when you want to create a minimal, working addon from scratch and understand the key manifest fields and entry-point shapes.

## Before You Start

- AICodeReviewer installed (GUI or CLI)
- A project directory where you want to create the addon
- A text editor

## Expected Result

By the end of this guide you will have:

- a valid `addon.json` manifest
- a simple review-pack file the addon contributes
- the addon discoverable by AICodeReviewer
- the ability to load and use the addon in the desktop app or CLI

## Step 1: Create Addon Directory

Create a folder for your addon. For this example we’ll use `my-first-addon`:

```bash
mkdir my-first-addon
cd my-first-addon
```

## Step 2: Create `addon.json`

Create `addon.json` with the required fields:

```json
{
  "manifest_version": 1,
  "id": "my-first-addon",
  "version": "1.0.0",
  "name": "My First Addon",
  "description": "A minimal addon that contributes a review pack.",
  "permissions": ["review_definitions"],
  "entry_points": {
    "review_packs": ["review-pack.json"]
  }
}
```

Key points:

- `manifest_version` must match the supported version (currently `1`).
- `id` is normalized to lowercase and must be unique across discovered addons.
- `entry_points.review_packs` lists files relative to the addon root.

## Step 3: Create a Review Pack

Create `review-pack.json` with a minimal review definition:

```json
{
  "review_type": "best_practices",
  "name": "My First Review Pack",
  "description": "A simple review pack to demonstrate addon contribution.",
  "rules": [
    {
      "id": "example-rule-1",
      "title": "Example rule from addon",
      "severity": "info",
      "description": "This rule is contributed by the addon and will appear in supported review types.",
      "remediation": "Follow project conventions for this pattern."
    }
  ]
}
```

You can expand this with more rules, conditions, and metadata as needed.

## Step 4: Register the Addon

Place your addon folder where AICodeReviewer can discover it. The default discovery locations are:

- the `addons/` directory beside `config.ini`
- any extra paths listed in `addons.paths` in `config.ini`

For a quick test, copy or symlink your addon into the project’s `addons/` folder:

```bash
mkdir -p ../addons
cp -r my-first-addon ../addons/
```

Alternatively, add an absolute path to `addons.paths` in `config.ini`:

```ini
[addons]
paths = /absolute/path/to/my-first-addon
```

## Step 5: Verify Discovery

Run the CLI to list discovered addons:

```bash
aicodereviewer --list-addons
```

You should see your addon listed with its review packs, backend providers, UI contributors, or editor hooks (if any).

In the desktop app, open the Addon Review tab and load the preview directory to inspect the generated bundle and approve/reject it.

## Step 6: Use the Addon

Once discovered, the addon’s review pack will be available in the review-type selection UI and CLI. Run a review that includes the relevant review type to see the contributed rules in action.

## Troubleshooting

- **Addon not listed**: check that `addon.json` is valid JSON and that the path is inside a configured discovery location.
- **Review pack not loaded**: verify that `review-pack.json` exists relative to the addon root and that the file is readable.
- **Validation errors**: the loader rejects unsupported `manifest_version`, missing required fields, or paths that escape the addon root.

## Next Steps

- Add a backend provider or UI contributor by including `backend_providers` or `ui_contributors` in `entry_points` (see [Addon Manifest Reference](../../addon-manifest-reference.md)).
- Explore the [Addons Guide](../../addons.md) for more on the runtime contract and generated-preview workflows.
- Use `aicodereviewer analyze-repo` to generate a preview scaffold for repository-specific review packs.

## Related Guides

- [Addons Guide](../../addons.md)
- [Addon Manifest Reference](../../addon-manifest-reference.md)
- [Review Quality Program](../../review-quality-program.md)
- [Contributing](../../contributing.md)