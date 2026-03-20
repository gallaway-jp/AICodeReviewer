# Backend Guide

AICodeReviewer supports four execution backends. Choose the one that matches your environment, cost model, and review workflow.

## Backend Matrix

| Backend | Best For | Requirements | Notes |
|---|---|---|---|
| `bedrock` | Managed cloud inference on AWS | AWS credentials or SSO, Bedrock model access | Best default path for production use |
| `kiro` | Teams already using Kiro on Windows | WSL plus Kiro CLI inside WSL | Windows paths are translated to WSL paths |
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
model_id = anthropic.claude-3-5-sonnet-20240620-v1:0

[aws]
region = us-east-1
sso_session =
```

## Kiro

Use when Kiro CLI is already part of your development environment.

Windows setup summary:

```bash
wsl --install
wsl -- kiro-cli --version
aicodereviewer --check-connection --backend kiro
```

Relevant config:

```ini
[backend]
type = kiro

[kiro]
wsl_distro = Ubuntu
cli_command = kiro-cli
timeout = 300
```

Path translation example:

| Windows | WSL |
|---|---|
| `D:\Projects\myapp` | `/mnt/d/Projects/myapp` |
| `C:\Users\me\code` | `/mnt/c/Users/me/code` |

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
model = auto
```

Operational note:
- The backend uses a temp-file path for large prompts to avoid Windows command-line length and prompt-size issues.

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
model = default
api_key =
timeout = 300
max_tokens = 4096
```

Typical local checks:

```bash
aicodereviewer --check-connection --backend local
```

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