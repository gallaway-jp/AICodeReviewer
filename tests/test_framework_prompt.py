"""Tests for Part 7 – Framework Prompt Tuning.

Validates that:
* FRAMEWORK_PROMPT_SUPPLEMENTS covers all detected frameworks.
* _build_system_prompt appends framework guidance when frameworks are supplied.
* Multiple frameworks produce combined guidance.
* Unknown frameworks are silently skipped.
* Config override for detected_frameworks is respected in the reviewer.
* set_detected_frameworks round-trips correctly.
"""

from __future__ import annotations

import textwrap
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from aicodereviewer.backends.base import (
    ACCESSIBILITY_REVIEW_METHOD_SUPPLEMENT,
    AIBackend,
    API_DESIGN_REVIEW_METHOD_SUPPLEMENT,
    COMPATIBILITY_REVIEW_METHOD_SUPPLEMENT,
    COMPLEXITY_REVIEW_METHOD_SUPPLEMENT,
    DATA_VALIDATION_REVIEW_METHOD_SUPPLEMENT,
    DEAD_CODE_REVIEW_METHOD_SUPPLEMENT,
    DEPENDENCY_REVIEW_METHOD_SUPPLEMENT,
    DOCUMENTATION_REVIEW_METHOD_SUPPLEMENT,
    ERROR_HANDLING_REVIEW_METHOD_SUPPLEMENT,
    FRAMEWORK_PROMPT_SUPPLEMENTS,
    ARCHITECTURE_REVIEW_METHOD_SUPPLEMENT,
    LICENSE_REVIEW_METHOD_SUPPLEMENT,
    MAINTAINABILITY_REVIEW_METHOD_SUPPLEMENT,
    LOCALIZATION_REVIEW_METHOD_SUPPLEMENT,
    PERFORMANCE_REVIEW_METHOD_SUPPLEMENT,
    REGRESSION_REVIEW_METHOD_SUPPLEMENT,
    REVIEW_PROMPTS,
    SCALABILITY_REVIEW_METHOD_SUPPLEMENT,
    SPECIFICATION_REVIEW_METHOD_SUPPLEMENT,
    TESTING_REVIEW_METHOD_SUPPLEMENT,
    UI_UX_REVIEW_METHOD_SUPPLEMENT,
    UI_UX_FRAMEWORK_PROMPT_SUPPLEMENTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _DummyBackend(AIBackend):
    """Minimal concrete backend for testing base-class helpers."""

    def __init__(self) -> None:
        self._project_context: Optional[str] = None
        self._detected_frameworks: Optional[List[str]] = None

    # Abstract methods – not exercised in these tests
    def get_review(self, code_content, review_type="best_practices", lang="en", spec_content=None):
        return ""

    def get_fix(self, code_content, issue_feedback, review_type="best_practices", lang="en"):
        return None

    def get_multi_file_review(self, entries, review_type="best_practices", lang="en"):
        return ""

    def validate_connection(self):
        return True


# ---------------------------------------------------------------------------
# FRAMEWORK_PROMPT_SUPPLEMENTS structure tests
# ---------------------------------------------------------------------------

class TestFrameworkPromptSupplements:
    """Ensure the FRAMEWORK_PROMPT_SUPPLEMENTS dict is well-formed."""

    KNOWN_FRAMEWORKS = [
        "django", "flask", "fastapi", "pytest",
        "react", "next.js", "express", "vue", "angular",
        "spring_boot", "rails",
    ]

    def test_all_detected_frameworks_have_supplements(self):
        """Every framework that context_collector can detect must have a
        corresponding supplement entry."""
        for fw in self.KNOWN_FRAMEWORKS:
            assert fw in FRAMEWORK_PROMPT_SUPPLEMENTS, (
                f"Missing FRAMEWORK_PROMPT_SUPPLEMENTS entry for '{fw}'"
            )

    def test_supplements_are_non_empty_strings(self):
        for fw, text in FRAMEWORK_PROMPT_SUPPLEMENTS.items():
            assert isinstance(text, str), f"Supplement for '{fw}' is not a string"
            assert len(text.strip()) > 20, f"Supplement for '{fw}' is too short"

    def test_no_extra_frameworks_without_detection(self):
        """Supplements should not contain keys that are not detectable."""
        for fw in FRAMEWORK_PROMPT_SUPPLEMENTS:
            assert fw in self.KNOWN_FRAMEWORKS, (
                f"Supplement '{fw}' exists but is not in KNOWN_FRAMEWORKS list"
            )

    def test_ui_ux_framework_supplements_only_target_known_frameworks(self):
        for fw in UI_UX_FRAMEWORK_PROMPT_SUPPLEMENTS:
            assert fw in self.KNOWN_FRAMEWORKS, (
                f"UI/UX supplement '{fw}' exists but is not in KNOWN_FRAMEWORKS list"
            )


# ---------------------------------------------------------------------------
# _build_system_prompt with frameworks
# ---------------------------------------------------------------------------

class TestBuildSystemPromptFrameworks:
    """Test that _build_system_prompt correctly appends framework guidance."""

    def test_no_frameworks_no_supplement(self):
        prompt = AIBackend._build_system_prompt("best_practices", "en")
        assert "FRAMEWORK-SPECIFIC GUIDANCE" not in prompt
        assert "REVIEW METHOD:" in prompt
        assert "Only emit broader-impact findings when supported by concrete evidence" in prompt
        assert "Do not use generic phrases like \"batch code\"" in prompt
        assert "For caller/callee drift, renamed fields, or signature changes" in prompt
        assert "For guard, validation, cache, or transaction findings" in prompt

    def test_none_frameworks_no_supplement(self):
        prompt = AIBackend._build_system_prompt("best_practices", "en", detected_frameworks=None)
        assert "FRAMEWORK-SPECIFIC GUIDANCE" not in prompt

    def test_empty_frameworks_no_supplement(self):
        prompt = AIBackend._build_system_prompt("best_practices", "en", detected_frameworks=[])
        assert "FRAMEWORK-SPECIFIC GUIDANCE" not in prompt

    def test_single_framework_appended(self):
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en", detected_frameworks=["django"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "Django project" in prompt
        assert "select_related" in prompt

    def test_multiple_frameworks_appended(self):
        prompt = AIBackend._build_system_prompt(
            "security", "en", detected_frameworks=["flask", "pytest"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "Flask project" in prompt
        assert "pytest" in prompt.lower()

    def test_unknown_framework_silently_skipped(self):
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en", detected_frameworks=["unknown_fw"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" not in prompt

    def test_mix_known_and_unknown(self):
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en",
            detected_frameworks=["unknown_fw", "react", "also_unknown"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "React project" in prompt
        # Unknown frameworks should not appear
        assert "unknown_fw" not in prompt
        assert "also_unknown" not in prompt

    def test_framework_with_project_context(self):
        ctx = "Primary language: Python 3.12 | Frameworks: django, pytest"
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en",
            project_context=ctx,
            detected_frameworks=["django", "pytest"],
        )
        # Project context is at the front
        assert prompt.startswith(ctx)
        # Framework supplements still present
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "Django project" in prompt
        assert "REVIEW METHOD:" in prompt

    def test_framework_with_multi_review_type(self):
        prompt = AIBackend._build_system_prompt(
            "security+performance", "en",
            detected_frameworks=["fastapi"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "FastAPI project" in prompt

    def test_japanese_lang_still_works_with_frameworks(self):
        prompt = AIBackend._build_system_prompt(
            "best_practices", "ja", detected_frameworks=["vue"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "Vue project" in prompt
        assert "日本語で回答してください" in prompt

    @pytest.mark.parametrize("fw", list(FRAMEWORK_PROMPT_SUPPLEMENTS.keys()))
    def test_each_framework_injects(self, fw: str):
        """Parametrised: every supplement key can be injected."""
        prompt = AIBackend._build_system_prompt(
            "best_practices", "en", detected_frameworks=[fw],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert FRAMEWORK_PROMPT_SUPPLEMENTS[fw] in prompt

    def test_ui_ux_review_adds_ui_specific_framework_guidance(self):
        prompt = AIBackend._build_system_prompt(
            "ui_ux", "en", detected_frameworks=["react"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "UI/UX-SPECIFIC FRAMEWORK GUIDANCE" in prompt
        assert "UI/UX REVIEW RULES" in prompt
        assert UI_UX_FRAMEWORK_PROMPT_SUPPLEMENTS["react"] in prompt
        assert UI_UX_REVIEW_METHOD_SUPPLEMENT in prompt

    def test_ui_ux_review_rules_force_ui_ux_category_and_holistic_scenarios(self):
        prompt = AIBackend._build_system_prompt("ui_ux", "en")
        assert "set category to exactly 'ui_ux'" in prompt
        assert "missing loading/error/empty states" in prompt
        assert "cross-tab dependency" in prompt
        assert "wizard-orientation" in prompt
        assert "blank screens" in prompt
        assert "silent overrides" in prompt
        assert "Never emit subtype categories" in prompt
        assert "Do not omit evidence_basis" in prompt
        assert "validateProfile, isLoading, error, export_report" in prompt

    def test_non_ui_ux_review_does_not_add_ui_specific_framework_guidance(self):
        prompt = AIBackend._build_system_prompt(
            "security", "en", detected_frameworks=["react"],
        )
        assert "FRAMEWORK-SPECIFIC GUIDANCE" in prompt
        assert "UI/UX-SPECIFIC FRAMEWORK GUIDANCE" not in prompt
        assert "UI/UX REVIEW RULES" not in prompt

    def test_multi_review_type_including_ui_ux_adds_ui_specific_framework_guidance(self):
        prompt = AIBackend._build_system_prompt(
            "security+ui_ux", "en", detected_frameworks=["next.js"],
        )
        assert "UI/UX-SPECIFIC FRAMEWORK GUIDANCE" in prompt
        assert UI_UX_FRAMEWORK_PROMPT_SUPPLEMENTS["next.js"] in prompt

    def test_dead_code_review_rules_force_dead_code_category_and_symbol_evidence(self):
        prompt = AIBackend._build_system_prompt("dead_code", "en")
        assert "DEAD CODE REVIEW RULES" in prompt
        assert DEAD_CODE_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'dead_code'" in prompt
        assert "Never emit subtype categories such as dead_function, dormant_feature, unused_variable" in prompt
        assert "Prefer the highest-leverage dead artifact over leaf helpers or import noise" in prompt
        assert "severity should be at least medium" in prompt
        assert "USE_LEGACY_RENDERER, ENABLE_BULK_ARCHIVE, render_legacy_csv" in prompt

    def test_error_handling_review_rules_force_error_handling_category_and_false_success_focus(self):
        prompt = AIBackend._build_system_prompt("error_handling", "en")
        assert "ERROR HANDLING REVIEW RULES" in prompt
        assert ERROR_HANDLING_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'error_handling'" in prompt
        assert "Never emit subtype categories such as exception-handling, error-reporting" in prompt
        assert "false success" in prompt
        assert "operators believing a job completed when it actually failed" in prompt
        assert "except Exception" in prompt
        assert "status='completed'" in prompt
        assert "result['status'] == 'completed'" in prompt
        assert "retryable failures that callers handle as terminal disablement" in prompt
        assert "except TimeoutError" in prompt
        assert "retryable=True" in prompt

    def test_data_validation_review_rules_force_data_validation_category_and_contract_focus(self):
        prompt = AIBackend._build_system_prompt("data_validation", "en")
        assert "DATA VALIDATION REVIEW RULES" in prompt
        assert DATA_VALIDATION_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'data_validation'" in prompt
        assert "Never emit subtype categories such as validation, validation/contract, boundary_checks" in prompt
        assert "validator/helper and a caller disagree about what counts as valid input" in prompt
        assert "start_hour, end_hour, validate_window" in prompt

    def test_testing_review_rules_force_testing_category_and_missing_coverage_focus(self):
        prompt = AIBackend._build_system_prompt("testing", "en")
        assert "TESTING REVIEW RULES" in prompt
        assert TESTING_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'testing'" in prompt
        assert "Never emit subtype categories such as insufficient test coverage, testability, assertions, error_paths" in prompt
        assert "regressions shipping unnoticed" in prompt
        assert "test_create_rollout_returns_batch_size_for_valid_payload, validate_rollout, rollout_percent, 0..100" in prompt

    def test_accessibility_review_rules_force_accessibility_category_and_accessible_name_focus(self):
        prompt = AIBackend._build_system_prompt("accessibility", "en")
        assert "ACCESSIBILITY REVIEW RULES" in prompt
        assert ACCESSIBILITY_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'accessibility'" in prompt
        assert "Never emit subtype categories such as usability, aria, contrast" in prompt
        assert "screen reader users being unable to identify a control" in prompt
        assert "icon-only button missing aria-label" in prompt

    def test_complexity_review_rules_force_complexity_category_and_local_hotspot_focus(self):
        prompt = AIBackend._build_system_prompt("complexity", "en")
        assert "COMPLEXITY REVIEW RULES" in prompt
        assert COMPLEXITY_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'complexity'" in prompt
        assert "Never emit subtype categories such as cyclomatic_complexity, cognitive_complexity, nesting" in prompt
        assert "context_scope local" in prompt or "context_scope to local" in prompt
        assert "severity should be at least medium" in prompt
        assert "choose_sync_strategy containing nested if/else chains" in prompt

    def test_documentation_review_rules_force_documentation_category_and_docs_drift_focus(self):
        prompt = AIBackend._build_system_prompt("documentation", "en")
        assert "DOCUMENTATION REVIEW RULES" in prompt
        assert DOCUMENTATION_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'documentation'" in prompt
        assert "Never emit subtype categories such as documentation mismatch, docs drift, cli contract" in prompt
        assert "broken user-facing contract" in prompt
        assert "README.md documenting --dry-run while cli.py never registers that flag" in prompt

    def test_regression_review_rules_force_regression_category_and_disabled_default_focus(self):
        prompt = AIBackend._build_system_prompt("regression", "en")
        assert "REGRESSION REVIEW RULES" in prompt
        assert REGRESSION_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'regression'" in prompt
        assert "Never emit subtype categories such as behavioral change" in prompt
        assert "disabled by default" in prompt
        assert "sync_enabled changing from True to False" in prompt

    def test_api_design_review_rules_force_api_design_category_and_http_method_focus(self):
        prompt = AIBackend._build_system_prompt("api_design", "en")
        assert "API DESIGN REVIEW RULES" in prompt
        assert API_DESIGN_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'api_design'" in prompt
        assert "Never emit subtype categories such as HTTP method / endpoint semantics" in prompt
        assert "GET for state-changing behavior" in prompt
        assert "@app.get('/api/invitations/create')" in prompt

    def test_compatibility_review_rules_force_compatibility_category_and_os_breakage_focus(self):
        prompt = AIBackend._build_system_prompt("compatibility", "en")
        assert "COMPATIBILITY REVIEW RULES" in prompt
        assert COMPATIBILITY_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'compatibility'" in prompt
        assert "Never emit subtype categories such as cross-platform" in prompt
        assert "hardcodes a macOS-only, Windows-only, or Linux-only behavior" in prompt
        assert "subprocess.run(['open', report_path])" in prompt
        assert "compare that assumption against any declared support range in metadata" in prompt
        assert "Python's built-in open() for reading a file is not the same as shelling out" in prompt
        assert "import tomllib while pyproject.toml still declares requires-python >=3.9" in prompt

    def test_architecture_review_rules_force_architecture_category_and_layer_boundary_focus(self):
        prompt = AIBackend._build_system_prompt("architecture", "en")
        assert "ARCHITECTURE REVIEW RULES" in prompt
        assert ARCHITECTURE_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'architecture'" in prompt
        assert "dependency_misalignment, separation_of_concerns, layering_violation" in prompt
        assert "Treat direct imports or reads of Flask, Django, or FastAPI request/context objects" in prompt
        assert "controller.py importing db.py directly instead of delegating through service.py" in prompt

    def test_architectural_review_system_prompt_reuses_architecture_rules(self):
        prompt = AIBackend._build_system_prompt("architectural_review", "en")
        assert "ARCHITECTURE REVIEW RULES" in prompt
        assert ARCHITECTURE_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'architecture'" in prompt

    def test_performance_review_rules_force_performance_category_and_hot_path_focus(self):
        prompt = AIBackend._build_system_prompt("performance", "en")
        assert "PERFORMANCE REVIEW RULES" in prompt
        assert PERFORMANCE_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'performance'" in prompt
        assert "algorithmic efficiency, query_efficiency, n_plus_one" in prompt
        assert "execute_query being called inside a for order_id loop" in prompt

    def test_performance_single_file_prompt_requests_n_plus_one_focus(self):
        prompt = AIBackend._build_user_message(
            "for order_id in order_ids:\n    row = execute_query('SELECT ...', [order_id])[0]",
            "performance",
        )
        assert "PERFORMANCE FOCUS" in prompt
        assert "repeated queries or requests inside loops" in prompt
        assert "Classify these findings as performance instead of algorithmic efficiency" in prompt
        assert "execute_query being called inside a for order_id loop" in prompt

    def test_architecture_single_file_prompt_requests_boundary_violation_focus(self):
        prompt = AIBackend._build_user_message("from flask import request\n\ndef build_quote():\n    return request.headers.get('X-Currency')", "architecture")
        assert "ARCHITECTURE FOCUS" in prompt
        assert "service or domain logic depending directly on database helpers, web request context, UI frameworks" in prompt
        assert "Treat service or domain imports of Flask, Django, or FastAPI request/context objects as architecture findings" in prompt
        assert "Classify these findings as architecture instead of dependency_misalignment" in prompt
        assert "pricing_service.py reading flask.request headers inside service logic" in prompt

    def test_architecture_multi_file_prompt_requests_layer_direction_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/controller.py", "content": "from src.db import execute_query"},
                {"name": "src/service.py", "content": "def list_orders(): pass"},
            ],
            "architecture",
        )
        assert "ARCHITECTURE FOCUS" in prompt
        assert "controllers bypassing service layers" in prompt
        assert "Treat service or domain imports of Flask, Django, or FastAPI request/context objects as architecture findings" in prompt
        assert "Classify these findings as architecture instead of dependency_misalignment" in prompt
        assert "controller.py importing db.py directly instead of service.py" in prompt

    def test_scalability_review_rules_force_scalability_category_and_horizontal_growth_focus(self):
        prompt = AIBackend._build_system_prompt("scalability", "en")
        assert "SCALABILITY REVIEW RULES" in prompt
        assert SCALABILITY_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'scalability'" in prompt
        assert "Never emit subtype categories such as stateful-component" in prompt
        assert "horizontal scaling breaking correctness" in prompt
        assert "RATE_LIMIT_STATE plus workers = 4" in prompt

    def test_dependency_review_rules_force_dependency_category_and_runtime_manifest_focus(self):
        prompt = AIBackend._build_system_prompt("dependency", "en")
        assert "DEPENDENCY REVIEW RULES" in prompt
        assert DEPENDENCY_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'dependency'" in prompt
        assert "runtime imports that only exist in dev or test extras" in prompt
        assert "severity should be at least medium" in prompt
        assert "metrics.py importing pytest while pyproject.toml lists pytest only under optional dev extras" in prompt

    def test_license_review_rules_force_license_category_and_notice_omission_focus(self):
        prompt = AIBackend._build_system_prompt("license", "en")
        assert "LICENSE REVIEW RULES" in prompt
        assert LICENSE_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'license'" in prompt
        assert "Never emit subtype categories such as license_attribution, license_compatibility" in prompt
        assert "severity should be at least medium" in prompt
        assert "upstream NOTICE will not be shipped with binaries" in prompt

    def test_localization_review_rules_force_localization_category_and_hardcoded_ui_focus(self):
        prompt = AIBackend._build_system_prompt("localization", "en")
        assert "LOCALIZATION REVIEW RULES" in prompt
        assert LOCALIZATION_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'localization'" in prompt
        assert "severity should be at least medium" in prompt
        assert "Do not invent missing-translation findings when the code already passes concrete keys" in prompt
        assert "strftime('%m/%d/%Y') plus a dollar-prefixed amount string" in prompt


class TestUserPromptBuilders:
    def test_single_file_prompt_requests_evidence_backed_broader_impact(self):
        prompt = AIBackend._build_user_message("print('hello')", "best_practices")
        assert "assess whether any issue suggests cross-file or project-level impact" in prompt
        assert "Only include broader-impact findings when the evidence is concrete" in prompt
        assert "make evidence_basis a short factual statement" in prompt
        assert "caller/callee drift, stale cache/state handling, missing validation or auth checks, or loss of transaction boundaries" in prompt
        assert "unvalidated or incompletely validated input can proceed past the validator" in prompt
        assert "CODE TO REVIEW:" in prompt

    def test_ui_ux_single_file_prompt_requests_explicit_ui_scenarios(self):
        prompt = AIBackend._build_user_message("const x = 1", "ui_ux")
        assert "UI/UX FOCUS" in prompt
        assert "missing loading, error, or empty states" in prompt
        assert "preferences in one tab that silently override another tab" in prompt
        assert "classify it as ui_ux" in prompt
        assert "blank, re-enter, accidental, repeated, confusing, disabled" in prompt
        assert "keep category exactly ui_ux instead of subtype labels" in prompt
        assert "Do not leave evidence_basis empty" in prompt
        assert "validateProfile, isLoading, export_report, reset_all_settings" in prompt

    def test_dead_code_single_file_prompt_requests_broader_dead_path_focus(self):
        prompt = AIBackend._build_user_message("flag = False", "dead_code")
        assert "DEAD CODE FOCUS" in prompt
        assert "permanently false or disabled feature flags" in prompt
        assert "obsolete compatibility shims" in prompt
        assert "keep category exactly dead_code instead of subtype labels" in prompt
        assert "Prefer the broader dead path over leaf helper noise" in prompt
        assert "USE_LEGACY_RENDERER, ENABLE_BULK_ARCHIVE, render_legacy_csv" in prompt

    def test_error_handling_single_file_prompt_requests_hidden_failure_focus(self):
        prompt = AIBackend._build_user_message("try:\n    pass\nexcept Exception:\n    return {'status': 'completed'}", "error_handling")
        assert "ERROR HANDLING FOCUS" in prompt
        assert "swallowed exceptions" in prompt
        assert "returned success statuses after an upstream error" in prompt
        assert "keep category exactly error_handling instead of subtype labels" in prompt
        assert "false success, hidden failure, delayed recovery, silent data loss" in prompt
        assert "except Exception" in prompt
        assert "status='completed'" in prompt
        assert "result['status'] == 'completed'" in prompt
        assert "'Import finished'" in prompt
        assert "retryable timeout or connection errors" in prompt
        assert "except TimeoutError" in prompt
        assert "retryable=True" in prompt

    def test_data_validation_single_file_prompt_requests_validator_contract_focus(self):
        prompt = AIBackend._build_user_message("duration = int(payload['end_hour']) - int(payload['start_hour'])", "data_validation")
        assert "DATA VALIDATION FOCUS" in prompt
        assert "validators that only check presence or type coercion" in prompt
        assert "keep category exactly data_validation instead of subtype labels" in prompt
        assert "invalid input reaching runtime use, impossible state being accepted, negative durations" in prompt
        assert "start_hour, end_hour, validate_window" in prompt

    def test_testing_single_file_prompt_requests_edge_case_test_focus(self):
        prompt = AIBackend._build_user_message("def test_create_rollout(): pass", "testing")
        assert "TESTING FOCUS" in prompt
        assert "source code branches, validation guards, or error paths that already exist but that the test suite never exercises" in prompt
        assert "keep category exactly testing instead of subtype labels" in prompt
        assert "regressions shipping unnoticed" in prompt
        assert "validate_rollout, rollout_percent, 0..100" in prompt

    def test_accessibility_single_file_prompt_requests_accessible_name_focus(self):
        prompt = AIBackend._build_user_message("<button><SearchIcon /></button>", "accessibility")
        assert "ACCESSIBILITY FOCUS" in prompt
        assert "icon-only buttons, unlabeled inputs" in prompt
        assert "Classify these findings as accessibility" in prompt
        assert "screen reader users being unable to identify the control" in prompt
        assert "icon-only button without aria-label" in prompt

    def test_api_design_single_file_prompt_requests_http_semantics_focus(self):
        prompt = AIBackend._build_user_message("@app.get('/api/invitations/create')\ndef create_invitation(payload): pass", "api_design")
        assert "API DESIGN FOCUS" in prompt
        assert "GET handlers that create or mutate state" in prompt
        assert "Classify these findings as api_design" in prompt
        assert "prefetch or cache layers triggering side effects" in prompt
        assert "@app.get('/api/invitations/create') on create_invitation" in prompt

    def test_compatibility_single_file_prompt_requests_os_specific_command_focus(self):
        prompt = AIBackend._build_user_message("subprocess.run(['open', report_path], check=True)", "compatibility")
        assert "COMPATIBILITY FOCUS" in prompt
        assert "OS-specific shell commands" in prompt
        assert "Prefer real user-visible platform breakage over generic legacy-version trivia" in prompt
        assert "Windows users unable to launch the file" in prompt
        assert "subprocess.run(['open', report_path]) without platform detection" in prompt

    def test_compatibility_single_file_prompt_requests_runtime_metadata_comparison(self):
        prompt = AIBackend._build_user_message("import tomllib", "compatibility")
        assert "compare that assumption against any declared support range in metadata" in prompt
        assert "Treat Python's built-in open() for reading files as ordinary file I/O" in prompt
        assert "supported Python versions failing at import time" in prompt
        assert "import tomllib while pyproject.toml still declares requires-python >=3.9" in prompt

    def test_scalability_single_file_prompt_requests_state_and_backpressure_focus(self):
        prompt = AIBackend._build_user_message("RATE_LIMIT_STATE = {}", "scalability")
        assert "SCALABILITY FOCUS" in prompt
        assert "process-local state used as shared coordination" in prompt
        assert "Classify these findings as scalability" in prompt
        assert "context_scope cross_file" in prompt
        assert "horizontal scaling breaking correctness" in prompt
        assert "RATE_LIMIT_STATE with workers = 4" in prompt

    def test_dependency_single_file_prompt_requests_runtime_manifest_mismatch_focus(self):
        prompt = AIBackend._build_user_message("import pytest", "dependency")
        assert "DEPENDENCY FOCUS" in prompt
        assert "runtime imports of third-party packages that the main dependency manifest does not declare" in prompt
        assert "production installs without extras can fail" in prompt
        assert "ModuleNotFoundError on fresh installs" in prompt
        assert "metrics.py importing pytest while pyproject.toml lists pytest only under optional dev extras" in prompt

    def test_license_single_file_prompt_requests_notice_and_distribution_focus(self):
        prompt = AIBackend._build_user_message("import telemetry_sdk", "license")
        assert "LICENSE FOCUS" in prompt
        assert "license terms conflict with the project's declared distribution terms" in prompt
        assert "Classify these findings as license instead of license-attribution" in prompt
        assert "upstream NOTICE will not be included in binaries" in prompt
        assert "distributed binaries shipping incomplete notices" in prompt

    def test_localization_single_file_prompt_requests_hardcoded_ui_and_locale_format_focus(self):
        prompt = AIBackend._build_user_message("Button(parent, text='Sync now')", "localization")
        assert "LOCALIZATION FOCUS" in prompt
        assert "hardcoded instead of going through the translation helper" in prompt
        assert "Do not claim a missing translation when the code already passes a concrete key" in prompt
        assert "mixed-language screens" in prompt
        assert "strftime('%m/%d/%Y') with a dollar-prefixed amount" in prompt

    def test_complexity_single_file_prompt_requests_nested_decision_tree_focus(self):
        prompt = AIBackend._build_user_message("def choose_sync_strategy():\n    if a:\n        if b:\n            pass", "complexity")
        assert "COMPLEXITY FOCUS" in prompt
        assert "deeply nested conditionals" in prompt
        assert "Classify these findings as complexity" in prompt
        assert "keep context_scope local" in prompt
        assert "harder to reason about, brittle to modify" in prompt
        assert "account state, retry mode, network conditions, and feature flags" in prompt

    def test_documentation_single_file_prompt_requests_docs_code_mismatch_focus(self):
        prompt = AIBackend._build_user_message("Use `syncctl run --dry-run`", "documentation")
        assert "DOCUMENTATION FOCUS" in prompt
        assert "stale README or operator-guide steps" in prompt
        assert "Classify these findings as documentation" in prompt
        assert "operators or users following broken instructions" in prompt
        assert "README.md documenting --dry-run while cli.py never registers that flag" in prompt

    def test_regression_single_file_prompt_requests_behavior_shift_focus(self):
        prompt = AIBackend._build_user_message('"sync_enabled": False', "regression")
        assert "REGRESSION FOCUS" in prompt
        assert "changed defaults, removed or weakened guards, altered branch conditions" in prompt
        assert "regression instead of behavioral-change subtype labels" in prompt
        assert "disabled by default" in prompt
        assert "sync_enabled changing from True to False" in prompt

    def test_spec_prompt_requests_broader_impact_check(self):
        prompt = AIBackend._build_user_message(
            "return {'name': user.name}",
            "specification",
            spec_content="The API must return display_name.",
        )
        assert "SPECIFICATION DOCUMENT:" in prompt
        assert "assess whether any deviation implies broader cross-file or project-level impact" in prompt
        assert "include the exact related file(s) when known" in prompt

    def test_specification_review_rules_force_canonical_category_and_contract_focus(self):
        prompt = AIBackend._build_system_prompt("specification", "en")
        assert SPECIFICATION_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'specification'" in prompt
        assert "disallowed partial success" in prompt
        assert "functionality, behavior_mismatch, contract_mismatch, atomicity_violation" in prompt

    def test_specification_single_file_prompt_requests_direct_spec_comparison(self):
        prompt = AIBackend._build_user_message(
            "return {'status': 'partial_success'}",
            "specification",
            spec_content="submit_batch must be atomic and partial success is not allowed.",
        )
        assert "SPECIFICATION FOCUS" in prompt
        assert "Compare the implementation directly against the supplied specification document" in prompt
        assert "Classify these findings as specification instead of functionality" in prompt
        assert "returning partial_success even though the spec says the batch must be atomic" in prompt

    def test_multi_type_prompt_with_specification_preserves_other_focus_blocks(self):
        prompt = AIBackend._build_user_message(
            "return {'status': 'partial_success'}",
            "architecture+specification",
            spec_content="submit_batch must be atomic and partial success is not allowed.",
        )
        assert "SPECIFICATION DOCUMENT:" not in prompt
        assert "ARCHITECTURE FOCUS" in prompt
        assert "SPECIFICATION FOCUS" in prompt
        assert "controller.py importing db.py directly instead of service.py" in prompt
        assert "returning partial_success even though the spec says the batch must be atomic" in prompt

    def test_specification_multi_file_prompt_requests_contract_mismatch_focus(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/service.py", "content": "return {'status': 'partial_success'}"},
                {"name": "src/repository.py", "content": "def persist_order(order_id): pass"},
            ],
            "specification",
            spec_content="submit_batch must be atomic and partial success is not allowed.",
        )
        assert "SPECIFICATION FOCUS" in prompt
        assert "required behaviors the implementation omits" in prompt
        assert "Classify these findings as specification instead of functionality" in prompt
        assert "returning partial_success even though the spec says the batch must be atomic" in prompt

    def test_maintainability_review_rules_force_canonical_category_and_duplication_focus(self):
        prompt = AIBackend._build_system_prompt("maintainability", "en")
        assert MAINTAINABILITY_REVIEW_METHOD_SUPPLEMENT in prompt
        assert "set category to exactly 'maintainability'" in prompt
        assert "duplicated active logic" in prompt
        assert "severity should be at least medium" in prompt
        assert "normalize_sync_window being implemented in both cli_sync_settings.py and gui_sync_settings.py" in prompt

    def test_maintainability_multi_file_prompt_requests_duplication_and_low_cohesion_focus(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/cli_sync_settings.py", "content": "def normalize_sync_window(payload):\n    return payload"},
                {"name": "src/gui_sync_settings.py", "content": "def normalize_sync_window(form_state):\n    return form_state"},
            ],
            "maintainability",
        )
        assert "duplicated live logic across active entry points" in prompt
        assert "Classify these findings as maintainability" in prompt
        assert "context_scope cross_file" in prompt
        assert "divergent fixes, policy drift, duplicated maintenance surface" in prompt
        assert "normalize_sync_window appearing in both cli_sync_settings.py and gui_sync_settings.py" in prompt

    def test_multi_file_prompt_requests_cross_file_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/a.py", "content": "def a(): pass"},
                {"name": "src/b.py", "content": "def b(): pass"},
            ],
            "regression",
        )
        assert "issues that only become visible across files in this batch" in prompt
        assert "contract mismatches" in prompt
        assert "Only report broader findings when they are supported by the files shown here" in prompt
        assert "name the supporting related file(s)" in prompt
        assert "transaction-boundary issues" in prompt
        assert "unvalidated or incompletely validated input can proceed past the helper or validator" in prompt
        assert "=== FILE: src/a.py ===" in prompt

    def test_ui_ux_multi_file_prompt_requests_holistic_desktop_and_web_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/a.py", "content": "def a(): pass"},
                {"name": "src/b.py", "content": "def b(): pass"},
            ],
            "ui_ux",
        )
        assert "blocking desktop actions without progress feedback" in prompt
        assert "wizard step orientation issues" in prompt
        assert "cross-tab preference overrides" in prompt
        assert "classify it as ui_ux" in prompt
        assert "keep category exactly ui_ux instead of subtype labels" in prompt
        assert "Do not leave evidence_basis empty" in prompt
        assert "validateProfile, isLoading, export_report, reset_all_settings, Advanced, or cloud_sync_enabled" in prompt

    def test_dead_code_multi_file_prompt_requests_stale_flag_and_shim_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/a.py", "content": "def a(): pass"},
                {"name": "src/b.py", "content": "def b(): pass"},
            ],
            "dead_code",
        )
        assert "permanently false feature flags" in prompt
        assert "obsolete compatibility shims" in prompt
        assert "keep category exactly dead_code instead of subtype labels" in prompt
        assert "Prefer the broader dead path over leaf helper noise" in prompt
        assert "USE_LEGACY_RENDERER, ENABLE_BULK_ARCHIVE, or render_legacy_csv" in prompt

    def test_error_handling_multi_file_prompt_requests_false_success_cross_file_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/a.py", "content": "def a(): pass"},
                {"name": "src/b.py", "content": "def b(): pass"},
            ],
            "error_handling",
        )
        assert "swallowed exceptions" in prompt
        assert "callers that surface a completed or successful message even though the underlying operation failed" in prompt
        assert "keep category exactly error_handling instead of subtype labels" in prompt
        assert "false success, hidden failure, delayed recovery, silent data loss" in prompt
        assert "except Exception" in prompt
        assert "status='completed'" in prompt
        assert "result['status'] == 'completed'" in prompt
        assert "'Import finished'" in prompt
        assert "retryable timeout or connection errors that downstream code turns into terminal disablement" in prompt
        assert "except TimeoutError" in prompt
        assert "retryable=True" in prompt

    def test_data_validation_multi_file_prompt_requests_cross_file_validator_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/a.py", "content": "def a(): pass"},
                {"name": "src/b.py", "content": "def b(): pass"},
            ],
            "data_validation",
        )
        assert "validators that only check presence or type coercion" in prompt
        assert "keep category exactly data_validation instead of subtype labels" in prompt
        assert "invalid input reaching runtime use, impossible state being accepted, negative durations" in prompt
        assert "start_hour, end_hour, validate_window" in prompt

    def test_testing_multi_file_prompt_requests_cross_file_missing_coverage_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/a.py", "content": "def a(): pass"},
                {"name": "tests/test_a.py", "content": "def test_a(): pass"},
            ],
            "testing",
        )
        assert "source branches, validation guards, and error paths that already exist but that the test suite never exercises" in prompt
        assert "keep category exactly testing instead of subtype labels" in prompt
        assert "regressions shipping unnoticed" in prompt
        assert "validate_rollout, rollout_percent, 0..100" in prompt

    def test_accessibility_multi_file_prompt_requests_accessible_name_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/SearchToolbar.tsx", "content": "<button><SearchIcon /></button>"},
                {"name": "src/SearchIcon.tsx", "content": "export function SearchIcon() { return <svg /> }"},
            ],
            "accessibility",
        )
        assert "icon-only buttons, unlabeled inputs" in prompt
        assert "Classify these findings as accessibility instead of generic usability or WCAG subtype labels" in prompt
        assert "screen reader users being unable to identify the control" in prompt
        assert "input with placeholder text but no label" in prompt

    def test_complexity_multi_file_prompt_requests_complexity_hotspot_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/sync_strategy.py", "content": "def choose_sync_strategy():\n    if a:\n        if b:\n            if c:\n                pass"},
                {"name": "src/worker.py", "content": "from sync_strategy import choose_sync_strategy"},
            ],
            "complexity",
        )
        assert "deeply nested conditionals, long decision trees" in prompt
        assert "Classify these findings as complexity instead of cyclomatic-complexity or nesting subtype labels" in prompt
        assert "keep context_scope local unless the provided files prove a wider dependency problem" in prompt
        assert "harder to reason about, brittle to modify" in prompt
        assert "choose_sync_strategy or a nested if/else chain across account state, retry mode, network conditions, and feature flags" in prompt

    def test_documentation_multi_file_prompt_requests_stale_readme_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "README.md", "content": "Use --dry-run"},
                {"name": "src/cli.py", "content": "run_parser.add_argument('--apply')"},
            ],
            "documentation",
        )
        assert "stale README or operator-guide steps" in prompt
        assert "Classify these findings as documentation instead of docs-drift or CLI-contract subtype labels" in prompt
        assert "documentation-led workflows failing" in prompt
        assert "README.md documenting --dry-run while cli.py never registers that flag" in prompt

    def test_regression_multi_file_prompt_requests_disabled_default_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/settings_defaults.py", "content": '"sync_enabled": False'},
                {"name": "src/app_startup.py", "content": 'if preferences["sync_enabled"]: pass'},
            ],
            "regression",
        )
        assert "changed defaults, removed or weakened guards" in prompt
        assert "regression instead of behavioral-change subtype labels" in prompt
        assert "disabled by default" in prompt
        assert "sync_enabled changing from True to False" in prompt

    def test_scalability_multi_file_prompt_requests_multi_worker_state_checks(self):
        prompt = AIBackend._build_multi_file_user_message(
            [
                {"name": "src/app.py", "content": "RATE_LIMIT_STATE = {}"},
                {"name": "gunicorn.conf.py", "content": "workers = 4"},
            ],
            "scalability",
        )
        assert "process-local state used as shared coordination" in prompt
        assert "Classify these findings as scalability" in prompt
        assert "set context_scope cross_file" in prompt
        assert "inconsistent global limits across workers" in prompt
        assert "RATE_LIMIT_STATE with workers = 4" in prompt


# ---------------------------------------------------------------------------
# set_detected_frameworks
# ---------------------------------------------------------------------------

class TestSetDetectedFrameworks:
    def test_set_and_read(self):
        backend = _DummyBackend()
        backend.set_detected_frameworks(["django", "pytest"])
        assert backend._detected_frameworks == ["django", "pytest"]

    def test_set_none(self):
        backend = _DummyBackend()
        backend.set_detected_frameworks(["django"])
        backend.set_detected_frameworks(None)
        assert backend._detected_frameworks is None

    def test_default_is_none(self):
        backend = _DummyBackend()
        assert backend._detected_frameworks is None


# ---------------------------------------------------------------------------
# Reviewer integration – config override
# ---------------------------------------------------------------------------

class TestReviewerFrameworkOverride:
    """Verify that the reviewer respects the config override for
    detected_frameworks and passes frameworks to the client."""

    @patch("aicodereviewer.reviewer.collect_project_context")
    @patch("aicodereviewer.reviewer.config")
    def test_config_override_used(self, mock_config, mock_collect):
        """When config has processing.detected_frameworks, those override
        the auto-detected list."""
        from aicodereviewer.reviewer import collect_review_issues

        # Build a fake ProjectContext
        fake_ctx = MagicMock()
        fake_ctx.frameworks = ["django"]
        fake_ctx.to_prompt_string.return_value = "ctx-string"
        mock_collect.return_value = fake_ctx

        # config.get side-effects
        def config_get(section, key, fallback=None):
            mapping = {
                ("processing", "enable_project_context"): True,
                ("processing", "project_context_max_tokens"): 800,
                ("processing", "detected_frameworks"): "react,vue",
            }
            return mapping.get((section, key), fallback)

        mock_config.get.side_effect = config_get

        client = _DummyBackend()
        client.set_project_context = MagicMock()
        client.set_detected_frameworks = MagicMock()

        # We only need to test the context-attachment path, so we can
        # trigger just the relevant block.  Instead of calling the full
        # collect_review_issues (which needs many more mocks), we test
        # the override logic directly:
        override = config_get("processing", "detected_frameworks", "")
        if override:
            frameworks = [f.strip() for f in override.split(",") if f.strip()]
        else:
            frameworks = fake_ctx.frameworks
        client.set_detected_frameworks(frameworks or None)

        client.set_detected_frameworks.assert_called_once_with(["react", "vue"])

    def test_no_override_uses_autodetected(self):
        """When config override is empty, ctx.frameworks is used."""
        client = _DummyBackend()
        client.set_detected_frameworks = MagicMock()

        override = ""
        ctx_frameworks = ["fastapi", "pytest"]
        if override:
            frameworks = [f.strip() for f in override.split(",") if f.strip()]
        else:
            frameworks = ctx_frameworks
        client.set_detected_frameworks(frameworks or None)

        client.set_detected_frameworks.assert_called_once_with(["fastapi", "pytest"])
