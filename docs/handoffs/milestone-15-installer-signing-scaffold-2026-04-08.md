# Milestone 15 Installer Signing Scaffold Handoff

Date: 2026-04-08

## Scope

Add an opt-in Windows code-signing path for the packaged EXE and installer without breaking the repository's existing unsigned local and CI build baselines.

## What Changed

- added `tools/sign_windows_binary.ps1` as the shared signing helper for Windows artifacts
- `build_exe.bat` now signs `dist/AICodeReviewer.exe` before writing the SHA256 checksum when `WINDOWS_SIGN_CERT_PATH` is configured
- `build_installer.bat` now signs `dist/installer/AICodeReviewer-Setup-<version>.exe` after Inno Setup completes when `WINDOWS_SIGN_CERT_PATH` is configured
- `.github/workflows/windows-installer.yml` now supports an optional signing path by decoding `WINDOWS_SIGN_CERT_BASE64` into a temporary `.pfx` file and passing `WINDOWS_SIGN_CERT_PASSWORD` into the build step
- `tools/manual_checks/installer/inspect_installer_artifact.ps1` and `tools/manual_checks/installer/run_installer_smoke_validation.ps1` now report both EXE and installer signature status
- `tools/manual_checks/installer/validation-log-template.md` now records EXE signature status alongside the installer preflight fields

## Design Constraints Locked In

- unsigned builds remain the default and must keep succeeding when no certificate is configured
- signing must happen before the EXE checksum is generated so the published checksum matches the signed binary
- CI certificate material should live in GitHub secrets, not in the repository
- the shared signing helper should fail loudly when signing is requested but `signtool.exe` or the configured certificate cannot be found

## Validation

- `cmd /c build_exe.bat` succeeded without signing configuration, and `tools/sign_windows_binary.ps1` skipped signing cleanly before checksum generation
- `cmd /c build_installer.bat` still stopped at the known missing-Inno-Setup prerequisite (`ISCC.exe` not found), which confirms the signing scaffold did not regress the existing local installer entry point on this machine

## Remaining Work

- provision a real signing certificate and GitHub secret-management path
- run the installer workflow with signing enabled and inspect the resulting EXE and installer signatures
- repeat the relevant smoke-validation path against a signed artifact
- complete the remaining elevated all-users interactive validation and then add user-manual install/uninstall guidance