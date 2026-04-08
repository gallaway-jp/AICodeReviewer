# Milestone 15 Installer Manual Validation Prep Handoff

Date: 2026-04-08

## Scope

Prepare the remaining Milestone 15 manual installer validation work so it can run on the documented branch structure and produce repeatable evidence instead of freeform notes.

## Branch Workflow Reset

- created `milestone/15-windows-installer` from `main`
- created `feature/installer-manual-validation-prep` from `milestone/15-windows-installer`

This resets ongoing Milestone 15 work onto the documented `feature/* -> milestone/*` path after the earlier installer foundation and CI validation slices had landed directly on `main`.

## What Was Added

- `tools/manual_checks/installer/inspect_installer_artifact.ps1`
- `tools/manual_checks/installer/validation-log-template.md`

## Purpose

- the PowerShell helper repeats the artifact preflight that had previously been performed manually against the downloaded CI artifact:
  - verifies the packaged EXE checksum against `AICodeReviewer.exe.sha256`
  - reports installer and EXE version metadata
  - reports the installer signing status
- the Markdown template gives maintainers a single place to record install, launch, uninstall, preserve-data, remove-data, and warning observations

Observed during helper validation:

- installer version metadata is present and reports `0.2.0`
- packaged EXE version metadata is currently blank, which is not a blocker for manual install validation but should be treated as a follow-on packaging polish gap

## Documentation Follow-Through

- `docs/windows-installer.md` now points maintainers at the new manual-check helper and validation log template
- `.github/specs/platform-extensibility/spec.md` now records that manual-validation prep exists, even though the actual install and uninstall run is still pending

## Remaining Work

- run the helper and template as part of a real installer install and uninstall pass on Windows
- merge this feature branch into `milestone/15-windows-installer`
- continue toward signing and eventual user-manual install guidance after manual validation is complete