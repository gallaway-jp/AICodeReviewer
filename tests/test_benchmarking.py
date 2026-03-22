"""Tests for holistic benchmark fixture discovery and evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from aicodereviewer import benchmarking


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "holistic_review" / "fixtures"


def test_discover_fixtures_returns_expected_catalog():
    fixtures = benchmarking.discover_fixtures(FIXTURES_ROOT)

    ids = {fixture.id for fixture in fixtures}

    assert len(fixtures) == 8
    assert ids == {
        "architectural-layer-leak",
        "auth-guard-regression",
        "cache-invalidation-gap",
        "diff-signature-break",
        "field-rename-contract",
        "partial-refactor-callers",
        "transaction-split",
        "validation-drift",
    }


def test_evaluate_fixture_matches_tool_mode_envelope(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "completed",
                "report": {
                    "issues_found": [
                        {
                            "issue_id": "issue-0001",
                            "file_path": "src/handlers.py",
                            "issue_type": "best_practices",
                            "severity": "high",
                            "description": "Handler still reads display_name after serializer renamed the field to full_name.",
                            "ai_feedback": "This is a cross-file contract mismatch between serializers.py and handlers.py.",
                            "context_scope": "cross_file",
                            "related_files": ["src/serializers.py"],
                            "systemic_impact": "Breaks callers expecting display_name in downstream payloads.",
                            "evidence_basis": "Serializer now emits full_name while handler still accesses display_name.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.score == 1.0
    assert result.matched_expectations == 1


def test_evaluate_fixture_directory_marks_missing_reports(tmp_path):
    fixtures = benchmarking.discover_fixtures(FIXTURES_ROOT)

    results = benchmarking.evaluate_fixture_directory(fixtures[:2], tmp_path)

    assert len(results) == 2
    assert all(result.passed is False for result in results)
    assert all(result.missing_report is True for result in results)


def test_evaluate_fixture_reports_failed_checks_for_best_candidate(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "auth-guard-regression" / "fixture.json"
    )
    report_path = tmp_path / "auth-guard-regression.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0007",
                        "file_path": "src/admin.py",
                        "issue_type": "dependency",
                        "severity": "high",
                        "description": "The admin endpoint bypasses the admin guard by skipping require_admin and accepts any authenticated user.",
                        "context_scope": "cross_file",
                        "related_files": ["src/auth.py"],
                        "systemic_impact": "Privilege checks are inconsistent across admin routes.",
                        "evidence_basis": "admin.py stopped calling require_admin before returning sensitive data.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is False
    expectation = result.expectation_results[0]
    assert expectation.best_candidate_issue_id == "issue-0007"
    assert expectation.best_candidate_file_path == "src/admin.py"
    assert expectation.failed_checks == ["issue_type"]


def test_evaluate_fixture_accepts_semantic_issue_type_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010",
                        "file_path": "src/handlers.py",
                        "issue_type": "contract_mismatch",
                        "severity": "high",
                        "description": "Handler still reads display_name after serializer renamed the field to full_name.",
                        "context_scope": "cross_file",
                        "related_files": ["src/serializers.py"],
                        "systemic_impact": "Breaks callers expecting display_name in downstream payloads.",
                        "evidence_basis": "Serializer now emits full_name while handler still accesses display_name.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010"


def test_evaluate_fixture_accepts_caching_issue_type_alias_for_performance(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0011",
                        "file_path": "src/profile_service.py",
                        "issue_type": "caching",
                        "severity": "medium",
                        "description": "Profile updates do not invalidate the reader cache.",
                        "context_scope": "cross_file",
                        "related_files": ["src/cache.py"],
                        "systemic_impact": "Stale user profile reads may continue after updates.",
                        "evidence_basis": "update_user_profile changes persisted state while get_user_profile reads user_profile data from PROFILE_CACHE.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0011"


def test_evaluate_fixture_accepts_user_profile_evidence_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap-evidence.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012",
                        "file_path": "src/cache.py",
                        "issue_type": "cache_invalidation",
                        "severity": "medium",
                        "description": "Profile updates do not invalidate the cache.",
                        "context_scope": "cross_file",
                        "related_files": ["src/profile_service.py"],
                        "systemic_impact": "Stale profile reads may continue after updates.",
                        "evidence_basis": "profile_service.py updates profiles while get_user_profile and set_user_profile continue serving cached profile data.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012"


def test_evaluate_fixture_accepts_invalidation_description_keyword_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012ca",
                        "file_path": "src/profile_service.py",
                        "issue_type": "caching",
                        "severity": "high",
                        "description": "Missing cache invalidation mechanism between the writer and cached reader.",
                        "context_scope": "cross_file",
                        "related_files": ["src/cache.py"],
                        "systemic_impact": "Stale user_profile data can reach callers.",
                        "evidence_basis": "update_user_profile writes state but cache.py keeps serving user_profile entries.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012ca"


def test_evaluate_fixture_accepts_issue_type_spacing_variants(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "diff-signature-break" / "fixture.json"
    )
    report_path = tmp_path / "diff-signature-break.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010b",
                        "file_path": "src/user_service.py",
                        "issue_type": "API Contract",
                        "severity": "high",
                        "description": "tenant_id was added but callers were not updated.",
                        "context_scope": "cross_file",
                        "related_files": ["src/controller.py"],
                        "systemic_impact": "Existing callers will fail at runtime.",
                        "evidence_basis": "fetch_user now requires tenant_id but controller.py still uses the old call shape.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010b"


def test_evaluate_fixture_accepts_issue_type_slash_variants(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "partial-refactor-callers" / "fixture.json"
    )
    report_path = tmp_path / "partial-refactor-callers.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010c",
                        "file_path": "src/service.py",
                        "issue_type": "interface/contract violation",
                        "severity": "high",
                        "description": "The caller still expects result while the service now returns value.",
                        "context_scope": "cross_file",
                        "related_files": ["src/client.py"],
                        "systemic_impact": "Callers will break at runtime.",
                        "evidence_basis": "service.py returns value while client.py still reads result.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010c"


def test_evaluate_fixture_accepts_caller_callee_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010d",
                        "file_path": "src/handlers.py",
                        "issue_type": "caller/callee mismatch",
                        "severity": "high",
                        "description": "The handler still expects display_name while the serializer returns full_name.",
                        "context_scope": "cross_file",
                        "related_files": ["src/serializers.py"],
                        "systemic_impact": "Callers will fail at runtime.",
                        "evidence_basis": "handlers.py reads display_name while serializers.py returns full_name.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010d"


def test_evaluate_fixture_accepts_integration_consistency_for_cache_performance(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010e",
                        "file_path": "src/cache.py",
                        "issue_type": "integration-consistency",
                        "severity": "high",
                        "description": "The cache layer is not invalidated when profile updates occur.",
                        "context_scope": "cross_file",
                        "related_files": ["src/profile_service.py", "src/cache.py"],
                        "systemic_impact": "Stale reads persist after profile updates.",
                        "evidence_basis": "update_user_profile never coordinates with set_user_profile for the same user_profile data.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010e"


def test_evaluate_fixture_accepts_api_signature_break_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "diff-signature-break" / "fixture.json"
    )
    report_path = tmp_path / "diff-signature-break.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0010f",
                        "file_path": "src/user_service.py",
                        "issue_type": "API/Signature Break",
                        "severity": "high",
                        "description": "tenant_id was added and existing callers still use the old signature.",
                        "context_scope": "cross_file",
                        "related_files": ["src/controller.py"],
                        "systemic_impact": "Call flows will fail at runtime.",
                        "evidence_basis": "controller.py still omits tenant_id when calling fetch_user.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0010f"


def test_evaluate_fixture_accepts_semantic_systemic_impact_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0011",
                        "file_path": "src/handlers.py",
                        "issue_type": "contract_mismatch",
                        "severity": "high",
                        "description": "Handler still reads display_name after serializer renamed the field to full_name.",
                        "context_scope": "cross_file",
                        "related_files": ["src/serializers.py"],
                        "systemic_impact": "Downstream payload consumers continue reading the old field name.",
                        "evidence_basis": "Serializer now emits full_name while handler still accesses display_name.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0011"


def test_evaluate_fixture_accepts_semantic_evidence_basis_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012",
                        "file_path": "src/controller.py",
                        "issue_type": "layer-leakage",
                        "severity": "medium",
                        "description": "Architecture violation in request flow.",
                        "context_scope": "project",
                        "related_files": ["src/service.py", "src/database.py"],
                        "systemic_impact": "Dependency direction between layers becomes inconsistent.",
                        "evidence_basis": "controller.py imports the database helper directly even though service.py already owns that access pattern.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012"


def test_evaluate_fixture_accepts_layering_violation_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012a",
                        "file_path": "src/controller.py",
                        "issue_type": "layering_violation",
                        "severity": "high",
                        "description": "Controller reaches into the database layer directly.",
                        "context_scope": "project",
                        "related_files": ["src/service.py", "src/db.py"],
                        "systemic_impact": "Layer boundaries are bypassed.",
                        "evidence_basis": "controller.py imports execute_query even though service.py owns that access.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012a"


def test_evaluate_fixture_accepts_layer_separation_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012aa",
                        "file_path": "src/controller.py",
                        "issue_type": "layer-separation",
                        "severity": "high",
                        "description": "The controller bypasses the service layer and reaches the database directly.",
                        "context_scope": "project",
                        "related_files": ["src/service.py", "src/db.py"],
                        "systemic_impact": "Layer boundaries are broken.",
                        "evidence_basis": "controller.py imports db.py directly instead of delegating through service.py.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012aa"


def test_evaluate_fixture_accepts_execute_query_as_db_evidence_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012b",
                        "file_path": "src/controller.py",
                        "issue_type": "architecture",
                        "severity": "high",
                        "description": "Controller bypasses the service layer and talks to the database directly.",
                        "context_scope": "project",
                        "related_files": ["src/service.py"],
                        "systemic_impact": "Layering boundaries are broken.",
                        "evidence_basis": "orders_page calls execute_query directly even though service.list_orders exists.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012b"


def test_evaluate_fixture_accepts_transactional_safety_pipe_delimited_issue_type(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "transaction-split" / "fixture.json"
    )
    report_path = tmp_path / "transaction-split.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012e",
                        "file_path": "src/service.py",
                        "issue_type": "encapsulation|transactional-safety",
                        "severity": "high",
                        "description": "The transaction wrapper is bypassed and partial writes are possible.",
                        "context_scope": "cross_file",
                        "related_files": ["src/repository.py"],
                        "systemic_impact": "Partial writes can escape the repository transaction boundary.",
                        "evidence_basis": "place_order bypasses save_order, which owns the begin/commit sequence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012e"


def test_evaluate_fixture_accepts_transaction_boundary_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "transaction-split" / "fixture.json"
    )
    report_path = tmp_path / "transaction-split.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012ea",
                        "file_path": "src/service.py",
                        "issue_type": "transaction_boundary",
                        "severity": "high",
                        "description": "The service bypasses the transaction wrapper and partial writes are possible.",
                        "context_scope": "cross_file",
                        "related_files": ["src/repository.py"],
                        "systemic_impact": "Partial writes can escape the repository transaction boundary.",
                        "evidence_basis": "place_order bypasses save_order and the begin/commit sequence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012ea"


def test_evaluate_fixture_accepts_api_mismatch_issue_type_variants(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "partial-refactor-callers" / "fixture.json"
    )
    report_path = tmp_path / "partial-refactor-callers.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012f",
                        "file_path": "src/client.py",
                        "issue_type": "API mismatch / runtime error",
                        "severity": "high",
                        "description": "The client still expects result while the service returns value.",
                        "context_scope": "cross_file",
                        "related_files": ["src/service.py"],
                        "systemic_impact": "Any downstream code expecting the old response key will fail.",
                        "evidence_basis": "service.py returns value while client.py still reads result.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012f"


def test_evaluate_fixture_accepts_downstream_code_as_callers_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "field-rename-contract" / "fixture.json"
    )
    report_path = tmp_path / "field-rename-contract.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0012g",
                        "file_path": "src/handlers.py",
                        "issue_type": "caller/callee mismatch",
                        "severity": "high",
                        "description": "The serializer and handler now disagree on the exported field name.",
                        "context_scope": "cross_file",
                        "related_files": ["src/serializers.py"],
                        "systemic_impact": "Any downstream code expecting display_name will fail at runtime.",
                        "evidence_basis": "serialize_user returns full_name while the handler still reads display_name.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0012g"


def test_evaluate_fixture_accepts_tool_mode_envelope_with_top_level_issues(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "diff-signature-break" / "fixture.json"
    )
    report_path = tmp_path / "diff-signature-break.json"
    report_path.write_text(
        json.dumps(
            {
                "command": "review",
                "status": "no_issues",
                "report": None,
                "issues": [],
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is False
    assert result.missing_report is False
    assert result.expectation_results[0].reason == "No issue matched the expected holistic finding"


def test_evaluate_fixture_accepts_multilingual_semantic_matches(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "architectural-layer-leak" / "fixture.json"
    )
    report_path = tmp_path / "architectural-layer-leak.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0013",
                        "file_path": "src/controller.py",
                        "issue_type": "layer-leak",
                        "severity": "high",
                        "description": "コントローラーがデータベース関数を直接呼び出している。",
                        "context_scope": "project",
                        "related_files": ["src/service.py"],
                        "systemic_impact": "レイヤー間の依存関係ルールが破られます。",
                        "evidence_basis": "controller.py が db.py を直接インポートしており、service.py を経由していません。",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0013"


def test_evaluate_fixture_accepts_expected_related_file_in_primary_file_path(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "cache-invalidation-gap" / "fixture.json"
    )
    report_path = tmp_path / "cache-invalidation-gap.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0014",
                        "file_path": "src/cache.py",
                        "issue_type": "cache_invalidation",
                        "severity": "high",
                        "description": "Cache entries are never invalidated after profile updates.",
                        "context_scope": "cross_file",
                        "related_files": ["src/profile_service.py"],
                        "systemic_impact": "Stale cache entries can be served after writes.",
                        "evidence_basis": "profile_service.update_user_profile changes stored data while cache.py only provides set/get helpers for user_profile.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0014"


def test_evaluate_fixture_accepts_unvalidated_semantic_aliases(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "validation-drift" / "fixture.json"
    )
    report_path = tmp_path / "validation-drift.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0015",
                        "file_path": "src/validation.py",
                        "issue_type": "input validation",
                        "severity": "high",
                        "description": "Validation no longer enforces email even though the API depends on it.",
                        "context_scope": "cross_file",
                        "related_files": ["src/api.py"],
                        "systemic_impact": "Malformed input can proceed into request handling and trigger runtime failures.",
                        "evidence_basis": "api.py reads payload['email'] while validation.py only validates username and password.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0015"


def test_evaluate_fixture_accepts_validation_runtime_error_issue_type_alias(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "validation-drift" / "fixture.json"
    )
    report_path = tmp_path / "validation-drift-2.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0016",
                        "file_path": "src/api.py",
                        "issue_type": "input validation / runtime error",
                        "severity": "high",
                        "description": "create_account depends on email that validation no longer enforces in validate_signup.",
                        "context_scope": "cross_file",
                        "related_files": ["src/validation.py"],
                        "systemic_impact": "Runtime crashes occur when requests proceed without email.",
                        "evidence_basis": "api.py indexes payload['email'] while validation.py does not require email.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0016"


def test_evaluate_fixture_accepts_validation_issue_type_alias_for_security(tmp_path):
    fixture = benchmarking.load_fixture(
        FIXTURES_ROOT / "validation-drift" / "fixture.json"
    )
    report_path = tmp_path / "validation-drift-3.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "issue_id": "issue-0017",
                        "file_path": "src/api.py",
                        "issue_type": "validation",
                        "severity": "high",
                        "description": "create_account consumes email even though validate_signup does not enforce it.",
                        "context_scope": "cross_file",
                        "related_files": ["src/validation.py"],
                        "systemic_impact": "Unvalidated input can proceed without email and trigger runtime failures.",
                        "evidence_basis": "api.py reads payload['email'] while validation.py does not validate it.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = benchmarking.evaluate_fixture_file(fixture, report_path)

    assert result.passed is True
    assert result.expectation_results[0].matched_issue_id == "issue-0017"


def test_cli_single_fixture_returns_success_for_matching_report(tmp_path, capsys):
    report_path = tmp_path / "single.json"
    report_path.write_text(
        json.dumps(
            {
                "issues_found": [
                    {
                        "file_path": "src/admin.py",
                        "issue_type": "security",
                        "severity": "high",
                        "description": "The admin endpoint bypasses the admin guard by skipping require_admin and accepts any authenticated user.",
                        "context_scope": "cross_file",
                        "related_files": ["src/auth.py"],
                        "systemic_impact": "Privilege checks are inconsistent across admin routes.",
                        "evidence_basis": "admin.py stopped calling require_admin before returning sensitive data.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = benchmarking.main(
        [
            "--fixtures-root",
            str(FIXTURES_ROOT),
            "--fixture",
            "auth-guard-regression",
            "--report-file",
            str(report_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["fixtures_passed"] == 1
    assert payload["results"][0]["fixture_id"] == "auth-guard-regression"