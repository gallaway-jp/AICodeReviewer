# Configuration Reference

Configuration is loaded from `config.ini` in the working directory or project root.

## Sections Overview

| Section | Purpose |
|---|---|
| `backend` | Active backend selection |
| `performance` | Rate limits, payload limits, and timeouts |
| `processing` | Batch behavior and analysis toggles |
| `logging` | Log level and file logging |
| `model` | Bedrock model selection |
| `aws` | AWS credentials and SSO settings |
| `kiro` | WSL distro and CLI command |
| `copilot` | CLI path, timeout, model |
| `local_llm` | Local server URL, API mode, model, token limits |
| `gui` | Theme, language, and saved GUI state |
| `output` | Report output formats |

## Example

```ini
[backend]
type = local

[performance]
max_file_size_mb = 10
max_fix_file_size_mb = 5
min_request_interval_seconds = 6.0
max_requests_per_minute = 10
api_timeout_seconds = 300

[processing]
batch_size = 5
enable_parallel_processing = false
enable_interaction_analysis = true
enable_architectural_review = false

[logging]
log_level = INFO
enable_file_logging = false

[local_llm]
api_url = http://localhost:1234
api_type = openai
model = default
api_key =
timeout = 300
max_tokens = 4096
enable_web_search = true

[output]
formats = json,txt,md
```

## Performance

Key settings:
- `max_file_size_mb`
- `max_fix_file_size_mb`
- `file_cache_size`
- `min_request_interval_seconds`
- `max_requests_per_minute`
- `api_timeout_seconds`
- `connect_timeout_seconds`
- `max_content_length`
- `max_fix_content_length`

## Processing

Key settings:
- `batch_size`
- `enable_parallel_processing`
- `enable_interaction_analysis`
- `enable_architectural_review`

Default behavior:
- `enable_interaction_analysis` is enabled by default because it adds a low-cost synthesis pass when the first review pass finds at least two issues.
- `enable_architectural_review` remains disabled by default because it adds a broader project-level pass.

Important distinction:
- `enable_interaction_analysis` and `enable_architectural_review` are processing toggles, not selectable `--type` values.

## Logging

Key settings:
- `log_level`
- `enable_performance_logging`
- `enable_file_logging`
- `log_file`

## Backend-Specific Settings

### Bedrock

- `model.model_id`
- `aws.region`
- `aws.access_key_id`
- `aws.session_token`
- `aws.sso_session`
- `aws.sso_account_id`
- `aws.sso_role_name`
- `aws.sso_region`
- `aws.sso_start_url`
- `aws.sso_registration_scopes`

### Kiro

- `kiro.wsl_distro`
- `kiro.cli_command`
- `kiro.timeout`

### Copilot

- `copilot.copilot_path`
- `copilot.timeout`
- `copilot.model`

### Local LLM

- `local_llm.api_url`
- `local_llm.api_type`
- `local_llm.model`
- `local_llm.api_key`
- `local_llm.timeout`
- `local_llm.max_tokens`
- `local_llm.enable_web_search`

Supported `api_type` values:
- `lmstudio`
- `ollama`
- `openai`
- `anthropic`

Behavior notes:
- `local_llm.enable_web_search` defaults to `true`.
- When enabled, the Local LLM backend fetches a small amount of high-level public guidance for the active review type.
- Source code and project identifiers are not sent to the search provider; only generic review and framework terms are used.
- For `performance` reviews, obvious stale-cache read/write gaps can still produce a deterministic cross-file finding even when the Local LLM returns no cache/state issue, but that supplement does not run for other review types.
- For `best_practices` reviews, obvious producer/caller return-shape drift can also produce a deterministic cross-file finding when the Local LLM returns no contract-style issue, but that supplement only runs for concrete imported-call dict-shape mismatches.

## GUI Settings

Common persisted fields:
- `gui.theme`
- `gui.language`
- `gui.review_language`
- `gui.editor_command`
- `gui.project_path`
- `gui.programmers`
- `gui.reviewers`
- `gui.spec_file`
- `gui.review_types`
- `gui.file_select_mode`
- `gui.selected_files`

## Output Formats

`output.formats` accepts a comma-separated list such as:

```ini
[output]
formats = json,txt,md
```

## Related Guides

- [Backend Guide](backends.md)
- [Reports and Outputs](reports.md)
- [Troubleshooting](troubleshooting.md)