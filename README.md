# AICodeReviewer

AICodeReviewer is an AI-assisted code review tool for teams that want repeatable code-quality, architecture, compliance, and specification checks across a CLI and a desktop GUI.

It supports four backends:
- AWS Bedrock
- Amazon Kiro CLI via WSL
- GitHub Copilot CLI
- Local LLM servers via LM Studio, Ollama, OpenAI-compatible, or Anthropic-compatible APIs

It supports 20 selectable review types across quality, architecture, and compliance domains, plus an interactive CLI review flow and a GUI with review, results, settings, and log views.

## What This Repository Contains

- CLI entry point and interactive review workflow
- CustomTkinter GUI
- Backend integrations for Bedrock, Kiro, Copilot, and local LLMs
- Structured report generation in JSON, text, and Markdown
- Example projects and walkthroughs for demo use

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

## GUI Preview

![AICodeReviewer GUI Results tab](docs/images/gui-results-tab.png)

## Documentation

- Documentation is the source of truth for supported user-facing behavior, workflows, configuration, and operational expectations.
- Code and tests implement and verify that documented contract.
- For internal implementation details not yet covered by the docs, code and tests remain authoritative.

See [docs/README.md](D:/Development/Python/AICodeReviewer/docs/README.md) for the maintained documentation set.

Start with [docs/README.md](docs/README.md).

Core guides:
- [Getting Started](docs/getting-started.md)
- [Backend Guide](docs/backends.md)
- [CLI Guide](docs/cli.md)
- [GUI Guide](docs/gui.md)
- [Configuration Reference](docs/configuration.md)
- [Review Types Reference](docs/review-types.md)
- [Reports and Outputs](docs/reports.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Architecture](docs/architecture.md)
- [Contributing](docs/contributing.md)

Examples:
- [examples/README.md](examples/README.md)

## Feature Summary

- 20 selectable review types
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

## Repository Status

The documentation now uses curated Markdown guides instead of generated HTML API pages. The code and tests are the source of truth for product behavior.

## License

See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
