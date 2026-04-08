# Milestone 15 Installer Checksum Artifact Handoff

Date: 2026-04-08

## Scope

Promote the installer SHA256 from an inspection-only derived value into a first-class published artifact, aligned with the existing packaged EXE checksum path.

## What Changed

- `build_installer.bat` now writes `dist/installer/AICodeReviewer-Setup-<version>.exe.sha256` after optional signing completes
- `.github/workflows/windows-installer.yml` now uploads `dist/installer/*.exe.sha256` alongside the installer executable
- `tools/manual_checks/installer/inspect_installer_artifact.ps1` now validates the installer checksum when it is published, returns explicit `ExpectedInstallerSha256` plus `InstallerChecksumStatus` fields, and stays backward-compatible with older artifacts that predate the checksum file
- `tools/manual_checks/installer/run_installer_smoke_validation.ps1` now records installer checksum status in the generated summary
- `tools/manual_checks/installer/validation-log-template.md` now records expected and actual installer SHA256 values explicitly

## Design Constraints Locked In

- installer checksum generation happens after optional signing so the published hash matches the final installer payload
- installer artifacts should now be treated as a four-file integrity set in CI and release handling:
  - `AICodeReviewer.exe`
  - `AICodeReviewer.exe.sha256`
  - `installer/AICodeReviewer-Setup-<version>.exe`
  - `installer/AICodeReviewer-Setup-<version>.exe.sha256`
- installer inspection should fail if the EXE checksum does not match, or if a published installer checksum does not match; older artifacts without the installer checksum remain inspectable as `InstallerChecksumStatus = NotPublished`

## Validation

- local batch syntax and PowerShell validation passed for the updated build and inspection scripts
- `pwsh -File tools/manual_checks/installer/inspect_installer_artifact.ps1 -ArtifactRoot artifacts/installer-ci-24119245773 -Json` succeeded against the latest existing artifact and reported `InstallerChecksumStatus = NotPublished`, which confirms backward compatibility for artifacts created before this slice
- full installer checksum generation still depends on the existing local prerequisite gap: this machine does not currently have Inno Setup available, so `build_installer.bat` still stops before the packaging step

## Remaining Work

- run the installer workflow again so the new installer checksum file is produced and uploaded in CI
- download that updated artifact and validate the published installer checksum path end to end
- continue with elevated all-users interactive validation, real certificate provisioning, and user-manual installer guidance