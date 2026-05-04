# Restore A Session And Finalize

Use this guide when you want to pause triage and come back later without rerunning the original review.

## Before You Start

You need:

- AICodeReviewer installed with GUI support
- a saved Results session JSON from an earlier review

If you have not worked through the normal desktop review flow yet, use [First GUI Session](../getting-started/first-gui-session.md) first.

## Expected Result

By the end of this guide you will:

- restore a saved Results session without rerunning the backend
- continue triage or AI-fix review from the restored session
- finalize the report from the current Results state

## Step 1: Save A Session When You Pause

If you are still in the original review session:

1. Run a review in the GUI.
2. Use the Results tab to save the current session to JSON.

Save the session before closing the app if you know you want to continue later.

## Step 2: Restore The Session Later

When you return:

1. Open the Results tab.
2. Load the saved session JSON.

What restore gives you:

- the issue list returns without rerunning the backend
- issue-level provenance such as AI suggestion and applied-fix details is restored when present
- finalize-ready report metadata is restored with the session when available

What restore does not do:

- it does not reconnect a live backend client
- it does not rerun the original scan or review

## Step 3: Continue Triage From The Restored Session

After restore, continue whatever remained unfinished:

- adjust issue status
- review or apply AI fixes
- prepare the issue list for final output

If you need the fix workflow itself, continue with [AI Fix Workflow](ai-fix-workflow.md).

## Step 4: Finalize The Report

Once the issue list is ready, finalize the report from the Results workflow.

Important behavior:

- finalize uses the issue list currently visible in Results, not an older saved copy
- if a session has no deferred report metadata, finalize is unavailable
- restoring a valid session is enough to rebuild report output without rerunning the review request

## If Something Looks Wrong

- If the session does not load, confirm the JSON file came from the Results save flow.
- If expected provenance details are missing, confirm they were present when the session was saved.
- If finalize is unavailable, check whether the restored session includes deferred report metadata.
- If you need output-format details, use [Reports and Outputs](../../reports.md).

## Related Guides

- [First GUI Session](../getting-started/first-gui-session.md)
- [AI Fix Workflow](ai-fix-workflow.md)
- [GUI Guide](../../gui.md)
- [Reports and Outputs](../../reports.md)