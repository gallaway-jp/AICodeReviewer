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
| `tool_file_access` | Enable audited backend file-tool access |
| `local_llm` | Local server URL, API mode, model, token limits |
| `gui` | Theme, language, and saved GUI state |
| `local_http` | Embedded local HTTP API enablement and port |
| `review_packs` | Extra review-pack discovery paths |
| `addons` | Extra addon discovery paths |
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
enable_api_audit_file_logging = true
api_audit_log_file = aicodereviewer-audit.log

[local_llm]
api_url = http://localhost:1234
api_type = openai
model = default
api_key = keyring://local_llm/api_key
timeout = 300
max_tokens = 4096
enable_web_search = true

[local_http]
enabled = false
port = 8765

[addons]
paths = examples/addon-echo-backend

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
- `enable_api_audit_file_logging`
- `api_audit_log_file`
- `api_audit_log_max_bytes`
- `api_audit_log_backup_count`

Audit logging notes:
- Local HTTP security-sensitive audit events can be retained in a dedicated rotating log even when ordinary file logging is disabled.
- `enable_api_audit_file_logging` defaults to `true`.
- `api_audit_log_file` defaults to `aicodereviewer-audit.log`.
- Rotation is controlled by `api_audit_log_max_bytes` and `api_audit_log_backup_count`.

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

### Tool-Aware File Access

- `tool_file_access.enabled`
- `tool_file_access.backend_allowlist`
- `tool_file_access.sensitive_path_globs`
- `tool_file_access.sensitive_path_policy`

Behavior notes:
- `tool_file_access.enabled` defaults to `false`.
- The initial supported backend is `copilot`; additional backends must opt in explicitly.
- Sensitive path patterns are denied by default and are audited whenever a tool-aware review attempts to read them.
- When tool-aware access is enabled but unavailable or unused for a request, the reviewer falls back to the existing static prompt path instead of failing the whole review session.

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
- When saved through the GUI, `local_llm.api_key` is stored in the system keyring and the config file keeps only a stable reference such as `keyring://local_llm/api_key`.
- Existing plain-text `local_llm.api_key` values still load for backward compatibility, but re-saving settings migrates them to the keyring-backed reference form.
- The Settings tab now exposes explicit `Rotate` and `Revoke` actions for the Local LLM API key. `Rotate` clears the stored keyring secret but leaves the config reference in place until you save a replacement value; `Revoke` clears both the secret and the config reference immediately.
- If a keyring-backed Local LLM credential reference is present but the secret is missing, the Local backend health check reports that explicitly instead of failing as a generic connection problem.
- When enabled, the Local LLM backend fetches a small amount of high-level public guidance for the active review type.
- Source code and project identifiers are not sent to the search provider; only generic review and framework terms are used.
- For `performance` reviews, obvious stale-cache read/write gaps can still produce a deterministic cross-file finding even when the Local LLM returns no cache/state issue, but that supplement does not run for other review types.
- For `best_practices` reviews, obvious producer/caller return-shape drift can also produce a deterministic cross-file finding when the Local LLM returns no contract-style issue, but that supplement only runs for concrete imported-call dict-shape mismatches.

## GUI Settings

Common persisted fields:
- `gui.theme`
- `gui.language`
- `gui.review_language`
- `gui.pinned_review_types`
- `gui.pinned_review_preset`
- `gui.editor_command`
- `gui.project_path`
- `gui.programmers`
- `gui.reviewers`
- `gui.spec_file`
- `gui.review_types`
- `gui.file_select_mode`
- `gui.selected_files`

Detached-window state:
- `gui.detached_pages`
- `gui.detached_log_geometry`
- `gui.detached_settings_geometry`
- `gui.detached_benchmark_geometry`

Benchmark-browser state:
- `gui.benchmark_fixtures_root`
- `gui.benchmark_artifacts_root`
- `gui.benchmark_fixture_filter_key`
- `gui.benchmark_fixture_sort_key`
- `gui.benchmark_compare_views`

Behavior notes:
- `gui.detached_pages` tracks which approved non-Review pages should reopen in detached windows after restart.
- Detached window geometry is persisted per page so the Output Log, Settings, and Benchmarks windows can reopen in their last desktop positions.
- Benchmark filter and sort preferences persist independently from detached-window state and comparison-specific benchmark view state is keyed by the active primary/comparison summary pair.

## Embedded Local HTTP API

Key settings:
- `local_http.enabled`
- `local_http.port`

Behavior notes:
- when `local_http.enabled = true`, the desktop app starts the loopback HTTP API automatically during GUI startup
- the embedded API uses the same execution runtime and queue state as the GUI instead of spinning up a separate review subsystem
- the default embedded API port is `8765`
- disabling the setting stops automatic startup, but you can still run the API explicitly from the CLI with `aicodereviewer serve-api`

## Addons

Use `addons.paths` to point discovery at one or more addon directories or manifest files.

Paths are resolved relative to the directory containing `config.ini` when they are not absolute.

Example:

```ini
[addons]
paths = examples/addon-echo-backend
```

That example points at the checked-in code-backed addon under [examples/addon-echo-backend/addon.json](../examples/addon-echo-backend/addon.json). You can verify discovery with `aicodereviewer --list-addons`.

## Output Formats

`output.formats` accepts a comma-separated list such as:

```ini
[output]
formats = json,txt,md
```

## Related Guides

- [Addons Guide](addons.md)
- [Backend Guide](backends.md)
- [Reports and Outputs](reports.md)
- [Troubleshooting](troubleshooting.md)