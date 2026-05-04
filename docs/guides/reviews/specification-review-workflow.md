# Specification Review Workflow

Use this guide when you want AICodeReviewer to compare code against an external requirements or design document.

## Before You Start

You need:

- AICodeReviewer installed in the current environment
- one configured backend: Bedrock, Kiro, Copilot, or Local LLM
- a readable specification file such as `requirements.md`
- a project path, commit range, or diff target to review

## Expected Result

By the end of this guide you will:

- run a focused specification review against a real spec file
- know when to combine `specification` with another review type
- know when to combine specification review with diff scope

## Step 1: Start With A Spec-Only Dry Run

Validate the target and specification file before spending backend time on a full run:

```bash
aicodereviewer . --type specification --spec-file requirements.md --dry-run
```

What to check:

- the target path is the repository or project you intended
- the specification file is readable
- the run completes without validation errors

## Step 2: Run The Real Specification Review

Once the dry run looks right, run the focused specification review:

```bash
aicodereviewer . --type specification --spec-file requirements.md --programmers Alice --reviewers Bob --backend local
```

Starting with a specification-only run is usually easier to validate than mixing several review types immediately.

## Step 3: Add Another Review Type Only When You Need It

If you want specification drift plus a broader quality pass, combine `specification` with one additional review type:

```bash
aicodereviewer . --type specification,maintainability --spec-file requirements.md --programmers Alice --reviewers Bob --backend local
```

The same `--spec-file` content is applied to the mixed review prompt.

## Step 4: Combine With Diff Scope For Recent Changes

If you only want to check a recent change against the requirements document, combine `specification` with diff scope:

```bash
aicodereviewer . --scope diff --commits HEAD~3..HEAD --type specification --spec-file requirements.md --programmers Alice --reviewers Bob --backend local
```

Use this pattern when the question is whether a recent patch preserved an agreed workflow or data contract.

## If Something Looks Wrong

- If validation fails immediately, confirm that `--spec-file` points to a readable file.
- If the result is too hard to interpret, rerun as `specification` only before mixing other review types.
- If you only care about a recent patch, move to diff scope instead of reviewing the whole project.
- If you need the full review-type contract, use [Review Types Reference](../../review-types.md).

## Related Guides

- [Diff Review Workflow](diff-review-workflow.md)
- [CLI Guide](../../cli.md)
- [Review Types Reference](../../review-types.md)
- [Troubleshooting](../../troubleshooting.md)