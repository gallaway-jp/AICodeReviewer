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
- certificate provisioning and signed-artifact validation still need explicit follow-through outside the checked-in signing scaffold
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

- uses `actions/checkout@v6`
- uses `actions/setup-python@v6`
- runs on `windows-latest`
- installs Inno Setup 6 through Chocolatey
- installs the Python package with GUI extras
- optionally decodes a signing certificate from GitHub Actions secrets when one is configured
- runs `build_installer.bat`
- uses `actions/upload-artifact@v7`
- uploads the produced installer, installer checksum, packaged EXE, and EXE checksum as workflow artifacts

That CI path is now validated end to end.

## Optional Signing Scaffold

The repository now includes an opt-in signing helper at `tools/sign_windows_binary.ps1`.

Unsigned builds remain the default. Signing activates only when `WINDOWS_SIGN_CERT_PATH` points to a `.pfx` certificate file.

Optional signing environment variables:

- `WINDOWS_SIGN_CERT_PATH` for the `.pfx` file to use
- `WINDOWS_SIGN_CERT_PASSWORD` for the certificate password when needed
- `WINDOWS_SIGN_TIMESTAMP_URL` to override the default timestamp server (`https://timestamp.digicert.com`)
- `WINDOWS_SIGNTOOL_PATH` to override `signtool.exe` discovery if the Windows SDK is installed in a nonstandard location

When certificate configuration is present:

- `build_exe.bat` signs `dist/AICodeReviewer.exe` before generating the SHA256 checksum
- `build_installer.bat` signs `dist/installer/AICodeReviewer-Setup-<version>.exe` after Inno Setup finishes packaging it
- `.github/workflows/windows-installer.yml` can sign both artifacts when `WINDOWS_SIGN_CERT_BASE64` and `WINDOWS_SIGN_CERT_PASSWORD` are configured as repository or organization secrets

Local validation on this machine for the unsigned default path:

- `cmd /c build_exe.bat` succeeded with no signing certificate configured, and the helper skipped signing before checksum generation as intended
- `cmd /c build_installer.bat` still stopped at the known missing-Inno-Setup prerequisite, which confirms the signing scaffold did not change the existing local compiler gate

Verified baseline:

- GitHub Actions workflow run `24111725510`
- commit `1d38689` on `main`
- successful artifact upload for the installer plus the packaged EXE and checksum

Post-maintenance revalidation:

- GitHub Actions workflow run `24115382363`
- commit `f6bc077` on `main`
- successful rerun after updating the workflow to current action majors to clear the observed Node 20 deprecation warning

The validation pass required three concrete fixes in the checked-in packaging path:

- replace fragile batch `for /f` version parsing with a temp-file read from `pyproject.toml`
- make `build_exe.bat` and `build_installer.bat` use explicit repository-root paths instead of implicit working-directory assumptions
- track the required checked-in `AICodeReviewer.spec` file in git instead of letting `.gitignore` exclude it from CI checkouts

The installer currently packages:

- `AICodeReviewer.exe`
- `AICodeReviewer.exe.sha256`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `README.md`
- a clean default `config.ini` derived from a sanitized installer template rather than the maintainer's working copy

The local installer output now also includes `dist/installer/AICodeReviewer-Setup-<version>.exe.sha256`, generated after optional signing so the published checksum matches the final installer binary.

## Verified CI Artifact Snapshot

The first validated installer workflow artifact was downloaded and inspected from GitHub Actions workflow run `24111725510`.

You can repeat the same artifact preflight locally with:

```powershell
pwsh -File tools/manual_checks/installer/inspect_installer_artifact.ps1 -ArtifactRoot artifacts/installer-ci-24111725510
```

Observed payload:

- `windows-installer/AICodeReviewer.exe`
- `windows-installer/AICodeReviewer.exe.sha256`
- `windows-installer/installer/AICodeReviewer-Setup-0.2.0.exe`

The current milestone branch extends that artifact contract with `windows-installer/installer/AICodeReviewer-Setup-<version>.exe.sha256` so future installer artifacts publish a checksum for the installer binary itself rather than relying only on an inspection-time recomputed hash.

That checksum path has now been validated in GitHub Actions workflow run `24130238872` on the active Milestone 15 branch: the downloaded artifact included `AICodeReviewer-Setup-0.2.0.exe.sha256`, and local inspection of `artifacts/installer-ci-24130238872` reported `InstallerChecksumStatus = Match`.

Observed properties:

- the checksum file matches the packaged EXE payload
- the installer file reports version `0.2.0`
- the installer is currently unsigned (`NotSigned`), which matches the current documented CI limitation
- the original inspected CI artifact had blank EXE version metadata, which was later addressed by the checked-in PyInstaller version-resource update

## EXE Version Metadata

The checked-in `AICodeReviewer.spec` now stamps Windows version-resource metadata onto the packaged EXE using the version from `pyproject.toml`.

Local validation on the current Milestone 15 branch produced:

- `FileVersion = 0.2.0.0`
- `ProductVersion = 0.2.0`

CI validation on workflow run `24117477221` produced the same EXE metadata in the downloaded `windows-installer` artifact:

- `ExeFileVersion = 0.2.0.0`
- `ExeProductVersion = 0.2.0`

This closes the earlier packaging-polish gap where the installer had version metadata but the packaged EXE did not.

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

- perform an elevated all-users interactive validation pass from a produced installer artifact, including GUI launch, CLI launch, and uninstall behavior from the default `Program Files` path
- add installer and uninstall instructions to the task-oriented user manual once the build is validated end to end
- provision a real signing certificate and secret-management path, then validate the signed EXE and installer artifacts in CI and on a Windows machine
- document update and rollback expectations after the all-users interactive path and signed-artifact validation are settled

Current CI limitation:

- the checked-in workflow signs artifacts only when `WINDOWS_SIGN_CERT_BASE64` and `WINDOWS_SIGN_CERT_PASSWORD` are configured; otherwise it still produces the unsigned baseline by design

Current local-maintainer limitation on this machine:

- `build_installer.bat` now gets through version detection correctly, but local installer compilation still stops until Inno Setup 6 is installed or `INNO_SETUP_COMPILER` is set

## Manual Validation Checklist

Use this checklist against a produced installer artifact before treating the install and uninstall path as fully validated.

Maintainer helpers for this step now live under `tools/manual_checks/installer/`:

- `download_installer_artifact.ps1` for downloading and extracting a GitHub Actions `windows-installer` artifact into the normalized local `artifacts/installer-ci-<runid>/windows-installer/` layout
- `inspect_installer_artifact.ps1` for EXE checksum validation, installer checksum validation when published, version inspection, and EXE-plus-installer signing preflight
- `run_installer_smoke_validation.ps1` for current-user or all-users silent install, CLI launch, and preserve/remove-data uninstall smoke validation
- `start_installer_manual_validation_session.ps1` for generating a prefilled manual validation log from a workflow run or local artifact root
- `validation-log-template.md` for recording the manual install and uninstall results

To download and normalize a specific workflow artifact locally, run:

```powershell
pwsh -File tools/manual_checks/installer/download_installer_artifact.ps1 -RunId 24130238872
```

To download the latest successful installer artifact for a branch, run:

```powershell
pwsh -File tools/manual_checks/installer/download_installer_artifact.ps1 -Branch milestone/15-windows-installer
```

The helper path has been validated against workflow run `24130238872`: after download, `artifacts/installer-ci-24130238872/windows-installer/` was immediately consumable by `inspect_installer_artifact.ps1`, which still reported `ExeChecksumMatches = True` and `InstallerChecksumStatus = Match`.

The inspection and smoke-validation helpers can now resolve artifacts through that download helper directly. For example:

```powershell
pwsh -File tools/manual_checks/installer/inspect_installer_artifact.ps1 -RunId 24130238872
```

```powershell
pwsh -File tools/manual_checks/installer/run_installer_smoke_validation.ps1 -RunId 24130238872 -InstallMode CurrentUser
```

To start an interactive manual-validation session log from a workflow run, run:

```powershell
pwsh -File tools/manual_checks/installer/start_installer_manual_validation_session.ps1 -RunId 24130238872 -Operator Colin
```

That session-bootstrap path is now validated on this machine as well. Running the helper against workflow run `24130238872` generated `artifacts/manual-installer-validation-prep/20260408-202542/validation-log.md` with the workflow branch (`feature/installer-checksum-artifact`), commit (`ba6ebb21712aef30a506c8092212810c0a037ec3`), matching EXE and installer checksums, `FileVersion 0.2.0.0`, `ProductVersion 0.2.0`, unsigned signature status for both binaries, and the expected follow-up inspection plus smoke-validation commands.

The helper now also preserves workflow branch and commit metadata when it reuses an existing `artifacts/installer-ci-<runid>/` download instead of fetching the artifact again, so repeated prep runs still produce a fully populated session log.

That direct smoke-validation path has now also been validated on this machine: it completed successfully against workflow run `24130238872` and recorded a passing summary at `artifacts/manual-installer-validation/20260408-195928/summary.md` with `InstallerChecksumStatus = Match`, both Start Menu shortcuts present after install, and passing preserve/remove-data uninstall paths.

For an elevated unattended smoke pass on a Windows machine, run:

```powershell
pwsh -File tools/manual_checks/installer/run_installer_smoke_validation.ps1 -ArtifactRoot artifacts/installer-ci-24119245773
```

For a non-admin current-user smoke pass, run:

```powershell
pwsh -File tools/manual_checks/installer/run_installer_smoke_validation.ps1 -ArtifactRoot artifacts/installer-ci-24119245773 -InstallMode CurrentUser
```

The smoke script does not replace the full interactive checklist. It is designed to validate:

- silent install to a controlled validation directory
- CLI launch via `AICodeReviewer.exe --help`
- preserve-data uninstall behavior via `/PRESERVEUSERDATA`
- remove-data uninstall behavior via `/REMOVEUSERDATA`

The Inno Setup uninstaller now recognizes those silent uninstall flags. In silent mode without an explicit flag, it defaults to preserving user data.

The installer itself now allows command-line privilege overrides, so the smoke script can use `/CURRENTUSER` in non-admin sessions and `/ALLUSERS` in elevated sessions.

Validation status for this automation path:

- local non-admin shells can now use `-InstallMode CurrentUser` for a per-user smoke pass
- packaged CLI help output no longer crashes on Windows console code pages because `src/aicodereviewer/main.py` now reconfigures stdout and stderr with replacement-safe encoding behavior before printing localized help text
- feature-branch workflow run `24119245773` produced a fresh installer artifact containing the current-user override support and CLI help fix
- a non-admin current-user smoke-validation run against `artifacts/installer-ci-24119245773` completed successfully, confirming checksum match, `FileVersion 0.2.0.0`, `ProductVersion 0.2.0`, both Start Menu shortcuts after install, and passing preserve-data plus remove-data uninstall paths
- the artifact-inspection and smoke-validation helpers now report both EXE and installer signature status so signed runs can be verified without a separate ad hoc check
- the installer build path now also emits a published installer checksum file, and the inspection plus smoke-validation helpers validate that checksum when present while remaining backward-compatible with older artifacts that predate it
- feature-branch workflow run `24130238872` validated the published installer checksum path end to end: the artifact contained `AICodeReviewer-Setup-0.2.0.exe.sha256`, the EXE checksum still matched, and the installer checksum inspected as `Match`
- the direct `-RunId` validation path is now also proven end to end: `run_installer_smoke_validation.ps1 -RunId 24130238872 -InstallMode CurrentUser` completed successfully and reused the helper-produced artifact layout without a separate manual download step
- the manual session-bootstrap path is now also proven end to end: `start_installer_manual_validation_session.ps1 -RunId 24130238872 -Operator Colin` generated a prefilled log with captured workflow metadata, checksum and version preflight, signature status, and follow-up commands even when the underlying artifact download was reused from the normalized local cache

1. Install `AICodeReviewer-Setup-<version>.exe` with default options.
2. Confirm the application lands under `Program Files\AICodeReviewer`.
3. Launch the GUI from the Start Menu shortcut and confirm the desktop window opens successfully.
4. Launch the CLI entry point from the Start Menu shortcut or install directory and run `AICodeReviewer.exe --help`.
5. Confirm `config.ini` is present in the install directory and is the sanitized installer default rather than a maintainer-local working copy.
6. Create or modify `config.ini`, `aicodereviewer.log`, and `aicodereviewer-audit.log` to exercise uninstall preservation behavior.
7. Run the uninstaller once and choose to preserve user data; confirm those files remain.
8. Reinstall if needed, rerun the uninstaller, choose removal, and confirm those files are deleted.
9. Record any SmartScreen, permission, or signing warnings observed during install or launch.

## Recommendation

Use the current Inno Setup baseline as the first implementation path for Milestone 15.

If later requirements shift toward enterprise deployment, policy-managed rollouts, or stricter Windows packaging guarantees, revisit MSI or MSIX after the basic installer workflow is proven and documented.