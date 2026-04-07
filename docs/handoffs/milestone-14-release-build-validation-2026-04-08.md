# Milestone 14 Handoff: Release Build Validation

Date: 2026-04-08

## Summary

The Windows release-packaging path was revalidated on the current `release/0.2.0` baseline so the next GitHub release can attach the same executable asset pair as `v0.1.0`.

## What Changed

- updated `build_exe.bat` to use the repository `.venv` interpreter when present instead of relying on ambient `PATH` resolution for `python`, `pip`, and `pyinstaller`
- updated `build_exe.bat` to package from the checked-in `AICodeReviewer.spec` file instead of invoking PyInstaller directly on `src/aicodereviewer/main.py`, which had been rewriting the spec on each build
- added deterministic checksum generation so the script now regenerates `dist/AICodeReviewer.exe.sha256` alongside `dist/AICodeReviewer.exe`
- updated `tools/generate_licenses.py` to invoke `pip-licenses` from the same interpreter environment as the build rather than assuming an activated shell
- moved the maintained ICO asset into `src/aicodereviewer/assets/icon.ico` and updated `AICodeReviewer.spec` plus `tools/convert_icon.py` to stop depending on ignored `build/icon.ico`
- kept icon regeneration tolerant of missing conversion tooling by reusing the maintained ICO when SVG conversion tools are unavailable

## Validation

- `cmd /c build_exe.bat`
  - completed successfully using `D:\Development\Python\AICodeReviewer\.venv\Scripts\python.exe`
  - rebuilt `dist/AICodeReviewer.exe`
  - regenerated `dist/AICodeReviewer.exe.sha256`
- `dist\AICodeReviewer.exe --help`
  - completed successfully, confirming the rebuilt executable starts and exposes the expected CLI surface

Rebuilt asset state after validation:

- `dist/AICodeReviewer.exe`
- `dist/AICodeReviewer.exe.sha256`
  - `18195B079234DB3138936261132B75552BE7FF345F004533055F9BB960929422  AICodeReviewer.exe`

## Remaining Release Work

- create the `v0.2.0` tag once the release branch is ready to merge
- publish the rebuilt `dist/AICodeReviewer.exe` and `dist/AICodeReviewer.exe.sha256` pair with the `v0.2.0` GitHub release