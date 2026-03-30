"""Run holistic benchmark fixtures through tool-mode review and score them."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from aicodereviewer import main as cli_main
from aicodereviewer.backends.health import check_backend
from aicodereviewer.benchmarking import (
    describe_fixture_invocation,
    discover_fixtures,
    evaluate_fixture_directory,
    summarize_results,
)
from aicodereviewer.config import config


def _default_fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "holistic_review" / "fixtures"


def _default_output_root() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / "holistic-benchmark-reports"


def _configured_backend_timeout_seconds(backend_name: str) -> float | None:
    section_by_backend = {
        "copilot": "copilot",
        "kiro": "kiro",
        "local": "local_llm",
    }
    section = section_by_backend.get(backend_name)
    fallback = config.get("performance", "api_timeout_seconds", "300")
    raw_value = config.get(section, "timeout", fallback) if section else fallback
    try:
        timeout_value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return timeout_value if timeout_value > 0 else None


def _fixture_timeout_seconds(runner_args: argparse.Namespace) -> float | None:
    explicit = getattr(runner_args, "fixture_timeout_seconds", None)
    if explicit is not None:
        return explicit if explicit > 0 else None

    base_timeout = runner_args.timeout
    if base_timeout is None:
        base_timeout = _configured_backend_timeout_seconds(_effective_backend(runner_args.backend))
    if base_timeout is None or base_timeout <= 0:
        return None

    return max(base_timeout + 30.0, base_timeout * 2.0)


def _review_api_timeout_seconds(runner_args: argparse.Namespace) -> float | None:
    explicit = getattr(runner_args, "timeout", None)
    if explicit is not None:
        return explicit if explicit > 0 else None

    fixture_timeout = _fixture_timeout_seconds(runner_args)
    if fixture_timeout is None:
        return None

    backend_name = _effective_backend(runner_args.backend)
    configured_timeout = _configured_backend_timeout_seconds(backend_name)
    derived_timeout = max(30.0, fixture_timeout / 2.0)
    if backend_name == "local":
        derived_timeout = min(derived_timeout, 90.0)
    if configured_timeout is None:
        return derived_timeout
    return min(configured_timeout, derived_timeout)


def _subprocess_timeout_seconds(review_args: Sequence[str]) -> float | None:
    if "--timeout-seconds" not in review_args:
        return None
    raw_value = review_args[review_args.index("--timeout-seconds") + 1]
    try:
        timeout_value = float(raw_value)
    except (IndexError, TypeError, ValueError):
        return None
    if timeout_value <= 0:
        return None
    return timeout_value + 5.0


def _review_json_out_path(review_args: Sequence[str]) -> Path | None:
    if "--json-out" not in review_args:
        return None
    try:
        return Path(review_args[review_args.index("--json-out") + 1])
    except (IndexError, TypeError, ValueError):
        return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute and score holistic review benchmarks via tool-mode review",
    )
    parser.add_argument("--fixtures-root", default=str(_default_fixtures_root()))
    parser.add_argument("--output-dir", default=str(_default_output_root()))
    parser.add_argument("--summary-out")
    parser.add_argument(
        "--backend",
        choices=["bedrock", "kiro", "copilot", "local"],
        default=None,
        help="Backend override; defaults to configured backend",
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
    parser.add_argument("--json-out")
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of repeated benchmark runs to execute for stability measurement",
    )
    parser.add_argument("--skip-health-check", action="store_true")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--fixture-timeout-seconds", type=float)
    parser.add_argument("--model")
    parser.add_argument("--api-url")
    parser.add_argument("--api-type")
    parser.add_argument("--local-model")
    local_web_search_group = parser.add_mutually_exclusive_group()
    local_web_search_group.add_argument(
        "--local-enable-web-search",
        dest="local_enable_web_search",
        action="store_true",
        default=None,
        help="Enable Local LLM web guidance for this benchmark invocation",
    )
    local_web_search_group.add_argument(
        "--local-disable-web-search",
        dest="local_enable_web_search",
        action="store_false",
        help="Disable Local LLM web guidance for this benchmark invocation",
    )
    parser.add_argument("--copilot-model")
    parser.add_argument("--kiro-cli-command")
    return parser


def _run_output_dir(base_output_dir: Path, run_index: int, total_runs: int) -> Path:
    if total_runs == 1:
        return base_output_dir
    return base_output_dir / f"run-{run_index:03d}"


def _stability_summary(run_results: Sequence[Sequence[Any]]) -> dict[str, Any]:
    total_runs = len(run_results)
    fixture_rows: dict[str, dict[str, Any]] = {}

    for run_index, results in enumerate(run_results, start=1):
        for result in results:
            row = fixture_rows.setdefault(
                result.fixture_id,
                {
                    "fixture_id": result.fixture_id,
                    "title": result.title,
                    "pass_count": 0,
                    "scores": [],
                    "runs": [],
                },
            )
            row["pass_count"] += 1 if result.passed else 0
            row["scores"].append(result.score)
            row["runs"].append(
                {
                    "run_index": run_index,
                    "passed": result.passed,
                    "score": result.score,
                    "report_path": result.report_path,
                    "missing_report": result.missing_report,
                    "failed_checks": [
                        expectation.failed_checks
                        for expectation in result.expectation_results
                        if not expectation.matched and expectation.failed_checks
                    ],
                }
            )

    fixtures = []
    mean_pass_rate = 0.0
    mean_score = 0.0
    for row in sorted(fixture_rows.values(), key=lambda entry: entry["fixture_id"]):
        pass_rate = row["pass_count"] / total_runs if total_runs else 0.0
        average_score = sum(row["scores"]) / len(row["scores"]) if row["scores"] else 0.0
        mean_pass_rate += pass_rate
        mean_score += average_score
        fixtures.append(
            {
                "fixture_id": row["fixture_id"],
                "title": row["title"],
                "pass_count": row["pass_count"],
                "fail_count": total_runs - row["pass_count"],
                "pass_rate": round(pass_rate, 4),
                "average_score": round(average_score, 4),
                "all_runs_passed": row["pass_count"] == total_runs,
                "any_run_passed": row["pass_count"] > 0,
                "runs": row["runs"],
            }
        )

    fixture_count = len(fixtures)
    return {
        "runs": total_runs,
        "fixtures_evaluated": fixture_count,
        "fixtures_all_runs_passed": sum(1 for fixture in fixtures if fixture["all_runs_passed"]),
        "fixtures_any_run_passed": sum(1 for fixture in fixtures if fixture["any_run_passed"]),
        "mean_pass_rate": round(mean_pass_rate / fixture_count, 4) if fixture_count else 0.0,
        "mean_score": round(mean_score / fixture_count, 4) if fixture_count else 0.0,
        "fixtures": fixtures,
    }


def _effective_backend(backend_override: str | None) -> str:
    return backend_override or config.get("backend", "type", "bedrock")


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


def _invoke_review_tool(args: list[str]) -> tuple[int, dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    src_path = str(repo_root / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else os.pathsep.join([src_path, existing_pythonpath])
    command = [
        sys.executable,
        "-c",
        "from aicodereviewer.main import main; import sys; sys.exit(main())",
        *args,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=repo_root,
            env=env,
            check=False,
            timeout=_subprocess_timeout_seconds(args),
        )
    except subprocess.TimeoutExpired as exc:
        timeout_seconds = _subprocess_timeout_seconds(args)
        payload = {
            "status": "error",
            "success": False,
            "error": {
                "message": (
                    "Benchmark subprocess exceeded the per-fixture timeout"
                    if timeout_seconds is None
                    else f"Benchmark subprocess exceeded the per-fixture timeout after {timeout_seconds - 5.0:.1f}s"
                )
            },
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
        json_out_path = _review_json_out_path(args)
        if json_out_path is not None:
            json_out_path.parent.mkdir(parents=True, exist_ok=True)
            json_out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 124, payload
    raw = completed.stdout.strip()
    payload = json.loads(raw) if raw else {}
    return completed.returncode, payload


def _build_review_args(
    fixture_args: dict[str, Any],
    output_path: Path,
    runner_args: argparse.Namespace,
) -> list[str]:
    argv = ["review"]
    path = fixture_args.get("path")
    if path:
        argv.append(path)
    argv.extend(["--scope", str(fixture_args["scope"])])
    argv.extend(["--type", ",".join(fixture_args["review_types"])])
    argv.extend(["--programmers", runner_args.programmer])
    argv.extend(["--reviewers", runner_args.reviewer])
    argv.extend(["--json-out", str(output_path)])
    if runner_args.backend:
        argv.extend(["--backend", runner_args.backend])
    if runner_args.lang:
        argv.extend(["--lang", runner_args.lang])
    if fixture_args["scope"] == "diff":
        diff_file = fixture_args.get("diff_file")
        if diff_file:
            argv.extend(["--diff-file", diff_file])
    spec_file = fixture_args.get("spec_file")
    if spec_file:
        argv.extend(["--spec-file", spec_file])
    fixture_timeout_seconds = _fixture_timeout_seconds(runner_args)
    if fixture_timeout_seconds is not None:
        argv.extend(["--timeout-seconds", str(fixture_timeout_seconds)])
    review_api_timeout = _review_api_timeout_seconds(runner_args)
    if review_api_timeout is not None:
        argv.extend(["--timeout", str(review_api_timeout)])
    if runner_args.model:
        argv.extend(["--model", runner_args.model])
    if runner_args.api_url:
        argv.extend(["--api-url", runner_args.api_url])
    if runner_args.api_type:
        argv.extend(["--api-type", runner_args.api_type])
    if runner_args.local_model:
        argv.extend(["--local-model", runner_args.local_model])
    if runner_args.local_enable_web_search is True:
        argv.append("--local-enable-web-search")
    elif runner_args.local_enable_web_search is False:
        argv.append("--local-disable-web-search")
    if runner_args.copilot_model:
        argv.extend(["--copilot-model", runner_args.copilot_model])
    if runner_args.kiro_cli_command:
        argv.extend(["--kiro-cli-command", runner_args.kiro_cli_command])
    return argv


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.runs < 1:
        parser.error("--runs must be at least 1")

    fixtures = discover_fixtures(Path(args.fixtures_root))
    if args.fixtures:
        requested = set(args.fixtures)
        fixtures = [fixture for fixture in fixtures if fixture.id in requested]
        missing = requested.difference({fixture.id for fixture in fixtures})
        if missing:
            parser.error(f"Unknown fixture ids: {', '.join(sorted(missing))}")

    backend_name = _effective_backend(args.backend)
    health = None if args.skip_health_check else _health_payload(backend_name)
    if health is not None and not health["ready"]:
        payload = {
            "backend": backend_name,
            "status": "backend_not_ready",
            "health": health,
            "generated_reports": [],
            "score_summary": None,
        }
        rendered = json.dumps(payload, indent=2)
        print(rendered)
        if args.json_out:
            Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_reports: list[dict[str, Any]] = []
    command_failures = 0
    per_run_results = []
    run_summaries = []

    for run_index in range(1, args.runs + 1):
        run_output_dir = _run_output_dir(output_dir, run_index, args.runs)
        run_output_dir.mkdir(parents=True, exist_ok=True)
        run_command_failures = 0

        for fixture in fixtures:
            invocation = describe_fixture_invocation(fixture)
            output_path = run_output_dir / f"{fixture.id}.json"
            review_args = _build_review_args(invocation, output_path, args)
            exit_code, payload = _invoke_review_tool(review_args)
            generated_reports.append(
                {
                    "run_index": run_index,
                    "fixture_id": fixture.id,
                    "exit_code": exit_code,
                    "output_path": str(output_path),
                    "status": payload.get("status"),
                    "issue_count": payload.get("issue_count"),
                    "success": payload.get("success", False),
                }
            )
            if exit_code != 0:
                command_failures += 1
                run_command_failures += 1

        score_results = evaluate_fixture_directory(fixtures, run_output_dir)
        per_run_results.append(score_results)
        run_summaries.append(
            {
                "run_index": run_index,
                "output_dir": str(run_output_dir),
                "command_failures": run_command_failures,
                "score_summary": summarize_results(score_results),
            }
        )

    score_summary = run_summaries[-1]["score_summary"]
    stability_summary = _stability_summary(per_run_results)
    summary_payload = {
        "backend": backend_name,
        "status": "completed" if command_failures == 0 else "partial_failure",
        "runs": args.runs,
        "health": health,
        "generated_reports": generated_reports,
        "score_summary": score_summary,
        "stability_summary": stability_summary,
    }
    if args.runs > 1:
        summary_payload["run_summaries"] = run_summaries
    rendered = json.dumps(summary_payload, indent=2)
    print(rendered)

    if args.summary_out:
        summary_output = stability_summary if args.runs > 1 else score_summary
        Path(args.summary_out).write_text(json.dumps(summary_output, indent=2) + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")

    if command_failures > 0:
        return 1
    if args.runs > 1:
        return 0 if stability_summary["fixtures_all_runs_passed"] == len(fixtures) else 1
    return 0 if score_summary["fixtures_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())