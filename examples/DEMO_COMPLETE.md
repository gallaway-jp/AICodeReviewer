# AICodeReviewer Demo Package

This file is the compact overview of the example/demo bundle.

## Contents

- [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) — canonical English walkthrough
- [DEMO_WALKTHROUGH_JA.md](DEMO_WALKTHROUGH_JA.md) — Japanese walkthrough
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — commands, actions, and expected issue areas
- [sample_project/README.md](sample_project/README.md) — intentional issue inventory
- `run_demo.py` — local helper that prints example commands and output locations

## What The Demo Covers

The sample project is intentionally flawed across five main areas:
- security
- performance
- best practices
- error handling
- maintainability

The goal is not to be exhaustive across all 20 review types. The goal is to provide a predictable, low-risk project for validating the core CLI review flow, issue presentation, and report generation.

## Fastest Way To Start

```bash
aicodereviewer examples/sample_project --type security --programmers Demo --reviewers Reviewer
```

If you want to avoid backend calls while checking paths and options first:

```bash
aicodereviewer examples/sample_project --type security --dry-run
```

## What To Expect

- interactive issue handling in the CLI
- report generation in configured output formats
- intentionally low quality scores before fixes
- clear examples of AI fix, ignore, skip, and resolve workflows

## Recommended Reading Order

1. [sample_project/README.md](sample_project/README.md)
2. [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md)
3. [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

Then go back to the main docs:
- [Project README](../README.md)
- [Documentation Hub](../docs/README.md)
