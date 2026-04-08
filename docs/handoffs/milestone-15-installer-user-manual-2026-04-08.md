# Milestone 15 Installer User Manual Handoff

Date: 2026-04-08

## Scope

Close the remaining Milestone 15 documentation gap for task-oriented packaged install and uninstall instructions.

## What Changed

- updated `docs/user-manual.md`
- added a new `Windows Installer Workflow` section for packaged Windows installs
- documented:
  - default install location under `Program Files\AICodeReviewer`
  - Start Menu GUI and CLI shortcuts
  - optional desktop shortcut behavior
  - first-launch verification steps for GUI, CLI, and `config.ini`
  - uninstall preserve/remove-data behavior for `config.ini`, `aicodereviewer.log`, and `aicodereviewer-audit.log`
  - current unsigned-preview warning expectations for SmartScreen or unknown publisher prompts
- updated `docs/windows-installer.md` to note that the task-oriented user-manual guidance now exists
- updated `.github/specs/platform-extensibility/spec.md` to record that the user-manual instruction gap is closed

## Why This Slice Exists

- Milestone 15 already had maintainer-facing build and validation documentation, but the user manual still lacked the packaged Windows install and uninstall workflow
- the installer acceptance criteria require installation and uninstallation instructions to be present in the documentation
- this slice closes that gap without claiming that the still-blocked elevated all-users validation or signed-artifact work is complete

## Validation

- doc content was aligned to the checked-in installer behavior in `installer/AICodeReviewer.iss`
- the user manual now matches the current installer contract for:
  - default install path
  - Start Menu shortcuts
  - optional desktop shortcut
  - preserve/remove-data uninstall prompt and affected files

## Remaining Work

- perform elevated all-users interactive validation from a produced installer artifact
- provision real signing material and validate signed EXE and installer artifacts
- document update and rollback expectations once the interactive all-users and signing paths are validated