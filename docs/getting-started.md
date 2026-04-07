# Getting Started

This guide gets you from install to a successful first review.

## Prerequisites

- Python 3.11 or newer
- A backend that matches your environment:
  - AWS Bedrock
  - Amazon Kiro CLI via WSL
  - GitHub Copilot CLI
  - A local LLM server

## Install

```bash
git clone <repo-url>
cd AICodeReviewer
pip install -e ".[gui]"
```

If you only need the CLI:

```bash
pip install -e .
```

## First Run Checklist

1. Pick a backend.
2. Configure credentials or local server access.
3. Check connectivity.
4. Run a dry run.
5. Run a real review.

## Check Your Backend

```bash
aicodereviewer --check-connection --backend bedrock
aicodereviewer --check-connection --backend kiro
aicodereviewer --check-connection --backend copilot
aicodereviewer --check-connection --backend local
```

## First CLI Review

```bash
aicodereviewer . --type security --programmers Alice --reviewers Bob
```

Notes:
- `--programmers` and `--reviewers` are required for normal reviews.
- They are not required for `--dry-run`.
- Pass `--backend` explicitly when you want deterministic backend selection.

## First Dry Run

Use this before spending tokens or waiting on a backend:

```bash
aicodereviewer . --type all --dry-run
```

## First GUI Session

```bash
aicodereviewer --gui
```

In the GUI:
1. Choose a project or diff scope on the Review tab.
2. Select one or more review types.
3. Pick a backend.
4. Enter programmer and reviewer names.
5. Run a dry run or start the review.

If you find yourself using the same recommended bundle repeatedly, pin the current review-type selection in the Review tab. Pinned defaults are deliberate startup defaults; ordinary last-used selections are only restored when no pin is set.

## Recommended Reading

- [User Manual](user-manual.md)
- [Backend Guide](backends.md)
- [CLI Guide](cli.md)
- [GUI Guide](gui.md)
- [Configuration Reference](configuration.md)
- [Troubleshooting](troubleshooting.md)