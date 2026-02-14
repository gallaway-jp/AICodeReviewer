# AICodeReviewer v2.0

AI-powered code review tool that analyses your codebase for security, performance, maintainability, and 16 more quality dimensions.  Supports **AWS Bedrock**, **Kiro CLI (WSL)**, and **GitHub Copilot CLI** backends, with both a full-featured **CLI** and a **CustomTkinter GUI**.

Supports 12+ programming languages: Python, JavaScript/TypeScript, Java, C/C++, C#, Go, Ruby, PHP, Rust, Swift, Kotlin, Objective-C, plus frameworks (React, Vue, Svelte, Astro, Laravel) and web technologies (HTML, CSS, Sass/Less, JSON, XML, YAML).

---

## What's New in v2.0

| Feature | Description |
|---------|-------------|
| **Multi-type reviews** | Combine any number of review types in a single session (`--type security,performance,testing`) |
| **AWS Bedrock improvements** | Exponential back-off retry, lazy connection validation, support for all Bedrock-provisioned models |
| **Kiro CLI backend** | Run reviews via Amazon Kiro CLI through WSL, with automatic Windows→WSL path conversion |
| **GitHub Copilot CLI backend** | Run reviews via `gh copilot` on Windows |
| **CustomTkinter GUI** | Full-featured graphical interface with live log, results viewer, and settings editor |
| **4 new review types** | `dependency`, `concurrency`, `api_design`, `data_validation` |
| **Skip action** | Leave issues pending during interactive review without being forced to act |
| **Force resolve** | Override failed verification when you know the issue is fixed |
| **English-first messages** | All user-facing messages default to English (Japanese still supported via `--lang ja`) |

---

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd AICodeReviewer

# Install core + GUI
pip install -e ".[gui]"

# Or core only (no GUI)
pip install -e .
```

### Backend-Specific Prerequisites

| Backend | Requirements |
|---------|-------------|
| **Bedrock** | AWS CLI configured (`aws configure sso` or credentials in `config.ini`) |
| **Kiro** | WSL installed (`wsl --install`), Kiro CLI installed inside WSL |
| **Copilot** | GitHub CLI (`gh`) + Copilot extension (`gh extension install github/gh-copilot`), active Copilot subscription |

---

## Quick Start

### CLI

```bash
# Basic project review (best practices, Bedrock)
aicodereviewer /path/to/project --programmers Alice --reviewers Bob

# Multi-type review
aicodereviewer . --type security,performance,testing --programmers Alice --reviewers Bob

# All review types at once
aicodereviewer . --type all --programmers Alice --reviewers Bob

# Use Kiro backend via WSL
aicodereviewer . --backend kiro --type security --programmers Alice --reviewers Bob

# Use GitHub Copilot backend
aicodereviewer . --backend copilot --type best_practices --programmers Alice --reviewers Bob

# Diff-based review (Git)
aicodereviewer . --scope diff --commits HEAD~3..HEAD --type security,maintainability \
    --programmers Alice --reviewers Bob

# Diff-based review (SVN)
aicodereviewer . --scope diff --commits 100:105 --type performance --programmers Alice --reviewers Bob

# Dry run (list files, no API calls)
aicodereviewer . --type all --dry-run

# Specification comparison
aicodereviewer . --type specification --spec-file requirements.md --programmers Alice --reviewers Bob

# Launch the GUI
aicodereviewer --gui
```

### GUI

```bash
aicodereviewer --gui
# or
python -m aicodereviewer --gui
```

The GUI provides:
- **Review tab** – project browser, scope selector, review type checkboxes, backend picker, metadata fields, Start/Dry-Run buttons with progress bar
- **Settings tab** – edit config.ini values and save
- **Results tab** – scrollable issue cards with severity colouring and detail popups
- **Output Log tab** – real-time log stream

---

## CLI Reference

```
aicodereviewer [path] [options]
```

### Positional

| Argument | Description |
|----------|-------------|
| `path` | Project directory (required for `--scope project`) |

### Options

| Flag | Description |
|------|-------------|
| `--scope {project,diff}` | Review scope (default: `project`) |
| `--diff-file FILE` | Unified diff / patch file |
| `--commits RANGE` | Git or SVN commit range |
| `--type TYPES` | Comma-separated review types, or `all` (default: `best_practices`) |
| `--spec-file FILE` | Specification doc (required with `specification` type) |
| `--backend {bedrock,kiro,copilot}` | AI backend (default: from `config.ini`) |
| `--lang {en,ja,default}` | Output language (default: auto-detect) |
| `--output FILE` | Custom JSON report path |
| `--programmers NAME…` | Code authors (required) |
| `--reviewers NAME…` | Reviewers (required) |
| `--dry-run` | List files without API calls |
| `--gui` | Launch graphical interface |
| `--set-profile PROFILE` | Store AWS profile in keyring |
| `--clear-profile` | Remove stored AWS profile |

---

## Review Types

| Key | Category | Description |
|-----|----------|-------------|
| `security` | Quality | OWASP / CWE vulnerability audit |
| `performance` | Quality | Algorithmic efficiency, N+1 queries, caching |
| `best_practices` | Quality | SOLID, DRY, clean code |
| `maintainability` | Quality | Readability, coupling, tech debt |
| `documentation` | Quality | Docstrings, comments, README |
| `testing` | Quality | Coverage gaps, testability |
| `error_handling` | Quality | Exception handling, resilience |
| `complexity` | Quality | Cyclomatic / cognitive complexity |
| `concurrency` | Quality | Thread safety, race conditions |
| `data_validation` | Quality | Input validation, sanitisation |
| `accessibility` | Compliance | WCAG 2.1 AA, ARIA, keyboard nav |
| `license` | Compliance | OSS license compatibility |
| `localization` | Compliance | i18n readiness, hardcoded strings |
| `specification` | Compliance | Code vs requirements comparison |
| `scalability` | Architecture | Horizontal scaling bottlenecks |
| `compatibility` | Architecture | Cross-platform, version compat |
| `architecture` | Architecture | Layer separation, design patterns |
| `dependency` | Architecture | Outdated / vulnerable dependencies |
| `api_design` | Architecture | REST/GraphQL design quality |

---

## Interactive Review Workflow

For each issue the AI finds, you choose:

| Action | Description |
|--------|-------------|
| **1. RESOLVED** | Mark resolved (AI re-verifies); force-resolve option on failure |
| **2. IGNORE** | Ignore with a reason (≥ 3 chars) |
| **3. AI FIX** | Generate a fix, preview the diff, apply or cancel |
| **4. VIEW CODE** | Print the full file for context |
| **5. SKIP** | Leave pending and move to next issue |

---

## Configuration (`config.ini`)

```ini
[backend]
type = bedrock              # bedrock | kiro | copilot

[model]
model_id = anthropic.claude-3-5-sonnet-20240620-v1:0

[aws]
region = us-east-1
# access_key_id = ...
# sso_session = my-sso

[kiro]
# wsl_distro = Ubuntu       # leave blank for default
cli_command = kiro
timeout = 300

[copilot]
gh_path = gh
timeout = 300
# model =                   # leave blank for default

[performance]
max_file_size_mb = 10
min_request_interval_seconds = 6.0
max_requests_per_minute = 10
api_timeout_seconds = 300

[processing]
batch_size = 5
enable_parallel_processing = false

[logging]
log_level = INFO
enable_file_logging = false
```

---

## Kiro CLI (WSL) Setup

Kiro is Amazon's AI development tool. On Windows, AICodeReviewer runs Kiro inside WSL and automatically translates Windows paths to `/mnt/` mount paths.

```bash
# 1. Install WSL (if not already)
wsl --install

# 2. Inside WSL, install Kiro CLI
#    (follow Kiro installation docs for your distro)

# 3. Verify
wsl -- kiro --version

# 4. Configure AICodeReviewer
#    In config.ini:
#    [backend]
#    type = kiro
#    [kiro]
#    wsl_distro = Ubuntu
```

### Path Translation

| Windows Path | WSL Path |
|-------------|----------|
| `D:\Projects\myapp` | `/mnt/d/Projects/myapp` |
| `C:\Users\me\code` | `/mnt/c/Users/me/code` |

> **Network paths** (`\\server\share\...`) require the share to be mounted inside WSL or mapped to a drive letter.

---

## GitHub Copilot CLI Setup

```bash
# 1. Install GitHub CLI
winget install GitHub.cli

# 2. Authenticate
gh auth login

# 3. Install Copilot extension
gh extension install github/gh-copilot

# 4. Verify
gh copilot --version

# 5. Configure AICodeReviewer
#    In config.ini:
#    [backend]
#    type = copilot
```

---

## Building Windows Executable

```bash
build_exe.bat
# Output: dist\AICodeReviewer.exe
```

---

## Development

```bash
# Install with dev dependencies
pip install -e ".[all]"

# Run tests
pytest -v

# Run specific test
pytest tests/test_scanner.py -v
```

---

## Performance Tips

1. **Large codebases** – use `--scope diff` to review only changed files
2. **Parallel processing** – set `enable_parallel_processing = true` for 2-4× speedup
3. **Multiple types** – combining types in one session reuses file scanning
4. **Batch size** – increase `batch_size` for projects with 100+ files
5. **Rate limits** – handled automatically with exponential back-off

---

## License

See [LICENSE](LICENSE) for details.
