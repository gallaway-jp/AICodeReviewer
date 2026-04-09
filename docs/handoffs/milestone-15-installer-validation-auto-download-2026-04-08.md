# Milestone 15 Installer Validation Auto-Download Handoff

Date: 2026-04-08

## Scope

Remove the remaining manual artifact-prep hop from installer inspection and smoke validation by letting those entrypoints resolve workflow artifacts directly.

## What Changed

- `tools/manual_checks/installer/inspect_installer_artifact.ps1` now accepts:
  - `-RunId`
  - `-Branch`
- `tools/manual_checks/installer/run_installer_smoke_validation.ps1` now accepts:
  - `-RunId`
  - `-Branch`
- both scripts now call `download_installer_artifact.ps1` when a workflow run or branch is supplied instead of requiring a pre-existing local artifact directory
- `docs/windows-installer.md` now documents the direct inspection and smoke-validation command paths that start from a workflow run id

## Why This Slice Exists

- the repository already had a deterministic artifact download helper, but maintainers still had to remember a separate prep command before inspection or smoke validation
- this keeps the validation entrypoints aligned with the way milestone evidence is actually produced: from specific workflow runs
- the remaining all-users and signed-artifact validation work will be easier to repeat if the validation scripts can fetch their own inputs

## Validation

- the updated scripts should reject ambiguous input when both `-ArtifactRoot` and `-RunId` or `-Branch` are supplied
- `pwsh -File tools/manual_checks/installer/inspect_installer_artifact.ps1 -RunId 24130238872 -Json` succeeded and reported:
  - `ExeChecksumMatches = True`
  - `InstallerChecksumStatus = Match`
- `pwsh -File tools/manual_checks/installer/run_installer_smoke_validation.ps1 -RunId 24130238872 -InstallMode CurrentUser` completed successfully and recorded a passing summary at `artifacts/manual-installer-validation/20260408-195928/summary.md`
- that summary confirmed:
  - `InstallerChecksumStatus = Match`
  - both Start Menu shortcuts were present after install
  - preserve-data uninstall passed
  - remove-data uninstall passed

## Remaining Work

- continue with elevated all-users validation, real certificate provisioning, and user-manual installer guidance