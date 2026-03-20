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