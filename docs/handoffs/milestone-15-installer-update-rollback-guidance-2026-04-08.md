# Milestone 15 Installer Update And Rollback Guidance Handoff

Date: 2026-04-08

## Scope

Document the currently supported packaged-build update and rollback policy for the Windows installer.

## What Changed

- updated `docs/windows-installer.md`
- updated `docs/user-manual.md`
- updated `.github/specs/platform-extensibility/spec.md`
- documented a conservative packaged-build policy:
  - uninstall the current build
  - choose preserve-data or remove-data for install-directory user files
  - install the target build
  - rerun the existing GUI, CLI, and `config.ini` first-launch checks

## Why This Slice Exists

- Milestone 15 still needed documented update and rollback expectations
- the checked-in installer contract already defines preserve/remove-data behavior clearly enough to document a supported reinstall-based workflow
- this closes the documentation gap without overstating support for an unvalidated in-place upgrade path

## Validation

- doc guidance was aligned to the checked-in installer contract in `installer/AICodeReviewer.iss`
- the documented policy depends on already validated behavior:
  - preserve/remove-data uninstall handling
  - `config.ini` packaged with `onlyifdoesntexist uninsneveruninstall`
  - existing first-launch verification steps for GUI, CLI, and install-directory configuration

## Remaining Work

- perform elevated all-users interactive validation from a produced installer artifact
- provision real signing material and validate signed EXE and installer artifacts