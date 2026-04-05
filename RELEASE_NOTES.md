# Release Notes

This file records notable product changes by release.

Current setup, installation, backend configuration, and usage guidance live in:
- [README.md](README.md)
- [docs/README.md](docs/README.md)

Maintainer release workflow guidance lives in:
- [docs/release-process.md](docs/release-process.md)

## Versioning Note

This changelog preserves historical release milestones. Repository metadata such as the package version in `pyproject.toml` is the source of truth for the current package build version.

---

## Unreleased

Local LLM review-quality improvements focused on holistic, cross-file issue detection and reproducible benchmarking.

### Added
- Local LLM optional web-guidance support with `enable_web_search = true` by default in `[local_llm]`
- GUI Local LLM settings toggle for web guidance
- Tool-mode and benchmark-runner runtime overrides: `--local-enable-web-search` and `--local-disable-web-search`
- Repeated holistic benchmark runs with stability summaries via `tools/run_holistic_benchmarks.py --runs N`
- `tools/compare_review_reports.py` for issue-shape deltas between two review artifacts or tool-mode envelopes
- A new holistic `best_practices` fixture for direct reads of private backing state instead of a collaborator's public filtered accessor
- CLI review-type bundle presets such as `runtime_safety`, `code_health`, `interface_platform`, `product_surface`, and `release_safety` for stable multi-review sessions
- GUI review-type preset picker for the same stable multi-review bundles, plus `--list-type-presets` to print preset definitions directly from the CLI

### Changed
- Local LLM prompt enrichment now uses privacy-constrained, high-level public guidance without sending repository source code to the search provider
- Holistic review prompts now ask more explicitly for downstream impact when validation drift allows unvalidated or incompletely validated input to reach runtime use
- Benchmark matching now accepts broader semantic aliases for architecture, validation, cache/state consistency, caller/callee drift, transaction-boundary loss, and invalidation wording
- Local holistic benchmark recovery now short-circuits `reasoning_content only` failures earlier for supplement-covered review types so deterministic fallback logic runs before a fixture exhausts its subprocess timeout budget
- Holistic benchmark runs now derive a child tool-mode review timeout automatically from `--fixture-timeout-seconds`, with a tighter default cap for Local backends so sampled Local checkpoints finish in one invocation without manual `--timeout` tuning
- Review execution and GUI session restore/finalize flows now run through a typed execution/session layer, with `AppRunner` retained as the stable CLI and GUI orchestration facade
- Saved GUI sessions still preserve the same legacy JSON payload shape on disk while the in-memory restore path now round-trips through typed session-state models

### Fixed
- Local LLM combined and per-file reviews now retry once on transient backend errors before failing
- Response parsing now preserves richer finding metadata, infers related files from evidence text, and promotes cache findings to cross-file scope when sibling findings prove broader context
- Performance reviews now add a narrow deterministic stale-cache finding when the model misses an obvious cache read/write split with no invalidation
- Best-practices reviews now add a narrow deterministic caller/return-shape finding when the model misses an obvious producer/caller dict-shape contract break
- The broader Local LLM web-enabled holistic benchmark artifacts now reevaluate cleanly at `8/8` passed with `overall_score = 1.0`
- Holistic benchmark runs now support per-fixture subprocess bounds via `--fixture-timeout-seconds`, preserving scoreable timeout envelopes instead of hanging the full batch
- Local holistic benchmark fallback coverage now includes the post-Phase4B `error_handling`, `license`, `maintainability`, `api_design`, and `scalability` fixture shapes, restoring the bounded Local sampled checkpoint to `8/8` passed with `overall_score = 1.0`
- Multi-type sessions that include `specification` now preserve the other selected review-type focus blocks instead of collapsing the user prompt into the specification-only shortcut path

---

## v2.0.1

Maintenance release focused on UX improvements and reliability fixes.

### Added
- AI Fix batch mode from the Results tab
- Diff preview before applying AI-generated changes
- More responsive cancellation behavior during review sessions

### Fixed
- Windows WinError 206 for large Copilot CLI command lines
- `UnicodeDecodeError` on Windows with `cp932` environments
- Copilot long-prompt failure cases by routing large prompts through a temp file
- Missing "Fix failed" status reporting for AI-fix failures
- Type-annotation coverage improvements across the codebase

---

## v2.0.0

Major release introducing multi-backend support, multi-type reviews, and the GUI.

### Added
- Multi-type reviews in one session with comma-separated `--type` values and `--type all`
- AWS Bedrock improvements including lazy validation and retry/backoff behavior
- Kiro CLI backend via WSL on Windows
- GitHub Copilot CLI backend
- CustomTkinter GUI with review, results, settings, and log tabs
- New review types introduced in this release: `dependency`, `concurrency`, `api_design`, `data_validation`
- Interactive review actions for skip and force-resolve flows
- Improved report summaries with richer severity and review-type breakdowns

### Changed
- English became the default output language, with Japanese still supported
- The `--type` flag expanded from single-value usage to comma-separated multi-value usage

### Breaking Changes
- Review-type inventory expanded relative to pre-2.0 releases
- Backend import paths shifted to the `aicodereviewer.backends.*` structure
- Minimum supported Python version was raised during the 2.0 line

---

## v0.1.0

Initial public Windows-focused release.

### Highlights
- First public packaged release
- Interactive review workflow for resolving, ignoring, fixing, and viewing code
- Multi-language scanning and review support
- JSON and summary report generation
- Configurable performance and rate-limit behavior via `config.ini`

### Historical Note

The original v0.1.0 release included a Windows executable distribution. That packaging model is historical context only and is not the primary usage path documented in the current repository.

### Historical Assets

The original release page included screenshots and executable artifacts. Those references are intentionally not repeated here as current installation guidance.