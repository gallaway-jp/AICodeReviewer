# Milestone 15 Installer Artifact Download Helper Handoff

Date: 2026-04-08

## Scope

Replace ad hoc GitHub CLI artifact download steps with a repeatable maintainer helper that downloads and extracts Windows installer workflow artifacts into the normalized local layout expected by the existing validation tools.

## What Changed

- added `tools/manual_checks/installer/download_installer_artifact.ps1`
- the helper can:
  - download a specific workflow run via `-RunId`
  - resolve the latest successful installer workflow run, optionally narrowed by `-Branch`
  - fetch the `windows-installer` artifact through the GitHub API
  - extract it directly into `artifacts/installer-ci-<runid>/windows-installer/`
  - reuse an already-normalized local artifact directory unless `-Force` is supplied
- `docs/windows-installer.md` now documents the helper before the inspection and smoke-validation commands

## Why This Slice Exists

- the installer inspection and smoke-validation helpers already assume a normalized local artifact layout, but prior retrieval steps were still manual and error-prone
- direct `gh run download` usage in local validation was inconsistent enough to warrant a repository-owned helper with predictable extraction behavior
- remaining Milestone 15 work such as elevated all-users validation and future signed-artifact checks benefit from a deterministic local artifact acquisition path

## Validation

- `pwsh -File tools/manual_checks/installer/download_installer_artifact.ps1 -RunId 24130238872 -Force -Json` produced the expected `artifacts/installer-ci-24130238872/windows-installer/` payload layout for the known-good checksum-bearing run
- `pwsh -File tools/manual_checks/installer/inspect_installer_artifact.ps1 -ArtifactRoot artifacts/installer-ci-24130238872 -Json` then succeeded against that helper-produced layout without any additional directory reshaping and reported:
  - `ExeChecksumMatches = True`
  - `InstallerChecksumPublished = True`
  - `InstallerChecksumStatus = Match`

## Remaining Work

- continue with elevated all-users validation, real certificate provisioning, and user-manual installer guidance