"""Measure pairwise review-type interference against representative holistic fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aicodereviewer.backends.base import REVIEW_TYPE_KEYS
from aicodereviewer.benchmarking import (
    BenchmarkFixture,
    describe_fixture_catalog_entry,
    describe_fixture_invocation,
    evaluate_fixture_file,
)
from tools import run_holistic_benchmarks as benchmark_runner
from tools import run_review_type_degradation_study as degradation_study
from tools.compare_review_reports import compare_reports


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a pairwise review-type interference study against representative holistic fixtures.",
    )
    parser.add_argument("--fixtures-root", default="benchmarks/holistic_review/fixtures")
    parser.add_argument("--output-dir", default="artifacts/review-type-pairwise-interference")
    parser.add_argument("--summary-out")
    parser.add_argument(
        "--backend",
        choices=["bedrock", "kiro", "copilot", "local"],
        default=None,
        help="Backend override; defaults to configured backend.",
    )
    parser.add_argument(
        "--lang",
        choices=["en", "ja", "default"],
        default="en",
        help="Language override for stable benchmark output; defaults to English.",
    )
    parser.add_argument("--programmer", default="benchmark-bot")
    parser.add_argument("--reviewer", default="benchmark-bot")
    parser.add_argument("--fixture", action="append", dest="fixtures", default=[])
    parser.add_argument(
        "--review-type",
        action="append",
        dest="review_types",
        default=[],
        help="Restrict the representative set to these target review types.",
    )
    parser.add_argument(
        "--distractor-type",
        action="append",
        dest="distractor_types",
        default=[],
        help="Restrict pairwise distractors to these review types.",
    )
    parser.add_argument(
        "--max-distractors",
        type=int,
        default=None,
        help="Cap the number of distractor review types tested per fixture after filtering.",
    )
    parser.add_argument("--skip-health-check", action="store_true")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--fixture-timeout-seconds", type=float)
    parser.add_argument("--model")
    parser.add_argument("--api-url")
    parser.add_argument("--api-type")
    parser.add_argument("--local-model")
    parser.add_argument("--copilot-model")
    parser.add_argument("--kiro-cli-command")
    local_web_search_group = parser.add_mutually_exclusive_group()
    local_web_search_group.add_argument(
        "--local-enable-web-search",
        dest="local_enable_web_search",
        action="store_true",
        default=None,
    )
    local_web_search_group.add_argument(
        "--local-disable-web-search",
        dest="local_enable_web_search",
        action="store_false",
    )
    return parser


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_matched_issue(result: dict[str, Any], report_path: Path) -> dict[str, Any] | None:
    if not report_path.exists():
        return None
    payload = _load_report(report_path)
    issues = payload.get("report", {}).get("issues_found") or payload.get("issues") or []
    issue_by_id = {
        issue.get("issue_id"): issue
        for issue in issues
        if isinstance(issue, dict) and issue.get("issue_id")
    }
    for expectation in result["expectation_results"]:
        matched_issue_id = expectation.get("matched_issue_id")
        if matched_issue_id and matched_issue_id in issue_by_id:
            return issue_by_id[matched_issue_id]
    return None


def _valid_review_types_for_fixture(fixture: BenchmarkFixture) -> list[str]:
    invocation = describe_fixture_invocation(fixture)
    has_spec_file = bool(invocation.get("spec_file"))
    valid_types: list[str] = []
    for review_type in REVIEW_TYPE_KEYS:
        if review_type == "specification" and not has_spec_file:
            continue
        valid_types.append(review_type)
    return valid_types


def _candidate_distractors(args: argparse.Namespace, fixture: BenchmarkFixture) -> list[str]:
    target_type = fixture.review_types[0]
    valid_types = [review_type for review_type in _valid_review_types_for_fixture(fixture) if review_type != target_type]
    if args.distractor_types:
        requested = [review_type for review_type in args.distractor_types if review_type in valid_types]
    else:
        requested = valid_types
    if args.max_distractors is not None:
        return requested[: max(0, args.max_distractors)]
    return requested


def _run_session(
    fixture: BenchmarkFixture,
    selected_types: list[str],
    output_path: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    invocation = dict(describe_fixture_invocation(fixture))
    invocation["review_types"] = list(selected_types)
    review_args = benchmark_runner._build_review_args(invocation, output_path, args)
    exit_code, payload = benchmark_runner._invoke_review_tool(review_args)
    evaluation = evaluate_fixture_file(fixture, output_path)
    return {
        "fixture_id": fixture.id,
        "fixture_title": fixture.title,
        "target_review_type": fixture.review_types[0],
        "selected_review_types": list(selected_types),
        "benchmark_metadata": dict(invocation.get("benchmark_metadata", {})),
        "exit_code": exit_code,
        "status": payload.get("status"),
        "score": evaluation.score,
        "passed": evaluation.passed,
        "matched_target": evaluation.passed and evaluation.matched_expectations == evaluation.total_expectations,
        "matched_expectations": evaluation.matched_expectations,
        "total_expectations": evaluation.total_expectations,
        "report_path": str(output_path),
        "report_exists": output_path.exists(),
        "expectation_results": [result.__dict__ for result in evaluation.expectation_results],
    }


def _classify_pair_result(result: dict[str, Any]) -> str:
    if result["matched_target"]:
        return "matched"
    if result["exit_code"] != 0 or not result["report_exists"]:
        return "command_failure"
    has_best_candidate = any(
        expectation.get("best_candidate_issue_id") or expectation.get("best_candidate_file_path")
        for expectation in result["expectation_results"]
    )
    if has_best_candidate:
        return "retained_with_drift"
    return "missed"


def _pair_delta(baseline_report: Path, pair_report: Path) -> dict[str, Any]:
    if not baseline_report.exists() or not pair_report.exists():
        return {
            "compare_unavailable": True,
            "issue_count_delta": None,
            "added_count": None,
            "removed_count": None,
        }
    comparison = compare_reports(baseline_report, pair_report)
    return {
        "compare_unavailable": False,
        "issue_count_delta": comparison["delta"]["issue_count"],
        "added_count": comparison["delta"]["added_count"],
        "removed_count": comparison["delta"]["removed_count"],
    }


def _summarize_pairs(pair_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_distractor: dict[str, list[dict[str, Any]]] = {}
    for row in pair_results:
        by_distractor.setdefault(row["distractor_review_type"], []).append(row)

    summaries: list[dict[str, Any]] = []
    for distractor, rows in sorted(by_distractor.items()):
        matched_count = sum(1 for row in rows if row["outcome"] == "matched")
        drift_count = sum(1 for row in rows if row["outcome"] == "retained_with_drift")
        missed_count = sum(1 for row in rows if row["outcome"] == "missed")
        failure_count = sum(1 for row in rows if row["outcome"] == "command_failure")
        deltas = [row["issue_count_delta"] for row in rows if row["issue_count_delta"] is not None]
        summaries.append(
            {
                "distractor_review_type": distractor,
                "fixtures_evaluated": len(rows),
                "matched_count": matched_count,
                "retained_with_drift_count": drift_count,
                "missed_count": missed_count,
                "command_failure_count": failure_count,
                "effective_retention_rate": (matched_count + drift_count) / len(rows),
                "strict_match_rate": matched_count / len(rows),
                "mean_issue_count_delta": mean(deltas) if deltas else None,
                "affected_fixtures": [
                    row["fixture_id"]
                    for row in rows
                    if row["outcome"] != "matched"
                ],
            }
        )
    return summaries


def _recommended_bundle_candidates(pair_summaries: list[dict[str, Any]]) -> list[str]:
    ranked = sorted(
        pair_summaries,
        key=lambda row: (
            row["strict_match_rate"],
            row["effective_retention_rate"],
            -row["command_failure_count"],
        ),
    )
    return [row["distractor_review_type"] for row in ranked[:3]]


def _write_summary_if_requested(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.summary_out:
        Path(args.summary_out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _build_summary_payload(
    args: argparse.Namespace,
    selected_fixtures: list[BenchmarkFixture],
    baseline_results: list[dict[str, Any]],
    pair_results: list[dict[str, Any]],
    command_failures: int,
    status: str,
) -> dict[str, Any]:
    pair_summaries = _summarize_pairs(pair_results) if pair_results else []
    return {
        "backend": benchmark_runner._effective_backend(args.backend),
        "status": status,
        "fixtures_evaluated": len(selected_fixtures),
        "baseline_runs": len(baseline_results),
        "pair_runs": len(pair_results),
        "expected_pair_runs": sum(len(_candidate_distractors(args, fixture)) for fixture in selected_fixtures),
        "command_failures": command_failures,
        "representative_fixture_ids": [fixture.id for fixture in selected_fixtures],
        "representative_fixtures": [describe_fixture_catalog_entry(fixture) for fixture in selected_fixtures],
        "baseline_results": baseline_results,
        "pair_summaries": pair_summaries,
        "pair_results": pair_results,
        "recommended_bundle_candidates": _recommended_bundle_candidates(pair_summaries),
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    fixtures = degradation_study.discover_fixtures(Path(args.fixtures_root))
    selected_fixtures = degradation_study._select_fixtures(args, fixtures)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    baseline_results: list[dict[str, Any]] = []
    pair_results: list[dict[str, Any]] = []
    command_failures = 0

    for fixture in selected_fixtures:
        fixture_dir = output_root / fixture.id
        fixture_dir.mkdir(parents=True, exist_ok=True)

        target_type = fixture.review_types[0]
        baseline_output = fixture_dir / "baseline.json"
        baseline = _run_session(fixture, [target_type], baseline_output, args)
        baseline_issue = _baseline_matched_issue(baseline, baseline_output)
        baseline["baseline_matched_issue_type"] = baseline_issue.get("issue_type") if baseline_issue else None
        baseline_results.append(baseline)
        if baseline["exit_code"] != 0:
            command_failures += 1
        _write_summary_if_requested(
            args,
            _build_summary_payload(
                args,
                selected_fixtures,
                baseline_results,
                pair_results,
                command_failures,
                status="in_progress",
            ),
        )

        for distractor in _candidate_distractors(args, fixture):
            pair_output = fixture_dir / f"with-{distractor}.json"
            pair = _run_session(fixture, [target_type, distractor], pair_output, args)
            pair["distractor_review_type"] = distractor
            pair["baseline_report_path"] = str(baseline_output)
            pair.update(_pair_delta(baseline_output, pair_output))
            pair["outcome"] = _classify_pair_result(pair)
            pair_results.append(pair)
            if pair["exit_code"] != 0:
                command_failures += 1
            _write_summary_if_requested(
                args,
                _build_summary_payload(
                    args,
                    selected_fixtures,
                    baseline_results,
                    pair_results,
                    command_failures,
                    status="in_progress",
                ),
            )

    summary_payload = _build_summary_payload(
        args,
        selected_fixtures,
        baseline_results,
        pair_results,
        command_failures,
        status="completed" if command_failures == 0 else "partial_failure",
    )

    rendered = json.dumps(summary_payload, indent=2)
    print(rendered)
    _write_summary_if_requested(args, summary_payload)
    return 0 if command_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())