# Milestone 15 Installer CI Handoff

Date: 2026-04-08

## Scope

Extend the initial Milestone 15 installer foundation with a reproducible CI packaging path.

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

## Why This Slice Exists

- the local installer foundation already had a checked-in Inno Setup definition and batch entry point, but the repository still lacked a reproducible CI path
- adding the workflow makes the installer baseline less dependent on one maintainer machine having Inno Setup preinstalled
- the workflow stays intentionally narrow and reuses the checked-in `build_installer.bat` path instead of reimplementing packaging logic inside YAML

## Remaining Work

- verify at least one successful CI run on the new workflow
- validate installer install and uninstall behavior end to end after a successful build artifact is produced
- add signing once the certificate and secret-management path are defined
- add user-manual install and uninstall guidance after the installer artifact path is validated beyond build-only CI