from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from run_holistic_benchmarks import main as run_holistic_benchmarks_main
from aicodereviewer.benchmarking import discover_fixtures, evaluate_fixture_directory, summarize_results


TRANCHE_FIXTURES: dict[str, list[str]] = {
    "maintainability": [
        "maintainability-duplicated-sync-window-rules",
        "maintainability-overloaded-settings-controller",
        "maintainability-parallel-parser-variants-drift",
    ],
    "dead_code": [
        "dead-code-unreachable-fallback",
        "dead-code-stale-feature-flag",
        "dead-code-obsolete-compat-shim",
    ],
    "security": [
        "auth-guard-regression",
        "validation-drift",
        "security-idor-invoice-download",
        "security-jwt-signature-bypass",
        "security-open-redirect-login",
        "security-path-traversal-download",
        "security-predictable-reset-token",
        "security-shell-command-injection",
        "security-ssrf-avatar-fetch",
        "security-sql-query-interpolation",
        "security-unsafe-yaml-load",
        "security-zip-slip-theme-import",
    ],
    "error_handling": [
        "error-handling-context-manager-exception-not-cleaned",
        "error-handling-retryless-sync-timeout",
        "error-handling-swallowed-import-failure",
    ],
    "data_validation": [
        "data-validation-enum-field-not-constrained",
        "data-validation-inverted-time-window",
        "data-validation-rollout-percent-range",
    ],
    "regression": [
        "regression-default-sync-disabled",
        "regression-inverted-sync-start-guard",
        "regression-stale-caller-utility-signature-change",
    ],
    "testing": [
        "testing-order-rollback-untested",
        "testing-rollout-percent-range-untested",
        "testing-timeout-retry-untested",
    ],
    "documentation": [
        "documentation-deployment-topology-docs-incomplete",
        "documentation-stale-dry-run-flag",
        "documentation-stale-sync-token-doc",
    ],
    "architecture": [
        "architectural-layer-leak",
        "architectural-service-web-context-leak",
    ],
    "api_design": [
        "api-design-create-missing-201-contract",
        "api-design-get-create-endpoint",
        "api-design-patch-without-change-contract",
    ],
    "ui_ux": [
        "desktop-busy-feedback-gap",
        "desktop-confirmation-gap",
        "desktop-cross-tab-preference-gap",
        "desktop-settings-discoverability-gap",
        "desktop-wizard-orientation-gap",
        "ui-form-recovery-gap",
        "ui-loading-feedback-gap",
    ],
    "accessibility": [
        "accessibility-dialog-semantic-gap",
        "accessibility-fieldset-without-legend",
        "accessibility-icon-button-label-gap",
    ],
    "localization": [
        "localization-concatenated-translation-grammar-break",
        "localization-hardcoded-settings-labels",
        "localization-us-only-receipt-format",
    ],
    "compatibility": [
        "compatibility-macos-open-command",
        "compatibility-python311-tomllib-runtime-gap",
        "compatibility-windows-path-separator-assumption",
    ],
    "dependency": [
        "dependency-missing-pyyaml-declaration",
        "dependency-runtime-imports-dev-only-pytest",
        "dependency-transitive-api-removal-runtime-gap",
    ],
    "license": [
        "license-agpl-notice-conflict",
        "license-apache-notice-omission",
        "license-embedded-mit-code-without-attribution",
    ],
    "scalability": [
        "scalability-connection-pool-exhaustion-under-burst",
        "scalability-instance-local-rate-limit-state",
        "scalability-unbounded-pending-events-buffer",
    ],
    "concurrency": [
        "concurrency-async-slot-double-booking",
        "concurrency-map-mutation-during-iteration",
        "concurrency-shared-sequence-race",
    ],
    "specification": [
        "specification-batch-atomicity-contract",
        "specification-profile-display-name-contract",
        "specification-type-mismatch-vs-spec-enum",
    ],
    "complexity": [
        "complexity-nested-sync-decision-tree",
        "complexity-notification-rule-ladder",
        "complexity-state-machine-branch-explosion",
    ],
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a named holistic benchmark tranche without spelling every fixture on the CLI.",
    )
    parser.add_argument("--tranche", choices=sorted(TRANCHE_FIXTURES), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--summary-out", required=True)
    parser.add_argument("--evaluate-existing", action="store_true")
    parser.add_argument("--backend", choices=["bedrock", "kiro", "copilot", "local"])
    parser.add_argument("--fixtures-root")
    parser.add_argument("--lang", choices=["en", "ja", "default"], default="en")
    parser.add_argument("--programmer", default="benchmark-bot")
    parser.add_argument("--reviewer", default="benchmark-bot")
    parser.add_argument("--runs", type=int, default=1)
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
    )
    local_web_search_group.add_argument(
        "--local-disable-web-search",
        dest="local_enable_web_search",
        action="store_false",
    )
    parser.add_argument("--copilot-model")
    parser.add_argument("--kiro-cli-command")
    return parser


def _build_runner_argv(args: argparse.Namespace) -> list[str]:
    runner_argv = [
        "--output-dir",
        args.output_dir,
        "--summary-out",
        args.summary_out,
        "--lang",
        args.lang,
        "--programmer",
        args.programmer,
        "--reviewer",
        args.reviewer,
        "--runs",
        str(args.runs),
    ]
    if args.backend:
        runner_argv.extend(["--backend", args.backend])
    if args.fixtures_root:
        runner_argv.extend(["--fixtures-root", args.fixtures_root])
    if args.skip_health_check:
        runner_argv.append("--skip-health-check")
    if args.timeout is not None:
        runner_argv.extend(["--timeout", str(args.timeout)])
    if args.fixture_timeout_seconds is not None:
        runner_argv.extend(["--fixture-timeout-seconds", str(args.fixture_timeout_seconds)])
    if args.model:
        runner_argv.extend(["--model", args.model])
    if args.api_url:
        runner_argv.extend(["--api-url", args.api_url])
    if args.api_type:
        runner_argv.extend(["--api-type", args.api_type])
    if args.local_model:
        runner_argv.extend(["--local-model", args.local_model])
    if args.local_enable_web_search is True:
        runner_argv.append("--local-enable-web-search")
    elif args.local_enable_web_search is False:
        runner_argv.append("--local-disable-web-search")
    if args.copilot_model:
        runner_argv.extend(["--copilot-model", args.copilot_model])
    if args.kiro_cli_command:
        runner_argv.extend(["--kiro-cli-command", args.kiro_cli_command])
    for fixture_id in TRANCHE_FIXTURES[args.tranche]:
        runner_argv.extend(["--fixture", fixture_id])
    return runner_argv


def _evaluate_existing_reports(args: argparse.Namespace) -> int:
    fixtures_root = Path(args.fixtures_root) if args.fixtures_root else None
    all_fixtures = discover_fixtures(fixtures_root or Path(__file__).resolve().parents[1] / "benchmarks" / "holistic_review" / "fixtures")
    requested_ids = set(TRANCHE_FIXTURES[args.tranche])
    fixtures = [fixture for fixture in all_fixtures if fixture.id in requested_ids]
    results = evaluate_fixture_directory(fixtures, Path(args.output_dir))
    summary = summarize_results(results)
    rendered = json.dumps(summary, indent=2)
    print(rendered)
    Path(args.summary_out).write_text(rendered + "\n", encoding="utf-8")
    return 0 if all(result.passed for result in results) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.evaluate_existing:
        return _evaluate_existing_reports(args)
    return run_holistic_benchmarks_main(_build_runner_argv(args))


if __name__ == "__main__":
    raise SystemExit(main())