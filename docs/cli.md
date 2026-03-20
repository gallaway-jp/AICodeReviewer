# CLI Guide

The CLI is the authoritative execution surface for scripted and interactive review workflows.

## Command Shape

```text
aicodereviewer [path] [options]
```

## Common Commands

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

Diff review from a patch file:

```bash
aicodereviewer . --scope diff --diff-file changes.diff --type maintainability --programmers Alice --reviewers Bob
```

Specification review:

```bash
aicodereviewer . --type specification --spec-file requirements.md --programmers Alice --reviewers Bob
```

Dry run:

```bash
aicodereviewer . --type all --dry-run
```

GUI launch:

```bash
aicodereviewer --gui
```

## Options

| Option | Meaning |
|---|---|
| `path` | Project directory for project-scope reviews |
| `--scope {project,diff}` | Review the full project or a diff |
| `--diff-file FILE` | Patch file input for diff scope |
| `--commits RANGE` | Git or SVN commit range for diff scope |
| `--type TYPES` | Comma-separated review types or `all` |
| `--spec-file FILE` | Required when using `specification` review type |
| `--backend {bedrock,kiro,copilot,local}` | Backend override |
| `--lang {en,ja,default}` | Output language |
| `--output FILE` | Output file path override |
| `--programmers NAME...` | Code authors |
| `--reviewers NAME...` | Reviewers |
| `--dry-run` | Scan only, no backend calls |
| `--gui` | Launch the GUI |
| `--check-connection` | Backend connectivity check |
| `--set-profile PROFILE` | Store AWS profile in keyring |
| `--clear-profile` | Remove stored AWS profile |

## Validation Rules

- `path` is required for `project` scope.
- `--diff-file` or `--commits` is required for `diff` scope.
- You cannot use `--diff-file` and `--commits` together.
- `--programmers` and `--reviewers` are required unless `--dry-run` is set.
- `--spec-file` is required when `specification` is selected.

## Interactive Review Flow

The CLI review flow is interactive after findings are generated.

Actions include:
- `RESOLVED`
- `IGNORE`
- `AI FIX`
- `VIEW CODE`
- `SKIP`
- force-resolve when verification fails and the user chooses to override

## Notes

- Pass `--backend` explicitly in scripts and CI so backend choice is deterministic.
- Configuration still influences model settings, timeouts, logging, and output formats.
- Use [Configuration Reference](configuration.md) for non-flag tuning.

## Related Guides

- [Review Types Reference](review-types.md)
- [Reports and Outputs](reports.md)
- [Troubleshooting](troubleshooting.md)