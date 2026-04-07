# AICodeReviewer Examples

This directory is for hands-on walkthroughs and demo material.

Use the main docs for setup and reference:
- [Project README](../README.md)
- [Documentation Hub](../docs/README.md)
- [Getting Started](../docs/getting-started.md)
- [CLI Guide](../docs/cli.md)
- [Addons Guide](../docs/addons.md)
- [Review Types Reference](../docs/review-types.md)

## What Is Here

- [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) — guided example run against the sample project
- [DEMO_WALKTHROUGH_JA.md](DEMO_WALKTHROUGH_JA.md) — Japanese walkthrough
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — command and issue cheat sheet
- [sample_project/README.md](sample_project/README.md) — inventory of intentional issues in the sample project
- `run_demo.py` — helper script for local demo runs
- [addon-secure-defaults/addon.json](addon-secure-defaults/addon.json) — manifest-only addon example that contributes review packs
- [addon-echo-backend/addon.json](addon-echo-backend/addon.json) — code-backed addon example that contributes a backend provider
- [addon-editor-hooks/addon.json](addon-editor-hooks/addon.json) — code-backed addon example that contributes editor and diff-preview hooks

## When To Use Examples

Use `examples/` when you want to:
- see realistic CLI output before using the tool on your code
- validate a backend or prompt flow against known intentional issues
- demo the project to teammates
- test documentation commands without risking a real codebase

## Quick Demo

```bash
aicodereviewer examples/sample_project --type security --programmers Demo --reviewers Reviewer
```

Expected outputs are described in the walkthrough and quick-reference documents.

## Addon Examples

- `addon-secure-defaults/` shows the manifest shape for review-pack contributions.
- `addon-echo-backend/` shows a code-backed addon that registers an in-process backend provider through `entry_points.backend_providers` and contributes a Settings surface through `entry_points.ui_contributors`.
- `addon-editor-hooks/` shows a code-backed addon that registers editor hooks through `entry_points.editor_hooks`, returns diagnostics for the popup editor and diff preview, and observes lifecycle plus staged-preview events.

Use [docs/addons.md](../docs/addons.md) for the maintained contract and discovery rules behind these examples.
