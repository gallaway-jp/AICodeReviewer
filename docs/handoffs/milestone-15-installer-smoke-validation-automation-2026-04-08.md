# Milestone 15 Installer Smoke Validation Automation Handoff

Date: 2026-04-08

## Scope

Reduce the remaining manual installer validation burden by making install and uninstall smoke validation scriptable on an elevated Windows shell.

## What Changed

- `installer/AICodeReviewer.iss` now accepts silent uninstall control flags:
  - `/PRESERVEUSERDATA`
  - `/REMOVEUSERDATA`
- silent uninstall now defaults to preserving user data when no explicit flag is provided
- `tools/manual_checks/installer/run_installer_smoke_validation.ps1` now performs a repeatable elevated smoke pass against a downloaded installer artifact

## Smoke Script Coverage

The PowerShell script:

- requires an elevated shell because the installer currently uses `PrivilegesRequired=admin`
- reuses `inspect_installer_artifact.ps1` to locate and preflight the artifact
- installs the application silently into a controlled validation directory
- verifies the installed EXE, config, uninstaller, and Start Menu shortcuts exist
- runs `AICodeReviewer.exe --help`
- executes a preserve-data uninstall via `/PRESERVEUSERDATA`
- reinstalls and executes a remove-data uninstall via `/REMOVEUSERDATA`
- writes logs and a Markdown summary under `artifacts/manual-installer-validation/`

## Why This Slice Exists

- the repository still cannot complete the full interactive installer validation in a non-elevated shell
- this automation does not replace interactive GUI launch checks, but it closes a meaningful part of the remaining install and uninstall evidence gap

## Remaining Work

- run the smoke-validation script from an elevated Windows shell
- run the full interactive checklist and capture GUI-launch observations
- decide whether signing should be introduced before or after the full validation pass is repeated on a signed installer