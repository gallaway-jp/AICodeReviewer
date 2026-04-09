# Milestone 16 Analyze-Repo Foundation

Date: 2026-04-08

## Scope

Start Milestone 16 with a conservative repository analyzer that emits a capability profile and generated addon scaffold as preview artifacts.

## What Changed

- added `src/aicodereviewer/addon_generator.py`
- added a new tool-mode command:
  - `aicodereviewer analyze-repo PATH --output-dir DIR [--addon-id ID] [--addon-name NAME]`
- the first slice:
  - scans a repository for languages, frameworks, tools, manifests, test harnesses, and style signals
  - recommends a conservative built-in review bundle based on those signals
  - writes:
    - `capability-profile.json`
    - `summary.txt`
    - `<addon-id>/addon.json`
    - `<addon-id>/review-pack.json`
  - validates the generated manifest through the existing addon loader before reporting success
- updated docs so the new preview path is discoverable from:
  - `docs/addons.md`
  - `docs/user-manual.md`
  - `.github/specs/platform-extensibility/spec.md`

## Why This Slice Exists

- Milestone 16 needs a narrow first step that builds on the existing addon and review-pack platform instead of jumping directly to a GUI approval flow
- the repository already had addon manifests, review-pack loading, and project-context collection; this slice connects those seams into a usable preview generator
- the generated output is intentionally conservative and reversible: it writes files only and does not activate them automatically

## Validation

- focused tests passed:
  - `d:/Development/Python/AICodeReviewer/.venv/Scripts/python.exe -m pytest tests/test_addon_generator.py tests/test_cli_tool_mode.py -k "analyze_repo or addon_generator"`
- result:
  - `3 passed, 27 deselected`

## Remaining Work

- expand repository analysis heuristics for more manifests and frameworks as needed
- add a HITL review and approval flow before generated addons are activated
- add judged or benchmark-backed evidence that generated addons improve review relevance over baseline behavior