from __future__ import annotations

from pathlib import Path

from aicodereviewer.benchmarking import discover_fixtures
from tools import run_review_type_pairwise_interference as pairwise


FIXTURES_ROOT = Path("benchmarks/holistic_review/fixtures")


def test_valid_review_types_for_fixture_uses_invocation_spec_file():
    fixtures = discover_fixtures(FIXTURES_ROOT)
    fixture = next(item for item in fixtures if item.id == "architectural-layer-leak")

    valid = pairwise._valid_review_types_for_fixture(fixture)

    assert "specification" not in valid


def test_classify_pair_result_distinguishes_drift_from_failure():
    drift_result = {
        "matched_target": False,
        "exit_code": 0,
        "report_exists": True,
        "expectation_results": [{"best_candidate_issue_id": "issue-1", "best_candidate_file_path": None}],
    }
    failure_result = {
        "matched_target": False,
        "exit_code": 2,
        "report_exists": False,
        "expectation_results": [{"best_candidate_issue_id": None, "best_candidate_file_path": None}],
    }

    assert pairwise._classify_pair_result(drift_result) == "retained_with_drift"
    assert pairwise._classify_pair_result(failure_result) == "command_failure"


def test_recommended_bundle_candidates_prioritize_low_retention():
    summaries = [
        {
            "distractor_review_type": "accessibility",
            "strict_match_rate": 1.0,
            "effective_retention_rate": 1.0,
            "command_failure_count": 0,
        },
        {
            "distractor_review_type": "architecture",
            "strict_match_rate": 0.25,
            "effective_retention_rate": 0.5,
            "command_failure_count": 0,
        },
        {
            "distractor_review_type": "security",
            "strict_match_rate": 0.5,
            "effective_retention_rate": 0.5,
            "command_failure_count": 1,
        },
        {
            "distractor_review_type": "ui_ux",
            "strict_match_rate": 0.75,
            "effective_retention_rate": 0.75,
            "command_failure_count": 0,
        },
    ]

    assert pairwise._recommended_bundle_candidates(summaries) == [
        "architecture",
        "security",
        "ui_ux",
    ]