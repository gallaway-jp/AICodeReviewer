# Milestone 7 Tool-Aware File Access Handoff

Date: 2026-04-06

## Objective

Start Milestone 7 from the current-spec baseline after revalidating Milestones 0 through 6, and implement the first safe tool-aware review path without regressing the existing static-prompt flow.

## Completed In This Slice

- added shared tool-review and tool-access audit models in `src/aicodereviewer/tool_access.py`
- added config defaults and sample config entries for:
  - `tool_file_access.enabled`
  - `tool_file_access.backend_allowlist`
  - `tool_file_access.sensitive_path_globs`
  - `tool_file_access.sensitive_path_policy`
- extended the backend contract so eligible backends can:
  - advertise tool-aware file access support
  - accept an optional tool-review context
  - expose reset/current/consume audit hooks
- marked the Copilot backend descriptor with the `tool_file_access` capability
- implemented a Copilot-first tool-aware review path with:
  - workspace-root scoping
  - sensitive-path denial by policy
  - permission and pre/post tool-use audit logging
  - runtime detection of whether actual file-read tools were used
  - explicit fallback trigger when tool-aware review completes without any file reads
- updated the reviewer so tool-aware review is only attempted when:
  - the feature is enabled
  - the backend supports it
  - the backend is allowlisted
- preserved the existing static prompt path as the fallback path for disabled, unsupported, denied, or unused tool access
- disabled internal parallel batch execution for tool-aware reviews so backend audit state stays per-session and coherent
- propagated tool-access audit metadata through:
  - `ReviewExecutionResult`
  - execution-service result creation
  - HTTP summary serialization via `to_summary_dict()`
  - CLI tool-mode JSON output
- exposed the primary enable toggle in the GUI Copilot settings section while leaving advanced path-policy controls config-driven for now
- updated the roadmap spec, configuration docs, and milestone handoff trail so Milestone 7 status is visible from the main planning artifacts
- upgraded the live Copilot adapter from the older SDK contract to the current `github-copilot-sdk>=0.2.1` surface so the real CLI protocol and session API work again
- fixed the live Copilot tool-policy/runtime mismatches discovered during empirical validation:
  - allow the observed safe tool names `view` and `report_intent`
  - parse JSON-string `toolArgs` payloads before path extraction and policy checks
  - keep workspace-root and sensitive-path enforcement active after the live payload-shape fixes

## Validation

- Milestone 0-6 baseline before implementation:
  - non-GUI milestone slice -> `137 passed`
  - GUI milestone slice -> `136 passed in 591.89s (0:09:51)`
- Milestone 7 focused validation after implementation:
  - `tests/test_copilot_backend.py tests/test_reviewer.py tests/test_execution_service.py tests/test_cli_tool_mode.py tests/test_orchestration.py tests/test_http_api.py` -> `170 passed in 17.91s`
- live Copilot validation after SDK/runtime fixes:
  - `validate_connection()` now succeeds live with Copilot SDK `0.2.1`
  - direct live tool probe on a temporary two-file command-injection scenario:
    - Copilot `gpt-5-mini` used `report_intent` plus `view` to read `app/runner.py` and `app/api.py`
    - returned cross-file command-injection findings
    - audit recorded `file_read_count = 2`, `denied_request_count = 0`
  - end-to-end live reviewer validation on the same scenario with `collect_review_issues(...)` and interaction analysis temporarily disabled:
    - returned `5` concrete security findings
    - audit recorded `file_read_count = 3`, `denied_request_count = 0`
    - tool-aware prompt size was `950` characters versus `1444` for the static embedded prompt, a `34.21%` reduction
  - updated Copilot backend regression slice after live fixes:
    - `tests/test_copilot_backend.py` -> `34 passed in 1.00s`

## Current Status

Milestone 7 is now complete in the repository baseline:

- tool-aware review can be enabled deliberately
- the Copilot path is workspace-bounded and audited
- unsupported or ineffective tool access falls back to the existing review path instead of silently degrading
- execution consumers can now inspect per-run tool-access audit metadata
- live Copilot validation now shows the reviewer path can use workspace reads successfully on a representative security scenario
- empirical evidence now exists for both:
  - efficiency improvement through smaller tool-aware prompts
  - live review quality through concrete cross-file findings backed by audited file reads

The main follow-on work is Milestone 8 hardening: broader tool-name compatibility, transport/auth diagnostics, and generalized permission/error normalization for external tool integrations.

## Resume Prompt

Resume from `docs/handoffs/milestone-7-tool-aware-file-access-handoff-2026-04-06.md`. Milestone 7 is now closed for the current Copilot-first baseline after live validation confirmed audited workspace reads, prompt-size reduction, and end-to-end reviewer findings on a representative repository scenario. The next milestone focus is Milestone 8: harden tool/runtime compatibility, permission/auth diagnostics, and broader external-tool failure handling without weakening the new audit and fallback guarantees.