# CLI Guide

The CLI currently has two supported operating modes:

- legacy interactive mode for terminal-driven reviews
- tool mode for non-interactive automation and AI-agent integrations

## Command Shapes

Legacy mode:

```text
aicodereviewer [path] [options]
```

Tool mode:

```text
aicodereviewer review [options]
aicodereviewer health [options]
aicodereviewer fix-plan [options]
aicodereviewer apply-fixes [options]
aicodereviewer resume [options]
```

## Legacy Interactive Mode

Basic review:

```bash
aicodereviewer . --type best_practices --programmers Alice --reviewers Bob
```

Multiple review types:

```bash
aicodereviewer . --type security,performance,testing --programmers Alice --reviewers Bob
```

All review types:

```bash
aicodereviewer . --type all --programmers Alice --reviewers Bob
```

Diff review from commits:

```bash
aicodereviewer . --scope diff --commits HEAD~3..HEAD --type security --programmers Alice --reviewers Bob
```

Specification review:

```bash
aicodereviewer . --type specification --spec-file requirements.md --programmers Alice --reviewers Bob
```

Dry run:

```bash
aicodereviewer . --type all --dry-run
```

Connection check:

```bash
aicodereviewer --check-connection --backend local
```

GUI launch:

```bash
aicodereviewer --gui
```

### Legacy Validation Rules

- `path` is required for `project` scope.
- `--diff-file` or `--commits` is required for `diff` scope.
- You cannot use `--diff-file` and `--commits` together.
- `--programmers` and `--reviewers` are required unless `--dry-run` is set.
- `--spec-file` is required when `specification` is selected.

### Legacy Interactive Review Flow

The legacy review flow remains interactive after findings are generated.

Actions include:

- `RESOLVED`
- `IGNORE`
- `AI FIX`
- `VIEW CODE`
- `SKIP`
- force-resolve when verification fails and the user chooses to override

## Tool Mode

Tool mode is the supported non-interactive surface for scripts, CI jobs, and other AI tools.

The commands are designed to be chainable through JSON artifacts so another tool can resume work from any completed step.

### review

Runs a review without interactive prompts and emits a JSON envelope to stdout.

Tool-mode `review` only writes a JSON report file when `--output` is provided. Otherwise the review envelope on stdout is the only persisted result unless you also pass `--json-out`.

Example:

```bash
aicodereviewer review . --type security --programmers Alice --reviewers Bob --backend bedrock --json-out artifacts/review-tool.json
```

Dry-run example:

```bash
aicodereviewer review . --type security --dry-run
```

Cancellation examples:

```bash
aicodereviewer review . --type security --programmers Alice --reviewers Bob --cancel-file stop.flag
aicodereviewer review . --type security --programmers Alice --reviewers Bob --timeout-seconds 120
```

Supported review flags:

- `path`
- `--scope {project,diff}`
- `--diff-file FILE`
- `--commits RANGE`
- `--type TYPES`
- `--spec-file FILE`
- `--backend {bedrock,kiro,copilot,local}`
- `--lang {en,ja,default}`
- `--output FILE`
- `--programmers NAME...`
- `--reviewers NAME...`
- `--dry-run`
- `--json-out FILE`
- `--cancel-file FILE`
- `--timeout-seconds SECONDS`

Runtime overrides:

- `--model MODEL`
- `--region REGION`
- `--api-url URL`
- `--api-type TYPE`
- `--local-model MODEL`
- `--local-enable-web-search`
- `--local-disable-web-search`
- `--copilot-model MODEL`
- `--kiro-cli-command CMD`
- `--timeout SECONDS`

The Local LLM web-search flags are useful for benchmarking and automation because they let you compare prompt enrichment on and off without editing `config.ini`.

### health

Runs backend readiness checks and emits a JSON envelope to stdout.

Example:

```bash
aicodereviewer health --backend local --api-url http://localhost:1234 --json-out artifacts/health.json
```

### fix-plan

Loads a review artifact, generates AI fixes for the selected issues, and emits a fix-plan JSON envelope without writing files.

Supported review artifacts:

- a raw JSON review report
- a tool-mode `review` JSON envelope containing a `report` object

Example:

```bash
aicodereviewer fix-plan --report-file review_report_20260320_100000.json --issue-id issue-0001 --json-out artifacts/fix-plan.json
```

If `--issue-id` is omitted, all issues in the review artifact are considered.

### apply-fixes

Loads a fix-plan artifact and writes selected generated fixes to disk. Each applied fix creates a sibling `.backup` file before overwriting the original source file.

Example:

```bash
aicodereviewer apply-fixes --plan-file artifacts/fix-plan.json --issue-id issue-0001 --json-out artifacts/apply-results.json
```

If `--issue-id` is omitted, all generated fixes in the plan are applied.

### resume

Loads an existing tool artifact and returns a normalized workflow-state envelope that tells automation what stage the workflow is in and what command can run next.

Supported artifact inputs:

- raw JSON review reports
- tool-mode `review` envelopes
- tool-mode `fix-plan` envelopes
- tool-mode `apply-fixes` envelopes

When a review envelope comes from a dry run, `resume` returns a normalized `dry-run` workflow state with no next command.

Example:

```bash
aicodereviewer resume --artifact-file artifacts/fix-plan.json --json-out artifacts/resume.json
```

You can also filter the returned state to specific issues:

```bash
aicodereviewer resume --artifact-file artifacts/review.json --issue-id issue-0003
```

Typical `resume` output includes:

- `artifact_type`
- `workflow_stage`
- `next_command`
- `can_resume`
- issue or fix/result lists depending on the artifact type
- filtered `selected_issue_ids` when `--issue-id` is used

## Exit Codes

- `0`: success
- `1`: failure or no applicable result for the requested tool action
- `3`: cancelled tool-mode review

## Notes

- Pass `--backend` explicitly in automation so backend choice is deterministic.
- Tool-mode commands print JSON to stdout; consume stdout as the primary machine contract.
- Use `--json-out` when you want to retain the same JSON envelope on disk.
- Use `--output` in tool-mode `review` only when you also want a standalone JSON review report written to disk.
- Configuration still influences model settings, timeouts, logging, and report formats unless you override them on the command line.
- Use [Configuration Reference](configuration.md) for non-flag tuning.

## Related Guides

- [Review Types Reference](review-types.md)
- [Reports and Outputs](reports.md)
- [Troubleshooting](troubleshooting.md)