"""Evaluate generated-addon review quality against judged representative repository fixtures."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from aicodereviewer.addon_generator import generate_addon_preview
from aicodereviewer.backends.health import check_backend
from aicodereviewer.benchmarking import BenchmarkFixture, describe_fixture_invocation, discover_fixtures, evaluate_fixture_file
from tools import run_holistic_benchmarks as benchmark_runner


@dataclass(frozen=True)
class ReviewQualityTarget:
    target_id: str
    fixture_id: str
    label: str
    stack: str


def _default_catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "addon_generation" / "review_quality_catalog.json"


def _default_fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "addon_generation" / "review_quality" / "fixtures"


def _default_output_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / "generated-addon-review-quality"


def load_review_quality_catalog(catalog_path: str | Path) -> list[ReviewQualityTarget]:
    path = Path(catalog_path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Review-quality catalog must contain an object: {path}")
    targets = payload.get("targets")
    if not isinstance(targets, list):
        raise ValueError(f"Review-quality catalog must contain a 'targets' list: {path}")
    return [
        ReviewQualityTarget(
            target_id=_coerce_non_empty_string(target.get("id"), "id"),
            fixture_id=_coerce_non_empty_string(target.get("fixture_id"), "fixture_id"),
            label=_coerce_non_empty_string(target.get("label"), "label"),
            stack=_coerce_non_empty_string(target.get("stack"), "stack"),
        )
        for target in targets
        if isinstance(target, dict)
    ]


def evaluate_review_quality_target(
    target: ReviewQualityTarget,
    fixture: BenchmarkFixture,
    output_dir: str | Path,
    runner_args: argparse.Namespace,
) -> dict[str, Any]:
    if fixture.project_dir is None:
        raise ValueError(f"Fixture {fixture.id} does not define a project_dir")

    preview_dir = Path(output_dir).resolve() / target.target_id / "preview"
    context_logger = logging.getLogger("aicodereviewer.context_collector")
    previous_context_level = context_logger.level
    try:
        context_logger.setLevel(logging.WARNING)
        preview = generate_addon_preview(
            fixture.project_dir,
            preview_dir,
            addon_id=f"{target.target_id}-generated-addon",
            addon_name=f"{target.label} Generated Addon",
        )
    finally:
        context_logger.setLevel(previous_context_level)
    generated_review_types = _coerce_string_list(preview.review_pack.get("review_presets", [{}])[0].get("review_types"))
    default_review_types = [review_type for review_type in ("best_practices", "maintainability", "testing") if review_type != "specification" or fixture.spec_file is not None]

    invocation = describe_fixture_invocation(fixture)

    default_output_path = Path(output_dir).resolve() / target.target_id / "default-report.json"
    default_invocation = dict(invocation)
    default_invocation["review_types"] = list(default_review_types)
    default_args = benchmark_runner._build_review_args(default_invocation, default_output_path, runner_args)
    default_exit_code, default_payload = benchmark_runner._invoke_review_tool(default_args)
    default_evaluation = evaluate_fixture_file(fixture, default_output_path)

    generated_output_path = Path(output_dir).resolve() / target.target_id / "generated-report.json"
    generated_invocation = dict(invocation)
    generated_invocation["review_types"] = list(generated_review_types)
    generated_args = benchmark_runner._build_review_args(generated_invocation, generated_output_path, runner_args)
    generated_args.extend(["--review-pack", str(preview.review_pack_path)])
    generated_exit_code, generated_payload = benchmark_runner._invoke_review_tool(generated_args)
    generated_evaluation = evaluate_fixture_file(fixture, generated_output_path)

    return {
        "target_id": target.target_id,
        "label": target.label,
        "stack": target.stack,
        "fixture_id": fixture.id,
        "fixture_title": fixture.title,
        "preview_dir": str(preview_dir),
        "review_pack_path": str(preview.review_pack_path),
        "default": {
            "review_types": list(default_review_types),
            "exit_code": default_exit_code,
            "status": default_payload.get("status"),
            "issue_count": default_payload.get("issue_count"),
            "score": default_evaluation.score,
            "passed": default_evaluation.passed,
            "matched_expectations": default_evaluation.matched_expectations,
            "total_expectations": default_evaluation.total_expectations,
            "report_path": str(default_output_path),
        },
        "generated": {
            "review_types": list(generated_review_types),
            "exit_code": generated_exit_code,
            "status": generated_payload.get("status"),
            "issue_count": generated_payload.get("issue_count"),
            "score": generated_evaluation.score,
            "passed": generated_evaluation.passed,
            "matched_expectations": generated_evaluation.matched_expectations,
            "total_expectations": generated_evaluation.total_expectations,
            "report_path": str(generated_output_path),
        },
        "score_delta": round(generated_evaluation.score - default_evaluation.score, 4),
        "pass_delta": int(generated_evaluation.passed) - int(default_evaluation.passed),
    }


def summarize_review_quality_results(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rows = list(results)
    summary: dict[str, Any] = {
        "targets_evaluated": len(rows),
        "results": rows,
    }
    if not rows:
        return summary
    summary["generated_average_score"] = round(mean(row["generated"]["score"] for row in rows), 4)
    summary["default_average_score"] = round(mean(row["default"]["score"] for row in rows), 4)
    summary["average_score_delta"] = round(mean(row["score_delta"] for row in rows), 4)
    summary["generated_better_count"] = sum(1 for row in rows if row["score_delta"] > 0)
    summary["default_better_count"] = sum(1 for row in rows if row["score_delta"] < 0)
    summary["ties"] = sum(1 for row in rows if row["score_delta"] == 0)
    return summary


def _health_payload(backend_name: str) -> dict[str, Any]:
    report = check_backend(backend_name)
    return {
        "backend": backend_name,
        "ready": report.ready,
        "summary": report.summary,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "detail": check.detail,
                "fix_hint": check.fix_hint,
            }
            for check in report.checks
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run judged generated-addon review quality comparisons on representative repository fixtures.",
    )
    parser.add_argument("--catalog", default=str(_default_catalog_path()))
    parser.add_argument("--fixtures-root", default=str(_default_fixtures_root()))
    parser.add_argument("--output-dir", default=str(_default_output_dir()))
    parser.add_argument("--json-out")
    parser.add_argument("--target-id", action="append", dest="target_ids", default=[])
    parser.add_argument("--backend", choices=["bedrock", "kiro", "copilot", "local"], default=None)
    parser.add_argument("--lang", choices=["en", "ja", "default"], default="en")
    parser.add_argument("--programmer", default="benchmark-bot")
    parser.add_argument("--reviewer", default="benchmark-bot")
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
    local_web_search_group.add_argument("--local-enable-web-search", dest="local_enable_web_search", action="store_true", default=None)
    local_web_search_group.add_argument("--local-disable-web-search", dest="local_enable_web_search", action="store_false")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    targets = load_review_quality_catalog(args.catalog)
    if args.target_ids:
        requested = set(args.target_ids)
        targets = [target for target in targets if target.target_id in requested]
        missing = requested.difference({target.target_id for target in targets})
        if missing:
            parser.error(f"Unknown target ids: {', '.join(sorted(missing))}")

    fixtures = discover_fixtures(Path(args.fixtures_root))
    fixtures_by_id = {fixture.id: fixture for fixture in fixtures}

    backend_name = benchmark_runner._effective_backend(args.backend)
    health = None if args.skip_health_check else _health_payload(backend_name)
    if health is not None and not health["ready"]:
        payload = {
            "backend": backend_name,
            "status": "backend_not_ready",
            "health": health,
            "summary": None,
        }
        rendered = json.dumps(payload, indent=2)
        print(rendered)
        if args.json_out:
            Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
        return 1

    results = []
    for target in targets:
        fixture = fixtures_by_id.get(target.fixture_id)
        if fixture is None:
            raise ValueError(f"Review-quality fixture not found: {target.fixture_id}")
        results.append(evaluate_review_quality_target(target, fixture, args.output_dir, args))

    summary = summarize_review_quality_results(results)
    payload = {
        "backend": backend_name,
        "status": "completed",
        "health": health,
        "summary": summary,
    }
    rendered = json.dumps(payload, indent=2)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
    return 0


def _coerce_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Catalog field '{field_name}' must be a non-empty string")
    return value.strip()


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


if __name__ == "__main__":
    raise SystemExit(main())