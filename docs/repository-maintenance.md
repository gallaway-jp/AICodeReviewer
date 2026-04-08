# Repository Maintenance Plan

This guide records the Milestone 14 cleanup inventory, layout expectations, and the execution plan for repository standardization.

It is intentionally non-destructive: define what stays, what is generated, and what needs review before deleting or moving anything.

## Purpose

Use this plan to:

- keep the repository layout predictable for contributors
- separate maintained source and docs from generated or local-only artifacts
- normalize release metadata and release branches without rewriting historical context
- stage cleanup as explicit tasks instead of one-off manual pruning

## Repository Layout Classes

Treat the current repository in these classes.

### Maintained Source Of Truth

Keep these as first-class tracked areas:

- `src/`
- `tests/`
- `tools/`
- `benchmarks/`
- `.github/specs/`
- `docs/`
- `examples/`
- `licenses/`
- `pyproject.toml`
- `requirements.txt`
- `README.md`
- `RELEASE_NOTES.md`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `config.ini` when it represents shipped defaults rather than a machine-local override

### Maintained Documentation And Handoffs

These are maintained, but should stay curated rather than grow without review:

- `docs/*.md` reference guides
- `docs/handoffs/` milestone and implementation handoffs
- `docs/images/` screenshots and annotated captures that are referenced from maintained docs

Retention rule:

- keep handoffs that record milestone-close decisions, shipped workflow changes, or roadmap state transitions
- archive or remove handoffs that become redundant once their decisions are fully folded into maintained reference docs, but only after an explicit review pass

### Benchmark Inputs Versus Outputs

Keep benchmark inputs and framework code tracked:

- `benchmarks/`
- `tools/run_benchmark_tranche.py`
- `docs/review-quality-program.md`
- `docs/review-quality-log.md`

Treat generated benchmark outputs as local or reproducible artifacts, not primary source of truth:

- `artifacts/`
- `.benchmarks/`

Retention rule:

- preserve named baseline and postfix artifacts only when they are intentionally part of milestone evidence or comparison history
- do not let ad hoc benchmark outputs become the only place where a conclusion is recorded; conclusions belong in `docs/review-quality-log.md` or a milestone handoff

### Generated Or Local-Only Working Artifacts

These should not drive repository decisions and should remain ignored, pruned, or regenerated as needed:

- `build/`
- `dist/`
- `.venv/`
- `.pytest_cache/`
- local log files such as `*.log`
- temporary validation outputs such as `gui_validation_report.json` when regenerated from the current app state
- machine-local scratch directories such as temporary test projects or one-off reproduction folders

### Review-Before-Prune Areas

These need explicit human review before deleting, moving, or ignoring them more aggressively:

- top-level debug helpers such as `debug_kiro_discovery.py` and `diagnose_kiro.py`
- top-level targeted test scripts outside `tests/`
- release-support files such as `AICodeReviewer.spec` and `build_exe.bat`
- long-lived docs assets that may look generated but are referenced from maintained docs

Rule:

- if a file affects release preparation, backend diagnostics, or contributor workflows, document its role before relocating or deleting it

## Minimal Layout Expectation

The repository should converge toward this working expectation:

- product code under `src/`
- automated tests under `tests/`
- contributor and runtime tools under `tools/`
- curated docs under `docs/`
- roadmap and design specs under `.github/specs/`
- examples under `examples/`
- reproducible benchmark inputs under `benchmarks/`
- only a small set of justified top-level operational files

Top-level exceptions are acceptable when they are one of:

- packaging or release entry points
- repository-wide configuration
- legal or licensing documents
- short contributor entry points

## Cleanup Execution Plan

## Current Top-Level Inventory

This is the first explicit top-level classification pass for the repository root as of 2026-04-07.

### Keep At Root

These are justified top-level files or directories and should remain where they are unless a later milestone changes their role:

- `.github/`
- `benchmarks/`
- `docs/`
- `examples/`
- `licenses/`
- `src/`
- `tests/`
- `tools/`
- `AICodeReviewer.spec`
- `build_exe.bat`
- `config.ini`
- `LICENSE`
- `README.md`
- `RELEASE_NOTES.md`
- `pyproject.toml`
- `requirements.txt`
- `THIRD_PARTY_NOTICES.md`
- `licenses_check.csv`

Reason:

- these are the current packaging, legal, configuration, source, test, benchmark, documentation, and contributor entry-point surfaces

### Keep But Treat As Generated Or Reproducible

These should not be treated as source-of-truth content even when temporarily retained locally:

- `artifacts/`
- `.benchmarks/`
- `build/`
- `dist/`

Action:

- keep `artifacts/` and `.benchmarks/` ignored and documentation-backed
- treat `build/` and `dist/` as disposable packaging outputs that can be pruned and rebuilt when needed

### Delete Or Recreate Freely

These are local scratch or empty generated areas and should not survive as meaningful repository state:

- `tmp-test-project/`
- `tmp-test-project-2/`
- empty `.benchmarks/` directories when they contain no retained evidence
- local log files such as `.pytest_gui_full_current.log`, `.pytest_gui_smoke.log`, `aicodereviewer-audit.log`, and similar one-off run outputs

Action:

- safe to remove locally when they are not needed for an active debugging session
- do not promote them into tracked documentation or release evidence

### Review Before Relocating Or Deleting

This list records the initial 2026-04-07 root-level review bucket before the first relocation pass was executed.

These were the plausible cleanup targets that needed to be documented or reassigned before any move:

- `debug_kiro_discovery.py`
- `diagnose_kiro.py`
- top-level targeted test helpers such as `test_copilot_models.py`, `test_dropdown_init.py`, `test_kiro_complete.py`, `test_kiro_dropdown.py`, `test_kiro_model_selector.py`, and `test_model_autoload.py`
- `gui_validation_report.json`
- `.kilocode/`
- `.vscode/`

Action:

- decide whether each item is:
	- a contributor utility that belongs under `tools/`
	- a real automated test that belongs under `tests/`
	- a local-machine workspace setting that should remain ignored
	- a one-off debug artifact that should be deleted after its purpose is captured elsewhere

Executed status:

- the Kiro diagnostics were moved to `tools/diagnostics/kiro/`
- the manual model and dropdown smoke scripts were moved to `tools/manual_checks/models/`
- GUI validation output now defaults to `artifacts/gui_validation_report.json`, and the root-level report was removed
- `.kilocode/` and `.vscode/` remain ignored local workspace configuration

## Ownership Decisions For Current Review-Before-Relocating Items

These are the first concrete ownership decisions for the ambiguous root-level items from that initial inventory, along with their current post-relocation status where applicable.

### Kiro Diagnostic Scripts

- initial root files: `debug_kiro_discovery.py`, `diagnose_kiro.py`

Decision:

- treat these as contributor diagnostics, not product entry points and not automated tests
- current maintained destination: `tools/diagnostics/kiro/`
- current files: `tools/diagnostics/kiro/debug_kiro_discovery.py` and `tools/diagnostics/kiro/diagnose_kiro.py`

Reason:

- both scripts are ad hoc Windows/WSL troubleshooting utilities for Kiro model discovery
- they print operator guidance and call internal helpers directly rather than participating in the normal test harness

### Top-Level Model And Dropdown Test Scripts

- initial root files: `test_copilot_models.py`, `test_dropdown_init.py`, `test_kiro_complete.py`, `test_kiro_dropdown.py`, `test_kiro_model_selector.py`, and `test_model_autoload.py`

Decision:

- treat these as manual smoke or contributor diagnostics, not canonical pytest coverage
- current maintained destination: `tools/manual_checks/models/`
- do not keep them as top-level `test_*.py` files once they are relocated or replaced by real automated coverage in `tests/`
- current files live under `tools/manual_checks/models/`

Reason:

- they are script-style checks with `print(...)` output and `sys.exit(...)`, not repository-integrated pytest modules
- several duplicate one another by checking model discovery, dropdown initialization, or Kiro selector wiring from a manual invocation path

Current audit status:

- keep `tools/manual_checks/models/test_copilot_models.py` as a live Copilot environment probe because it exercises real SDK-backed model discovery and authentication state rather than mocked unit seams
- keep `tools/manual_checks/models/test_model_autoload.py` as a live local-model environment probe because it exercises real local endpoint behavior rather than the mocked discovery cases covered by pytest
- `test_dropdown_init.py`, `test_kiro_complete.py`, `test_kiro_dropdown.py`, and `test_kiro_model_selector.py` overlapped substantially with automated coverage in `tests/test_backend_model_cache.py`, `tests/test_kiro_backend.py`, `tests/test_gui_workflows.py`, and `tests/test_health_mixin.py`
- those overlapping Kiro dropdown smoke scripts were pruned after the direct pytest coverage was added, leaving only the two retained live environment probes under `tools/manual_checks/models/`

### GUI Validation Report

- initial root file: `gui_validation_report.json`

Decision:

- treat as a generated validation artifact, not maintained repository source of truth
- current default output path: `artifacts/gui_validation_report.json`
- when retained, keep it under `artifacts/` rather than the repository root
- current root status: removed from the repository root after the validator default was updated

Reason:

- the file is a timestamped validator output describing one GUI snapshot and widget tree, which makes it evidence or debugging output rather than maintained documentation

### Local Workspace Directories

- `.kilocode/`
- `.vscode/`

Decision:

- treat as local-machine workspace configuration and keep ignored
- do not move into maintained docs or release artifacts

Reason:

- `.kilocode/` contains local MCP configuration and may include credential-bearing developer settings
- `.vscode/` contains editor-local overrides rather than repository contract surfaces

### Follow-Up Rule

For the remaining follow-up on these items:

- convert any script that should be part of regression coverage into real tests under `tests/`
- move retained validation output into `artifacts/` or regenerate it on demand
- keep local workspace config ignored and out of milestone-close documentation except when a guide intentionally documents how to create local settings

### Root Items To Revisit During Release Normalization

These are valid root files today, but Milestone 14 should confirm their long-term role while the `release/0.2.0` flow is prepared:

- `AICodeReviewer.spec`
- `build_exe.bat`
- `requirements.txt`

Action:

- keep them at root for now
- confirm whether they remain part of the supported release path, especially once the repository moves toward a more standardized release branch workflow and later Windows-installer work

Current release-packaging status:

- `AICodeReviewer.spec` and `build_exe.bat` remain the supported Windows release entry points for the current pre-installer flow
- `build_exe.bat` now builds from the checked-in spec instead of regenerating packaging config from `main.py`
- the maintained icon asset now lives under `src/aicodereviewer/assets/icon.ico`, so release packaging no longer depends on ignored `build/` state
- the validated release asset pair for GitHub releases is now `dist/AICodeReviewer.exe` plus `dist/AICodeReviewer.exe.sha256`

### Phase 1: Inventory Stabilization

1. Review top-level files that sit outside `src/`, `tests/`, `tools/`, `docs/`, and `benchmarks/`.
2. Mark each as one of: keep at root, relocate, archive, ignore, or delete.
3. Record the reason before applying any destructive cleanup.

### Phase 2: Ignore And Artifact Hygiene

1. Confirm generated directories and logs are covered by `.gitignore` where appropriate.
2. Add ignore rules only for clearly local or reproducible outputs.
3. Do not ignore maintained docs, reference screenshots, or milestone handoffs.

### Phase 3: Release Normalization

Execute the first standardized maintained pre-1.0 release from `release/0.2.0`:

1. branch from `main` to `release/0.2.0`
2. align `pyproject.toml` to `0.2.0`
3. move the relevant `Unreleased` release-note content into a `v0.2.0` section while reopening an empty `Unreleased` heading for future work
4. validate docs and targeted tests for the release scope, including `python tools/check_release_metadata.py --target-version 0.2.0 --require-aligned`
5. merge `release/0.2.0` back into `main`
6. create the `v0.2.0` tag from the merged `main` commit

Current repository baseline:

- `pyproject.toml` and `RELEASE_NOTES.md` are now aligned to `0.2.0` in-repo
- `tools/check_release_metadata.py` can now also report local branch/tag readiness for `release/0.2.0` and `v0.2.0`
- the Windows packaging path has now been validated again on the current baseline: `build_exe.bat` rebuilds `dist/AICodeReviewer.exe`, regenerates `dist/AICodeReviewer.exe.sha256`, and smoke-tests cleanly via `dist/AICodeReviewer.exe --help`
- the release-normalization path has now been executed end to end: `release/0.2.0` was cut, validated, merged into `main`, tagged as `v0.2.0`, pushed to `origin`, and published with the validated Windows asset pair

Current git preflight baseline:

- current branch: `main`
- local `release/0.2.0` branch: merged and no longer required for the published baseline
- local and remote `v0.2.0` tag: present
- current release publication state: the GitHub `v0.2.0` release is live with `AICodeReviewer.exe` and `AICodeReviewer.exe.sha256`

### Phase 4: Retention And Archive Rules

1. decide whether older milestone handoffs stay in `docs/handoffs/` indefinitely or move to an archive subfolder after milestone closeout
2. document any archive threshold by milestone age or by whether the handoff still contains unique information
3. keep milestone-close and release-normalization handoffs easy to find even if archival is introduced later

### Phase 5: Enforcement

1. if checked-in CI workflows are added later, encode the manual merge bar from `docs/contributing.md`
2. add validation for version/tag consistency during release preparation where practical
3. keep enforcement narrow and documentation-backed rather than adding broad failing checks without a published workflow

## Current Non-Goals

This plan does not yet:

- delete existing files automatically
- rewrite historical release notes
- retag historical releases
- archive old handoffs without a reviewed retention rule
- relocate ambiguous top-level scripts until their maintained owner is documented

## Related Guides

- [Contributing](contributing.md)
- [Release Process](release-process.md)
- [Review Quality Program](review-quality-program.md)
- [Architecture](architecture.md)