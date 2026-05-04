# Backend Guide

AICodeReviewer supports four execution backends. Choose the one that matches your environment, cost model, and review workflow.

## Backend Matrix

| Backend | Best For | Requirements | Notes |
|---|---|---|---|
| `bedrock` | Managed cloud inference on AWS | AWS credentials or SSO, Bedrock model access | Best default path for production use |
| `kiro` | Teams already using Kiro | Kiro CLI for Windows or inside WSL | Native Windows is preferred; WSL remains a fallback |
| `copilot` | Teams standardized on GitHub tooling | GitHub Copilot CLI and auth | Long prompts use a temp-file workaround |
| `local` | Local/offline or self-hosted inference | Running LLM server | Supports `lmstudio`, `ollama`, `openai`, `anthropic` API modes |

## Bedrock

Use when you want managed hosted models and AWS-native access control.

Typical setup:

```bash
aws configure sso
aicodereviewer --check-connection --backend bedrock
```

Relevant config:

```ini
[backend]
type = bedrock

[model]
model_id = amazon.nova-micro-v1:0

[aws]
region = us-east-1
sso_session =
```

Operational note:
- `amazon.nova-micro-v1:0` is the low-cost default path in this project because it is active in `us-east-1` and materially cheaper than the older Claude default.

## Kiro

Use when Kiro CLI is already part of your development environment.

Windows setup summary:

```bash
kiro-cli --version
aicodereviewer --check-connection --backend kiro
```

If you still run Kiro inside WSL, the existing `wsl_distro` setting remains available as a fallback.

Relevant config:

```ini
[backend]
type = kiro

[kiro]
cli_command = kiro-cli
model = minimax-m2.1
wsl_distro =
timeout = 300
```

Operational note:
- `minimax-m2.1` is the explicit ultra-low-cost Kiro test model used in this audit branch.

## Copilot

Use when your team already relies on GitHub Copilot and wants the review flow to align with GitHub tooling.

Typical setup:

```bash
copilot
aicodereviewer --check-connection --backend copilot
```

Relevant config:

```ini
[backend]
type = copilot

[copilot]
copilot_path = copilot
timeout = 300
model = gpt-5-mini
```

Operational note:
- `gpt-5-mini` is the explicit low-cost Copilot model used for testing in this audit branch so premium requests are not consumed by accident.
- The backend uses a temp-file path for large prompts to avoid Windows command-line length and prompt-size issues.
- When `tool_file_access.enabled = true` and `copilot` is allowlisted, tool-aware reviews stay limited to workspace-relative reads, deny configured sensitive-path globs such as `.env`, and record per-review audit metadata.
- If a Copilot review does not use the workspace file tools, the reviewer falls back to the static prompt path instead of failing the run.
- Very wide multi-type sessions still produce substantially larger prompts than focused review bundles. Prefer targeted bundles of related review types over `--type all`, especially when you include `specification`, `license`, `architecture`, or other large guidance blocks.

## Local LLM

Use when you want to run against a local or self-hosted model server.

Supported API modes:
- `lmstudio`
- `ollama`
- `openai`
- `anthropic`

Relevant config:

```ini
[backend]
type = local

[local_llm]
api_url = http://localhost:1234
api_type = openai
model = qwen/qwen3.5-9b
api_key = keyring://local_llm/api_key
timeout = 300
max_tokens = 4096
enable_web_search = true
```

Typical local checks:

```bash
aicodereviewer --check-connection --backend local
```

Operational notes:
- `qwen/qwen3.5-9b` is the current low-cost default because it is already available in the local model server on this machine and is materially lighter than the larger local models.
- The GUI stores `local_llm.api_key` in the system keyring and leaves only a `keyring://...` reference in `config.ini`; older plain-text values still load, but re-saving migrates them.
- The Local LLM settings section now includes explicit `Rotate` and `Revoke` actions so users can clear the stored keyring secret without manually editing `config.ini`.
- Local backend health checks now distinguish a missing keyring-backed credential from ordinary server reachability failures.
- `enable_web_search` is on by default for the Local LLM backend.
- When enabled, the backend appends small amounts of public, high-level review guidance to the prompt.
- The search flow is privacy-constrained: it does not send source code or project-specific identifiers to the search provider.
- For `performance` reviews, the reviewer also adds a narrow deterministic stale-cache finding when the Local LLM returns no cache/state issue even though the code clearly shows a cache read path and a separate write path for the same entity without invalidation.
- For `best_practices` reviews, the reviewer also adds a narrow deterministic caller/return-shape finding when the Local LLM returns no contract-style issue even though one file returns a literal dict shape and another caller still reads a removed key from that result.
- Because Local sessions can also pay a latency penalty on larger prompts, use the same bundle discipline there: several related review types in one pass is fine, but very broad multi-type sessions are lower-confidence and slower than targeted passes.

## Choosing a Backend

Choose `bedrock` if you want the most stable managed-service path.

Choose `kiro` if:
- you already use Kiro CLI
- you are comfortable with WSL-based execution on Windows

Choose `copilot` if:
- your team already uses GitHub Copilot CLI
- you want GitHub-centered auth and tooling

Choose `local` if:
- you want local privacy or lower-cost experimentation
- you already run LM Studio, Ollama, vLLM, LocalAI, or a compatible proxy

## Related Guides

- [Getting Started](getting-started.md)
- [Configuration Reference](configuration.md)
- [Troubleshooting](troubleshooting.md)