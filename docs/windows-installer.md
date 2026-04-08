# Windows Installer Guide

This guide records the Milestone 15 Windows-installer baseline for AICodeReviewer.

It is currently maintainer-focused: it documents the chosen installer technology, the checked-in installer build inputs, and the remaining gaps before Milestone 15 can be treated as fully complete.

## Chosen Approach

The current repository baseline chooses Inno Setup for the first native Windows installer implementation.

## Trade-Off Analysis

### MSI

Pros:

- standard Windows enterprise format
- strong Group Policy and fleet-management story
- familiar to many managed Windows environments

Cons:

- authoring and custom action flow are heavier than this repository needs right now
- a robust MSI path usually implies WiX or another dedicated authoring toolchain
- slower contributor iteration for a single-desktop-app packaging flow

Decision:

- not chosen for the first milestone slice because the repository needs a practical maintainer build path before it needs enterprise deployment controls

### NSIS

Pros:

- lightweight and flexible
- good scriptability for custom install and uninstall behavior

Cons:

- lower-level installer scripting burden than needed for this application
- more custom work for a polished modern wizard baseline
- less straightforward default experience for the desktop-focused installer path than Inno Setup

Decision:

- not chosen because the repository benefits more from a batteries-included desktop installer than from NSIS's lower-level flexibility

### Inno Setup

Pros:

- mature Windows-native installer toolchain with broad contributor familiarity
- simple packaging model for a PyInstaller-produced desktop executable
- built-in support for shortcuts, uninstall flows, license display, and modern wizard UX
- pragmatic scripting model for modest custom behavior such as optional preservation of config and log files during uninstall

Cons:

- Windows-only toolchain
- signing and CI integration still need explicit follow-through outside the basic local build script
- less aligned with enterprise deployment policy than MSI-based approaches

Decision:

- chosen for the current Milestone 15 baseline as the best balance of contributor simplicity, native Windows UX, and fit with the existing PyInstaller release path

### MSIX

Pros:

- modern Windows packaging story
- cleaner sandboxing and update model when aligned with Windows app-distribution expectations

Cons:

- more restrictive app model than the current desktop application expects
- greater friction around local file access, process behavior, and traditional desktop deployment assumptions
- higher packaging-policy overhead for the current repository baseline

Decision:

- not chosen for the first milestone slice because the application is still optimized around a conventional desktop executable and local-maintainer release flow rather than a Store-style packaging model

## Checked-In Installer Inputs

The initial installer baseline now uses these files:

- `build_installer.bat`
- `installer/AICodeReviewer.iss`
- `installer/default-config.ini`
- existing EXE packaging inputs:
  - `build_exe.bat`
  - `AICodeReviewer.spec`

## Build Flow

The maintainer flow is:

1. install Inno Setup 6 or set `INNO_SETUP_COMPILER` to `ISCC.exe`
2. run `build_installer.bat`
3. let the script rebuild the EXE via `build_exe.bat`
4. let the script stage the release payload and invoke the checked-in Inno Setup definition
5. collect the installer output from `dist/installer/`

The repository also now includes a first CI baseline at `.github/workflows/windows-installer.yml`.

That workflow:

- runs on `windows-latest`
- installs Inno Setup 6 through Chocolatey
- installs the Python package with GUI extras
- runs `build_installer.bat`
- uploads the produced installer plus the packaged EXE and checksum as workflow artifacts

The installer currently packages:

- `AICodeReviewer.exe`
- `AICodeReviewer.exe.sha256`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `README.md`
- a clean default `config.ini` derived from a sanitized installer template rather than the maintainer's working copy

## Install And Uninstall Behavior

The current Inno Setup baseline installs to `Program Files\AICodeReviewer` and creates:

- a Start Menu shortcut that launches the GUI via `AICodeReviewer.exe --gui`
- a Start Menu shortcut for the CLI entry point
- an optional desktop shortcut for the GUI

The uninstaller now asks whether user data stored in the install directory should be preserved.

Current user-data definition for the installer flow:

- `config.ini`
- `aicodereviewer.log`
- `aicodereviewer-audit.log`

This is intentionally scoped to the current application behavior, where the default config and log paths are relative to the working directory or install directory rather than an AppData-only layout.

## Current Limitations

Milestone 15 is not fully complete yet.

Open follow-on work:

- validate a full successful installer build on a machine with Inno Setup installed
- verify install, GUI launch, CLI launch, uninstall, and preserve/remove-data flows end to end
- add installer and uninstall instructions to the task-oriented user manual once the build is validated end to end
- decide whether installer signing should be wired into the local script, the CI workflow, or both
- document update and rollback expectations after the first successful installer build is validated

Current CI limitation:

- the checked-in workflow produces an unsigned installer artifact baseline only; signing is still explicitly pending

## Recommendation

Use the current Inno Setup baseline as the first implementation path for Milestone 15.

If later requirements shift toward enterprise deployment, policy-managed rollouts, or stricter Windows packaging guarantees, revisit MSI or MSIX after the basic installer workflow is proven and documented.