# Milestone 15 Installer Foundation Handoff

Date: 2026-04-08

## Scope

Start Milestone 15 by choosing the Windows installer approach and checking in the first installer build surface.

## What Was Added

- `build_installer.bat` as the maintainer entry point for Windows installer packaging
- `installer/AICodeReviewer.iss` as the checked-in Inno Setup definition
- `installer/default-config.ini` as a sanitized installed default configuration template
- `docs/windows-installer.md` as the trade-off analysis and maintainer guide for the current installer baseline

## Key Decisions

- chose Inno Setup over MSI, NSIS, and MSIX for the first native Windows installer path
- kept the installer layered over the already validated `build_exe.bat` and `AICodeReviewer.spec` flow rather than replacing the EXE packaging contract
- avoided shipping the repository working-copy `config.ini`, because that file can contain machine-specific maintainer values and should not become the installed default
- treated install-directory `config.ini` and log files as the current uninstall preservation boundary, because the application still defaults to working-directory-relative config and log paths

## Validation

- local environment check confirmed Inno Setup 6 is not currently installed on this machine and no `ISCC.exe` path was detected
- `cmd /c build_installer.bat` failed early with the expected prerequisite message: `ERROR: Inno Setup 6 compiler (ISCC.exe) was not found.`
- the checked-in `build_installer.bat` therefore fails early with a clear prerequisite error instead of silently producing an incomplete installer path

## Remaining Work

- validate a successful end-to-end installer build on a Windows machine with Inno Setup 6 installed
- verify install, uninstall, and preserve/remove-user-data behavior end to end
- add user-manual install/uninstall instructions after the installer path is validated beyond scaffolding
- decide and implement the signing path for installer artifacts