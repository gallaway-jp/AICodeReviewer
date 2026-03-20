# AICodeReviewer Documentation

This directory now contains the maintained documentation set for AICodeReviewer.

The goal of this docs set is simple:
- help users install, configure, and run the tool reliably
- help contributors understand the architecture and development workflow
- keep reference material aligned with the actual codebase and tests

## Start Here

- [Getting Started](getting-started.md)
- [Backend Guide](backends.md)
- [CLI Guide](cli.md)
- [GUI Guide](gui.md)
- [Configuration Reference](configuration.md)
- [Review Types Reference](review-types.md)
- [Reports and Outputs](reports.md)
- [Troubleshooting](troubleshooting.md)
- [Architecture](architecture.md)
- [Contributing](contributing.md)
- [Release Process](release-process.md)

## Documentation Principles

- The code and tests are the source of truth.
- Root `README.md` stays short and task-oriented.
- Deep reference material lives in `docs/`.
- `examples/` is for hands-on walkthroughs and sample-project usage.
- Generated API HTML is no longer the primary documentation format.

## Audience Map

Use these guides if you are:

- A first-time user: start with [Getting Started](getting-started.md)
- Choosing a backend: read [Backend Guide](backends.md)
- Running reviews from the terminal: read [CLI Guide](cli.md)
- Using the desktop app: read [GUI Guide](gui.md)
- Tuning settings: read [Configuration Reference](configuration.md)
- Understanding review coverage: read [Review Types Reference](review-types.md)
- Integrating outputs into workflows: read [Reports and Outputs](reports.md)
- Fixing setup problems: read [Troubleshooting](troubleshooting.md)
- Contributing to the project: read [Contributing](contributing.md)
- Preparing and documenting a release: read [Release Process](release-process.md)

## Scope of This Revamp

The previous `docs/` directory mixed generated HTML, internal planning notes, and user-facing documentation. This curated set replaces that structure with maintainable Markdown guides.