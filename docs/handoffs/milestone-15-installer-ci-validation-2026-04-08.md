# Milestone 15 Installer CI Validation Handoff

Date: 2026-04-08

## Scope

Validate the newly added Windows installer GitHub Actions workflow by running it for real, fixing concrete failures, and reaching a successful artifact-producing run.

## Validation Timeline

- first validation run failed in `build_installer.bat` because inline batch `for /f` parsing around the Python version-detection command broke under `cmd.exe` in GitHub Actions
- second validation run failed because the EXE packaging path still depended on implicit working-directory behavior and PyInstaller could not locate the spec file reliably through that path
- third validation run exposed the underlying repository issue: `AICodeReviewer.spec` existed locally but was ignored by `.gitignore`, so CI checkouts never received the required PyInstaller input
- fourth validation run succeeded after the spec file was tracked and the batch scripts were hardened

## Successful Run

- workflow run: `24111725510`
- job id: `70347524379`
- validated commit: `1d38689`
- result: success

## What Was Fixed

- `build_installer.bat` now reads the project version from `pyproject.toml` via a temp file instead of fragile inline parsing
- `build_exe.bat` and `build_installer.bat` now use explicit repository-root paths for helper scripts, the checked-in spec file, output directories, and the Inno Setup definition
- `.gitignore` now explicitly unignores `AICodeReviewer.spec`, and the spec file is tracked in git as a real build input

## Resulting Repository State

- the Windows installer workflow at `.github/workflows/windows-installer.yml` is now validated end to end on GitHub-hosted Windows CI
- the workflow produces and uploads:
  - the installer from `dist/installer/`
  - `dist/AICodeReviewer.exe`
  - `dist/AICodeReviewer.exe.sha256`
- the packaging path remains layered on top of the existing PyInstaller EXE flow rather than duplicating build logic in YAML

## Remaining Work

- manually install and uninstall from the produced artifact and verify preserve/remove-data behavior
- add installer signing once the certificate and secret-management path is defined
- add task-oriented installer and uninstall instructions to the user manual
- document update and rollback expectations after manual artifact validation