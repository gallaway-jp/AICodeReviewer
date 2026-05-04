# Diff Review Workflow

Use this guide when you want to review only changed files or a specific patch instead of the whole project.

## Before You Start

You need:

- AICodeReviewer installed in the current environment
- one configured backend: Bedrock, Kiro, Copilot, or Local LLM
- a repository or project path to review
- either a commit range or a patch file

If you have not run a first end-to-end CLI review yet, use [First CLI Review](../getting-started/first-cli-review.md) first.

## Expected Result

By the end of this guide you will:

- confirm the selected diff target with a dry run
- run a focused real review on only the selected changes
- know when to use a commit range versus a patch file

## Step 1: Choose The Diff Input

Use one diff source per run:

- use `--commits` when the changes already exist in local git history
- use `--diff-file` when you already have an exported patch file

Important rule:

- use either `--commits` or `--diff-file`, not both

## Step 2: Dry Run A Commit-Range Review First

Start with a dry run so you can confirm that the selected changes are the ones you actually meant to review:

```bash
aicodereviewer . --scope diff --commits HEAD~3..HEAD --type security --dry-run
```

What to check:

- the commit range matches the intended change set
- the review bundle is focused enough for the patch size
- the run completes without validation errors

## Step 3: Run The Real Diff Review

Once the dry run looks right, run the real review on the same diff target:

```bash
aicodereviewer . --scope diff --commits HEAD~3..HEAD --type security,testing --programmers Alice --reviewers Bob --backend local
```

Keep the review bundle focused when the diff is small or narrowly scoped.

## Step 4: Use A Patch File When The Diff Is Already Exported

If the review input already exists as a patch file, point the diff review at that file instead of a commit range:

```bash
aicodereviewer . --scope diff --diff-file changes.diff --type security --programmers Alice --reviewers Bob --backend local
```

This is the better fit when you are reviewing a shared patch outside your local git history.

## Step 5: Keep The Review Narrow

Diff review is usually the best starting point for:

- pull-request review
- pre-merge validation
- targeted regression checking

If you need broader repository context than the patch alone provides, move back to project scope instead of widening the diff bundle indefinitely.

## If Something Looks Wrong

- If validation fails, confirm you did not pass both `--commits` and `--diff-file`.
- If the diff target looks wrong, fix the commit range or patch file and rerun the dry run.
- If the review still feels too broad, reduce the review bundle before retrying.
- If you need to compare the changes against an external requirements document, continue with [Specification Review Workflow](specification-review-workflow.md).

## Related Guides

- [First CLI Review](../getting-started/first-cli-review.md)
- [Specification Review Workflow](specification-review-workflow.md)
- [CLI Guide](../../cli.md)
- [Troubleshooting](../../troubleshooting.md)