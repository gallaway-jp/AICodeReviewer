# Reports and Outputs

AICodeReviewer produces machine-readable and human-readable outputs for downstream workflows.

## Output Formats

Supported formats:
- `json`
- `txt`
- `md`

Configure them in `config.ini`:

```ini
[output]
formats = json,txt,md
```

## Default Naming

Generated reports use timestamp-based names such as:

- `review_report_YYYYMMDD_HHMMSS.json`
- `review_report_YYYYMMDD_HHMMSS_summary.txt`

## CLI Output Override

You can override the main output file path in the CLI:

```bash
aicodereviewer . --type security --output reports/security-review.json --programmers Alice --reviewers Bob
```

In tool mode, `--json-out` writes the command's JSON envelope to a separate file while still printing the same JSON to stdout. Tool-mode `review` writes a standalone JSON review report only when `--output` is explicitly provided.

## What Reports Contain

Reports include:
- project and scope metadata
- selected review types
- programmer and reviewer metadata
- issue severity and status
- issue-level resolution provenance when present
- file-level findings
- quality score and summary breakdowns

Tool-mode review reports also include stable `issue_id` values when emitted through the non-interactive `review` command. Those IDs are intended for downstream `fix-plan` and `apply-fixes` workflows.

## Issue Provenance In JSON Reports

JSON review reports preserve issue-level provenance fields when the workflow records them.

Common issue fields relevant to fix provenance:

- `status`
- `resolution_reason`
- `resolved_at`
- `resolution_provenance`
- `ai_fix_suggested`
- `ai_fix_applied`

These fields are populated when the issue resolution path carries meaningful provenance. Typical examples:

- direct AI fix application stores both `ai_fix_suggested` and `ai_fix_applied` with `resolution_provenance = "ai_applied"`
- AI-generated fixes edited before apply store the original suggestion in `ai_fix_suggested`, the final written content in `ai_fix_applied`, and `resolution_provenance = "ai_edited"`
- manual built-in or external editor flows keep `resolution_provenance` without pretending the final content came directly from AI
- ignore, skip, verification, and forced-resolution flows store `resolution_provenance` even when no fix content exists

The JSON structure is intentionally straightforward so downstream tooling can distinguish:

- what the AI suggested
- what the reviewer actually applied
- whether a result was manual, verified, ignored, skipped, or AI-assisted

## Provenance In TXT And Markdown Reports

Human-readable TXT and Markdown reports include provenance details for each issue when available.

Possible provenance sections include:

- `Resolution Path`
- `AI Suggestion`
- `Applied Fix`

Those sections appear only when the underlying issue data contains the relevant fields. This keeps unresolved or non-fix findings readable while still surfacing AI-assisted resolution details for adjudicated issues.

In practice, that means:

- reports can show that an AI suggestion was applied unchanged
- reports can show that an AI suggestion was edited before apply
- reports can show manual resolution paths even when no AI patch content exists

This is the same provenance model used by the GUI Results workflow and the interactive CLI review flow.

## Tool-Mode JSON Envelopes

Tool mode emits JSON envelopes for the following commands:

- `review`
- `health`
- `fix-plan`
- `apply-fixes`
- `resume`

### review envelope

The `review` command writes a JSON object with fields such as:

- `schema_version`
- `command`
- `backend`
- `dry_run`
- `review_types`
- `scope`
- `path`
- `status`
- `files_scanned`
- `target_paths`
- `issue_count`
- `issues`
- `report`
- `report_path`

The embedded `report` object uses the same structure as the standard JSON review report written to disk when `--output` is used. For dry runs, `report` and `report_path` are `null`.

### health envelope

The `health` command writes:

- `schema_version`
- `command`
- `backend`
- `ready`
- `summary`
- `checks`
- `exit_code`

### fix-plan envelope

The `fix-plan` command writes:

- `schema_version`
- `command`
- `backend`
- `report_file`
- `selected_issue_ids`
- `issue_count`
- `generated_count`
- `failed_count`
- `fixes`

Each `fixes` entry includes:

- `issue_id`
- `file_path`
- `issue_type`
- `severity`
- `description`
- `status`
- `proposed_content`

`fix-plan` does not write source files.

### apply-fixes envelope

The `apply-fixes` command writes:

- `schema_version`
- `command`
- `plan_file`
- `selected_issue_ids`
- `applied_count`
- `failed_count`
- `results`

Each `results` entry includes:

- `issue_id`
- `file_path`
- `status`
- `backup_path` when the write succeeds
- `error` when the write fails

### resume envelope

The `resume` command normalizes a previously generated artifact into canonical workflow state.

Common fields:

- `schema_version`
- `command`
- `artifact_file`
- `artifact_type`
- `workflow_stage`
- `next_command`
- `can_resume`
- `selected_issue_ids`

Artifact-specific state:

- review artifacts return normalized `issues`, `pending_issue_ids`, and the embedded `report`; dry-run review envelopes normalize to a `dry-run` workflow stage with no next command
- fix-plan artifacts return `fixes`, `generated_issue_ids`, and `failed_issue_ids`
- apply-fixes artifacts return `results`, `applied_issue_ids`, and `failed_issue_ids`

## Tool-Mode Workflow

Typical non-interactive workflow:

1. Run `review` and capture the JSON envelope, or pass `--output` if you also want a standalone generated report file.
2. Run `fix-plan` against that review artifact.
3. Inspect the plan or select specific `issue_id` values.
4. Run `apply-fixes` to write the selected fixes.
5. Run `resume` against any saved artifact when another tool or later process needs to recover the current workflow state.

## GUI Reporting Flow

In the GUI, final reports are produced from the Results workflow after issues are reviewed or finalized.

The GUI reporting path uses the issue list currently shown in the Results tab together with the saved deferred report metadata attached to the active or restored session state.

The Results tab also supports:
- session save and load with the existing JSON file structure preserved on disk
- AI fix review flows
- issue filtering before finalization

Session notes:
- loading a saved session restores finalize-ready reporting state without rerunning the original review
- loading a saved session also restores persisted issue-level provenance such as `resolution_provenance`, `ai_fix_suggested`, and `ai_fix_applied`
- editing issue status in the Results tab changes what will be emitted in the final report
- restoring a session does not reconnect a live backend client, but it does restore the deferred report context needed for finalize to build a report from the currently shown issues
- the issue detail popup in the Results workflow reflects the same provenance fields that will later be emitted into TXT, Markdown, and JSON reports
- if no active or restored session carries deferred report metadata, finalize is unavailable in the GUI

## Recommended Workflow

1. Use JSON for automation and integrations.
2. Use TXT or Markdown for human review.
3. Use `--output` when you want stable report filenames in scripts or CI jobs.
4. Use `--json-out` in tool mode when you want to persist the full command envelope alongside stdout consumption.

## Related Guides

- [CLI Guide](cli.md)
- [GUI Guide](gui.md)
- [Configuration Reference](configuration.md)