# AI Fix Workflow

Use this guide when you want the desktop app to generate and stage proposed edits for selected findings.

## Before You Start

You need:

- AICodeReviewer installed with GUI support
- one configured backend that supports the fix flow you intend to use
- a completed review with findings visible in the Results tab

If you have not run a first desktop review yet, use [First GUI Session](../getting-started/first-gui-session.md) first.

## Expected Result

By the end of this guide you will:

- enter AI Fix mode from the Results tab
- review generated staged edits before anything is written
- apply only the fixes you intend to keep

## Step 1: Start From The Results Tab

![AI Fix mode screenshot](../../images/gui-ai-fix-mode.png)

1. Complete a review and open the Results tab.
2. Filter or inspect issue cards until you find the findings you want to address.
3. Enter AI Fix mode for one issue or a batch of issues.

Start with a small set of findings if this is your first time using the flow.

## Step 2: Wait For The Proposed Edits

Let the desktop workflow generate the proposed fixes and populate the preview surface.

What to check:

- the proposal targets the file and issue you intended
- the generated change actually addresses the finding
- the staged content does not introduce unrelated edits

## Step 3: Review And Edit The Preview

Before applying anything:

1. Review the staged preview carefully.
2. Edit the proposed content if needed.
3. Leave any proposal unapplied if it is not good enough to keep.

Important behavior:

- generated edits are previewed before they are written
- preview edits stay staged until you choose `Apply Selected Fixes`
- fix failures can surface as issue state and should be reviewed before retrying

## Step 4: Apply Only The Fixes You Want

Apply the selected fixes once the staged preview is acceptable.

Use this workflow when you want help with straightforward remediations but still need a human check before the file changes land.

## Step 5: Continue Triage Or Finalize Later

After applying fixes, you can:

- continue triage in the Results tab
- save the session and return later
- finalize the report once the issue list is ready

If you plan to pause before finalizing, continue with [Restore A Session And Finalize](restore-session-and-finalize.md).

## If Something Looks Wrong

- If proposals do not appear, confirm the backend is configured and the review completed successfully.
- If a proposal is low quality, edit it or leave it unapplied instead of forcing it through.
- If fix generation fails, inspect the issue state and the Output Log before retrying.
- If you want the broader Results-tab flow first, return to [First GUI Session](../getting-started/first-gui-session.md).

## Related Guides

- [First GUI Session](../getting-started/first-gui-session.md)
- [Restore A Session And Finalize](restore-session-and-finalize.md)
- [GUI Guide](../../gui.md)
- [Troubleshooting](../../troubleshooting.md)