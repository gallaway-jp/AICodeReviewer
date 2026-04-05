# AICodeReviewer

AICodeReviewer is an AI-assisted code review tool for teams that want repeatable code-quality, architecture, compliance, and specification checks across a CLI and a desktop GUI.

It supports four backends:
- AWS Bedrock
- Amazon Kiro CLI via WSL
- GitHub Copilot CLI
- Local LLM servers via LM Studio, Ollama, OpenAI-compatible, or Anthropic-compatible APIs

It supports 22 selectable review types across quality, architecture, and compliance domains, plus an interactive CLI review flow and a GUI with review, results, settings, and log views.

The repository also includes holistic benchmark fixtures that score review quality against known cross-file and UI/UX scenarios.

Implementation snapshot:
- `src/aicodereviewer/execution/` is the typed execution and session core used by both CLI and GUI flows.
- `AppRunner` remains the public orchestration entry point, but it now acts primarily as a compatibility facade over the execution service and runner-state models.
- GUI session save/load still uses the same JSON shape on disk, while the in-memory restore/finalize path now round-trips through typed session state.

## What This Repository Contains

- CLI entry point and interactive review workflow
- CustomTkinter GUI
- Backend integrations for Bedrock, Kiro, Copilot, and local LLMs
- Structured report generation in JSON, text, and Markdown
- Example projects and walkthroughs for demo use
- Holistic benchmark fixtures and runner scripts for review-quality regression checks

## Install

Python 3.11 or newer is required.

```bash
git clone <repo-url>
cd AICodeReviewer
pip install -e ".[gui]"
```

Core-only install:

```bash
pip install -e .
```

Development install:

```bash
pip install -e ".[all]"
```

## Quick Start

Run a basic CLI review:

```bash
aicodereviewer . --type security --programmers Alice --reviewers Bob
```

Run a combined review:

```bash
aicodereviewer . --type security,performance,testing --programmers Alice --reviewers Bob
```

Run a dry run without backend calls:

```bash
aicodereviewer . --type all --dry-run
```

Launch the GUI:

```bash
aicodereviewer --gui
```

Check backend connectivity:

```bash
aicodereviewer --check-connection --backend bedrock
aicodereviewer --check-connection --backend local
```

Start the local HTTP API:

```bash
aicodereviewer serve-api --host 127.0.0.1 --port 8765
```

## GUI Preview

![AICodeReviewer GUI Results tab](docs/images/gui-results-tab.png)

The desktop GUI now uses a clearer sectioned Review tab and a Results tab with overview cards, quick triage filters, and richer issue cards. The Review tab can also pin a recommended review-type bundle as the startup default, distinct from ordinary last-used selections. See [docs/gui.md](docs/gui.md) for the full workflow and all screenshots.

## Documentation

- Documentation is the source of truth for supported user-facing behavior, workflows, configuration, and operational expectations.
- Code and tests implement and verify that documented contract.
- For internal implementation details not yet covered by the docs, code and tests remain authoritative.

See [docs/README.md](docs/README.md) for the maintained documentation set.

Start with [docs/README.md](docs/README.md).

Core guides:
- [Getting Started](docs/getting-started.md)
- [Backend Guide](docs/backends.md)
- [CLI Guide](docs/cli.md)
- [GUI Guide](docs/gui.md)
- [Configuration Reference](docs/configuration.md)
- [Review Types Reference](docs/review-types.md)
- [Quality Benchmarks](docs/benchmarks.md)
- [Reports and Outputs](docs/reports.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Architecture](docs/architecture.md)
- [Contributing](docs/contributing.md)

Examples:
- [examples/README.md](examples/README.md)
- [examples/addon-editor-hooks/addon.json](examples/addon-editor-hooks/addon.json)

## Local HTTP API

The shared local HTTP API exposes the same review runtime used by the desktop GUI and the CLI tool-mode flows.

Start it explicitly from the CLI:

```bash
aicodereviewer serve-api --host 127.0.0.1 --port 8765
```

Or enable the embedded local API from the desktop Settings panel.

Common routes:
- `GET /api/backends`
- `GET /api/review-types`
- `GET /api/review-presets`
- `POST /api/recommendations/review-types`
- `GET /api/jobs`
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `GET /api/jobs/{job_id}/report`
- `GET /api/jobs/{job_id}/artifacts`
- `GET /api/jobs/{job_id}/artifacts/{artifact_key}/raw`
- `GET /api/events`
- `GET /api/jobs/{job_id}/events`

Recommendation requests accept the same targeting inputs already used by the GUI and CLI, including project path, diff scope, `selected_files`, and diff-filter fields. Example:

```json
{
	"path": ".",
	"scope": "project",
	"backend_name": "local",
	"target_lang": "en",
	"selected_files": ["src/app.py"],
	"diff_filter_file": "changes.diff"
}
```

The response includes the recommended review bundle, optional preset, project signals, rationale, and the recommendation source.

Quality regression:
- Holistic benchmark fixtures live under [benchmarks/holistic_review/fixtures](benchmarks/holistic_review/fixtures)
- Run the benchmark runner with `python tools/run_holistic_benchmarks.py --backend <backend> --skip-health-check`
- See [docs/benchmarks.md](docs/benchmarks.md) for fixture structure, runner flags, and update guidance

## Feature Summary

- 22 selectable review types
- Project and diff review scopes
- Multi-type reviews in one session
- Interactive CLI workflow with resolve, ignore, AI fix, view code, skip, and force-resolve paths
- GUI workflows for review setup, issue management, AI fix mode, session save/load, and output logs
- Structured outputs in JSON, TXT, and Markdown
- English and Japanese localization support

## Backend Notes

- Pass `--backend` explicitly in scripts and automation for predictable execution.
- The GUI uses saved configuration and lets you switch backends interactively.
- Local LLM support includes `lmstudio`, `ollama`, `openai`, and `anthropic` API modes.
- The Local LLM settings section now includes an `Enable Web Search` toggle. When enabled, the local backend fetches high-level public guidance for the active review type without sending your source code to the search provider.
- Performance reviews also include a narrow deterministic stale-cache supplement when the code clearly shows a cache read/write split and the Local LLM misses it entirely.
- Best-practices reviews also include a narrow deterministic caller/return-shape supplement when the code clearly shows a producer changed its returned dict keys but a caller still reads a removed field and the Local LLM misses that contract break entirely.

## Repository Status

The documentation now uses curated Markdown guides instead of generated HTML API pages. The code and tests are the source of truth for product behavior.

The current execution/session architecture is split intentionally:
- user-facing CLI and GUI entry points stay stable
- shared execution, deferred-report, and saved-session behavior lives in the typed execution package
- contributor-oriented implementation details are summarized in [docs/architecture.md](docs/architecture.md)

## License

See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
