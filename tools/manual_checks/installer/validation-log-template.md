# Windows Installer Manual Validation Log

Use this template when validating a produced Windows installer artifact by hand.

## Session Metadata

- Date:
- Operator:
- Machine / Windows version:
- Branch:
- Commit:
- Workflow run:
- Artifact root:

## Artifact Preflight

- [ ] Run `pwsh -File tools/manual_checks/installer/inspect_installer_artifact.ps1 -ArtifactRoot <artifact-dir>`
- Expected EXE SHA256:
- Actual EXE SHA256:
- EXE checksum match:
- Expected installer SHA256:
- Actual installer SHA256:
- Installer checksum status:
- EXE file version:
- EXE product version:
- EXE signature status:
- Installer file version:
- Installer product version:
- Installer signature status:
- Preflight notes:

## Install Validation

- [ ] Installer launches successfully
- [ ] Default install completes successfully
- [ ] Files are installed under `Program Files\AICodeReviewer`
- [ ] `config.ini` is present and matches the sanitized installer default
- [ ] Start Menu GUI shortcut launches the desktop app
- [ ] Start Menu CLI shortcut launches successfully
- [ ] `AICodeReviewer.exe --help` runs from the install directory
- Install notes:

## Preserve-Data Uninstall Validation

- [ ] Created or modified `config.ini`
- [ ] Created or modified `aicodereviewer.log`
- [ ] Created or modified `aicodereviewer-audit.log`
- [ ] Uninstaller preserve-data option was selected
- [ ] Data files remained after uninstall
- Preserve-data notes:

## Remove-Data Uninstall Validation

- [ ] Reinstalled if needed for a second uninstall pass
- [ ] Uninstaller remove-data option was selected
- [ ] Data files were deleted after uninstall
- Remove-data notes:

## Warnings And User Experience

- [ ] SmartScreen warning observed
- [ ] Unsigned publisher warning observed
- [ ] Unexpected permission/UAC issue observed
- Warning details:

## Result

- Overall status:
- Follow-up actions: