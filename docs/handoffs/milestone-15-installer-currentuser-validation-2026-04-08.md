# Milestone 15 Installer Current-User Validation Handoff

Date: 2026-04-08

## Scope

Remove the non-admin validation blocker by allowing the installer and smoke-validation script to run in explicit current-user mode, then validate that path end to end against a fresh CI artifact.

## What Changed

- `installer/AICodeReviewer.iss` now allows command-line privilege overrides via `PrivilegesRequiredOverridesAllowed=commandline`
- `installer/AICodeReviewer.iss` now sets `UsePreviousPrivileges=no` so validation runs do not silently inherit an earlier install mode
- `tools/manual_checks/installer/run_installer_smoke_validation.ps1` now supports:
  - `-InstallMode Auto`
  - `-InstallMode CurrentUser`
  - `-InstallMode AllUsers`
- `src/aicodereviewer/main.py` now reconfigures stdout and stderr with replacement-safe error handling so packaged `AICodeReviewer.exe --help` does not crash on Windows console encodings such as cp932 during smoke validation

## Why This Slice Exists

- the prior smoke-validation script required elevation unconditionally because the installer defaulted to admin mode
- Inno Setup supports `/CURRENTUSER` and `/ALLUSERS` overrides when command-line privilege overrides are enabled
- this allows real install and uninstall smoke validation to proceed on developer shells that are not elevated, while preserving the existing all-users admin default for the normal installer path

## Expected Validation Path

- use `-InstallMode CurrentUser` from a non-admin shell to install under a user-writable directory and validate preserve/remove-data uninstall behavior
- use `-InstallMode AllUsers` from an elevated shell when validating the default Program Files path

## Validation Result

- feature-branch workflow run `24119245773` produced the first fresh artifact with both current-user installer override support and the packaged CLI help encoding fix
- artifact root used for validation: `artifacts/installer-ci-24119245773`
- non-admin smoke-validation summary: `artifacts/manual-installer-validation/20260408-144307/summary.md`
- validated install directory: `C:\Users\Colin\AppData\Local\Programs\AICodeReviewer-Validation`
- checksum verification passed
- EXE metadata matched expectations: `FileVersion 0.2.0.0`, `ProductVersion 0.2.0`
- GUI and CLI Start Menu shortcuts were both present immediately after install
- preserve-data uninstall passed
- remove-data uninstall passed

## Remaining Work

- repeat the smoke-validation path in all-users mode from an elevated shell when convenient
- complete the full interactive GUI validation from the default all-users install path
- decide and implement the installer-signing path
- add user-manual installer and uninstall guidance once the remaining validation work is closed