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