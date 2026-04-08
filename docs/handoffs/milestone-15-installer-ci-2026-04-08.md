# Milestone 15 Installer CI Handoff

Date: 2026-04-08

## Scope

Extend the initial Milestone 15 installer foundation with a reproducible CI packaging path.

This handoff now also records the first successful validation pass for that workflow.

## What Was Added

- `.github/workflows/windows-installer.yml`

## Workflow Behavior

- triggers on `workflow_dispatch`
- triggers on pushed release-like tags matching `v*`
- runs on `windows-latest`
- installs Inno Setup 6 via Chocolatey
- installs the Python package with GUI extras
- runs `build_installer.bat`
- uploads these artifacts:
  - `dist/installer/*.exe`
  - `dist/AICodeReviewer.exe`
  - `dist/AICodeReviewer.exe.sha256`

## Validation Result

- first successful end-to-end run: GitHub Actions workflow run `24111725510`
- validated commit: `1d38689` on `main`
- outcome: the workflow built the EXE, compiled the Inno Setup installer, and uploaded the expected artifacts successfully

## Fixes Required To Reach Green CI

- `build_installer.bat` now reads the package version from `pyproject.toml` through a temp file instead of fragile inline `for /f` Python parsing in `cmd.exe`
- `build_exe.bat` and `build_installer.bat` now use explicit repository-root paths for the spec file, helper scripts, staged payload, and installer definition instead of depending on implicit working-directory resolution
- `.gitignore` now explicitly allows the checked-in `AICodeReviewer.spec` file so the required PyInstaller input is present in GitHub Actions checkouts

## Why This Slice Exists

- the local installer foundation already had a checked-in Inno Setup definition and batch entry point, but the repository still lacked a reproducible CI path
- adding the workflow makes the installer baseline less dependent on one maintainer machine having Inno Setup preinstalled
- the workflow stays intentionally narrow and reuses the checked-in `build_installer.bat` path instead of reimplementing packaging logic inside YAML

## Remaining Work

- validate installer install and uninstall behavior end to end after a successful build artifact is produced
- add signing once the certificate and secret-management path are defined
- add user-manual install and uninstall guidance after the installer artifact path is validated beyond build-only CI

The CI-build acceptance slice is now satisfied; the remaining Milestone 15 work is primarily artifact-consumption, signing, and user-facing documentation.