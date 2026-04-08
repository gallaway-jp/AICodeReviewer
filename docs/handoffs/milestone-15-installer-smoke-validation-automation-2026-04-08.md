# Milestone 15 Installer Smoke Validation Automation Handoff

Date: 2026-04-08

## Scope

Reduce the remaining manual installer validation burden by making install and uninstall smoke validation scriptable for both elevated all-users and non-admin current-user Windows shells.

## What Changed

- `installer/AICodeReviewer.iss` now accepts silent uninstall control flags:
  - `/PRESERVEUSERDATA`
  - `/REMOVEUSERDATA`
- silent uninstall now defaults to preserving user data when no explicit flag is provided
- `tools/manual_checks/installer/run_installer_smoke_validation.ps1` now performs a repeatable smoke pass against a downloaded installer artifact in either current-user or all-users mode

## Smoke Script Coverage

The PowerShell script:

- reuses `inspect_installer_artifact.ps1` to locate and preflight the artifact
- installs the application silently into a controlled validation directory appropriate for the selected install mode
- verifies the installed EXE, config, uninstaller, and Start Menu shortcuts exist immediately after install
- runs `AICodeReviewer.exe --help` with process-level exit-code validation and captured stdout/stderr logs
- executes a preserve-data uninstall via `/PRESERVEUSERDATA`
- reinstalls and executes a remove-data uninstall via `/REMOVEUSERDATA`
- writes logs and a Markdown summary under `artifacts/manual-installer-validation/`

## Why This Slice Exists

- the repository still cannot complete the full interactive installer validation unattended, but it can now gather repeatable install and uninstall evidence in both non-admin and elevated shells
- this automation does not replace interactive GUI launch checks, but it closes a meaningful part of the remaining install and uninstall evidence gap

## Remaining Work

- run the smoke-validation script from an elevated Windows shell for the all-users path
- run the full interactive checklist and capture GUI-launch observations
- decide whether signing should be introduced before or after the full validation pass is repeated on a signed installer

## Validation Notes

- feature-branch workflow run `24117818915` succeeded, which confirmed the updated Inno Setup script still compiled and packaged correctly in CI after the initial smoke automation slice
- a later non-admin validation run surfaced a real packaged CLI failure on Windows console code pages, which was fixed by making CLI stdout and stderr replacement-safe before printing localized help output
- feature-branch workflow run `24119245773` then produced a fresh installer artifact with that CLI fix and the current-user override support
- a non-admin current-user smoke-validation run against `artifacts/installer-ci-24119245773` completed successfully and recorded a passing summary at `artifacts/manual-installer-validation/20260408-144307/summary.md`