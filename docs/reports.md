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

## What Reports Contain

Reports include:
- project and scope metadata
- selected review types
- programmer and reviewer metadata
- issue severity and status
- file-level findings
- quality score and summary breakdowns

## GUI Reporting Flow

In the GUI, final reports are produced from the Results workflow after issues are reviewed or finalized.

The Results tab also supports:
- session save and load
- AI fix review flows
- issue filtering before finalization

## Recommended Workflow

1. Use JSON for automation and integrations.
2. Use TXT or Markdown for human review.
3. Use `--output` when you want stable filenames in scripts or CI jobs.

## Related Guides

- [CLI Guide](cli.md)
- [GUI Guide](gui.md)
- [Configuration Reference](configuration.md)