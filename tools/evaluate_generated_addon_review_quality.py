"""Evaluate generated-addon review quality against judged representative repository fixtures."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
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
    stack_summary: dict[str, Any] = {}
    for stack in sorted({str(row.get("stack") or "unknown") for row in rows}):
        stack_rows = [row for row in rows if str(row.get("stack") or "unknown") == stack]
        stack_summary[stack] = {
            "targets_evaluated": len(stack_rows),
            "generated_average_score": round(mean(row["generated"]["score"] for row in stack_rows), 4),
            "default_average_score": round(mean(row["default"]["score"] for row in stack_rows), 4),
            "average_score_delta": round(mean(row["score_delta"] for row in stack_rows), 4),
            "generated_better_count": sum(1 for row in stack_rows if row["score_delta"] > 0),
            "default_better_count": sum(1 for row in stack_rows if row["score_delta"] < 0),
            "ties": sum(1 for row in stack_rows if row["score_delta"] == 0),
        }
    summary["stack_summary"] = stack_summary
    return summary


def update_review_quality_history(
    history_path: str | Path,
    *,
    backend_name: str,
    summary: dict[str, Any],
    recorded_at: str | None = None,
    max_runs: int = 50,
) -> dict[str, Any]:
    path = Path(history_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Review-quality history must contain an object: {path}")
    else:
        payload = {"schema_version": 1, "backends": {}}

    backends = payload.setdefault("backends", {})
    backend_history = backends.setdefault(backend_name, {"runs": []})
    if not isinstance(backend_history, dict):
        raise ValueError(f"Backend history entry must be an object: {backend_name}")
    runs = backend_history.setdefault("runs", [])
    if not isinstance(runs, list):
        raise ValueError(f"Backend history runs must be a list: {backend_name}")

    history_entry = {
        "recorded_at": recorded_at or datetime.now(timezone.utc).isoformat(),
        "targets_evaluated": summary.get("targets_evaluated", 0),
        "generated_average_score": summary.get("generated_average_score", 0.0),
        "default_average_score": summary.get("default_average_score", 0.0),
        "average_score_delta": summary.get("average_score_delta", 0.0),
        "generated_better_count": summary.get("generated_better_count", 0),
        "default_better_count": summary.get("default_better_count", 0),
        "ties": summary.get("ties", 0),
        "stack_summary": summary.get("stack_summary", {}),
    }
    runs.append(history_entry)
    if max_runs > 0:
        del runs[:-max_runs]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def build_review_quality_trend(history_payload: dict[str, Any], *, backend_name: str) -> dict[str, Any]:
    backend_runs = list(history_payload.get("backends", {}).get(backend_name, {}).get("runs", []))
    latest = backend_runs[-1] if backend_runs else None
    previous = backend_runs[-2] if len(backend_runs) >= 2 else None
    trend: dict[str, Any] = {
        "backend": backend_name,
        "run_count": len(backend_runs),
        "latest": latest,
        "previous": previous,
        "change_since_previous": None,
        "stack_changes": {},
    }
    if latest is None or previous is None:
        return trend

    trend["change_since_previous"] = {
        "generated_average_score": _round_delta(
            float(latest.get("generated_average_score", 0.0)) - float(previous.get("generated_average_score", 0.0))
        ),
        "default_average_score": _round_delta(
            float(latest.get("default_average_score", 0.0)) - float(previous.get("default_average_score", 0.0))
        ),
        "average_score_delta": _round_delta(
            float(latest.get("average_score_delta", 0.0)) - float(previous.get("average_score_delta", 0.0))
        ),
        "generated_better_count": int(latest.get("generated_better_count", 0)) - int(previous.get("generated_better_count", 0)),
        "default_better_count": int(latest.get("default_better_count", 0)) - int(previous.get("default_better_count", 0)),
        "ties": int(latest.get("ties", 0)) - int(previous.get("ties", 0)),
        "targets_evaluated": int(latest.get("targets_evaluated", 0)) - int(previous.get("targets_evaluated", 0)),
    }

    latest_stack_summary = latest.get("stack_summary", {}) if isinstance(latest.get("stack_summary"), dict) else {}
    previous_stack_summary = previous.get("stack_summary", {}) if isinstance(previous.get("stack_summary"), dict) else {}
    for stack_name in sorted(set(latest_stack_summary) | set(previous_stack_summary)):
        latest_stack = latest_stack_summary.get(stack_name, {})
        previous_stack = previous_stack_summary.get(stack_name, {})
        trend["stack_changes"][stack_name] = {
            "latest_average_score_delta": float(latest_stack.get("average_score_delta", 0.0)),
            "previous_average_score_delta": float(previous_stack.get("average_score_delta", 0.0)),
            "average_score_delta_change": _round_delta(
                float(latest_stack.get("average_score_delta", 0.0)) - float(previous_stack.get("average_score_delta", 0.0))
            ),
            "latest_targets_evaluated": int(latest_stack.get("targets_evaluated", 0)),
            "previous_targets_evaluated": int(previous_stack.get("targets_evaluated", 0)),
        }
    return trend


def render_review_quality_markdown(
    *,
    backend_name: str,
    summary: dict[str, Any],
    trend: dict[str, Any],
) -> str:
    lines = [
        "# Generated Addon Review Quality",
        "",
        f"- Backend: `{backend_name}`",
        f"- Targets evaluated: `{summary.get('targets_evaluated', 0)}`",
        f"- Generated average score: `{summary.get('generated_average_score', 0.0):.4f}`",
        f"- Default average score: `{summary.get('default_average_score', 0.0):.4f}`",
        f"- Average score delta: `{_format_delta(float(summary.get('average_score_delta', 0.0)))}`",
        f"- Generated better count: `{summary.get('generated_better_count', 0)}`",
        f"- Default better count: `{summary.get('default_better_count', 0)}`",
        f"- Ties: `{summary.get('ties', 0)}`",
        "",
        "## Trend",
        "",
        f"- Recorded backend runs: `{trend.get('run_count', 0)}`",
    ]

    latest = trend.get("latest")
    if isinstance(latest, dict) and latest.get("recorded_at"):
        lines.append(f"- Latest run: `{latest.get('recorded_at')}`")

    change_since_previous = trend.get("change_since_previous")
    previous = trend.get("previous")
    if isinstance(previous, dict) and previous.get("recorded_at"):
        lines.append(f"- Previous run: `{previous.get('recorded_at')}`")
    if isinstance(change_since_previous, dict):
        lines.extend(
            [
                f"- Change vs previous generated average: `{_format_delta(float(change_since_previous.get('generated_average_score', 0.0)))}`",
                f"- Change vs previous default average: `{_format_delta(float(change_since_previous.get('default_average_score', 0.0)))}`",
                f"- Change vs previous score delta: `{_format_delta(float(change_since_previous.get('average_score_delta', 0.0)))}`",
            ]
        )
    else:
        lines.append("- No previous run recorded for this backend yet.")

    stack_changes = trend.get("stack_changes") if isinstance(trend.get("stack_changes"), dict) else {}
    if stack_changes:
        lines.extend(
            [
                "",
                "## Stack Trend",
                "",
                "| Stack | Latest delta | Previous delta | Change | Targets |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for stack_name, stack_change in stack_changes.items():
            if not isinstance(stack_change, dict):
                continue
            lines.append(
                "| {stack} | {latest} | {previous} | {change} | {targets} |".format(
                    stack=stack_name,
                    latest=_format_delta(float(stack_change.get("latest_average_score_delta", 0.0))),
                    previous=_format_delta(float(stack_change.get("previous_average_score_delta", 0.0))),
                    change=_format_delta(float(stack_change.get("average_score_delta_change", 0.0))),
                    targets=stack_change.get("latest_targets_evaluated", 0),
                )
            )

    return "\n".join(lines) + "\n"


def render_review_quality_health_failure_markdown(*, backend_name: str, health: dict[str, Any]) -> str:
    lines = [
        "# Generated Addon Review Quality",
        "",
        f"- Backend: `{backend_name}`",
        "- Status: `backend_not_ready`",
        f"- Summary: {health.get('summary', 'Backend health check failed.')}",
    ]
    checks = health.get("checks") if isinstance(health.get("checks"), list) else []
    if checks:
        lines.extend(
            [
                "",
                "## Health Checks",
                "",
                "| Check | Passed | Detail |",
                "| --- | --- | --- |",
            ]
        )
        for check in checks:
            if not isinstance(check, dict):
                continue
            lines.append(
                "| {name} | {passed} | {detail} |".format(
                    name=check.get("name", "(unknown)"),
                    passed="yes" if check.get("passed") else "no",
                    detail=str(check.get("detail", "")).replace("|", "\\|"),
                )
            )
    return "\n".join(lines) + "\n"


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
    parser.add_argument("--markdown-summary-out")
    parser.add_argument("--history-file")
    parser.add_argument("--history-limit", type=int, default=50)
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
        if args.markdown_summary_out:
            Path(args.markdown_summary_out).write_text(
                render_review_quality_health_failure_markdown(backend_name=backend_name, health=health),
                encoding="utf-8",
            )
        return 1

    results = []
    for target in targets:
        fixture = fixtures_by_id.get(target.fixture_id)
        if fixture is None:
            raise ValueError(f"Review-quality fixture not found: {target.fixture_id}")
        results.append(evaluate_review_quality_target(target, fixture, args.output_dir, args))

    summary = summarize_review_quality_results(results)
    history_path = Path(args.history_file).resolve() if args.history_file else Path(args.output_dir).resolve() / "history.json"
    history_payload = update_review_quality_history(
        history_path,
        backend_name=backend_name,
        summary=summary,
        max_runs=max(0, int(args.history_limit)),
    )
    trend = build_review_quality_trend(history_payload, backend_name=backend_name)
    payload = {
        "backend": backend_name,
        "status": "completed",
        "health": health,
        "summary": summary,
        "history": {
            "path": str(history_path),
            "backend_run_count": len(history_payload.get("backends", {}).get(backend_name, {}).get("runs", [])),
            "latest": history_payload.get("backends", {}).get(backend_name, {}).get("runs", [])[-1],
            "trend": trend,
        },
    }
    rendered = json.dumps(payload, indent=2)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
    if args.markdown_summary_out:
        Path(args.markdown_summary_out).write_text(
            render_review_quality_markdown(backend_name=backend_name, summary=summary, trend=trend),
            encoding="utf-8",
        )
    return 0


def _coerce_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Catalog field '{field_name}' must be a non-empty string")
    return value.strip()


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _round_delta(value: float) -> float:
    return round(value, 4)


def _format_delta(value: float) -> str:
    return f"{value:+.4f}"


if __name__ == "__main__":
    raise SystemExit(main())