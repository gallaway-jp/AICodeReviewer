# Guided Workflows

Quick, step-by-step walkthroughs for the most common tasks. Each guide is intentionally narrow and includes concrete commands, expected outputs, and troubleshooting tips.

## Get Started

- [First CLI Review](getting-started/first-cli-review.md) — run your first end-to-end review from the terminal.
- [First GUI Session](getting-started/first-gui-session.md) — set up and run a review in the desktop app.

## Review Targeted Changes

- [Diff Review Workflow](reviews/diff-review-workflow.md) — review a commit range or patch file without scanning the whole project.
- [Specification Review Workflow](reviews/specification-review-workflow.md) — compare code against a requirements or design document.

## Automate & Integrate

- [Local HTTP Workflow](automation/local-http-review-workflow.md) — drive reviews from scripts, CI, or other tools via the local API.

## Extend

- [Build A Basic Addon](addons/build-basic-addon.md) — create a minimal addon and contribute a review pack.

## How to use these guides

1. Pick the workflow that matches your immediate goal.
2. Follow the steps in order; each step includes the exact commands or UI actions you need.
3. If something fails, check the troubleshooting section at the bottom of the guide before opening an issue.

## Next steps

After completing a workflow, consult the corresponding reference pages for deeper details:

- [CLI Guide](../cli.md) — full flag and tool-mode reference.
- [Review Types Reference](../review-types.md) — review-type semantics and coverage.
- [GUI Guide](../gui.md) — complete tab-by-tab UI reference.
- [HTTP API Guide](../http-api.md) — route and payload contracts.
- [Addons Guide](../addons.md) — runtime contract and discovery details.

## Feedback

If a guide is unclear or omits a critical step, open an issue or submit a PR — these pages are meant to be living documentation that evolves with the product.