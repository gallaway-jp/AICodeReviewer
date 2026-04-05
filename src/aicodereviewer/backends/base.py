# src/aicodereviewer/backends/base.py
"""
Abstract base for all AI backends.

Every backend must implement :pymethod:`get_review` and :pymethod:`get_fix`
so the rest of the application can remain backend-agnostic.
"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, List

from aicodereviewer.registries import get_review_registry
from aicodereviewer import review_definitions as _review_definitions

REVIEW_PROMPTS = _review_definitions.REVIEW_PROMPTS
REVIEW_TYPE_KEYS = _review_definitions.REVIEW_TYPE_KEYS
REVIEW_TYPE_META = _review_definitions.REVIEW_TYPE_META

# ── JSON output schema (injected into system prompt) ───────────────────────

_JSON_SCHEMA_INSTRUCTION = """\

IMPORTANT — OUTPUT FORMAT:
You MUST respond with valid JSON matching this schema.  Do NOT include
markdown code fences, preamble, or any text outside the JSON object.

{
  "review_type": "<type>",
  "language": "<en|ja>",
  "files": [
    {
      "filename": "<path>",
      "findings": [
        {
          "severity": "critical|high|medium|low|info",
          "line": <int or null>,
          "category": "<review category>",
          "title": "<short title>",
          "description": "<detailed description>",
          "code_context": "<relevant code snippet>",
                    "suggestion": "<how to fix>",
                    "context_scope": "local|cross_file|project",
                    "related_files": ["<path>", "..."],
                    "systemic_impact": "<brief broader impact>",
                    "confidence": "high|medium|low",
                                        "evidence_basis": "<brief concrete evidence, e.g. serializers.py emits full_name while handlers.py reads display_name>"
        }
      ]
    }
  ]
}

Rules:
- Return ONLY the JSON object.  No markdown, no fences, no extra text.
- "severity" MUST be one of: critical, high, medium, low, info.
- "line" is the 1-based line number (null if file-level).
- Include ALL findings you discover — do not merge multiple issues.
- Use "context_scope" = "local" unless the finding is clearly supported across files or at project level.
- Use "context_scope" = "cross_file" for a specific mismatch, caller/callee break, or dependency problem spanning multiple files.
- Use "context_scope" = "project" for architectural, layering, or cross-cutting contract findings that describe the project structure as a whole.
- Keep "related_files" short (0-3 entries) and only include files supported by concrete evidence.
- When "context_scope" is "cross_file" or "project", include the most relevant supporting file(s) in "related_files" whenever they are known.
- Use systemic fields only when you can justify them from the provided code, prompt context, or framework guidance.
- "evidence_basis" must be a short concrete statement naming the exact evidence, such as a field mismatch, missing guard, stale caller, dependency edge, or changed signature. Do not use generic phrases like "batch code", "project context", or "diff context" by themselves.
- For producer/consumer or caller/callee mismatches, name both sides in related_files when known and make systemic_impact explain what breaks for downstream callers or consumers.
- For missing guards or validation drift, name the supporting route, validator, or auth helper file and make systemic_impact explain the resulting exposure, unvalidated input reaching runtime use, or inconsistent boundary enforcement.
- For stale cache, state split, or transaction boundary issues, include the collaborating cache/repository/service file in related_files and make systemic_impact describe stale reads, partial writes, or loss of atomicity.
"""


# ── Framework-specific prompt supplements ──────────────────────────────────
# Keyed by framework name as returned by context_collector.detect_frameworks().
# Each supplement is appended to the system prompt when the framework is
# detected, giving the AI model domain-specific review guidance.

FRAMEWORK_PROMPT_SUPPLEMENTS: Dict[str, str] = {
    # ── Python ──────────────────────────────────────────────────────────────
    "django": (
        "This is a Django project. Pay special attention to:\n"
        "- ORM N+1 query patterns (use select_related/prefetch_related)\n"
        "- CSRF middleware and token handling\n"
        "- QuerySet lazy evaluation and caching\n"
        "- Template injection and XSS vulnerabilities\n"
        "- Middleware execution order\n"
        "- Proper use of Django settings and SECRET_KEY protection"
    ),
    "flask": (
        "This is a Flask project. Pay special attention to:\n"
        "- Request context and application context management\n"
        "- Blueprint structure and route registration\n"
        "- Secret key management and session security\n"
        "- SQL injection via raw queries (use SQLAlchemy properly)\n"
        "- Debug mode must be disabled in production"
    ),
    "fastapi": (
        "This is a FastAPI project. Pay special attention to:\n"
        "- Pydantic model validation and coercion\n"
        "- Async/await correctness (no blocking calls in async routes)\n"
        "- Dependency injection resolution and lifecycle\n"
        "- Request/response serialization\n"
        "- Background task execution and error handling"
    ),
    # ── JavaScript / TypeScript ─────────────────────────────────────────────
    "react": (
        "This is a React project. Pay special attention to:\n"
        "- React Hook rules (dependencies array completeness)\n"
        "- Memory leaks from uncleared intervals/listeners\n"
        "- Unnecessary re-renders and useCallback/useMemo usage\n"
        "- Stale closures in event handlers\n"
        "- Prop drilling that should use Context or state management\n"
        "- Key prop usage in lists"
    ),
    "next.js": (
        "This is a Next.js project. Pay special attention to:\n"
        "- Server vs. client component boundaries (use client directive)\n"
        "- Data fetching patterns (getServerSideProps vs. getStaticProps vs. App Router)\n"
        "- Image optimisation via next/image\n"
        "- Environment variable exposure (NEXT_PUBLIC_ prefix)\n"
        "- API route security and input validation"
    ),
    "vue": (
        "This is a Vue project. Pay special attention to:\n"
        "- Reactivity system (ref vs. reactive, toRefs)\n"
        "- Composition API lifecycle hooks\n"
        "- V-model binding correctness\n"
        "- Computed property side effects\n"
        "- Vuex/Pinia store mutation patterns"
    ),
    "angular": (
        "This is an Angular project. Pay special attention to:\n"
        "- Observable subscription leaks (use async pipe or takeUntilDestroyed)\n"
        "- Change detection strategy (OnPush vs. Default)\n"
        "- Dependency injection tree scope\n"
        "- Template expression complexity\n"
        "- Lazy-loaded module boundaries"
    ),
    "express": (
        "This is an Express.js project. Pay special attention to:\n"
        "- Middleware ordering (error handler must be last)\n"
        "- Input validation and sanitisation\n"
        "- Async error handling (express-async-errors or wrapper)\n"
        "- CORS and helmet security headers\n"
        "- Route parameter injection"
    ),
    # ── Java ────────────────────────────────────────────────────────────────
    "spring_boot": (
        "This is a Spring Boot project. Pay special attention to:\n"
        "- Bean lifecycle and scope (singleton vs. prototype)\n"
        "- @Transactional propagation and rollback rules\n"
        "- N+1 JPA/Hibernate queries (use @EntityGraph or JOIN FETCH)\n"
        "- Security filter chain configuration\n"
        "- Property injection vs. constructor injection"
    ),
    # ── Ruby ────────────────────────────────────────────────────────────────
    "rails": (
        "This is a Ruby on Rails project. Pay special attention to:\n"
        "- ActiveRecord N+1 queries (use includes/eager_load)\n"
        "- Mass assignment protection (strong parameters)\n"
        "- CSRF and session security\n"
        "- Callback chain complexity\n"
        "- Raw SQL injection via string interpolation"
    ),
    # ── Testing ─────────────────────────────────────────────────────────────
    "pytest": (
        "This project uses pytest. In testing-related reviews:\n"
        "- Check fixture scope and teardown safety\n"
        "- Verify parametrize coverage of edge cases\n"
        "- Flag monkeypatch leaks across tests\n"
        "- Ensure conftest.py fixtures are not overly broad"
    ),
}


UI_UX_FRAMEWORK_PROMPT_SUPPLEMENTS: Dict[str, str] = {
    "react": (
        "For UI/UX review in React code, pay special attention to confusing component composition, "
        "state-driven layout jumps, missing empty/loading/error states, unclear button intent, weak form feedback, "
        "modal/drawer focus flow, and interaction friction caused by stale or duplicated state."
    ),
    "next.js": (
        "For UI/UX review in Next.js code, pay special attention to loading transitions between server/client boundaries, "
        "navigation clarity, optimistic UI states, search/filter persistence, and whether SEO or route structure creates confusing user journeys."
    ),
    "vue": (
        "For UI/UX review in Vue code, pay special attention to reactive state clarity in templates, form validation timing, "
        "conditional rendering that hides key actions, and component communication patterns that make user flows hard to follow."
    ),
    "angular": (
        "For UI/UX review in Angular code, pay special attention to template complexity, wizard or dashboard flow clarity, validation timing, "
        "error-state visibility, and interaction lag or state mismatch caused by change-detection boundaries."
    ),
    "django": (
        "For UI/UX review in Django projects, examine template hierarchy, form error visibility, empty-state handling, confirmation flows, "
        "and whether server-rendered navigation or messaging makes task completion ambiguous."
    ),
    "flask": (
        "For UI/UX review in Flask projects, examine template-driven forms, flash-message visibility, post-submit navigation, and whether page structure gives users clear next actions."
    ),
    "fastapi": (
        "For UI/UX review in FastAPI projects, pay attention to the user-facing API experience in docs and clients: validation feedback quality, schema clarity, error payload usability, and whether UI layers built around these contracts will force confusing recovery flows."
    ),
    "express": (
        "For UI/UX review in Express applications, pay attention to validation and error-response consistency, multi-step form flow, and whether API-driven UI states have enough information to present clear user feedback."
    ),
}


UI_UX_REVIEW_METHOD_SUPPLEMENT = (
    "For UI/UX reviews, treat the primary finding category as ui_ux. In the JSON response, set category to exactly 'ui_ux' "
    "for user-facing usability, interaction-flow, hierarchy, navigation, empty/loading/error state, confirmation-flow, wizard-orientation, "
    "discoverability, and cross-tab dependency findings instead of inventing custom category names. Never emit subtype categories such as wizard-orientation, missing_error_state, confirmation-flow, or discoverability as the category field; keep category exactly 'ui_ux'. "
    "Prioritise holistic interface problems over implementation-only code quality notes. "
    "Actively look for these scenario classes when supported by the code: missing loading/error/empty states, destructive form recovery that clears input, "
    "blocking desktop actions without busy feedback, destructive actions without confirmation or undo, hidden settings architecture, multi-step wizard orientation gaps, "
    "and preferences in one tab silently overriding settings configured in another tab. "
    "When you write systemic_impact for these findings, prefer concrete user-outcome wording such as blank screens, users needing to re-enter data, accidental loss, repeated clicks, hard-to-find settings, disabled controls that feel broken, hidden state changes, silent overrides, confusion, or loss of trust. "
    "When a dependency or mismatch spans multiple UI files, prefer one cross_file ui_ux finding with related_files, concrete evidence_basis, and systemic_impact written in user-outcome terms such as confusion, accidental data loss, hidden state changes, or loss of trust. "
    "Do not omit evidence_basis for ui_ux findings. evidence_basis must be a short factual statement that names the exact symbol, state field, control label, or function from the code that proves the issue, such as validateProfile, isLoading, error, export_report, reset_all_settings, Advanced, cloud_sync_enabled, or a specific button label."
)


DEAD_CODE_REVIEW_METHOD_SUPPLEMENT = (
    "For dead_code reviews, treat the primary finding category as dead_code. In the JSON response, set category to exactly 'dead_code' "
    "for unreachable branches, dormant feature flags, obsolete compatibility shims, unused entrypoints, dormant UI handlers, stale migration paths, and code that no longer has live wiring. "
    "Never emit subtype categories such as dead_function, dormant_feature, unused_variable, unused_import, or obsolete_code as the category field when the broader issue is dead code; keep category exactly 'dead_code'. "
    "Prefer the highest-leverage dead artifact over leaf helpers or import noise. When one permanently false flag, unreachable guard, obsolete compatibility function, or dormant entrypoint explains several smaller unused helpers, report the broader dead path instead of fragmenting the finding. "
    "Do not treat framework hooks, public extension points, interface implementations, or intentionally reserved compatibility surfaces as dead code unless the code shown proves they are no longer reachable or referenced. "
    "For stale feature flags, unreachable fallbacks, obsolete compatibility layers, and dormant UI flows, severity should be at least medium when the code clearly shows the path no longer runs. "
    "When you write systemic_impact for dead_code findings, prefer maintenance-outcome wording such as obsolete path, misleading fallback, dormant behavior, future changes updating code that never runs, cleanup risk, or loss of trust in what code is still live. "
    "Do not omit evidence_basis for dead_code findings. evidence_basis must cite the exact symbol, guard, flag, function, route, export, or branch condition that proves the dead path, such as USE_LEGACY_RENDERER, ENABLE_BULK_ARCHIVE, render_legacy_csv, or a guard that is permanently false."
)


LOCALIZATION_REVIEW_METHOD_SUPPLEMENT = (
    "For localization reviews, treat the primary finding category as localization. In the JSON response, set category to exactly 'localization' "
    "for hardcoded user-facing strings, missing translation-key usage, locale-insensitive date or currency formatting, untranslated status messages, and UI text that bypasses the project's translation helper. "
    "Never emit subtype categories such as hardcoded-string, i18n, internationalization, translator-context, locale-formatting, or translation-readiness as the category field when the broader issue is localization; keep category exactly 'localization'. "
    "Prioritise real user-visible translation gaps over speculative localization hygiene. When a screen mixes translated strings with literal English UI labels, or when formatting is hardcoded to one locale such as month/day/year dates or dollar-prefixed amounts, report that broader localization issue instead of weaker notes about future translator workflow. "
    "When visible UI text remains hardcoded or formatting is clearly locale-specific in a user-facing path, severity should be at least medium. "
    "Do not invent missing-translation findings when the code already passes concrete keys to the translation helper such as t('settings.title'). "
    "When you write systemic_impact for these findings, prefer user-outcome wording such as mixed-language UI, untranslated controls, confusing dates or amounts for international users, or localized builds still showing English-only text. "
    "Do not omit evidence_basis for localization findings. evidence_basis must cite the exact hardcoded label, translation-helper mismatch, or locale-specific format token, such as Button(..., text='Sync now') next to t('settings.title') calls, or strftime('%m/%d/%Y') plus a dollar-prefixed amount string."
)


ERROR_HANDLING_REVIEW_METHOD_SUPPLEMENT = (
    "For error_handling reviews, treat the primary finding category as error_handling. In the JSON response, set category to exactly 'error_handling' "
    "for swallowed exceptions, broad catch blocks, missing retries for transient failures, missing cleanup/finally behavior, hidden failure states, false-success responses after an error, and callers that surface success even though an upstream operation failed. "
    "Never emit subtype categories such as exception-handling, error-reporting, failure_handling, robustness, or business-logic as the category field when the broader issue is error handling; keep category exactly 'error_handling'. "
    "Prioritise the highest-leverage failure path over secondary style notes. When one swallowed exception, broad catch, or hidden failure status causes callers or operators to see a false success state, report that broader failure-propagation issue instead of fragmenting it into multiple local notes. "
    "When the code shows an upstream failure being converted into a success-looking result, severity should be at least high if callers, operators, or user-visible flows can no longer distinguish success from failure. "
    "When you write systemic_impact for these findings, prefer concrete outcome wording such as false success, hidden failure, delayed recovery, silent data loss, misleading metrics, or operators believing a job completed when it actually failed. "
    "For cross-file failure propagation, prefer one cross_file error_handling finding with related_files naming the caller or downstream consumer that treats the failed operation as successful. "
    "For transient failures such as TimeoutError, connection resets, or throttling responses, treat retryable failures that callers handle as terminal disablement or one-shot failure as error_handling too. When a callee marks a failure as retryable but a caller disables a feature, stops background work, or converts the transient error into a terminal state without retry/backoff, prefer one cross_file error_handling finding about the missing recovery path. "
    "Do not omit evidence_basis for error_handling findings. evidence_basis must cite the exact catch clause, returned status/error payload, retryable marker, and downstream condition that prove the hidden failure or missing recovery, such as except Exception, except TimeoutError, status='completed', retryable=True, result['status'] == 'completed', result['status'] == 'failed', or a success/disablement message like 'Import finished' or 'Background sync disabled'."
)


DATA_VALIDATION_REVIEW_METHOD_SUPPLEMENT = (
    "For data_validation reviews, treat the primary finding category as data_validation. In the JSON response, set category to exactly 'data_validation' "
    "for missing required-field checks, ordering or boundary validation gaps, schema validation omissions, unsafe coercion, validators that accept impossible values, and cross-file validation contracts that let invalid input reach runtime use. "
    "Never emit subtype categories such as validation, validation/contract, boundary_checks, type_handling, sanitization, or input-checks as the category field when the broader issue is data validation; keep category exactly 'data_validation'. "
    "Prioritise the highest-leverage validation contract gap over smaller parser or coercion notes. When a validator/helper and a caller disagree about what counts as valid input, prefer one cross_file data_validation finding describing the contract gap instead of fragmenting it into isolated local notes. "
    "When you write systemic_impact for these findings, prefer concrete outcome wording such as invalid input reaching runtime use, impossible state being accepted, negative durations, incorrect scheduling, persisted bad data, or downstream logic operating on incompletely validated fields. "
    "For cross-file validation drift, prefer one cross_file data_validation finding with related_files naming the validator/helper file that failed to enforce the constraint. "
    "Do not omit evidence_basis for data_validation findings. evidence_basis must cite the exact field names, validator/helper, coercion, and missing boundary/order check that prove the gap, such as start_hour, end_hour, validate_window, int(payload['end_hour']), or a missing end > start comparison."
)


TESTING_REVIEW_METHOD_SUPPLEMENT = (
    "For testing reviews, treat the primary finding category as testing. In the JSON response, set category to exactly 'testing' "
    "for missing test coverage, untested edge cases, brittle assertions, missing regression tests, untested error paths, and source/test mismatches where code already enforces a contract that the suite never exercises. "
    "Never emit subtype categories such as insufficient test coverage, testability, assertions, error_paths, or missing_tests as the category field when the broader issue is testing; keep category exactly 'testing'. "
    "Prioritise the highest-leverage missing test or unpinned contract over smaller assertion-style notes. When one missing edge-case or regression test leaves several validation or error branches uncovered, report that broader testing gap instead of fragmenting it into multiple local test comments. "
    "When you write systemic_impact for these findings, prefer regression-outcome wording such as regressions shipping unnoticed, boundary behavior becoming unpinned, confidence dropping during refactors, or existing contracts changing without a failing test. "
    "For cross-file testing gaps, prefer one cross_file testing finding on the test file with related_files naming the source/helper file whose branch or contract is untested. "
    "Do not omit evidence_basis for testing findings. evidence_basis must cite the exact test name, source/helper, and missing branch, guard, or symbol that should be covered, such as test_create_rollout_returns_batch_size_for_valid_payload, validate_rollout, rollout_percent, 0..100, or a specific pytest.raises path that is missing."
)


REGRESSION_REVIEW_METHOD_SUPPLEMENT = (
    "For regression reviews, treat the primary finding category as regression. In the JSON response, set category to exactly 'regression' "
    "for changed defaults that disable existing features, backward-incompatible behavior shifts, removed or weakened guards, changed return semantics that break existing callers, and diffs that silently alter previously shipped behavior. "
    "Never emit subtype categories such as behavioral change, behavior change, cross_file behavioral impact, or breaking_change as the category field when the broader issue is regression; keep category exactly 'regression'. "
    "Prioritise the highest-leverage user-visible or workflow-visible break over smaller style notes. When one changed default, removed guard, or altered branch condition explains the downstream behavior change, report that broader regression rather than fragmenting it into local observations. "
    "When you write systemic_impact for these findings, prefer outcome wording such as disabled by default, silently stops working, behavior changes for existing users, existing startup flow no longer runs, or previously enabled functionality becoming opt-in without migration. "
    "For cross-file regression impact, prefer one cross_file regression finding with related_files naming the consumer or startup path that inherits the changed behavior. "
    "Do not omit evidence_basis for regression findings. evidence_basis must cite the exact changed default, branch, or symbol and the downstream consumer that proves the behavior break, such as sync_enabled changing from True to False and a startup path that gates work on that setting."
)


DOCUMENTATION_REVIEW_METHOD_SUPPLEMENT = (
    "For documentation reviews, treat the primary finding category as documentation. In the JSON response, set category to exactly 'documentation' "
    "for stale READMEs, outdated command examples, docs/code mismatches, missing operational guidance, misleading comments, and public-interface docs that no longer describe the shipped behavior. "
    "Never emit subtype categories such as documentation mismatch, docs drift, cli contract, command example, outdated docs, or stale README as the category field when the broader issue is documentation; keep category exactly 'documentation'. "
    "Prioritise the highest-leverage docs/code mismatch over smaller style notes. When one stale README command, outdated migration note, or misleading operator guide creates a broken user-facing contract, report that broader documentation issue instead of fragmenting it into local docstring suggestions. "
    "When you write systemic_impact for these findings, prefer concrete reader-outcome wording such as operators or users following the docs into a broken command, misleading setup steps, failed automation, confusing tutorials, or documentation-led workflows failing in production. "
    "For cross-file docs drift, prefer one cross_file documentation finding on the stale doc or mismatched implementation file with related_files naming the collaborating code or doc file. "
    "Do not omit evidence_basis for documentation findings. evidence_basis must cite the exact doc file, command, flag, option, API name, or comment text that no longer matches the implementation, such as README.md documenting --dry-run while cli.py never registers that flag."
)


ACCESSIBILITY_REVIEW_METHOD_SUPPLEMENT = (
    "For accessibility reviews, treat the primary finding category as accessibility. In the JSON response, set category to exactly 'accessibility' "
    "for missing accessible names, unlabeled form controls, icon-only buttons without labels, keyboard-navigation traps, focus-management failures, missing semantics, and screen-reader compatibility issues. "
    "Never emit subtype categories such as usability, aria, contrast, keyboard, wcag, or semantic-html as the category field when the broader issue is accessibility; keep category exactly 'accessibility'. "
    "Prioritise the highest-leverage barrier over smaller style notes. When one missing label, aria-label, aria-labelledby, or semantic relationship explains why assistive technology users cannot identify or operate the control, report that broader accessibility issue instead of fragmenting it into generic usability comments. "
    "When you write systemic_impact for these findings, prefer concrete user-outcome wording such as screen reader users being unable to identify a control, keyboard-only users getting stuck, or assistive technology users missing the primary action. "
    "Do not omit evidence_basis for accessibility findings. evidence_basis must cite the exact control and missing accessible-name mechanism that proves the barrier, such as an icon-only button missing aria-label or an input that relies only on placeholder text without a label."
)


COMPLEXITY_REVIEW_METHOD_SUPPLEMENT = (
    "For complexity reviews, treat the primary finding category as complexity. In the JSON response, set category to exactly 'complexity' "
    "for excessive cyclomatic complexity, cognitive complexity, deep nesting, long decision trees, overgrown methods, and helpers that combine too many policy dimensions in one place. "
    "Never emit subtype categories such as cyclomatic_complexity, cognitive_complexity, nesting, large_method, or maintainability as the category field when the broader issue is complexity; keep category exactly 'complexity'. "
    "Prioritise the highest-leverage complexity hotspot over secondary style notes. When one function or method collapses multiple flags, states, or branches into a single nested decision tree, report that broader complexity issue instead of fragmenting it into smaller local observations. "
    "For single-function nesting and branch explosions, prefer context_scope local unless the provided files prove a broader architectural coupling problem. "
    "When the code shows a core helper with deep nesting or a long branch tree that will be difficult to change safely, severity should be at least medium. "
    "When you write systemic_impact for these findings, prefer maintainability-outcome wording such as harder to reason about, brittle during changes, branch interactions being easy to break, or refactors needing more regression coverage because the decision logic is concentrated in one place. "
    "Do not omit evidence_basis for complexity findings. evidence_basis must cite the exact function, method, or branch structure that proves the hotspot, such as choose_sync_strategy containing nested if/else chains across several policy dimensions."
)


PERFORMANCE_REVIEW_METHOD_SUPPLEMENT = (
    "For performance reviews, treat the primary finding category as performance. In the JSON response, set category to exactly 'performance' "
    "for N+1 query patterns, repeated database or network calls inside loops, avoidable O(n^2) hotspots, blocking I/O in hot paths, redundant recomputation, missing batching, wasteful serialization, and cache-consistency problems that create unnecessary repeated work. "
    "Never emit subtype categories such as algorithmic efficiency, query_efficiency, n_plus_one, database_performance, caching, or redundant_work as the category field when the broader issue is performance; keep category exactly 'performance'. "
    "Prioritise the highest-leverage throughput or latency bottleneck over smaller style notes. When code performs a query, request, or expensive helper call once per item in a loop, report that broader performance issue instead of fragmenting it into local observations. "
    "When a hot path adds one database, cache, or network round trip per record, or when the code structure implies avoidable quadratic growth, severity should be at least medium. "
    "When you write systemic_impact for these findings, prefer outcome wording such as latency growing with input size, throughput collapsing under larger batches, avoidable repeated round trips, stale reads forcing redundant work, or response times degrading as data volume grows. "
    "Do not omit evidence_basis for performance findings. evidence_basis must cite the exact loop, helper call, or repeated operation that proves the bottleneck, such as execute_query being called inside a for order_id loop, a request made once per item, or nested scans over the same collection."
)


API_DESIGN_REVIEW_METHOD_SUPPLEMENT = (
    "For api_design reviews, treat the primary finding category as api_design. In the JSON response, set category to exactly 'api_design' "
    "for HTTP method misuse, resource naming problems, incorrect status-code behavior, nonstandard request or response contracts, pagination omissions, versioning mistakes, and endpoints whose semantics will surprise API consumers. "
    "Never emit subtype categories such as HTTP method / endpoint semantics, request validation / spec, response modeling, endpoint design, rest_api, or contract style as the category field when the broader issue is API design; keep category exactly 'api_design'. "
    "Prioritise the highest-leverage API contract problem over smaller implementation notes. When one route uses the wrong HTTP method or exposes a nonstandard contract that can mislead clients, caches, generated SDKs, or OpenAPI consumers, report that broader api_design issue instead of fragmenting it into secondary observations. "
    "When the code uses GET for state-changing behavior, bodies on GET handlers, or creation endpoints that do not behave like creation endpoints, severity should be at least medium. "
    "When you write systemic_impact for these findings, prefer client-outcome wording such as caches or prefetchers triggering side effects, client expectations breaking, OpenAPI docs becoming misleading, retries creating duplicate state, or consumers treating a mutating endpoint as safe or read-only. "
    "Do not omit evidence_basis for api_design findings. evidence_basis must cite the exact decorator, route path, handler, status code, or request or response contract that proves the mismatch, such as @app.get('/api/invitations/create') on create_invitation or a create route returning 200 without 201 semantics."
)


DEPENDENCY_REVIEW_METHOD_SUPPLEMENT = (
    "For dependency reviews, treat the primary finding category as dependency. In the JSON response, set category to exactly 'dependency' "
    "for undeclared third-party packages, runtime imports that only exist in dev or test extras, dependency manifest drift, missing runtime package declarations, and dependency scope mistakes that will break installs or imports. "
    "Never emit subtype categories such as dependency management, dependency_usage, runtime-test-dependency, dependency-misconfiguration, lockfile-discipline, or package declaration as the category field when the broader issue is dependency; keep category exactly 'dependency'. "
    "Prioritise dependency contract breakage over generic package hygiene trivia. When runtime code imports a third-party package that is missing from the main dependency manifest, or only declared in a dev/test extra, report that install-time or import-time breakage instead of weaker notes about version pinning, package size, or abstract supply-chain concerns. "
    "When a runtime import can fail in fresh installs because the package is undeclared or only available through optional dev/test dependencies, severity should be at least medium. "
    "When you write systemic_impact for these findings, prefer outcome wording such as fresh installs failing with ModuleNotFoundError, production environments missing the package, deploys breaking without dev extras, or runtime imports crashing consumers. "
    "Do not omit evidence_basis for dependency findings. evidence_basis must cite the exact import plus the manifest mismatch, such as config_writer.py importing yaml while pyproject.toml never declares PyYAML, or metrics.py importing pytest while pyproject.toml lists pytest only under optional dev extras."
)


LICENSE_REVIEW_METHOD_SUPPLEMENT = (
    "For license reviews, treat the primary finding category as license. In the JSON response, set category to exactly 'license' "
    "for incompatible third-party license combinations, incorrect project distribution-license claims, missing or misleading third-party notices, omitted NOTICE retention, attribution obligations that are not being shipped, and dependency-license metadata that conflicts with the published notice package. "
    "Never emit subtype categories such as license_attribution, license_compatibility, dependency_license, third_party_notice, or license_declaration as the category field when the broader issue is license compliance; keep category exactly 'license'. "
    "Prioritise concrete distribution and compliance defects over abstract legal hygiene. When the provided files show that a bundled or runtime dependency is AGPL/GPL-incompatible with the project's declared distribution terms, that an Apache-style NOTICE obligation is explicitly being omitted from shipped binaries, or that a vendored source-file header says code was copied from a third-party package while the shipped notice files deny bundling third-party source or omit that package's attribution text, report that broader license issue instead of weaker notes about transparency or adding comments near imports. "
    "When a shipped binary, package, or published notice file explicitly omits required third-party notice or attribution material, severity should be at least medium. "
    "When you write systemic_impact for these findings, prefer release-outcome wording such as distributed binaries shipping incomplete notices, misleading downstream redistributors, incompatible licensing terms for packaged builds, or compliance failures in released artifacts. "
    "Do not omit evidence_basis for license findings. evidence_basis must cite the exact dependency, license label, and notice mismatch, such as licenses_check.csv marking networksync as AGPL-3.0-only while THIRD_PARTY_NOTICES.md says all bundled dependencies are MIT-compatible, THIRD_PARTY_NOTICES.md stating an Apache-2.0 dependency's upstream NOTICE will not be shipped with binaries, or src/vendor/foo.py saying it was copied from tinytable (MIT) while THIRD_PARTY_NOTICES.md says the distribution does not bundle third-party source files."
)


COMPATIBILITY_REVIEW_METHOD_SUPPLEMENT = (
    "For compatibility reviews, treat the primary finding category as compatibility. In the JSON response, set category to exactly 'compatibility' "
    "for OS-specific commands, runtime-version assumptions, deprecated APIs that break on supported environments, browser-specific behavior, environment-sensitive file handling, and code paths that will fail on one of the target platforms. "
    "Never emit subtype categories such as cross-platform, platform-specific, runtime compatibility, shell command portability, or OS command portability as the category field when the broader issue is compatibility; keep category exactly 'compatibility'. "
    "Prioritise the highest-leverage environment-breakage issue over weaker style or legacy-version trivia. When the code hardcodes a platform-specific executable or API and that would break a real user-visible feature on another supported OS, report that broader compatibility issue instead of secondary notes about subprocess style or hypothetical Python 2 support. When the code depends on a stdlib module or API that only exists on newer runtimes, compare that assumption against any declared support range in metadata such as pyproject.toml, setup.cfg, CI config, Docker images, or README instructions and report the runtime-support mismatch as compatibility. "
    "When the code hardcodes a macOS-only, Windows-only, or Linux-only behavior for a user-visible path and there is no platform branching or fallback, severity should be at least medium. "
    "Distinguish shell-launch compatibility issues from ordinary file I/O: Python's built-in open() for reading a file is not the same as shelling out to the OS command named open. Do not invent OS-command portability issues from normal file reads or writes unless the code is actually launching a platform-specific program. "
    "When you write systemic_impact for these findings, prefer outcome wording such as feature broken on Windows, Linux users unable to launch the action, runtime failure on non-macOS machines, CI failures on another platform, or supported environments diverging in behavior. "
    "Do not omit evidence_basis for compatibility findings. evidence_basis must cite the exact executable, API, runtime assumption, metadata contract, or OS-specific branch that proves the mismatch, such as subprocess.run(['open', report_path]) without platform detection or import tomllib while pyproject.toml still declares requires-python >=3.9."
)


ARCHITECTURE_REVIEW_METHOD_SUPPLEMENT = (
    "For architecture reviews, treat the primary finding category as architecture. In the JSON response, set category to exactly 'architecture' "
    "for layer leaks, dependency-direction violations, service or domain code depending on presentation or framework request context, controllers bypassing service boundaries, modules that reach across intended boundaries, and abstractions that collapse architectural separation. "
    "Never emit subtype categories such as dependency_misalignment, separation_of_concerns, layering_violation, layer_leakage, framework-coupling, or dependency-direction as the category field when the broader issue is architectural; keep category exactly 'architecture'. "
    "Prioritise the highest-leverage boundary violation over smaller local style notes. When code in one layer directly reaches into another layer's implementation details, report that broader architecture issue instead of fragmenting it into generic coupling comments. "
    "Treat direct imports or reads of Flask, Django, or FastAPI request/context objects from service or domain modules as architecture findings even when the function is otherwise small or appears to work, because business logic should stay framework-agnostic. Do not downgrade those cases into generic security, style, or dependency-hygiene findings when the real defect is the layer boundary leak. "
    "When the code bypasses an intended service boundary, or service/domain logic depends directly on a web, UI, or persistence framework, severity should be at least medium because the dependency direction and change surface become harder to control. "
    "When you write systemic_impact for these findings, prefer architecture-outcome wording such as layer boundaries becoming inconsistent, dependency direction being inverted, framework coupling spreading into business logic, or changes in one layer forcing edits across others. "
    "Do not omit evidence_basis for architecture findings. evidence_basis must cite the exact import, function call, or boundary bypass that proves the leak, such as controller.py importing db.py directly instead of delegating through service.py, or pricing_service.py reading flask.request headers inside service logic."
)


SCALABILITY_REVIEW_METHOD_SUPPLEMENT = (
    "For scalability reviews, treat the primary finding category as scalability. In the JSON response, set category to exactly 'scalability' "
    "for stateful components that block horizontal scaling, per-process coordination or quotas that break across workers, unbounded in-memory queues or buffers, missing backpressure, synchronous fan-out paths that grow with tenant or subscriber count, and deployment/runtime choices that make throughput collapse under growth. "
    "Never emit subtype categories such as stateful-component, throughput, queue-growth, deployment-configuration, capacity-planning, or scaling-bottleneck as the category field when the broader issue is scalability; keep category exactly 'scalability'. "
    "Prefer the highest-leverage growth bottleneck over smaller local implementation notes. When a stateful code path and a deployment/runtime file together prove the issue, prefer one cross_file scalability finding with related_files naming the supporting deployment file. "
    "When a code path keeps coordination state in process-local memory or allows unbounded backlog growth, severity should be at least medium, and high is appropriate when scaling out weakens correctness guarantees or allows backlog/resource pressure to grow with load. "
    "When you write systemic_impact for these findings, prefer outcome wording such as horizontal scaling breaking correctness, inconsistent global limits across workers, throughput collapsing as tenants grow, backlog growth without backpressure, or memory pressure increasing with traffic. "
    "Do not omit evidence_basis for scalability findings. evidence_basis must cite the exact state symbol, queue, deployment knob, or bottleneck trigger that proves the scaling problem, such as RATE_LIMIT_STATE plus workers = 4, or a pending_events buffer that never applies backpressure or drains asynchronously."
)


SPECIFICATION_REVIEW_METHOD_SUPPLEMENT = (
    "For specification reviews, treat the primary finding category as specification. In the JSON response, set category to exactly 'specification' "
    "for behavior that contradicts the supplied specification document, including missing required fields, disallowed partial success, wrong return semantics, omitted failure handling promised by the spec, ordering or atomicity mismatches, and features the spec requires but the code does not implement. "
    "Never emit subtype categories such as functionality, behavior_mismatch, contract_mismatch, atomicity_violation, spec_mismatch_return_value, or requirements_gap as the category field when the broader issue is a spec/code mismatch; keep category exactly 'specification'. "
    "Prioritise the highest-leverage mismatch between the code and the supplied specification over generic code quality commentary. "
    "When the specification states a required behavior and the code does something else, severity should be at least medium, and high when the mismatch can cause callers or operators to rely on prohibited behavior. "
    "When you write systemic_impact for these findings, prefer contract-outcome wording such as callers observing undocumented behavior, partial success where the spec forbids it, required guarantees not being met, or integrations depending on semantics the specification does not allow. "
    "If the mismatch is local to one implementation file, keep context_scope local unless the provided code shows a broader cross-file effect. "
    "Do not omit evidence_basis for specification findings. evidence_basis must cite the exact implementation behavior and the exact required behavior from the specification, such as returning partial_success even though the spec says submit_batch must be atomic and partial success is not allowed."
)


MAINTAINABILITY_REVIEW_METHOD_SUPPLEMENT = (
    "For maintainability reviews, treat the primary finding category as maintainability. In the JSON response, set category to exactly 'maintainability' "
    "for duplicated active logic, mixed responsibilities, low-cohesion classes or modules, overgrown coordinators, technical-debt hotspots, and code that is difficult to change safely because the same policy or workflow is implemented in multiple places. "
    "Never emit subtype categories such as duplicated_code, code_reuse, technical_debt, god_class, god_object, cohesion, or separation_of_concerns as the category field when the broader issue is maintainability; keep category exactly 'maintainability'. "
    "Prioritise the highest-leverage maintainability hotspot over smaller style notes. When multiple active files implement the same normalization, policy, or orchestration rules, prefer one cross_file maintainability finding about duplicated responsibility instead of fragmenting the issue into separate local notes. "
    "When the code shows duplicated active business rules across entry points or a single class/function carrying too many responsibilities, severity should be at least medium because future fixes can drift or become expensive to apply consistently. "
    "When you write systemic_impact for these findings, prefer maintenance-outcome wording such as behavioral drift between entry points, divergent bug fixes, duplicated maintenance surface, low cohesion making refactors risky, or future changes requiring edits in multiple places. "
    "Do not omit evidence_basis for maintainability findings. evidence_basis must cite the exact duplicated symbol, class, or responsibility split that proves the hotspot, such as normalize_sync_window being implemented in both cli_sync_settings.py and gui_sync_settings.py, or a SettingsController class that loads config, validates input, persists settings, triggers sync, and formats UI summaries in one place."
)


class AIBackend(ABC):
    """
    Abstract base class for AI code-review backends.

    Subclasses must implement :meth:`get_review` and :meth:`get_fix`.
    """

    # Project-level context string (set once per review session by the
    # orchestrator).  Backends read this when building the system prompt.
    _project_context: Optional[str] = None

    # Detected frameworks (e.g. ["django", "pytest"]).  Set once per
    # review session by the orchestrator so that framework-specific
    # prompt supplements are automatically appended.
    _detected_frameworks: Optional[List[str]] = None

    def set_project_context(self, context: Optional[str]) -> None:
        """Store project context for injection into system prompts."""
        self._project_context = context

    def set_detected_frameworks(self, frameworks: Optional[List[str]]) -> None:
        """Store detected frameworks for prompt supplement injection."""
        self._detected_frameworks = frameworks

    def set_stream_callback(
        self, callback: Optional[Callable[[str], None]]
    ) -> None:
        """Register a callback that receives incremental response tokens.

        The default implementation is a no-op so Bedrock, Kiro, and any
        other backends that don't support streaming require no changes.
        Backends that support streaming (e.g. :class:`CopilotBackend`)
        override this to store *callback* and invoke it with each token.

        Args:
            callback: Callable receiving a single :class:`str` token, or
                      ``None`` to remove a previously registered callback.
        """

    def close(self) -> None:
        """Release any backend-owned resources.

        The default implementation is a no-op so stateless backends do not
        need to override it. Backends that own processes, threads, sessions,
        or event loops should override this method.
        """

    # ── public API ─────────────────────────────────────────────────────────

    @abstractmethod
    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
    ) -> str:
        """
        Run an AI code review and return the feedback as plain text.

        Args:
            code_content: Source code to review.
            review_type: One of :data:`REVIEW_TYPE_KEYS`.
            lang: ``'en'`` or ``'ja'``.
            spec_content: Specification document (required when
                          *review_type* is ``'specification'``).

        Returns:
            AI feedback text, or a string starting with ``"Error:"`` on failure.
        """
        ...

    @abstractmethod
    def get_fix(
        self,
        code_content: str,
        issue_feedback: str,
        review_type: str = "best_practices",
        lang: str = "en",
    ) -> Optional[str]:
        """
        Generate an AI-powered code fix.

        Args:
            code_content: Original source code.
            issue_feedback: AI feedback describing the issue.
            review_type: The review type that found the issue.
            lang: Response language.

        Returns:
            Fixed code as a string, or *None* on failure.
        """
        ...

    def get_review_recommendations(
        self,
        recommendation_context: str,
        lang: str = "en",
    ) -> str:
        """Return a focused review-type recommendation for the given project context."""
        raise NotImplementedError("This backend does not implement review recommendations")

    @abstractmethod
    def validate_connection(self) -> bool:
        """
        Test whether the backend is reachable and authenticated.

        Returns:
            True if a trivial request succeeds.
        """
        ...

    # ── helpers available to all subclasses ─────────────────────────────────

    @staticmethod
    def _build_system_prompt(
        review_type: str,
        lang: str,
        project_context: Optional[str] = None,
        detected_frameworks: Optional[List[str]] = None,
    ) -> str:
        """Combine the review persona prompt with a language instruction.

        When *review_type* contains ``'+'`` (e.g. ``'security+performance'``),
        the personas for all included types are merged into a single prompt.

        The prompt now also includes a JSON output schema so models return
        structured findings that can be reliably parsed.

        When *detected_frameworks* is supplied, matching entries from
        :data:`FRAMEWORK_PROMPT_SUPPLEMENTS` are appended to give the
        model framework-specific review guidance.

        Args:
            review_type:          Review type key(s), ``'+'``-delimited for multi.
            lang:                 ``'en'`` or ``'ja'``.
            project_context:      Optional compact project summary string
                                  produced by :mod:`context_collector`.
            detected_frameworks:  Optional list of framework names from
                                  :func:`context_collector.detect_frameworks`.
        """
        review_registry = get_review_registry()
        if "+" in review_type:
            raw_parts = [part.strip() for part in review_type.split("+") if part.strip()]
            parts: list[str] = []
            for raw_part in raw_parts:
                try:
                    rt = review_registry.resolve_key(raw_part)
                except KeyError:
                    rt = raw_part
                parts.append(rt)
            base = (
                "You are a multi-disciplinary code review expert. "
                "Perform a combined review covering ALL of the following areas. "
                "Tag each finding with its category.\n\n"
                + "\n\n".join(
                    f"[{rt.upper()}]: {REVIEW_PROMPTS.get(rt, '')}"
                    for rt in parts if REVIEW_PROMPTS.get(rt)
                )
            )
        else:
            try:
                review_type = review_registry.resolve_key(review_type)
            except KeyError:
                pass
            base = REVIEW_PROMPTS.get(review_type, REVIEW_PROMPTS["best_practices"])
            parts = [review_type]

        review_type_parts = [part.strip() for part in parts if part.strip()]
        review_type_scope = AIBackend._review_type_scope("+".join(review_type_parts))
        context_augmentation_rules: list[str] = []
        seen_context_rules: set[str] = set()
        for review_type_key in review_type_parts:
            try:
                lineage_keys = tuple(reversed(review_registry.lineage_keys(review_type_key)))
            except KeyError:
                lineage_keys = (review_type_key,)
            for lineage_key in lineage_keys:
                try:
                    definition = review_registry.get(lineage_key)
                except KeyError:
                    continue
                for rule in definition.context_augmentation_rules:
                    if rule not in seen_context_rules:
                        context_augmentation_rules.append(rule)
                        seen_context_rules.add(rule)

        # Prepend project context if available
        if project_context:
            base = f"{project_context}\n\n{base}"

        if context_augmentation_rules:
            base += (
                "\n\nCONTEXT AUGMENTATION RULES:\n- "
                + "\n- ".join(context_augmentation_rules)
            )

        # Append framework-specific guidance
        if detected_frameworks:
            supplements = [
                FRAMEWORK_PROMPT_SUPPLEMENTS[fw]
                for fw in detected_frameworks
                if fw in FRAMEWORK_PROMPT_SUPPLEMENTS
            ]
            if supplements:
                base += (
                    "\n\nFRAMEWORK-SPECIFIC GUIDANCE:\n"
                    + "\n\n".join(supplements)
                )

            if "ui_ux" in review_type_scope:
                ui_ux_supplements = [
                    UI_UX_FRAMEWORK_PROMPT_SUPPLEMENTS[fw]
                    for fw in detected_frameworks
                    if fw in UI_UX_FRAMEWORK_PROMPT_SUPPLEMENTS
                ]
                if ui_ux_supplements:
                    base += (
                        "\n\nUI/UX-SPECIFIC FRAMEWORK GUIDANCE:\n"
                        + "\n\n".join(ui_ux_supplements)
                    )

        if "ui_ux" in review_type_scope:
            base += (
                "\n\nUI/UX REVIEW RULES:\n"
                + UI_UX_REVIEW_METHOD_SUPPLEMENT
            )

        if "dead_code" in review_type_scope:
            base += (
                "\n\nDEAD CODE REVIEW RULES:\n"
                + DEAD_CODE_REVIEW_METHOD_SUPPLEMENT
            )

        if "localization" in review_type_scope:
            base += (
                "\n\nLOCALIZATION REVIEW RULES:\n"
                + LOCALIZATION_REVIEW_METHOD_SUPPLEMENT
            )

        if "error_handling" in review_type_scope:
            base += (
                "\n\nERROR HANDLING REVIEW RULES:\n"
                + ERROR_HANDLING_REVIEW_METHOD_SUPPLEMENT
            )

        if "data_validation" in review_type_scope:
            base += (
                "\n\nDATA VALIDATION REVIEW RULES:\n"
                + DATA_VALIDATION_REVIEW_METHOD_SUPPLEMENT
            )

        if "testing" in review_type_scope:
            base += (
                "\n\nTESTING REVIEW RULES:\n"
                + TESTING_REVIEW_METHOD_SUPPLEMENT
            )

        if "accessibility" in review_type_scope:
            base += (
                "\n\nACCESSIBILITY REVIEW RULES:\n"
                + ACCESSIBILITY_REVIEW_METHOD_SUPPLEMENT
            )

        if "compatibility" in review_type_scope:
            base += (
                "\n\nCOMPATIBILITY REVIEW RULES:\n"
                + COMPATIBILITY_REVIEW_METHOD_SUPPLEMENT
            )

        if "performance" in review_type_scope:
            base += (
                "\n\nPERFORMANCE REVIEW RULES:\n"
                + PERFORMANCE_REVIEW_METHOD_SUPPLEMENT
            )

        if "architecture" in review_type_scope or "architectural_review" in review_type_scope:
            base += (
                "\n\nARCHITECTURE REVIEW RULES:\n"
                + ARCHITECTURE_REVIEW_METHOD_SUPPLEMENT
            )

        if "scalability" in review_type_scope:
            base += (
                "\n\nSCALABILITY REVIEW RULES:\n"
                + SCALABILITY_REVIEW_METHOD_SUPPLEMENT
            )

        if "specification" in review_type_scope:
            base += (
                "\n\nSPECIFICATION REVIEW RULES:\n"
                + SPECIFICATION_REVIEW_METHOD_SUPPLEMENT
            )

        if "maintainability" in review_type_scope:
            base += (
                "\n\nMAINTAINABILITY REVIEW RULES:\n"
                + MAINTAINABILITY_REVIEW_METHOD_SUPPLEMENT
            )

        if "dependency" in review_type_scope:
            base += (
                "\n\nDEPENDENCY REVIEW RULES:\n"
                + DEPENDENCY_REVIEW_METHOD_SUPPLEMENT
            )

        if "license" in review_type_scope:
            base += (
                "\n\nLICENSE REVIEW RULES:\n"
                + LICENSE_REVIEW_METHOD_SUPPLEMENT
            )

        if "api_design" in review_type_scope:
            base += (
                "\n\nAPI DESIGN REVIEW RULES:\n"
                + API_DESIGN_REVIEW_METHOD_SUPPLEMENT
            )

        if "complexity" in review_type_scope:
            base += (
                "\n\nCOMPLEXITY REVIEW RULES:\n"
                + COMPLEXITY_REVIEW_METHOD_SUPPLEMENT
            )

        if "documentation" in review_type_scope:
            base += (
                "\n\nDOCUMENTATION REVIEW RULES:\n"
                + DOCUMENTATION_REVIEW_METHOD_SUPPLEMENT
            )

        if "regression" in review_type_scope:
            base += (
                "\n\nREGRESSION REVIEW RULES:\n"
                + REGRESSION_REVIEW_METHOD_SUPPLEMENT
            )

        base += (
            "\n\nREVIEW METHOD:\n"
            "1. Identify direct defects in the provided code first.\n"
            "2. Assess whether any direct defect implies broader cross_file or project impact based on the provided code, project context, framework guidance, or dependency hints.\n"
            "3. Only emit broader-impact findings when supported by concrete evidence from the provided code, prompt context, framework guidance, or dependency hints.\n"
            "4. Set context_scope to local, cross_file, or project based on the breadth of the actual evidence; use project only for genuinely architectural or cross-cutting impact.\n"
            "5. When you provide systemic metadata, name the specific supporting files and write evidence_basis as a short factual explanation of the exact mismatch, dependency, signature change, or missing check.\n"
            "6. For caller/callee drift, renamed fields, or signature changes, include the other side in related_files and make systemic_impact explain what breaks for callers or consumers.\n"
            "7. For guard, validation, cache, or transaction findings, include the supporting auth/helper/cache/repository file when known and make systemic_impact describe the resulting exposure, unvalidated or incompletely validated input reaching runtime use, stale state, or partial-write risk.\n"
            "8. When reviewing against a specification, keep concrete code/spec mismatches in the specification category instead of diluting them into generic code-quality findings.\n"
            "9. When a local defect suggests broader risk, preserve the local finding and use systemic metadata instead of duplicating the issue."
        )

        if lang == "ja":
            lang_inst = "IMPORTANT: Provide your entire response in Japanese (日本語で回答してください)."
        else:
            lang_inst = "IMPORTANT: Provide your entire response in English."
        return f"{base} {lang_inst}{_JSON_SCHEMA_INSTRUCTION}"

    @staticmethod
    def _build_user_message(
        code_content: str,
        review_type: str,
        spec_content: Optional[str] = None,
    ) -> str:
        """Build the user-role message for the AI.

        The message now reminds the model to respond with JSON.
        """
        has_spec = review_type == "specification" and spec_content
        if has_spec:
            return (
                f"SPECIFICATION DOCUMENT:\n{spec_content}\n\n---\n\n"
                f"CODE TO REVIEW:\n{code_content}\n\n---\n\n"
                "Compare the code against the specification and identify "
                "deviations, missing implementations, or areas that don't "
                "meet the requirements. After identifying direct mismatches, "
                "assess whether any deviation implies broader cross-file or project-level impact based on the provided context. Only include broader findings when the evidence is concrete. For broader findings, set context_scope deliberately, include the exact related file(s) when known, and make evidence_basis a short factual statement about the exact mismatch or missing contract.\n\n"
                "SPECIFICATION FOCUS: Compare the implementation directly against the supplied specification document and look explicitly for required behaviors that are missing, forbidden behaviors that still occur, wrong success or failure semantics, atomicity or ordering guarantees that are violated, and return payloads that do not match the documented contract. Classify these findings as specification instead of functionality, contract-mismatch, or atomicity subtype labels. Prefer the broader code/spec mismatch over generic code quality notes. Keep context_scope local unless the provided files show a broader cross-file impact. Do not leave evidence_basis empty: cite the exact return value, side effect, or branch that contradicts the exact specification requirement, such as returning partial_success even though the spec says the batch must be atomic and partial success is not allowed.\n\n"
                "Respond with the JSON format described in your instructions."
            )
        review_type_scope = AIBackend._review_type_scope(review_type)

        ui_ux_focus = ""
        if "ui_ux" in review_type_scope:
            ui_ux_focus = (
                "\n\nUI/UX FOCUS: Look explicitly for missing loading, error, or empty states; destructive validation or recovery flows that clear user input; blocking desktop actions without busy feedback; destructive actions without confirmation or undo; settings that are hard to find; wizard steps that hide prerequisites; and preferences in one tab that silently override another tab. "
                "If the problem is user-visible, classify it as ui_ux even when the immediate cause is state or logic code, and keep category exactly ui_ux instead of subtype labels. Write systemic_impact in user-outcome terms such as blank, re-enter, accidental, repeated, confusing, disabled, hard to find, silently overridden, or loss of trust. Do not leave evidence_basis empty: cite the exact symbol or label from the code that proves the issue, such as validateProfile, isLoading, export_report, reset_all_settings, Advanced, cloud_sync_enabled, or the visible button/control text."
            )
        dead_code_focus = ""
        if "dead_code" in review_type_scope:
            dead_code_focus = (
                "\n\nDEAD CODE FOCUS: Look explicitly for permanently false or disabled feature flags, unreachable fallback branches, obsolete compatibility shims, dormant entrypoints, handlers that can no longer be reached from the live flow, and code paths with no remaining call sites or wiring in the provided code. Classify these findings as dead_code even when the immediate artifact is a function, import, flag, or handler, and keep category exactly dead_code instead of subtype labels. Prefer the broader dead path over leaf helper noise. Write systemic_impact in maintenance-outcome terms such as obsolete path, misleading fallback, dormant behavior, future changes updating code that never runs, or cleanup risk. Do not leave evidence_basis empty: cite the exact symbol or guard that proves the dead path, such as USE_LEGACY_RENDERER, ENABLE_BULK_ARCHIVE, render_legacy_csv, or a permanently false branch condition."
            )
        localization_focus = ""
        if "localization" in review_type_scope:
            localization_focus = (
                "\n\nLOCALIZATION FOCUS: Look explicitly for visible UI labels, buttons, status text, or messages that are hardcoded instead of going through the translation helper, and for date, time, number, or currency formatting that is hardcoded to one locale. Classify these findings as localization instead of hardcoded-string, i18n, or locale-formatting subtype labels. Prefer user-visible mixed-language UI or locale-specific output over speculative translator-workflow notes. Do not claim a missing translation when the code already passes a concrete key to the helper, such as t('settings.title'). Write systemic_impact in terms such as mixed-language screens, untranslated controls, or confusing dates and amounts for international users. Do not leave evidence_basis empty: cite the exact literal label, helper mismatch, or locale-specific format token, such as Button(..., text='Sync now') beside t(...) calls, or strftime('%m/%d/%Y') with a dollar-prefixed amount."
            )
        error_handling_focus = ""
        if "error_handling" in review_type_scope:
            error_handling_focus = (
                "\n\nERROR HANDLING FOCUS: Look explicitly for swallowed exceptions, broad catch blocks that hide the real failure, returned success statuses after an upstream error, missing error propagation to callers, retry-free transient failure paths, and cleanup or state updates that still run as if work succeeded. Classify these findings as error_handling even when the immediate artifact is a return payload, status check, controller branch, or message string, and keep category exactly error_handling instead of subtype labels. Prefer the broader false-success or hidden-failure path over local style notes. For transient failures, also look for retryable timeout or connection errors that downstream code treats as terminal disablement or one-shot failure instead of retry/backoff. Write systemic_impact in outcome terms such as false success, hidden failure, delayed recovery, silent data loss, misleading metrics, or operators believing a job completed when it actually failed. Do not leave evidence_basis empty: cite the exact catch clause, returned status, retryable marker, or downstream success/disablement check that proves the hidden failure, such as except Exception, except TimeoutError, status='completed', retryable=True, result['status'] == 'completed', result['status'] == 'failed', 'Import finished', or 'Background sync disabled'."
            )
        data_validation_focus = ""
        if "data_validation" in review_type_scope:
            data_validation_focus = (
                "\n\nDATA VALIDATION FOCUS: Look explicitly for validators that only check presence or type coercion but never enforce ordering, ranges, boundaries, allowed values, normalization, or schema completeness before callers use the data. Classify these findings as data_validation even when the immediate artifact is a coercion call, arithmetic expression, or helper contract, and keep category exactly data_validation instead of subtype labels. Prefer the broader validator/caller contract gap over smaller parser notes. Write systemic_impact in outcome terms such as invalid input reaching runtime use, impossible state being accepted, negative durations, incorrect scheduling, or persisted bad data. Do not leave evidence_basis empty: cite the exact field names, validator/helper, coercion, and missing comparison that prove the gap, such as start_hour, end_hour, validate_window, int(payload['end_hour']), or a missing end > start check."
            )
        testing_focus = ""
        if "testing" in review_type_scope:
            testing_focus = (
                "\n\nTESTING FOCUS: Look explicitly for source code branches, validation guards, or error paths that already exist but that the test suite never exercises. Classify these findings as testing even when the immediate artifact is a validator, a pytest function, or a missing parametrized case, and keep category exactly testing instead of subtype labels. Prefer the broader missing regression or edge-case test over smaller assertion-style notes. Write systemic_impact in regression terms such as regressions shipping unnoticed, existing contracts becoming unpinned, or refactors changing behavior without a failing test. Do not leave evidence_basis empty: cite the exact test name, source helper, and untested symbol or boundary, such as test_create_rollout..., validate_rollout, rollout_percent, 0..100, or a missing pytest.raises case."
            )
        accessibility_focus = ""
        if "accessibility" in review_type_scope:
            accessibility_focus = (
                "\n\nACCESSIBILITY FOCUS: Look explicitly for icon-only buttons, unlabeled inputs, placeholder-only form fields, missing accessible names, keyboard-only navigation blockers, focus-management problems, and controls that assistive technology cannot describe clearly. Classify these findings as accessibility instead of generic usability or WCAG subtype labels. Prefer the broader barrier over smaller style notes. Write systemic_impact in user-outcome terms such as screen reader users being unable to identify the control, assistive technology users missing the primary action, or keyboard-only users being unable to complete the task. Do not leave evidence_basis empty: cite the exact control and missing mechanism, such as an icon-only button without aria-label or an input with placeholder text but no label."
            )
        compatibility_focus = ""
        if "compatibility" in review_type_scope:
            compatibility_focus = (
                "\n\nCOMPATIBILITY FOCUS: Look explicitly for OS-specific shell commands, platform-only APIs, browser-specific assumptions, runtime-version dependencies, and environment-sensitive behavior that will make a feature fail on another supported platform. Prefer real user-visible platform breakage over generic legacy-version trivia. If code hardcodes a command like `open`, `xdg-open`, or `os.startfile` without platform branching, classify that as compatibility and describe which supported environments will break. If code imports a stdlib module or uses an API that only exists on newer runtimes, compare that assumption against any declared support range in metadata such as pyproject.toml, setup.cfg, CI config, Docker images, or README instructions and report the mismatch as compatibility. Treat Python's built-in open() for reading files as ordinary file I/O, not as the macOS shell command `open`, unless the code is actually spawning a platform-specific executable. Write systemic_impact in terms such as Windows users unable to launch the file, Linux environments failing at runtime, or supported Python versions failing at import time. Do not leave evidence_basis empty: cite the exact command, API call, or metadata contract, such as subprocess.run(['open', report_path]) without platform detection or import tomllib while pyproject.toml still declares requires-python >=3.9."
            )
        performance_focus = ""
        if "performance" in review_type_scope:
            performance_focus = (
                "\n\nPERFORMANCE FOCUS: Look explicitly for repeated queries or requests inside loops, avoidable O(n^2) scans, expensive work repeated for each item instead of batching, blocking I/O in hot paths, and cache or state handling that forces redundant work. Classify these findings as performance instead of algorithmic efficiency, caching, query_efficiency, or redundant_work subtype labels. Prefer the broader throughput or latency bottleneck over smaller style notes. Write systemic_impact in terms such as latency growing with input size, throughput degrading under larger batches, or one extra round trip per record. Do not leave evidence_basis empty: cite the exact loop and repeated operation, such as execute_query being called inside a for order_id loop."
            )
        architecture_focus = ""
        if "architecture" in review_type_scope:
            architecture_focus = (
                "\n\nARCHITECTURE FOCUS: Look explicitly for controllers bypassing service layers, service or domain logic depending directly on database helpers, web request context, UI frameworks, or presentation modules, and modules that invert the intended dependency direction between layers. Treat service or domain imports of Flask, Django, or FastAPI request/context objects as architecture findings even when the code is otherwise simple, because framework request state belongs at the boundary layer. Classify these findings as architecture instead of dependency_misalignment, separation_of_concerns, security, or layering subtype labels. Prefer the broader boundary violation over smaller coupling notes. When the code and a collaborating layer file together prove the leak, set context_scope cross_file and name the supporting file in related_files; otherwise keep context_scope local. Write systemic_impact in terms such as layer boundaries becoming inconsistent, dependency direction being inverted, framework coupling spreading into business logic, or changes in one layer forcing edits across others. Do not leave evidence_basis empty: cite the exact import or call that proves the leak, such as controller.py importing db.py directly instead of service.py, or pricing_service.py reading flask.request headers inside service logic."
            )
        scalability_focus = ""
        if "scalability" in review_type_scope:
            scalability_focus = (
                "\n\nSCALABILITY FOCUS: Look explicitly for process-local state used as shared coordination, rate limits or quotas that rely on in-memory dictionaries or lists, deployment knobs that reveal multi-worker or multi-instance execution, unbounded in-memory queues or buffers, missing backpressure, and synchronous fan-out work that grows with accounts, tenants, or subscribers. Classify these findings as scalability instead of stateful-component, throughput, or deployment-configuration subtype labels. Prefer the broader growth bottleneck over smaller local notes. When the code and a deployment/runtime file together prove the issue, set context_scope cross_file and name the supporting file in related_files. Write systemic_impact in terms such as horizontal scaling breaking correctness, inconsistent global limits across workers, backlog growth without backpressure, or memory pressure rising with traffic. Do not leave evidence_basis empty: cite the exact state symbol or deployment knob, such as RATE_LIMIT_STATE with workers = 4."
            )
        specification_focus = ""
        if "specification" in review_type_scope:
            specification_focus = (
                "\n\nSPECIFICATION FOCUS: Compare the implementation directly against the supplied specification document and look explicitly for required behaviors that are missing, forbidden behaviors that still occur, wrong success or failure semantics, atomicity or ordering guarantees that are violated, and return payloads that do not match the documented contract. Classify these findings as specification instead of functionality, contract-mismatch, or atomicity subtype labels. Prefer the broader code/spec mismatch over generic code quality notes. Keep context_scope local unless the provided files show a broader cross-file impact. Write systemic_impact in contract terms such as callers observing behavior the specification forbids, required guarantees not being met, or integrations relying on undocumented semantics. Do not leave evidence_basis empty: cite the exact return value, side effect, or branch that contradicts the exact specification requirement, such as returning partial_success even though the spec says the batch must be atomic and partial success is not allowed."
            )
        maintainability_focus = ""
        if "maintainability" in review_type_scope:
            maintainability_focus = (
                "\n\nMAINTAINABILITY FOCUS: Look explicitly for duplicated live logic across active entry points, large helpers or classes with mixed responsibilities, low-cohesion modules that mix validation, persistence, orchestration, and presentation work, and code that will require the same policy change in multiple places. Classify these findings as maintainability instead of duplicated_code, code_reuse, technical_debt, or god_class subtype labels. Prefer the broader maintainability hotspot over smaller style notes. For duplicated rules spanning a few collaborating files, keep context_scope cross_file instead of project unless the evidence really shows a repo-wide pattern. Write systemic_impact in terms such as divergent fixes, policy drift, duplicated maintenance surface, risky refactors, or future edits needing to stay synchronized across files. Do not leave evidence_basis empty: cite the exact duplicated symbol or overloaded class, such as normalize_sync_window being implemented in both cli_sync_settings.py and gui_sync_settings.py, or a SettingsController that loads config, validates input, saves settings, triggers sync, and builds display text."
            )
        dependency_focus = ""
        if "dependency" in review_type_scope:
            dependency_focus = (
                "\n\nDEPENDENCY FOCUS: Look explicitly for runtime imports of third-party packages that the main dependency manifest does not declare, imports that rely on packages only present in dev/test extras, and package-scope mistakes that will make fresh installs or production environments fail. Classify these findings as dependency instead of dependency-management or package-hygiene subtype labels. Prefer real install-time or import-time breakage over weaker notes about pinning or package size. If runtime code imports a package that is only listed under optional dev/test dependencies, call out that production installs without extras can fail. Write systemic_impact in terms such as ModuleNotFoundError on fresh installs, deploys breaking without dev extras, or runtime imports crashing consumers. Do not leave evidence_basis empty: cite the exact import and manifest mismatch, such as config_writer.py importing yaml while pyproject.toml never declares PyYAML, or metrics.py importing pytest while pyproject.toml lists pytest only under optional dev extras."
            )
        license_focus = ""
        if "license" in review_type_scope:
            license_focus = (
                "\n\nLICENSE FOCUS: Look explicitly for bundled or runtime dependencies whose license terms conflict with the project's declared distribution terms, and for notice or attribution files that say required license or NOTICE material will not be shipped with releases. Also compare vendored source-file headers against the shipped notice package: if a file says it was copied from a third-party project or names an upstream license, verify that the distributed notices and preserved headers still carry the required attribution text and do not falsely claim that no third-party source is bundled. Classify these findings as license instead of license-attribution, third-party-notice, dependency-license, or transparency subtype labels. Prefer concrete packaged-distribution compliance defects over weaker notes about adding comments near imports or improving metadata formatting. If a notice file says an Apache dependency's upstream NOTICE will not be included in binaries, if license inventory files contradict the project's stated MIT-compatible dependency story, or if a vendored header copied from an MIT package conflicts with THIRD_PARTY_NOTICES.md, treat that as at least a medium-severity license issue. Write systemic_impact in terms such as distributed binaries shipping incomplete notices, downstream redistributors receiving misleading license information, or released artifacts carrying incompatible license obligations. Do not leave evidence_basis empty: cite the exact dependency, license label, copied-source header, and notice mismatch, such as licenses_check.csv marking networksync as AGPL-3.0-only while THIRD_PARTY_NOTICES.md says dependencies are MIT-compatible, THIRD_PARTY_NOTICES.md stating telemetry-sdk's upstream NOTICE will not be shipped with binaries, or src/vendor/markdown_table.py saying it was copied from tinytable 1.4.0 (MIT) while THIRD_PARTY_NOTICES.md says the distribution does not bundle third-party source files."
            )
        api_design_focus = ""
        if "api_design" in review_type_scope:
            api_design_focus = (
                "\n\nAPI DESIGN FOCUS: Look explicitly for GET handlers that create or mutate state, bodies attached to GET endpoints, create, update, or delete routes with the wrong HTTP method semantics, missing 201-style creation behavior, misleading resource paths, and response contracts that will surprise generated clients or OpenAPI consumers. Classify these findings as api_design instead of HTTP-method or endpoint-semantics subtype labels. Prefer the broader client-facing contract issue over smaller implementation notes. Write systemic_impact in client-outcome terms such as prefetch or cache layers triggering side effects, retries creating duplicate state, or API consumers being misled about whether an endpoint is safe and idempotent. Do not leave evidence_basis empty: cite the exact decorator, route path, handler, or status behavior, such as @app.get('/api/invitations/create') on create_invitation."
            )
        complexity_focus = ""
        if "complexity" in review_type_scope:
            complexity_focus = (
                "\n\nCOMPLEXITY FOCUS: Look explicitly for deeply nested conditionals, long decision trees, repeated branching on multiple policy dimensions, and helpers that bundle too many states or flags into one function. Classify these findings as complexity instead of cyclomatic-complexity or nesting subtype labels. Prefer the broader hotspot over smaller style notes. For single-function complexity hotspots, keep context_scope local unless the provided code proves a wider cross-file dependency problem. Write systemic_impact in maintainability terms such as harder to reason about, brittle to modify, branch interactions being easy to break, or future changes requiring broad regression coverage. Do not leave evidence_basis empty: cite the exact function and branch structure, such as choose_sync_strategy or a nested if/else chain across account state, retry mode, network conditions, and feature flags."
            )
        documentation_focus = ""
        if "documentation" in review_type_scope:
            documentation_focus = (
                "\n\nDOCUMENTATION FOCUS: Look explicitly for stale README or operator-guide steps, documented flags or commands that no longer exist, comments or docs that describe old behavior, and public documentation that no longer matches the implementation. Classify these findings as documentation instead of docs-drift or CLI-contract subtype labels. Prefer the broader docs/code mismatch over smaller missing-docstring notes when a reader following the docs would hit the wrong behavior. Write systemic_impact in reader-outcome terms such as operators or users following broken instructions, failed automation, misleading tutorials, or documentation-led workflows failing. Do not leave evidence_basis empty: cite the exact doc file, command, flag, option, or comment text that no longer matches the implementation, such as README.md documenting --dry-run while cli.py never registers that flag."
            )
        regression_focus = ""
        if "regression" in review_type_scope:
            regression_focus = (
                "\n\nREGRESSION FOCUS: Look explicitly for changed defaults, removed or weakened guards, altered branch conditions, and behavior shifts that can break previously shipped workflows even when the code still looks internally consistent. Classify these findings as regression instead of behavioral-change subtype labels. Prefer the broader user-visible break over smaller implementation notes. Write systemic_impact in terms such as disabled by default, silently stops working, existing startup flow no longer runs, or prior behavior changing without migration. Do not leave evidence_basis empty: cite the exact changed symbol and the downstream consumer it affects, such as sync_enabled changing from True to False and startup code that gates work on that setting."
            )
        return (
            "Review this code. After identifying direct issues, assess whether any issue suggests cross-file or project-level impact based on the provided project context, framework guidance, or implied dependencies. Only include broader-impact findings when the evidence is concrete. For broader findings, set context_scope deliberately, include the exact related file(s) when known, and make evidence_basis a short factual statement about the exact mismatch, dependency, signature change, or missing check. When the evidence shows caller/callee drift, stale cache/state handling, missing validation or auth checks, or loss of transaction boundaries, name the supporting file and describe the downstream impact concretely. For validation drift, explicitly say when unvalidated or incompletely validated input can proceed past the validator and reach runtime use.\n\n"
            f"CODE TO REVIEW:\n{code_content}\n\n"
            f"Respond with the JSON format described in your instructions.{ui_ux_focus}{dead_code_focus}{localization_focus}{error_handling_focus}{data_validation_focus}{testing_focus}{accessibility_focus}{compatibility_focus}{performance_focus}{architecture_focus}{scalability_focus}{specification_focus}{maintainability_focus}{dependency_focus}{license_focus}{api_design_focus}{complexity_focus}{documentation_focus}{regression_focus}"
        )

    @staticmethod
    def _build_multi_file_user_message(
        files: List[Dict[str, Any]],
        review_type: str,
        spec_content: Optional[str] = None,
    ) -> str:
        """Build a user-role message that combines multiple files.

        Each entry in *files* is ``{"name": "...", "content": "..."}``.
        The model is instructed to respond with JSON (schema is in the
        system prompt).  Legacy ``=== FILE:`` delimiters are kept as
        a hint so the fallback parser still works if the model ignores
        the JSON instruction.
        """
        parts: List[str] = []
        if review_type == "specification" and spec_content:
            parts.append(f"SPECIFICATION DOCUMENT:\n{spec_content}\n\n---\n")

        review_type_scope = AIBackend._review_type_scope(review_type)

        ui_ux_focus = ""
        if "ui_ux" in review_type_scope:
            ui_ux_focus = (
                " Also check explicitly for missing loading/error/empty states, destructive recovery flows that clear input, blocking desktop actions without progress feedback, destructive confirmation gaps, settings discoverability problems, wizard step orientation issues, and cross-tab preference overrides. If the problem is user-visible, classify it as ui_ux even when state or logic code is the immediate cause, and keep category exactly ui_ux instead of subtype labels. Write systemic_impact in user-outcome terms such as blank, re-enter, accidental, repeated, confusing, disabled, hard to find, silently overridden, or loss of trust. Do not leave evidence_basis empty: cite the exact function, prop, state variable, dialog label, or control text that proves the issue, such as validateProfile, isLoading, export_report, reset_all_settings, Advanced, or cloud_sync_enabled."
            )
        dead_code_focus = ""
        if "dead_code" in review_type_scope:
            dead_code_focus = (
                " Also check explicitly for permanently false feature flags, unreachable fallback branches, obsolete compatibility shims, dormant UI handlers, stale migration paths, and symbols that no longer have live wiring across the provided files. Classify these findings as dead_code even when the immediate artifact is a function, import, flag, or handler, and keep category exactly dead_code instead of subtype labels. Prefer the broader dead path over leaf helper noise. Write systemic_impact in maintenance-outcome terms such as obsolete path, misleading fallback, dormant behavior, future changes updating code that never runs, or cleanup risk. Do not leave evidence_basis empty: cite the exact symbol, export, flag, route, or branch condition that proves the dead path, such as USE_LEGACY_RENDERER, ENABLE_BULK_ARCHIVE, or render_legacy_csv."
            )
        localization_focus = ""
        if "localization" in review_type_scope:
            localization_focus = (
                " Also check explicitly for visible UI labels, buttons, status text, or messages that are hardcoded instead of going through the translation helper, and for date, time, number, or currency formatting that is hardcoded to one locale. Classify these findings as localization instead of hardcoded-string, i18n, or locale-formatting subtype labels. Prefer user-visible mixed-language UI or locale-specific output over speculative translator-workflow notes. Do not claim a missing translation when the code already passes a concrete key to the helper, such as t('settings.title'). Write systemic_impact in terms such as mixed-language screens, untranslated controls, or confusing dates and amounts for international users. Do not leave evidence_basis empty: cite the exact literal label, helper mismatch, or locale-specific format token, such as Button(..., text='Sync now') beside t(...) calls, or strftime('%m/%d/%Y') with a dollar-prefixed amount."
            )
        error_handling_focus = ""
        if "error_handling" in review_type_scope:
            error_handling_focus = (
                " Also check explicitly for swallowed exceptions, broad catch blocks that hide the real failure, returned success states after an upstream error, missing error propagation to callers, retry-free transient failure paths, and callers that surface a completed or successful message even though the underlying operation failed. Classify these findings as error_handling even when the immediate artifact is a result payload, controller branch, or message string, and keep category exactly error_handling instead of subtype labels. Prefer the broader false-success or hidden-failure path over local style notes. For transient failures, also look for retryable timeout or connection errors that downstream code turns into terminal disablement or one-shot failure instead of retry/backoff. Write systemic_impact in outcome terms such as false success, hidden failure, delayed recovery, silent data loss, misleading metrics, or operators believing a job completed when it actually failed. Do not leave evidence_basis empty: cite the exact catch clause, returned status, retryable marker, downstream success check, or success/disablement message that proves the hidden failure, such as except Exception, except TimeoutError, status='completed', retryable=True, result['status'] == 'completed', result['status'] == 'failed', 'Import finished', or 'Background sync disabled'."
            )
        data_validation_focus = ""
        if "data_validation" in review_type_scope:
            data_validation_focus = (
                " Also check explicitly for validators that only check presence or type coercion but never enforce ordering, ranges, boundaries, allowed values, normalization, or schema completeness before callers use the data. Classify these findings as data_validation even when the immediate artifact is a coercion call, arithmetic expression, or helper contract, and keep category exactly data_validation instead of subtype labels. Prefer the broader validator/caller contract gap over smaller parser notes. Write systemic_impact in outcome terms such as invalid input reaching runtime use, impossible state being accepted, negative durations, incorrect scheduling, or persisted bad data. Do not leave evidence_basis empty: cite the exact field names, validator/helper, coercion, and missing comparison that prove the gap, such as start_hour, end_hour, validate_window, int(payload['end_hour']), or a missing end > start check."
            )
        testing_focus = ""
        if "testing" in review_type_scope:
            testing_focus = (
                " Also check explicitly for source branches, validation guards, and error paths that already exist but that the test suite never exercises. Classify these findings as testing even when the immediate artifact is a pytest function, missing parametrized case, or untested helper contract, and keep category exactly testing instead of subtype labels. Prefer the broader missing regression or edge-case test over smaller assertion-style notes. Write systemic_impact in regression terms such as regressions shipping unnoticed, boundary behavior becoming unpinned, or refactors changing behavior without a failing test. Do not leave evidence_basis empty: cite the exact test name, source helper, and untested symbol or boundary, such as test_create_rollout..., validate_rollout, rollout_percent, 0..100, or a missing pytest.raises case."
            )
        accessibility_focus = ""
        if "accessibility" in review_type_scope:
            accessibility_focus = (
                " Also check explicitly for icon-only buttons, unlabeled inputs, placeholder-only form fields, missing accessible names, keyboard-only navigation blockers, focus-management problems, and controls that assistive technology cannot describe clearly. Classify these findings as accessibility instead of generic usability or WCAG subtype labels. Prefer the broader barrier over smaller style notes. Write systemic_impact in user-outcome terms such as screen reader users being unable to identify the control, assistive technology users missing the primary action, or keyboard-only users being unable to complete the task. Do not leave evidence_basis empty: cite the exact control and missing mechanism, such as an icon-only button without aria-label or an input with placeholder text but no label."
            )
        compatibility_focus = ""
        if "compatibility" in review_type_scope:
            compatibility_focus = (
                " Also check explicitly for OS-specific shell commands, platform-only APIs, browser-specific assumptions, runtime-version dependencies, and environment-sensitive behavior that will make a feature fail on another supported platform. Prefer real user-visible platform breakage over generic legacy-version trivia. If code hardcodes a command like `open`, `xdg-open`, or `os.startfile` without platform branching, classify that as compatibility and describe which supported environments will break. If code imports a stdlib module or uses an API that only exists on newer runtimes, compare that assumption against any declared support range in metadata such as pyproject.toml, setup.cfg, CI config, Docker images, or README instructions and report the mismatch as compatibility. Treat Python's built-in open() for reading files as ordinary file I/O, not as the macOS shell command `open`, unless the code is actually spawning a platform-specific executable. Write systemic_impact in terms such as Windows users unable to launch the file, Linux environments failing at runtime, or supported Python versions failing at import time. Do not leave evidence_basis empty: cite the exact command, API call, or metadata contract, such as subprocess.run(['open', report_path]) without platform detection or import tomllib while pyproject.toml still declares requires-python >=3.9."
            )
        performance_focus = ""
        if "performance" in review_type_scope:
            performance_focus = (
                " PERFORMANCE FOCUS: Also check explicitly for repeated queries or requests inside loops, avoidable O(n^2) scans, expensive work repeated for each item instead of batching, blocking I/O in hot paths, and cache or state handling that forces redundant work. Classify these findings as performance instead of algorithmic efficiency, caching, query_efficiency, or redundant_work subtype labels. Prefer the broader throughput or latency bottleneck over smaller style notes. Write systemic_impact in terms such as latency growing with input size, throughput degrading under larger batches, or one extra round trip per record. Do not leave evidence_basis empty: cite the exact loop and repeated operation, such as execute_query being called inside a for order_id loop."
            )
        architecture_focus = ""
        if "architecture" in review_type_scope:
            architecture_focus = (
                " ARCHITECTURE FOCUS: Also check explicitly for controllers bypassing service layers, service or domain logic depending directly on persistence helpers, web request context, UI frameworks, or presentation modules, and modules that invert the intended dependency direction between layers. Treat service or domain imports of Flask, Django, or FastAPI request/context objects as architecture findings even when the code is otherwise simple, because framework request state belongs at the boundary layer. Classify these findings as architecture instead of dependency_misalignment, separation_of_concerns, security, or layering subtype labels. Prefer one broader architecture finding when the files together prove the boundary violation. Write systemic_impact in terms such as layer boundaries becoming inconsistent, dependency direction being inverted, framework coupling spreading into business logic, or changes in one layer forcing edits across others. Do not leave evidence_basis empty: cite the exact import or call that proves the leak, such as controller.py importing db.py directly instead of service.py, or pricing_service.py reading flask.request headers inside service logic."
            )
        scalability_focus = ""
        if "scalability" in review_type_scope:
            scalability_focus = (
                " Also check explicitly for process-local state used as shared coordination, rate limits or quotas that rely on in-memory dictionaries or lists, deployment knobs that reveal multi-worker or multi-instance execution, unbounded in-memory queues or buffers, missing backpressure, and synchronous fan-out work that grows with accounts, tenants, or subscribers. Classify these findings as scalability instead of stateful-component, throughput, or deployment-configuration subtype labels. Prefer the broader growth bottleneck over smaller local notes. When the code and a deployment/runtime file together prove the issue, set context_scope cross_file and name the supporting file in related_files. Write systemic_impact in terms such as horizontal scaling breaking correctness, inconsistent global limits across workers, backlog growth without backpressure, or memory pressure rising with traffic. Do not leave evidence_basis empty: cite the exact state symbol or deployment knob, such as RATE_LIMIT_STATE with workers = 4 or a pending_events queue that never applies backpressure."
            )
        specification_focus = ""
        if "specification" in review_type_scope:
            specification_focus = (
                " SPECIFICATION FOCUS: Also check explicitly for required behaviors the implementation omits, forbidden behaviors that still occur, wrong success or failure semantics, and side effects that violate documented guarantees in the supplied specification. Classify these findings as specification instead of functionality, contract-mismatch, or atomicity subtype labels. Prefer the broader code/spec mismatch over generic code quality notes. Keep context_scope local unless multiple implementation files are needed to prove the spec deviation. Write systemic_impact in contract terms such as callers observing behavior the specification forbids, required guarantees not being met, or integrations depending on undocumented semantics. Do not leave evidence_basis empty: cite the exact implementation behavior and the exact required behavior from the specification, such as returning partial_success even though the spec says the batch must be atomic and partial success is not allowed."
            )
        maintainability_focus = ""
        if "maintainability" in review_type_scope:
            maintainability_focus = (
                " Also check explicitly for duplicated live logic across active entry points, low-cohesion classes or modules with mixed responsibilities, overgrown coordinators, and workflows that require the same policy change in multiple files. Classify these findings as maintainability instead of duplicated_code, code_reuse, technical_debt, or god_class subtype labels. Prefer one cross_file maintainability finding when several files duplicate the same normalization or policy rules. For duplicated responsibility across a few collaborating files, keep context_scope cross_file unless the evidence truly shows a project-wide structural problem. Write systemic_impact in maintenance-outcome terms such as divergent fixes, policy drift, duplicated maintenance surface, low cohesion making refactors risky, or future edits needing to stay synchronized. Do not leave evidence_basis empty: cite the exact duplicated symbol or overloaded class, such as normalize_sync_window appearing in both cli_sync_settings.py and gui_sync_settings.py, or a SettingsController that mixes config loading, validation, persistence, sync orchestration, and UI summary formatting."
            )
        dependency_focus = ""
        if "dependency" in review_type_scope:
            dependency_focus = (
                " Also check explicitly for runtime imports of third-party packages that the main dependency manifest does not declare, imports that rely on packages only present in dev/test extras, and package-scope mistakes that will make fresh installs or production environments fail. Classify these findings as dependency instead of dependency-management or package-hygiene subtype labels. Prefer real install-time or import-time breakage over weaker notes about pinning or package size. If runtime code imports a package that is only listed under optional dev/test dependencies, call out that production installs without extras can fail. Write systemic_impact in terms such as ModuleNotFoundError on fresh installs, deploys breaking without dev extras, or runtime imports crashing consumers. Do not leave evidence_basis empty: cite the exact import and manifest mismatch, such as config_writer.py importing yaml while pyproject.toml never declares PyYAML, or metrics.py importing pytest while pyproject.toml lists pytest only under optional dev extras."
            )
        license_focus = ""
        if "license" in review_type_scope:
            license_focus = (
                " Also check explicitly for bundled or runtime dependencies whose license terms conflict with the project's declared distribution terms, and for notice or attribution files that say required license or NOTICE material will not be shipped with releases. Compare vendored source-file headers against the shipped notice package too: if a file says it was copied from a third-party package or names an upstream license, verify that the release notices still preserve that attribution and do not falsely claim no third-party source is bundled. Classify these findings as license instead of license-attribution, third-party-notice, dependency-license, or transparency subtype labels. Prefer concrete packaged-distribution compliance defects over weaker notes about adding comments near imports or reformatting metadata. If a notice file says an Apache dependency's upstream NOTICE will not be included in binaries, if license inventory files contradict the project's stated MIT-compatible dependency story, or if a copied MIT-licensed source header conflicts with THIRD_PARTY_NOTICES.md, treat that as at least a medium-severity license issue. Write systemic_impact in terms such as distributed binaries shipping incomplete notices, downstream redistributors receiving misleading license information, or released artifacts carrying incompatible license obligations. Do not leave evidence_basis empty: cite the exact dependency, license label, copied-source header, and notice mismatch, such as licenses_check.csv marking networksync as AGPL-3.0-only while THIRD_PARTY_NOTICES.md says dependencies are MIT-compatible, THIRD_PARTY_NOTICES.md stating telemetry-sdk's upstream NOTICE will not be shipped with binaries, or src/vendor/markdown_table.py saying it was copied from tinytable 1.4.0 (MIT) while THIRD_PARTY_NOTICES.md says the distribution does not bundle third-party source files."
            )
        api_design_focus = ""
        if "api_design" in review_type_scope:
            api_design_focus = (
                " Also check explicitly for GET handlers that create or mutate state, bodies attached to GET endpoints, create, update, or delete routes with the wrong HTTP method semantics, missing 201-style creation behavior, misleading resource paths, and response contracts that will surprise generated clients or OpenAPI consumers. Classify these findings as api_design instead of HTTP-method or endpoint-semantics subtype labels. Prefer the broader client-facing contract issue over smaller implementation notes. Write systemic_impact in client-outcome terms such as prefetch or cache layers triggering side effects, retries creating duplicate state, or API consumers being misled about whether an endpoint is safe and idempotent. Do not leave evidence_basis empty: cite the exact decorator, route path, handler, or status behavior, such as @app.get('/api/invitations/create') on create_invitation."
            )
        complexity_focus = ""
        if "complexity" in review_type_scope:
            complexity_focus = (
                " Also check explicitly for deeply nested conditionals, long decision trees, repeated branching on multiple policy dimensions, and helpers that bundle too many states or flags into one function. Classify these findings as complexity instead of cyclomatic-complexity or nesting subtype labels. Prefer the broader hotspot over smaller style notes. For single-function complexity hotspots, keep context_scope local unless the provided files prove a wider dependency problem. Write systemic_impact in maintainability terms such as harder to reason about, brittle to modify, branch interactions being easy to break, or future changes requiring broad regression coverage. Do not leave evidence_basis empty: cite the exact function and branch structure, such as choose_sync_strategy or a nested if/else chain across account state, retry mode, network conditions, and feature flags."
            )
        documentation_focus = ""
        if "documentation" in review_type_scope:
            documentation_focus = (
                " Also check explicitly for stale README or operator-guide steps, documented flags or commands that no longer exist, comments or docs that describe old behavior, and public documentation that no longer matches the implementation. Classify these findings as documentation instead of docs-drift or CLI-contract subtype labels. Prefer the broader docs/code mismatch over smaller missing-docstring notes when a reader following the docs would hit the wrong behavior. Write systemic_impact in reader-outcome terms such as operators or users following broken instructions, failed automation, misleading tutorials, or documentation-led workflows failing. Do not leave evidence_basis empty: cite the exact doc file, command, flag, option, or comment text that no longer matches the implementation, such as README.md documenting --dry-run while cli.py never registers that flag."
            )
        regression_focus = ""
        if "regression" in review_type_scope:
            regression_focus = (
                " Also check explicitly for changed defaults, removed or weakened guards, altered branch conditions, and behavior shifts that can break previously shipped workflows. Classify these findings as regression instead of behavioral-change subtype labels. Prefer the broader user-visible or workflow-visible break over smaller implementation notes. Write systemic_impact in terms such as disabled by default, silently stops working, existing startup flow no longer runs, or prior behavior changing without migration. Do not leave evidence_basis empty: cite the exact changed symbol and the downstream consumer it affects, such as sync_enabled changing from True to False and startup code that gates work on that setting."
            )

        parts.append(
            "Review each of the following files. Also look for issues that only become visible across files in this batch, such as contract mismatches, incomplete refactors, duplicated responsibility, dependency direction problems, and caller/callee inconsistencies. Only report broader findings when they are supported by the files shown here or by the provided project context. "
            "For broader findings, set context_scope deliberately, name the supporting related file(s), and make evidence_basis a short factual statement about the exact cross-file mismatch or dependency. For caller/callee drift, stale cache/state handling, missing guards or validation, and transaction-boundary issues, include the collaborating file when known and describe the downstream impact concretely. For validation drift, explicitly say when unvalidated or incompletely validated input can proceed past the helper or validator and reach runtime use. "
            "Respond with JSON following the schema in your instructions. "
            "Include a separate entry in the \"files\" array for each file, "
            f"and a separate object in \"findings\" for each distinct issue.\n{ui_ux_focus}{dead_code_focus}{localization_focus}{error_handling_focus}{data_validation_focus}{testing_focus}{accessibility_focus}{compatibility_focus}{performance_focus}{architecture_focus}{scalability_focus}{specification_focus}{maintainability_focus}{dependency_focus}{license_focus}{api_design_focus}{complexity_focus}{documentation_focus}{regression_focus}"
        )
        for f in files:
            parts.append(f"=== FILE: {f['name']} ===")
            parts.append(f"{f['content']}\n")

        return "\n".join(parts)

    @staticmethod
    def _review_type_scope(review_type: str) -> set[str]:
        scope: set[str] = set()
        review_registry = get_review_registry()
        for raw_part in (part.strip() for part in review_type.split("+") if part.strip()):
            try:
                scope.update(review_registry.lineage_keys(raw_part))
            except KeyError:
                scope.add(raw_part)
        return scope

    @staticmethod
    def _build_diff_user_message(
        file_entry: Dict[str, Any],
        review_type: str,
        spec_content: Optional[str] = None,
    ) -> str:
        """Build a user-role message optimised for diff-scope reviews.

        When the file entry carries ``hunks`` (produced by
        :func:`scanner.parse_diff_file_enhanced`), the prompt presents
        each hunk with:

        * The function/class context extracted from the ``@@`` header.
        * Removed (``-``) and added (``+``) lines with line numbers.
        * Surrounding unchanged context so the model understands intent.

        A ``COMMIT MESSAGE`` section is prepended when available.

        Args:
            file_entry: Dict with keys ``filename``, ``content``, and
                        optionally ``hunks``, ``commit_messages``.
            review_type: Review type key(s).
            spec_content: Specification content (for ``specification``
                          review type).
        """
        parts: list[str] = []

        # Spec preamble (if applicable)
        if review_type == "specification" and spec_content:
            parts.append(f"SPECIFICATION DOCUMENT:\n{spec_content}\n\n---\n")

        # Commit messages
        commit_msgs = file_entry.get("commit_messages")
        if commit_msgs:
            parts.append(f"COMMIT MESSAGE:\n{commit_msgs}\n\n---\n")

        filename = file_entry.get("filename", file_entry.get("name", "unknown"))
        hunks = file_entry.get("hunks")

        if not hunks:
            # Fallback — no hunk data; treat as plain content review
            parts.append(f"CHANGED FILE: {filename}\n")
            parts.append(f"{file_entry.get('content', '')}\n")
            parts.append(
                "FOCUS YOUR REVIEW ON THE CHANGED LINES.\n"
                "Use surrounding context only to understand intent and impact.\n"
                "If a changed-line issue indicates a likely broader regression, only report that broader impact when it is supported by concrete evidence from this diff, the surrounding context, the commit message, or the specification.\n"
                "If you report broader impact, set context_scope deliberately, include the supporting related file(s) when known, and make evidence_basis a short factual statement about the exact signature, contract, or guard that changed. When the change breaks callers, weakens a guard, leaves stale state, or removes transaction safety, name the supporting file and describe that downstream impact directly. For validation drift, explicitly say when the changed code allows unvalidated or incompletely validated input to reach runtime use.\n"
                "For regression reviews, classify changed defaults, removed guards, and behavior shifts as regression rather than behavioral-change subtype labels. When a changed default disables an existing workflow, prefer one cross_file regression finding that names the downstream startup or consumer path and states that the feature becomes disabled by default.\n"
                "Keep the primary finding anchored to the changed code.\n"
                "Respond with the JSON format described in your instructions."
            )
            return "\n".join(parts)

        parts.append(f"CHANGED FILE: {filename}\n")

        for idx, hunk in enumerate(hunks, 1):
            parts.append(f"--- Hunk {idx} ---")
            if hunk.function_name:
                line_hint = hunk.new_start
                parts.append(
                    f"FUNCTION/CLASS CONTEXT: {hunk.function_name} [line {line_hint}]"
                )

            # Context before
            if hunk.context_before:
                parts.append("\nSURROUNDING CONTEXT (before change):")
                for ctx_line in hunk.context_before:
                    parts.append(f"  {ctx_line}")

            # Changed lines
            if hunk.removed or hunk.added:
                parts.append("\nDIFF (changed lines):")
                for lineno, text in hunk.removed:
                    parts.append(f"- L{lineno}: {text}")
                for lineno, text in hunk.added:
                    parts.append(f"+ L{lineno}: {text}")

            # Context after
            if hunk.context_after:
                parts.append("\nSURROUNDING CONTEXT (after change):")
                for ctx_line in hunk.context_after:
                    parts.append(f"  {ctx_line}")

            parts.append("")  # blank separator

        parts.append(
            "FOCUS YOUR REVIEW ON THE CHANGED LINES.\n"
            "Use surrounding context only to understand intent and impact.\n"
            "If a changed-line issue indicates a likely broader regression, only report that broader impact when it is supported by concrete evidence from this diff, the surrounding context, the commit message, or the specification.\n"
            "If you report broader impact, set context_scope deliberately, include the supporting related file(s) when known, and make evidence_basis a short factual statement about the exact signature, contract, or guard that changed. When the change breaks callers, weakens a guard, leaves stale state, or removes transaction safety, name the supporting file and describe that downstream impact directly. For validation drift, explicitly say when the changed code allows unvalidated or incompletely validated input to reach runtime use.\n"
            "For regression reviews, classify changed defaults, removed guards, and behavior shifts as regression rather than behavioral-change subtype labels. When a changed default disables an existing workflow, prefer one cross_file regression finding that names the downstream startup or consumer path and states that the feature becomes disabled by default.\n"
            "Keep the primary finding anchored to the changed code.\n"
            "Respond with the JSON format described in your instructions."
        )
        return "\n".join(parts)

    @staticmethod
    def _build_multi_file_diff_user_message(
        file_entries: list[Dict[str, Any]],
        review_type: str,
        spec_content: Optional[str] = None,
    ) -> str:
        """Combine multiple diff-aware file entries into a single prompt.

        Each file is formatted via :meth:`_build_diff_user_message` and
        separated by ``=== FILE: <name> ===`` delimiters for fallback
        parsing compatibility.
        """
        parts: list[str] = []

        if review_type == "specification" and spec_content:
            parts.append(f"SPECIFICATION DOCUMENT:\n{spec_content}\n\n---\n")

        # Commit messages (same across all files in a commit-based diff)
        commit_msgs = None
        for entry in file_entries:
            commit_msgs = entry.get("commit_messages")
            if commit_msgs:
                break
        if commit_msgs:
            parts.append(f"COMMIT MESSAGE:\n{commit_msgs}\n\n---\n")

        parts.append(
            "Review each of the following changed files. "
            "FOCUS YOUR REVIEW ON THE CHANGED LINES. "
            "Use surrounding context only to understand intent and impact. "
            "Also check whether the touched files reveal cross-file problems such as contract mismatches, partial refactors, broken call paths, or inconsistent validation/state handling. "
            "Only report broader findings when they are supported by concrete evidence in these diffs, the surrounding context, the commit message, or the specification. "
            "For broader findings, set context_scope deliberately, name the supporting related file(s), and make evidence_basis a short factual statement about the exact changed contract, caller/callee mismatch, or missing guard. For stale state, cache invalidation, or transaction-boundary loss, include the collaborating file when known and describe the downstream impact directly. For validation drift, explicitly say when unvalidated or incompletely validated input can proceed past the changed boundary and reach runtime use. "
            "Keep each finding anchored to the changed code that exposes it.\n"
            "Respond with JSON following the schema in your instructions. "
            "Include a separate entry in the \"files\" array for each file.\n"
        )

        for entry in file_entries:
            fname = entry.get("filename", entry.get("name", "unknown"))
            parts.append(f"=== FILE: {fname} ===")
            hunks = entry.get("hunks")
            if hunks:
                for idx, hunk in enumerate(hunks, 1):
                    parts.append(f"--- Hunk {idx} ---")
                    if hunk.function_name:
                        parts.append(
                            f"FUNCTION/CLASS CONTEXT: {hunk.function_name} "
                            f"[line {hunk.new_start}]"
                        )
                    if hunk.context_before:
                        parts.append("CONTEXT (before):")
                        for ctx_line in hunk.context_before:
                            parts.append(f"  {ctx_line}")
                    if hunk.removed or hunk.added:
                        parts.append("DIFF:")
                        for lineno, text in hunk.removed:
                            parts.append(f"- L{lineno}: {text}")
                        for lineno, text in hunk.added:
                            parts.append(f"+ L{lineno}: {text}")
                    if hunk.context_after:
                        parts.append("CONTEXT (after):")
                        for ctx_line in hunk.context_after:
                            parts.append(f"  {ctx_line}")
                    parts.append("")
            else:
                # No hunks — include raw content
                parts.append(entry.get("content", ""))
            parts.append("")

        return "\n".join(parts)

    @staticmethod
    def _build_fix_message(code_content: str, issue_feedback: str, review_type: str) -> str:
        """Build the user-role message for a fix request."""
        return (
            f"You are an expert code fixer. Fix this specific issue in the code:\n\n"
            f"ISSUE TYPE: {review_type}\n"
            f"FEEDBACK: {issue_feedback}\n\n"
            f"CODE TO FIX:\n{code_content}\n\n"
            "Return ONLY the complete corrected code, no explanations or markdown."
        )

    @staticmethod
    def _build_recommendation_system_prompt(lang: str = "en") -> str:
        lang_instruction = (
            "Respond entirely in Japanese." if lang == "ja"
            else "Respond entirely in English."
        )
        return (
            "You are a code-review planning assistant. Choose a focused set of existing review types "
            "for the current project context before a full review runs. Return ONLY valid JSON using this schema:\n\n"
            "{\n"
            '  "recommended_review_types": ["<type>", "..."],\n'
            '  "recommended_preset": "<preset or null>",\n'
            '  "rationale": [\n'
            "    {\n"
            '      "review_type": "<type>",\n'
            '      "reason": "<short explanation grounded in the observed signals>"\n'
            "    }\n"
            "  ],\n"
            '  "project_signals": ["<signal>", "..."]\n'
            "}\n\n"
            "Rules:\n"
            "- Recommend 2 to 5 review types unless the context only justifies one.\n"
            "- Only use review types that appear in AVAILABLE REVIEW TYPES.\n"
            "- Prefer a preset only when its exact bundle fits the observed signals.\n"
            "- Ground each reason in the provided project signals, frameworks, manifests, changed files, or scope.\n"
            "- Avoid recommending every type. Focus on the highest-leverage bundle first.\n"
            f"- {lang_instruction}\n"
            "- Return JSON only. No markdown fences or commentary."
        )

    @staticmethod
    def _build_recommendation_user_message(recommendation_context: str) -> str:
        return (
            "Use the following observed repository context to recommend a focused review bundle.\n\n"
            f"{recommendation_context}\n\n"
            "Return JSON following the schema in your instructions."
        )

    @staticmethod
    def _build_interaction_user_message(
        issues: List[Any],
        lang: str = "en",
    ) -> str:
        """Build the user message for cross-issue interaction analysis.

        Each issue is summarised as a one-line entry with its index so the
        AI can reference findings by position.

        Args:
            issues: List of :class:`ReviewIssue` instances.
            lang:   Response language (``'en'`` or ``'ja'``).
        """
        lines: List[str] = []
        for idx, issue in enumerate(issues):
            fp = issue.file_path or "unknown"
            ln = issue.line_number or "n/a"
            lines.append(
                f"[{idx}] {fp}:{ln} ({issue.severity}) "
                f"{issue.issue_type}: {issue.description}"
            )

        lang_note = (
            "Respond in Japanese (日本語で回答してください)." if lang == "ja"
            else "Respond in English."
        )

        return (
            "Below are the code review findings from this session.  "
            "Analyse the interactions between them.\n\n"
            + "\n".join(lines)
            + f"\n\n{lang_note}"
        )
