# Troubleshooting

Use this page when setup, connectivity, or review execution does not behave as expected.

## First Checks

1. Confirm the backend is the one you intended.
2. Run a connection check.
3. Run a dry run.
4. Increase logging if needed.

## Backend Checks

```bash
aicodereviewer --check-connection --backend bedrock
aicodereviewer --check-connection --backend kiro
aicodereviewer --check-connection --backend copilot
aicodereviewer --check-connection --backend local
```

## Common Issues

## Bedrock Authentication Problems

Symptoms:
- connection check fails
- model access errors
- AWS auth or region errors

Check:
- AWS SSO or credentials are valid
- the configured region is correct
- the configured model is enabled in Bedrock

## Kiro on Windows

Symptoms:
- Kiro cannot be found
- path translation errors
- WSL invocation fails

Check:
- WSL is installed and working
- `kiro-cli` is available inside the chosen distro
- `kiro.wsl_distro` matches an actual distro name if specified

## Copilot CLI Problems

Symptoms:
- Copilot command not found
- auth not available
- prompt-related failures on large reviews

Check:
- `copilot` is installed and authenticated
- the account has the correct subscription and permissions
- if tool-aware file access is enabled, confirm `tool_file_access.backend_allowlist` still includes `copilot`
- if a file read is denied, compare the path against the configured workspace root and `tool_file_access.sensitive_path_globs`
- inspect `tool_access_audit` in tool-mode or execution output if you need to distinguish a true tool failure from a clean fallback to the static prompt path
- rerun with narrower review scope if investigating prompt-size behavior

## Local LLM Connection Problems

Symptoms:
- connection refused
- timeout
- model discovery fails
- unsupported API responses

Check:
- the server is actually running
- `local_llm.api_url` contains only the base URL and port
- `local_llm.api_type` matches the server mode
- `local_llm.model` exists or `default` can discover one

## Large Prompt or Command-Length Issues

This codebase includes workarounds for long Copilot CLI prompts, but very large reviews can still be expensive or slow.

Try:
- `--scope diff`
- fewer `--type` values in one run
- lower file count or selected-file mode in the GUI

## Logging

Raise log verbosity in `config.ini`:

```ini
[logging]
log_level = DEBUG
enable_file_logging = true
log_file = aicodereviewer.log
```

In the GUI, use the Output Log tab and its severity filter.

## Related Guides

- [Backend Guide](backends.md)
- [Configuration Reference](configuration.md)
- [GUI Guide](gui.md)