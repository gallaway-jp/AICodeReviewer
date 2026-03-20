# Demo Walkthrough

This is the canonical English walkthrough for the sample project.

## Goal

Use the sample project to validate that:
- your environment is configured correctly
- the CLI review workflow behaves as expected
- findings, actions, and report outputs make sense before you run the tool on a real project

## Before You Start

Review the intentional issue inventory:

```bash
python -c "from pathlib import Path; print((Path('examples/sample_project/README.md')).read_text(encoding='utf-8'))"
```

Or open [sample_project/README.md](sample_project/README.md) directly.

## Suggested First Command

Start with a dry run:

```bash
aicodereviewer examples/sample_project --type security --dry-run
```

Then run a real review:

```bash
aicodereviewer examples/sample_project --type security --programmers "Demo User" --reviewers "AI Reviewer"
```

## What Happens During A Review

1. The project is scanned.
2. Files are selected for the chosen scope.
3. The backend analyzes the content.
4. Findings are presented interactively.
5. Final reports are written using the configured output formats.

## Interactive Actions

During CLI review, you will see action prompts for each issue.

Current workflow includes:
- `RESOLVED`
- `IGNORE`
- `AI FIX`
- `VIEW CODE`
- `SKIP`
- force-resolve when verification fails and you choose to override

## Example Review Flow

Security reviews should surface issues such as:
- SQL injection in `user_auth.py`
- weak password hashing
- unsafe deserialization
- hardcoded credentials
- predictable tokens

Performance reviews should surface issues such as:
- nested-loop duplicate detection
- repeated I/O
- inefficient list operations

Best-practices reviews should surface issues such as:
- magic numbers
- naming problems
- duplicated logic
- global mutable state

Error-handling reviews should surface issues such as:
- missing exception handling
- bare `except` clauses
- missing validation

Maintainability reviews should surface issues such as:
- deep nesting
- oversized functions
- cryptic names

## Reports

By default, reports are timestamped. Output formats are controlled through `config.ini`.

Typical outputs include:
- `review_report_YYYYMMDD_HHMMSS.json`
- `review_report_YYYYMMDD_HHMMSS_summary.txt`

If Markdown output is enabled, a Markdown report is generated too.

You can force a stable output filename:

```bash
aicodereviewer examples/sample_project --type performance --programmers Demo --reviewers Reviewer --output examples/demo_outputs/performance.json
```

## Suggested Demo Sequence

1. Run `security`
2. Run `performance`
3. Run `best_practices`
4. Run `error_handling`
5. Run `maintainability`

This sequence makes it easy to compare how different review types interpret the same codebase.

## Related Guides

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
- [examples/README.md](README.md)
- [Project README](../README.md)
- [CLI Guide](../docs/cli.md)
