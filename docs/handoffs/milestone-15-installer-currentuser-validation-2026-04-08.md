# Milestone 15 Installer Current-User Validation Handoff

Date: 2026-04-08

## Scope

Remove the non-admin validation blocker by allowing the installer and smoke-validation script to run in explicit current-user mode.

## What Changed

- `installer/AICodeReviewer.iss` now allows command-line privilege overrides via `PrivilegesRequiredOverridesAllowed=commandline`
- `installer/AICodeReviewer.iss` now sets `UsePreviousPrivileges=no` so validation runs do not silently inherit an earlier install mode
- `tools/manual_checks/installer/run_installer_smoke_validation.ps1` now supports:
  - `-InstallMode Auto`
  - `-InstallMode CurrentUser`
  - `-InstallMode AllUsers`

## Why This Slice Exists

- the prior smoke-validation script required elevation unconditionally because the installer defaulted to admin mode
- Inno Setup supports `/CURRENTUSER` and `/ALLUSERS` overrides when command-line privilege overrides are enabled
- this allows real install and uninstall smoke validation to proceed on developer shells that are not elevated, while preserving the existing all-users admin default for the normal installer path

## Expected Validation Path

- use `-InstallMode CurrentUser` from a non-admin shell to install under a user-writable directory and validate preserve/remove-data uninstall behavior
- use `-InstallMode AllUsers` from an elevated shell when validating the default Program Files path

## Remaining Work

- run the current-user smoke-validation path end to end and capture the result
- optionally repeat the smoke-validation path in all-users mode from an elevated shell
- continue toward the full interactive GUI validation, signing, and user-manual installer guidance