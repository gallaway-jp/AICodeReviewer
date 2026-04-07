# Security Review

This document is the Milestone 9 security artifact for AICodeReviewer. It captures the current threat model, major trust boundaries, final remediation state for confirmed findings in the current baseline, and the residual risks that remain intentionally accepted or deferred.

## Scope

The current review covers:
- local desktop and CLI execution
- the loopback-only HTTP API
- addon discovery and loading
- filesystem reads, report generation, and artifact serving
- benchmark saved-run browsing and source-folder opening
- benchmark fixture manifest loading
- backend credential storage and usage
- subprocess execution for external tooling

It does not claim strong sandboxing for trusted in-process addons, and it does not model a hostile administrator on the local machine.

## Attacker Assumptions

- an attacker may be able to submit requests to the local API from the same machine
- an attacker may be able to supply untrusted repository content for review
- an attacker may attempt to coerce report or artifact generation into writing outside the intended review scope
- an attacker may attempt to abuse addon manifests or backend/tool configuration if the user installs untrusted local content

## Trust Boundaries

### Local API

- the HTTP API is intended for loopback use only
- API clients can submit review jobs, inspect queue state, and fetch reports/artifacts
- the API must not become a generic file-write or file-read surface outside the review/runtime contract

### Addons

- addons are trusted local extensions, not sandboxed plugins
- incompatible or invalid addons should fail closed during loading
- the addon boundary is a compatibility and diagnostics boundary, not a hard security boundary

### Filesystem

- review targets, diff inputs, reports, and saved sessions operate on local files
- report and artifact handling must avoid expanding review requests into arbitrary filesystem access

### Credentials

- backend credentials are user-controlled configuration
- Local LLM API keys can be stored via keyring-backed references rather than plain text
- secret values should not be echoed back into config files, logs, or ordinary UI surfaces

### External Tools And Backends

- subprocess-backed or HTTP-backed integrations are treated as partially trusted dependencies
- failures must surface clear diagnostics without corrupting review state

## Findings And Remediation Ledger

## Broader Code Review Snapshot

The Milestone 9 review is not limited to the local HTTP API. The current pass examined the codebase's major security-sensitive surfaces across:
- local API request parsing and artifact serving
- GUI session persistence and restore flows
- GUI popup recovery and restored issue-path handling
- addon manifest parsing and dynamic module loading
- benchmark saved-run browsing and summary-embedded paths
- benchmark fixture manifest path resolution
- subprocess-backed backend integration
- filesystem report and artifact writes
- credential resolution and storage

High-confidence conclusions from the broader code review so far:
- credential handling is materially improved by keyring-backed Local LLM secret references and explicit rotate/revoke flows
- subprocess-backed integrations are generally using argument lists or controlled command construction rather than shell interpolation
- JSON deserialization uses standard `json` parsing rather than unsafe loaders
- the current confirmed issues continue to cluster around boundary validation, trusted-addon assumptions, and audit visibility rather than an obvious built-in remote-code-execution flaw in the current shipped feature set

## Milestone 9 Closeout

Milestone 9 is complete for the current repository baseline.

The final review outcome is:
- confirmed issues were boundary-validation and audit-visibility gaps around persisted app data and local API artifact exposure, not an obvious built-in remote-code-execution flaw in the shipped feature set
- benchmark-related hardening is now closed end-to-end across saved summary selection, summary-derived report paths, summary-derived source-folder paths, and fixture manifest input paths
- restored-session and popup-recovery payloads now re-validate issue file paths before those paths can drive editor, preview, or AI-fix workflows
- direct user-selected file and save destinations remain intentionally user-controlled inputs rather than Milestone 9 vulnerabilities
- the main residual product risk remains the explicitly trusted in-process addon model

### Fixed

1. Local HTTP API arbitrary report destination risk
Status: fixed on 2026-04-06
Severity: medium
Surface: `POST /api/jobs` `output_file`
Issue: the API accepted client-provided report destinations without validating whether the target path stayed within the submitted review scope.
Remediation: `output_file` is now resolved and rejected unless it stays within either the requested review root or the current workspace directory.
Validation: `tests/test_http_api.py`

2. Local HTTP artifact-serving scope gap
Status: fixed on 2026-04-06
Severity: medium
Surface: local API artifact listing and raw artifact download
Issue: artifact enumeration trusted sibling report files without re-validating that their resolved paths still stayed within the job's review/workspace boundary.
Remediation: runtime artifact listing now re-validates resolved artifact paths against the review root and workspace before exposing them.
Validation: `tests/test_execution_runtime.py`, `tests/test_http_api.py`

3. GUI session restore boundary gap
Status: fixed on 2026-04-06
Severity: medium
Surface: saved session loading in the desktop GUI
Issue: the GUI would read any user-selected JSON file as a session payload without validating that the file came from an expected session/workspace boundary.
Remediation: session restore now rejects session files that escape both the config directory and current workspace.
Validation: `tests/test_results_session.py`

4. Addon entry-point path escape risk
Status: fixed on 2026-04-06
Severity: medium
Surface: addon manifest `review_packs`, backend-provider modules, and editor-hook modules
Issue: addon entry-point paths were resolved but not constrained to stay under the addon root, allowing manifests to point at files outside their package directory.
Remediation: addon entry-point paths must now stay within the addon root before they can be loaded.
Validation: `tests/test_addons.py`

5. Local API audit visibility for sensitive actions
Status: fixed on 2026-04-06
Severity: low to medium
Surface: local API job submission, cancellation, report fetch, artifact list, artifact fetch
Issue: security-sensitive local API actions were not emitted as explicit audit log records.
Remediation: the local API now logs structured audit entries for job submission and artifact/report access, plus request rejections and server-side failures.
Validation: `tests/test_http_api.py`

6. Benchmark browser saved-run boundary gap
Status: fixed on 2026-04-06
Severity: medium
Surface: benchmark summary browsing and summary-referenced report paths
Issue: the benchmark browser trusted chosen summary files and report paths embedded inside summary payloads without constraining them to the selected saved-runs root.
Remediation: benchmark summary browse/select actions now stay within the configured saved-runs folder, and summary-referenced report paths that escape that boundary are ignored rather than opened or previewed.
Validation: `tests/test_benchmark_security.py`, `tests/test_gui_workflows.py`

7. Local API audit retention dependency on general logging
Status: fixed on 2026-04-06
Severity: low
Surface: local API audit trail retention
Issue: audit events originally depended on the normal application logger and could be lost when general file logging was disabled.
Remediation: local API audit events now use a dedicated rotating audit log sink with separate configuration.
Validation: `tests/test_main_cli.py`

8. Benchmark browser source-folder boundary gap
Status: fixed on 2026-04-06
Severity: medium
Surface: benchmark "Open Scenario Folder" action and summary-embedded `project_dir` / `fixture_dir` paths
Issue: the benchmark browser still trusted source-folder paths embedded in saved summary payloads, which could coerce the GUI into opening arbitrary external directories.
Remediation: summary-embedded benchmark source paths are now resolved relative to the configured fixtures root and ignored unless they stay within that root; when rejected, the UI falls back to the saved-run folder instead of opening the external path.
Validation: `tests/test_gui_workflows.py`, `tests/test_benchmark_security.py`

9. Benchmark fixture manifest path escape risk
Status: fixed on 2026-04-06
Severity: medium
Surface: benchmark fixture manifest `project_dir`, `diff_file`, and `spec_file`
Issue: benchmark fixture manifests discovered under the configured fixtures root could still point their scenario inputs at paths outside that root, allowing persisted benchmark definitions to drive reviews against arbitrary external files or folders.
Remediation: discovered fixture manifests now fail closed unless their resolved `project_dir`, `diff_file`, and `spec_file` values stay within the configured fixtures root.
Validation: `tests/test_benchmark_security.py`, `tests/test_gui_workflows.py`

10. Restored session issue-path trust gap
Status: fixed on 2026-04-06
Severity: medium
Surface: GUI session restore and popup recovery issue payloads
Issue: restored session state could still carry `issue.file_path` values outside the expected session roots, and those paths later drove editor and AI-fix actions.
Remediation: restored issue file paths are now re-validated against the expected session roots before the GUI accepts the session or popup recovery payload.
Validation: `tests/test_results_session.py`, `tests/test_gui_workflows.py`

### Mitigated By Existing Design

1. Plain-text Local LLM credential persistence
Status: mitigated
Severity: medium
Surface: local backend configuration
Mitigation: `local_llm.api_key` supports keyring-backed references, and the GUI rotate/revoke flow keeps secrets out of `config.ini`.

2. Generic failure handling for authenticated or transient tool failures
Status: mitigated
Severity: low to medium
Surface: backend health, runtime review/fix failures, tool-mode output, GUI failed-fix messaging
Mitigation: structured failure diagnostics now classify auth, permission, timeout, transport, provider, configuration, and tool-compatibility failures, including retry guidance for transient cases.

3. Command injection through built-in subprocess-backed backends
Status: mitigated
Severity: medium
Surface: Kiro and other external-tool integrations
Mitigation: the current built-in subprocess paths generally use structured argument lists or controlled command assembly rather than interpolating raw user input into shell strings.

### Accepted Current Risk

1. In-process addon execution is not sandboxed
Status: accepted for current architecture
Severity: high if untrusted addons are installed
Surface: addon loading and execution
Reason: the current addon model explicitly trusts local Python extensions; this is a product constraint, not an accidental exposure.
Follow-up: preserve fail-closed compatibility checks and keep documenting that addons are trusted code.

### Residual Follow-Up

1. Keep the trusted-addon model explicitly documented and revisit optional addon integrity or signing only if the product moves beyond intentionally trusted local extensions.
2. Reassess local API exposure assumptions if the service ever expands beyond loopback-only desktop use or gains remote-access scenarios.
3. Continue treating direct user-selected file and save destinations as UX-controlled inputs rather than silently widening internal persisted-data trust.

## Decision Notes

1. Dedicated retained audit sink
Decision: yes, keep a dedicated rotating audit log for local API audit events.
Reason: these events are security-relevant enough that retention should not depend on ordinary file logging being enabled, and the event volume is narrow enough to justify a separate sink.

2. Primary user-input file pickers
Decision: do not broadly constrain project-path, diff-file, spec-file, or save-log pickers to the workspace.
Reason: those are direct user-chosen inputs or destinations, not internal artifact/session restore surfaces. The boundary hardening in Milestone 9 is aimed at secondary loaders that consume persisted app data or app-generated outputs with implied trust.

## Remediation Checklist

- [x] Constrain local API report output paths to the review root or workspace.
- [x] Re-validate artifact paths before listing or serving raw artifacts.
- [x] Constrain GUI session restore to expected filesystem roots.
- [x] Constrain addon entry-point files to the addon root.
- [x] Emit audit logs for security-sensitive local API actions.
- [x] Review benchmark artifact browsing and constrain saved-run/report-path loading to the selected artifacts root.
- [x] Constrain benchmark summary-embedded source-folder paths to the configured fixtures root.
- [x] Constrain benchmark fixture manifest paths to the configured fixtures root.
- [x] Constrain restored session and popup-recovery issue file paths to expected session roots before editor or AI-fix actions can use them.
- [x] Add a dedicated retained rotating audit sink for local API audit events.
- [x] Complete the whole-code Milestone 9 review of persisted-data loaders and classify remaining direct-input surfaces versus accepted addon trust.

## Security Testing Notes

- targeted automated regressions should accompany each confirmed hardening change
- manual review remains appropriate for addon trust assumptions, UX disclosure quality, and local API exposure assumptions

Current targeted validation tied to this document:
- `python -m pytest tests/test_benchmark_security.py tests/test_results_session.py tests/test_gui_workflows.py -k "benchmark or popup_recovery or load_session" -q`