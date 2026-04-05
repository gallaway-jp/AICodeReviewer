"""Measure target-review retention as more review types are selected in one session."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aicodereviewer.backends.base import REVIEW_TYPE_KEYS
from aicodereviewer.benchmarking import (
    BenchmarkFixture,
    describe_fixture_catalog_entry,
    describe_fixture_invocation,
    discover_fixtures,
    evaluate_fixture_file,
)
from tools.compare_review_reports import compare_reports
from tools import run_holistic_benchmarks as benchmark_runner


DEFAULT_FIXTURE_BY_TYPE = {
    "accessibility": "accessibility-fieldset-without-legend",
    "api_design": "api-design-patch-without-change-contract",
    "architecture": "architectural-layer-leak",
    "best_practices": "private-state-access-bypass",
    "compatibility": "compatibility-windows-path-separator-assumption",
    "complexity": "complexity-state-machine-branch-explosion",
    "concurrency": "concurrency-map-mutation-during-iteration",
    "data_validation": "data-validation-enum-field-not-constrained",
    "dead_code": "dead-code-stale-feature-flag",
    "dependency": "dependency-missing-pyyaml-declaration",
    "documentation": "documentation-stale-sync-token-doc",
    "error_handling": "error-handling-context-manager-exception-not-cleaned",
    "license": "license-embedded-mit-code-without-attribution",
    "localization": "localization-concatenated-translation-grammar-break",
    "maintainability": "maintainability-parallel-parser-variants-drift",
    "performance": "cache-invalidation-gap",
    "regression": "regression-stale-caller-utility-signature-change",
    "scalability": "scalability-connection-pool-exhaustion-under-burst",
    "security": "auth-guard-regression",
    "specification": "specification-type-mismatch-vs-spec-enum",
    "testing": "testing-timeout-retry-untested",
    "ui_ux": "desktop-cross-tab-preference-gap",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a review-type degradation study against representative holistic fixtures.",
    )
    parser.add_argument("--fixtures-root", default="benchmarks/holistic_review/fixtures")
    parser.add_argument("--output-dir", default="artifacts/review-type-degradation")
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
    parser.add_argument(
        "--levels",
        default="1,4,8,12,22",
        help="Comma-separated review-type counts to test. The target type is always included.",
    )
    parser.add_argument("--fixture", action="append", dest="fixtures", default=[])
    parser.add_argument(
        "--review-type",
        action="append",
        dest="review_types",
        default=[],
        help="Restrict the representative set to these target review types.",
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


def _parse_levels(raw: str, max_count: int) -> list[int]:
    levels: list[int] = []
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        value = int(text)
        if value < 1:
            raise ValueError("Review-type counts must be positive")
        levels.append(min(value, max_count))
    unique = sorted(set(levels))
    if 1 not in unique:
        unique.insert(0, 1)
    return unique


def _pick_representative_fixture(
    fixtures_by_id: dict[str, BenchmarkFixture],
    fixtures: Iterable[BenchmarkFixture],
    review_type: str,
) -> BenchmarkFixture:
    preferred_id = DEFAULT_FIXTURE_BY_TYPE.get(review_type)
    if preferred_id and preferred_id in fixtures_by_id:
        return fixtures_by_id[preferred_id]

    candidates = [fixture for fixture in fixtures if review_type in fixture.review_types]
    if not candidates:
        raise ValueError(f"No fixture found for review type: {review_type}")
    return sorted(candidates, key=lambda fixture: fixture.id)[0]


def _select_fixtures(args: argparse.Namespace, fixtures: list[BenchmarkFixture]) -> list[BenchmarkFixture]:
    fixtures_by_id = {fixture.id: fixture for fixture in fixtures}
    if args.fixtures:
        missing = sorted(set(args.fixtures).difference(fixtures_by_id))
        if missing:
            raise ValueError(f"Unknown fixture ids: {', '.join(missing)}")
        return [fixtures_by_id[fixture_id] for fixture_id in args.fixtures]

    target_types = args.review_types or list(REVIEW_TYPE_KEYS)
    unknown = sorted(set(target_types).difference(REVIEW_TYPE_KEYS))
    if unknown:
        raise ValueError(f"Unknown review types: {', '.join(unknown)}")
    return [_pick_representative_fixture(fixtures_by_id, fixtures, review_type) for review_type in target_types]


def _type_set_for_level(target_type: str, level: int, review_type_order: list[str]) -> list[str]:
    distractors = [review_type for review_type in review_type_order if review_type != target_type]
    return [target_type, *distractors[: max(0, level - 1)]]


def _valid_review_types_for_fixture(
    fixture: BenchmarkFixture,
    review_type_order: list[str],
) -> list[str]:
    valid_types: list[str] = []
    has_spec_file = bool(getattr(fixture, "spec_file", None))
    for review_type in review_type_order:
        if review_type == "specification" and not has_spec_file:
            continue
        valid_types.append(review_type)
    return valid_types


def _type_set_for_fixture_level(
    fixture: BenchmarkFixture,
    level: int,
    review_type_order: list[str],
) -> list[str]:
    target_type = fixture.review_types[0]
    valid_review_types = _valid_review_types_for_fixture(fixture, review_type_order)
    if target_type not in valid_review_types:
        raise ValueError(f"Target review type {target_type} is not valid for fixture {fixture.id}")
    return _type_set_for_level(target_type, level, valid_review_types)


def _issue_count(payload: dict[str, Any]) -> int:
    count = payload.get("issue_count")
    if isinstance(count, int):
        return count
    report = payload.get("report")
    if isinstance(report, dict) and isinstance(report.get("issues_found"), list):
        return len(report["issues_found"])
    issues = payload.get("issues")
    if isinstance(issues, list):
        return len(issues)
    return 0


def _run_fixture_level(
    fixture: BenchmarkFixture,
    selected_types: list[str],
    level_output_path: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    invocation = dict(describe_fixture_invocation(fixture))
    invocation["review_types"] = list(selected_types)
    review_args = benchmark_runner._build_review_args(invocation, level_output_path, args)
    exit_code, payload = benchmark_runner._invoke_review_tool(review_args)
    evaluation = evaluate_fixture_file(fixture, level_output_path)
    matched = evaluation.matched_expectations == evaluation.total_expectations and evaluation.passed
    return {
        "fixture_id": fixture.id,
        "fixture_title": fixture.title,
        "target_review_type": fixture.review_types[0],
        "selected_review_types": list(selected_types),
        "benchmark_metadata": dict(invocation.get("benchmark_metadata", {})),
        "type_count": len(selected_types),
        "exit_code": exit_code,
        "status": payload.get("status"),
        "issue_count": _issue_count(payload),
        "score": evaluation.score,
        "passed": evaluation.passed,
        "matched_target": matched,
        "matched_expectations": evaluation.matched_expectations,
        "total_expectations": evaluation.total_expectations,
        "report_path": str(level_output_path),
        "report_exists": level_output_path.exists(),
        "expectation_results": [result.__dict__ for result in evaluation.expectation_results],
    }


def _aggregate_levels(level_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_level: dict[int, list[dict[str, Any]]] = {}
    for result in level_results:
        by_level.setdefault(result["type_count"], []).append(result)

    summaries: list[dict[str, Any]] = []
    baseline_pass_rate = None
    for type_count in sorted(by_level):
        rows = by_level[type_count]
        pass_rate = sum(1 for row in rows if row["matched_target"]) / len(rows)
        mean_issue_count = mean(row["issue_count"] for row in rows)
        summary = {
            "type_count": type_count,
            "fixtures_evaluated": len(rows),
            "fixtures_passed": sum(1 for row in rows if row["matched_target"]),
            "pass_rate": pass_rate,
            "mean_issue_count": mean_issue_count,
            "median_issue_count": sorted(row["issue_count"] for row in rows)[len(rows) // 2],
            "failed_fixture_ids": [row["fixture_id"] for row in rows if not row["matched_target"]],
        }
        if baseline_pass_rate is None:
            baseline_pass_rate = pass_rate
            summary["pass_rate_delta_vs_baseline"] = 0.0
        else:
            summary["pass_rate_delta_vs_baseline"] = pass_rate - baseline_pass_rate
        summaries.append(summary)
    return summaries


def _fixture_trends(level_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_fixture: dict[str, list[dict[str, Any]]] = {}
    for result in level_results:
        by_fixture.setdefault(result["fixture_id"], []).append(result)

    trends: list[dict[str, Any]] = []
    for fixture_id, rows in sorted(by_fixture.items()):
        ordered = sorted(rows, key=lambda row: row["type_count"])
        baseline = ordered[0]
        first_failure = next((row["type_count"] for row in ordered if not row["matched_target"]), None)
        trend = {
            "fixture_id": fixture_id,
            "fixture_title": ordered[0]["fixture_title"],
            "target_review_type": ordered[0]["target_review_type"],
            "baseline_issue_count": baseline["issue_count"],
            "baseline_passed": baseline["matched_target"],
            "first_failure_type_count": first_failure,
            "levels": ordered,
        }
        if len(ordered) > 1:
            baseline_report = Path(baseline["report_path"])
            deltas = []
            for row in ordered[1:]:
                current_report = Path(row["report_path"])
                if not baseline_report.exists() or not current_report.exists():
                    deltas.append(
                        {
                            "type_count": row["type_count"],
                            "issue_count_delta": None,
                            "added_count": None,
                            "removed_count": None,
                            "compare_unavailable": True,
                        }
                    )
                    continue
                comparison = compare_reports(baseline_report, current_report)
                deltas.append(
                    {
                        "type_count": row["type_count"],
                        "issue_count_delta": comparison["delta"]["issue_count"],
                        "added_count": comparison["delta"]["added_count"],
                        "removed_count": comparison["delta"]["removed_count"],
                        "compare_unavailable": False,
                    }
                )
            trend["baseline_delta_summary"] = deltas
        trends.append(trend)
    return trends


def _build_summary_payload(
    args: argparse.Namespace,
    selected_fixtures: list[BenchmarkFixture],
    levels: list[int],
    level_results: list[dict[str, Any]],
    command_failures: int,
    status: str,
) -> dict[str, Any]:
    return {
        "backend": benchmark_runner._effective_backend(args.backend),
        "status": status,
        "fixtures_evaluated": len(selected_fixtures),
        "levels": levels,
        "representative_fixture_ids": [fixture.id for fixture in selected_fixtures],
        "representative_fixtures": [describe_fixture_catalog_entry(fixture) for fixture in selected_fixtures],
        "completed_runs": len(level_results),
        "expected_runs": len(selected_fixtures) * len(levels),
        "command_failures": command_failures,
        "level_summaries": _aggregate_levels(level_results) if level_results else [],
        "fixture_trends": _fixture_trends(level_results) if level_results else [],
    }


def _write_summary_if_requested(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.summary_out:
        Path(args.summary_out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    fixtures = discover_fixtures(Path(args.fixtures_root))
    selected_fixtures = _select_fixtures(args, fixtures)
    levels = _parse_levels(args.levels, len(REVIEW_TYPE_KEYS))
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    level_results: list[dict[str, Any]] = []
    command_failures = 0

    for fixture in selected_fixtures:
        fixture_dir = output_root / fixture.id
        fixture_dir.mkdir(parents=True, exist_ok=True)
        for level in levels:
            selected_types = _type_set_for_fixture_level(fixture, level, list(REVIEW_TYPE_KEYS))
            output_path = fixture_dir / f"{level:02d}-types.json"
            result = _run_fixture_level(fixture, selected_types, output_path, args)
            level_results.append(result)
            if result["exit_code"] != 0:
                command_failures += 1
            _write_summary_if_requested(
                args,
                _build_summary_payload(
                    args,
                    selected_fixtures,
                    levels,
                    level_results,
                    command_failures,
                    status="in_progress",
                ),
            )

    summary_payload = _build_summary_payload(
        args,
        selected_fixtures,
        levels,
        level_results,
        command_failures,
        status="completed" if command_failures == 0 else "partial_failure",
    )

    rendered = json.dumps(summary_payload, indent=2)
    print(rendered)
    _write_summary_if_requested(args, summary_payload)
    return 0 if command_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())