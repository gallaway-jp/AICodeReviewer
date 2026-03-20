"""Run holistic benchmark fixtures through tool-mode review and score them."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
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
    parser.add_argument("--lang", choices=["en", "ja", "default"], default="default")
    parser.add_argument("--programmer", default="benchmark-bot")
    parser.add_argument("--reviewer", default="benchmark-bot")
    parser.add_argument("--fixture", action="append", dest="fixtures", default=[])
    parser.add_argument("--json-out")
    parser.add_argument("--skip-health-check", action="store_true")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--model")
    parser.add_argument("--api-url")
    parser.add_argument("--api-type")
    parser.add_argument("--local-model")
    parser.add_argument("--copilot-model")
    parser.add_argument("--kiro-cli-command")
    return parser


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
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = cli_main.main(args)
    raw = buffer.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return exit_code, payload


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
    if runner_args.timeout is not None:
        argv.extend(["--timeout", str(runner_args.timeout)])
    if runner_args.model:
        argv.extend(["--model", runner_args.model])
    if runner_args.api_url:
        argv.extend(["--api-url", runner_args.api_url])
    if runner_args.api_type:
        argv.extend(["--api-type", runner_args.api_type])
    if runner_args.local_model:
        argv.extend(["--local-model", runner_args.local_model])
    if runner_args.copilot_model:
        argv.extend(["--copilot-model", runner_args.copilot_model])
    if runner_args.kiro_cli_command:
        argv.extend(["--kiro-cli-command", runner_args.kiro_cli_command])
    return argv


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

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

    for fixture in fixtures:
        invocation = describe_fixture_invocation(fixture)
        output_path = output_dir / f"{fixture.id}.json"
        review_args = _build_review_args(invocation, output_path, args)
        exit_code, payload = _invoke_review_tool(review_args)
        generated_reports.append(
            {
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

    score_results = evaluate_fixture_directory(fixtures, output_dir)
    score_summary = summarize_results(score_results)
    summary_payload = {
        "backend": backend_name,
        "status": "completed" if command_failures == 0 else "partial_failure",
        "health": health,
        "generated_reports": generated_reports,
        "score_summary": score_summary,
    }
    rendered = json.dumps(summary_payload, indent=2)
    print(rendered)

    if args.summary_out:
        Path(args.summary_out).write_text(json.dumps(score_summary, indent=2) + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")

    if command_failures > 0:
        return 1
    return 0 if score_summary["fixtures_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())