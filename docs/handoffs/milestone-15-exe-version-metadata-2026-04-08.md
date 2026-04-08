# Milestone 15 EXE Version Metadata Handoff

Date: 2026-04-08

## Scope

Close the packaging-polish gap where the Windows installer carried version metadata but the packaged `AICodeReviewer.exe` did not.

## What Changed

- updated `AICodeReviewer.spec` to build a Windows version resource from `pyproject.toml`
- attached that version resource to the PyInstaller `EXE(...)` definition

## Validation

Local validation via `cmd /c build_exe.bat` succeeded.

Observed version metadata on `dist/AICodeReviewer.exe`:

- `FileVersion = 0.2.0.0`
- `ProductVersion = 0.2.0`

The PyInstaller log also confirmed the resource step explicitly with `Copying version information to EXE`.

CI validation also succeeded:

- workflow run: `24117477221`
- branch: `feature/installer-exe-version-metadata`
- downloaded artifact inspection reported:
	- `ExeFileVersion = 0.2.0.0`
	- `ExeProductVersion = 0.2.0`
	- checksum match = `True`

## Notes

- the first inspected CI artifact still reflects the earlier pre-fix state, where the EXE had blank version metadata
- the updated spec means future EXE and installer builds from this branch will carry versioned EXE metadata without needing a separate manual step

## Remaining Work

- run the Windows installer workflow on this branch to confirm the EXE version-resource change carries through CI as expected
- continue with manual installer install and uninstall validation
- keep signing and user-manual install guidance as the remaining Milestone 15 follow-on items