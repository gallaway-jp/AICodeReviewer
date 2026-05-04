# First GUI Session

Use this guide when you want review setup, triage, AI-fix preview, session save/load, and report finalization in one desktop workflow.

## Before You Start

You need:

- AICodeReviewer installed with GUI support
- one configured backend: Bedrock, Kiro, Copilot, or Local LLM
- a project or diff target you want to review

Launch the app:

```bash
aicodereviewer --gui
```

## Expected Result

By the end of this guide you will:

- start the desktop app and configure a first review from the Review tab
- inspect the findings in the Results tab
- know where AI Fix, session save/load, and final report generation fit in the normal desktop workflow

## Step 1: Set Up The First Review

![Review tab screenshot](../../images/gui-review-tab.png)

1. Open the Review tab.
2. Choose project or diff scope.
3. Pick review types.
4. Choose a backend.
5. Enter programmer and reviewer names.
6. Run a dry run or start the review.

Start with a dry run if you are not sure the path, scope, or diff filter is correct.

## Step 2: Triage Findings In The Results Tab

![Results tab screenshot](../../images/gui-results-tab.png)

After a review completes:

1. Use overview cards and filters to prioritize findings.
2. Open issue details.
3. Use AI Fix mode when you want generated edits.
4. Save a session if you want to return later.
5. Finalize reports from the current active or restored session.

## Step 3: Use The Supporting Desktop Surfaces When Needed

Useful companion workflows:

- detach Addon Review, Benchmarks, Settings, or Output Log into their own windows when you want a multi-window layout
- pin a preferred review-type bundle if you repeat the same startup selection often
- use Benchmarks to compare saved benchmark runs if you are tuning prompts, models, or review bundles

## If Something Looks Wrong

- If the app launches but the backend is not ready, fix backend configuration in Settings before retrying the review.
- If the review target is too broad, switch to diff scope or narrow the selected files.
- If you want a pure terminal workflow, use [First CLI Review](first-cli-review.md) instead.
- If you hit setup or runtime problems, use [Troubleshooting](../../troubleshooting.md) and [GUI Guide](../../gui.md).

## Related Guides

- [User Manual](../../user-manual.md)
- [GUI Guide](../../gui.md)
- [Backend Guide](../../backends.md)
- [AI Fix Workflow](../gui/ai-fix-workflow.md)
- [Restore A Session And Finalize](../gui/restore-session-and-finalize.md)