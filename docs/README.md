# AICodeReviewer Documentation

This directory now contains the maintained documentation set for AICodeReviewer.

The goal of this docs set is simple:
- help users install, configure, and run the tool reliably
- help contributors understand the architecture and development workflow
- keep reference material aligned with the actual codebase and tests

## Start Here

- [User Manual](user-manual.md)
- [Getting Started](getting-started.md)
- [Addons Guide](addons.md)
- [Backend Guide](backends.md)
- [CLI Guide](cli.md)
- [HTTP API Guide](http-api.md)
- [Local HTTP Quick Reference](local-http-quick-reference.md)
- [Security Review](security.md)
- [GUI Guide](gui.md)
- [GUI UX Audit And Backlog](gui-ux-audit.md)
- [Configuration Reference](configuration.md)
- [Review Types Reference](review-types.md)
- [Quality Benchmarks](benchmarks.md)
- [Review Quality Program](review-quality-program.md)
- [Review Quality Log](review-quality-log.md)
- [Reports and Outputs](reports.md)
- [Troubleshooting](troubleshooting.md)
- [Architecture](architecture.md)
- [Contributing](contributing.md)
- [Repository Maintenance Plan](repository-maintenance.md)
- [Release Process](release-process.md)
- [Windows Installer Guide](windows-installer.md)

## Documentation Principles

- Documentation is the source of truth for supported user-facing behavior, workflows, configuration, and operational expectations.
- Code and tests must implement and verify the documented contract.
- For internal implementation details not yet covered by the docs, code and tests remain authoritative.
- Root `README.md` stays short and task-oriented.
- Deep reference material lives in `docs/`.
- `examples/` is for hands-on walkthroughs and sample-project usage.
- Generated API HTML is no longer the primary documentation format.

## Audience Map

Use these guides if you are:

- Starting from the shortest task-oriented path: read [User Manual](user-manual.md)
- A first-time user: start with [Getting Started](getting-started.md)
- Building or debugging addons: read [Addons Guide](addons.md)
- Choosing a backend: read [Backend Guide](backends.md)
- Running reviews from the terminal: read [CLI Guide](cli.md)
- Integrating with the local HTTP surface: read [HTTP API Guide](http-api.md)
- Changing local API routes, embedding, or tests: read [Local HTTP Quick Reference](local-http-quick-reference.md)
- Reviewing trust boundaries and hardening status: read [Security Review](security.md)
- Using the desktop app: read [GUI Guide](gui.md)
- Using the desktop benchmark browser or detachable desktop pages: read [GUI Guide](gui.md)
- Tuning settings: read [Configuration Reference](configuration.md)
- Understanding review coverage: read [Review Types Reference](review-types.md)
- Running review-quality regression checks: read [Quality Benchmarks](benchmarks.md)
- Running tranche-by-tranche repository quality adjudication: read [Review Quality Program](review-quality-program.md)
- Reviewing completed tranche logs and adjudication outcomes: read [Review Quality Log](review-quality-log.md)
- Integrating outputs into workflows: read [Reports and Outputs](reports.md)
- Fixing setup problems: read [Troubleshooting](troubleshooting.md)
- Contributing to the project: read [Contributing](contributing.md)
- Planning repository cleanup and release normalization: read [Repository Maintenance Plan](repository-maintenance.md)
- Understanding addon/runtime internals: read [Architecture](architecture.md)
- Preparing and documenting a release: read [Release Process](release-process.md)
- Working on the native Windows installer path: read [Windows Installer Guide](windows-installer.md)

## Scope of This Revamp

The previous `docs/` directory mixed generated HTML, internal planning notes, and user-facing documentation. This curated set replaces that structure with maintainable Markdown guides.