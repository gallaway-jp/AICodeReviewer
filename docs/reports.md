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
- file-level findings
- quality score and summary breakdowns

Tool-mode review reports also include stable `issue_id` values when emitted through the non-interactive `review` command. Those IDs are intended for downstream `fix-plan` and `apply-fixes` workflows.

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

The Results tab also supports:
- session save and load
- AI fix review flows
- issue filtering before finalization

## Recommended Workflow

1. Use JSON for automation and integrations.
2. Use TXT or Markdown for human review.
3. Use `--output` when you want stable report filenames in scripts or CI jobs.
4. Use `--json-out` in tool mode when you want to persist the full command envelope alongside stdout consumption.

## Related Guides

- [CLI Guide](cli.md)
- [GUI Guide](gui.md)
- [Configuration Reference](configuration.md)