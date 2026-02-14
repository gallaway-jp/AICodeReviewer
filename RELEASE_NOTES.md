# AICodeReviewer v2.0.0

Major upgrade with multi-backend support, multi-type reviews, and a graphical interface.

## New Features
- **Multi-type reviews** – combine any review types in one session (`--type security,performance,testing` or `--type all`)
- **AWS Bedrock improvements** – exponential back-off retry, lazy connection validation, multi-model support
- **Kiro CLI backend** – run reviews via Amazon Kiro CLI through WSL with automatic Windows→WSL path translation
- **GitHub Copilot CLI backend** – run reviews via standalone GitHub Copilot CLI (`copilot -p`) in programmatic mode
- **CustomTkinter GUI** – full-featured graphical interface (`--gui`) with live log, results viewer, settings editor
- **4 new review types** – `dependency`, `concurrency`, `api_design`, `data_validation` (19 total)
- **Skip action** – leave issues pending during interactive review
- **Force resolve** – override failed verification when you know an issue is fixed
- **English-first messages** – all output defaults to English (Japanese via `--lang ja`)
- **Improved reporter** – breakdowns by severity and review type in summary reports

## Breaking Changes
- `--type` now accepts comma-separated values; old single-value usage still works
- Review types list expanded from 15 to 19
- `BedrockClient` import path changed to `aicodereviewer.backends.bedrock.BedrockBackend` (backward-compat shim at old path)
- Minimum Python version raised to 3.10

---

# AICodeReviewer v0.1.0 — First Release

This is the first public release of AICodeReviewer for Windows.

- Binary: `dist/AICodeReviewer.exe`
- SHA256: `7E87BAD805F41EC90198DDDD9874D96E7F33FA7A1801E886C21026AC28B9AB31`
- Minimum Python runtime: Not required (standalone)
- Supported OS: Windows (x64)

## Highlights
- Single-file Windows executable built with PyInstaller
- Multi-language code analysis (security, performance, best practices, and more)
- Interactive workflow (confirm, ignore with reason, AI fix, view code)
- Generates JSON + summary reports

## Install & Run
1. Download `AICodeReviewer.exe` from the release assets.
2. Optionally download `AICodeReviewer.exe.sha256` and verify:
   ```powershell
   Get-FileHash .\AICodeReviewer.exe -Algorithm SHA256
   ```
3. Run:
   ```powershell
   .\AICodeReviewer.exe "C:\path\to\project" --type best_practices --programmers "Alice Bob" --reviewers "Charlie"
   ```

For advanced usage and options, see [README.md](README.md).

## Known Notes
- Windows SmartScreen may warn because the executable is not code-signed. If possible, use a code signing certificate for future releases.
- AWS profile features use Windows Credential Manager via `keyring`. Use `--set-profile`/`--clear-profile` if needed.

## Licenses
- Project license: see [LICENSE](LICENSE)
- Third-party notices: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

## Changelog
- v0.1.0
  - Initial Windows binary release
  - Adds interactive review flow and multi-language scanning
  - Includes performance and rate-limit controls via `config.ini`

## Screenshots
Below are sample screenshots from the interactive workflow and reports:

![Sample Project 1](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_1.PNG)
![Sample Project 2](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_2.PNG)
![Sample Project 3](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_3.PNG)
![Sample Project 4](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_4.PNG)
![Sample Project 5](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_5.PNG)
![Sample Project 6](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_6.PNG)
![Sample Project 7](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_7.PNG)
![Sample Project 8](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_8.PNG)
![Sample Project 9](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_9.PNG)
![Sample Project 10](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_10.PNG)
![Sample Project 11](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_11.PNG)
![Sample Project 12](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_12.PNG)
![Sample Project 13](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_13.PNG)
![Sample Project 14](https://github.com/gallaway-jp/AICodeReviewer/releases/download/v0.1.0/AICodeReviewer_sample_project_14.PNG)