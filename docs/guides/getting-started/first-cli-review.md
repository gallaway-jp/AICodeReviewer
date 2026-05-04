# First CLI Review

Use this guide when you want the fastest end-to-end review from the terminal without learning the full CLI surface first.

## Before You Start

You need:

- Python 3.11 or newer
- AICodeReviewer installed in the current environment
- one configured backend: Bedrock, Kiro, Copilot, or Local LLM
- a project or repository you want to review

If you have not chosen a backend yet, read [Backend Guide](../../backends.md) first.

## Expected Result

By the end of this guide you will:

- confirm your backend connection works
- confirm the target selection with a dry run
- complete one focused real review from the CLI

## Step 1: Check That The Backend Works

Run a connection check before spending backend time on a full review:

```bash
aicodereviewer --check-connection --backend local
```

Replace `local` with the backend you actually intend to use.

Use [Backend Guide](../../backends.md) if you need backend-specific setup details.

## Step 2: Run A Dry Run First

Use a dry run to confirm the target and review scope without generating a real report:

```bash
aicodereviewer . --type all --dry-run
```

What to check:

- the target path is the repository you intended
- the run completes without validation errors
- the scope is broad enough to cover the area you want to review

If the target looks wrong, fix the path or scope before running a real review.

## Step 3: Run A Focused Real Review

Start with a narrow bundle instead of `all` for the first real run:

```bash
aicodereviewer . --type security --programmers Alice --reviewers Bob --backend local
```

Why start narrow:

- the result set is easier to validate
- backend time and token use stay lower
- it is easier to tell whether the first run matches expectations

## Step 4: Move To Diff Review If The Run Is Too Broad

If the first real review is larger or slower than you want, move to [Diff Review Workflow](../reviews/diff-review-workflow.md) instead of repeating the full CLI reference here.

Common next moves:

- use `--scope diff` with `--commits` or `--diff-file`
- choose a smaller review bundle instead of `--type all`
- pass `--backend` explicitly in scripts and repeatable runs

## If Something Looks Wrong

- If the backend check fails, fix credentials, local model availability, or backend-specific configuration first.
- If validation fails, confirm you supplied required fields such as `--programmers` and `--reviewers` for a real run.
- If the run is too broad, move to diff scope or reduce the review-type bundle.
- If the review target is right but the workflow is too interactive for your use case, move to the tool-mode commands in [CLI Guide](../../cli.md).

## Related Guides

- [User Manual](../../user-manual.md)
- [CLI Guide](../../cli.md)
- [Backend Guide](../../backends.md)
- [Diff Review Workflow](../reviews/diff-review-workflow.md)
- [Troubleshooting](../../troubleshooting.md)