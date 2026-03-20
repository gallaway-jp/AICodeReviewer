# Architecture

This page is a contributor-oriented overview of how the system is structured.

## High-Level Flow

1. Input enters through the CLI or GUI.
2. Files are discovered by the scanner.
3. The orchestrator batches and routes work to a backend.
4. Review findings are normalized into model objects.
5. Interactive or GUI workflows let users inspect, resolve, ignore, skip, or fix issues.
6. The reporter writes the final outputs.

## Flow Diagram

```mermaid
flowchart TD
	CLI[CLI: main.py] --> ORCH[AppRunner / orchestration.py]
	GUI[GUI: app.py + mixins] --> ORCH
	ORCH --> SCAN[scanner.py]
	ORCH --> BACKENDS[backends/*]
	BACKENDS --> REVIEW[reviewer.py]
	REVIEW --> MODELS[models.py]
	MODELS --> INTERACTIVE[interactive.py or GUI Results]
	INTERACTIVE --> REPORT[reporter.py]
	CONFIG[config.py] --> CLI
	CONFIG --> GUI
	CONFIG --> BACKENDS
	CONFIG --> REPORT
```

## Component Diagram

```mermaid
flowchart LR
	subgraph Entry[Entry Points]
		CLI[CLI\nmain.py]
		GUI[GUI\napp.py + mixins]
	end

	subgraph Core[Core Review Pipeline]
		SCAN[scanner.py]
		ORCH[orchestration.py]
		REVIEW[reviewer.py]
		INTERACTIVE[interactive.py]
		REPORT[reporter.py]
		MODELS[models.py]
	end

	subgraph Infra[Infrastructure]
		CONFIG[config.py]
		BACKENDS[backends/*]
		AUTH[auth.py]
		BACKUP[backup.py]
	end

	CLI --> ORCH
	GUI --> ORCH
	ORCH --> SCAN
	ORCH --> REVIEW
	REVIEW --> BACKENDS
	REVIEW --> MODELS
	INTERACTIVE --> MODELS
	ORCH --> INTERACTIVE
	ORCH --> REPORT
	REPORT --> MODELS
	CONFIG --> CLI
	CONFIG --> GUI
	CONFIG --> BACKENDS
	CONFIG --> REVIEW
	AUTH --> CLI
	AUTH --> BACKENDS
	BACKUP --> ORCH
```

## CLI Sequence

```mermaid
sequenceDiagram
	participant User
	participant CLI as main.py
	participant Config as config.py
	participant Backend as create_backend()
	participant Runner as AppRunner
	participant Scanner as scanner.py
	participant Reviewer as reviewer.py
	participant Interactive as interactive.py
	participant Reporter as reporter.py

	User->>CLI: run command
	CLI->>Config: load settings / locale
	CLI->>Backend: create backend when needed
	CLI->>Runner: construct runner
	Runner->>Scanner: discover files for scope
	alt dry run
		Runner-->>User: list files and exit
	else full review
		Runner->>Reviewer: collect review issues
		Reviewer->>Backend: request model responses
		Runner->>Interactive: resolve / ignore / fix flow
		Runner->>Reporter: write reports
		Reporter-->>User: output paths and summary
	end
```

## Reviewer Pipeline Sequence

```mermaid
sequenceDiagram
	participant User
	participant Entry as CLI or GUI
	participant Runner as AppRunner
	participant Scanner as scanner.py
	participant Reviewer as collect_review_issues()
	participant Backend as AIBackend
	participant Parser as response_parser.py
	participant Results as Interactive CLI or GUI Results
	participant Fixer as fixer.py / AI Fix UI

	User->>Entry: start review
	Entry->>Runner: run(review_types, scope, backend)
	Runner->>Scanner: resolve target files
	Runner->>Reviewer: review discovered files
	Reviewer->>Backend: get_review(...) per batch or file
	Backend-->>Reviewer: raw model response
	Reviewer->>Parser: parse_review_response(...)
	Parser-->>Reviewer: ReviewIssue objects
	Reviewer-->>Runner: normalized issues
	Runner-->>Results: show issue list

	alt reviewer resolves or skips
		Results-->>Runner: update issue status only
	else reviewer requests AI Fix
		Results->>Fixer: apply_ai_fix(issue, client, review_type)
		Fixer->>Backend: get_fix(...) or fix-style review prompt
		Backend-->>Fixer: proposed file contents
		Fixer-->>Results: diff / preview payload
		Results-->>User: inspect changes and confirm
		User-->>Results: apply or cancel
	end
```

## Main Components

| Area | Responsibility |
|---|---|
| `main.py` | CLI argument parsing and entry-point flow |
| `gui/` | Desktop UI, state, workflows, health checks, settings, and log output |
| `scanner.py` | File discovery and diff-scope handling |
| `orchestration.py` | Review-session orchestration and backend coordination |
| `backends/` | Bedrock, Kiro, Copilot, and local LLM integrations |
| `reviewer.py` | Core review generation and advanced analysis behavior |
| `interactive.py` | Interactive CLI actions after findings are produced |
| `reporter.py` | Report generation in configured formats |
| `models.py` | Report and issue data structures |
| `config.py` | Config loading, defaults, and typed access |

## Backends

Backends share a common interface via `AIBackend` and are created through `create_backend()`.

Key design points:
- lazy imports keep startup lighter
- backends can stream partial output into the GUI status flow
- backend choice affects auth, timeouts, and transport details, not the higher-level review model

## GUI Structure

The GUI is composed around mixins:
- review tab behavior
- results and AI-fix behavior
- settings mapping and persistence
- backend health checks and model refreshes

This keeps the main application shell smaller while preserving a unified window and shared state.

## GUI Internal Roles

| Module | Responsibility |
|---|---|
| `gui/app.py` | top-level window, tabs, log plumbing, common status UI |
| `gui/review_mixin.py` | review setup, validation, execution start, dry-run flow |
| `gui/results_mixin.py` | issue cards, filtering, AI fix mode, sessions, finalization |
| `gui/settings_mixin.py` | config editing and persistence |
| `gui/health_mixin.py` | backend health checks and model refresh behavior |
| `gui/widgets.py` | shared widgets, tooltips, log handler |

## Documentation Rule

When product behavior changes, update:
- the relevant user-facing guide in `docs/`
- any impacted example or walkthrough
- contributor docs if the change affects development workflows

## Related Guides

- [Contributing](contributing.md)
- [Configuration Reference](configuration.md)
- [Release Process](release-process.md)