# src/aicodereviewer/main.py
"""
CLI entry point for AICodeReviewer.

Supports:
- Multiple review types per session (``--type security,performance``)
- Backend selection with canonical names or aliases (for example ``--backend bedrock`` or ``--backend ollama``)
- Full-project and diff-based scopes
- Dry-run mode
- Profile management
- Connection testing (``--check-connection``)
- GUI launcher (``--gui``)
"""
import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence, cast

from aicodereviewer.addons import AddonRuntime, get_active_addon_runtime, install_addon_runtime
from aicodereviewer.addon_generator import generate_addon_preview
from aicodereviewer.auth import get_system_language, set_profile_name, clear_profile
from aicodereviewer.backends import create_backend, get_backend_choices, resolve_backend_type
from aicodereviewer.backends.health import check_backend, HealthReport
from aicodereviewer.config import config
from aicodereviewer.diagnostics import (
    FailureDiagnostic,
    build_failure_diagnostic,
    diagnostic_from_exception,
    failure_fix_hint,
)
from aicodereviewer.fixer import generate_ai_fix_result
from aicodereviewer.models import ReviewIssue, ReviewReport
from aicodereviewer.scanner import scan_project_with_scope
from aicodereviewer.orchestration import AppRunner
from aicodereviewer.http_api import create_local_http_app, run_local_http_server
from aicodereviewer.i18n import t, set_locale
from aicodereviewer.recommendations import recommend_review_types
from aicodereviewer.registries import get_review_registry
from aicodereviewer.review_definitions import install_review_registry, merge_review_pack_paths
from aicodereviewer.review_presets import REVIEW_TYPE_PRESETS, format_review_type_preset_lines, resolve_review_preset_key

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
TOOL_COMMANDS = {"review", "health", "fix-plan", "apply-fixes", "resume", "serve-api", "analyze-repo"}
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_CANCELLED = 3

def cleanup_old_backups(path: str) -> None:
    """Compatibility shim kept for legacy tests and integrations."""
    from aicodereviewer.backup import cleanup_old_backups as _cleanup_old_backups

    _cleanup_old_backups(path)


def _print_console(text: str, end: str = "\n") -> None:
    """Write console output using replacement for unsupported characters."""
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    payload = f"{text}{end}"

    try:
        if hasattr(stream, "buffer"):
            stream.buffer.write(payload.encode(encoding, errors="replace"))
            stream.flush()
        else:
            stream.write(payload.encode(encoding, errors="replace").decode(encoding, errors="replace"))
            stream.flush()
    except Exception:
        print(payload, end="")


def _configure_console_streams() -> None:
    """Avoid console encoding crashes when localized or rich help text is printed."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            continue


def _determine_target_lang(argv: Sequence[str]) -> str:
    """Resolve locale before building the full parser so help is localized."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--lang", choices=["en", "ja", "default"], default="default")
    args, _ = parser.parse_known_args(list(argv))
    return args.lang if args.lang != "default" else get_system_language()


def _extract_review_pack_paths(argv: Sequence[str]) -> list[str]:
    pack_paths: list[str] = []
    index = 0
    argv_list = list(argv)
    while index < len(argv_list):
        token = argv_list[index]
        if token == "--review-pack":
            if index + 1 < len(argv_list):
                pack_paths.append(argv_list[index + 1])
                index += 2
                continue
            break
        if token.startswith("--review-pack="):
            _, value = token.split("=", 1)
            if value.strip():
                pack_paths.append(value.strip())
        index += 1
    return pack_paths


def _build_epilog() -> str:
    """Generate CLI epilog with review type listing."""
    review_registry = get_review_registry()
    lines = [
        t("cli.epilog_types"),
    ]
    for definition, depth in review_registry.iter_hierarchy(visible_only=True):
        key = definition.key
        display_key = f"{'  ' * depth}{key}"
        # Use translated label if available, otherwise fall back to registry metadata.
        label = t(f"review_type.{key}")
        if label == f"review_type.{key}":
            label = definition.label or key
        group = definition.group
        summary_key = definition.summary_key
        summary = t(summary_key) if summary_key else ""
        if summary == summary_key:
            summary = ""
        lines.append(f"  {display_key:20s}  {label}  [{group}]")
        if summary:
            lines.append(f"{'':24s}{summary}")

    lines += [
        "",
        t("cli.epilog_presets"),
    ]
    lines.extend(format_review_type_preset_lines())

    lines += [
        "",
        t("cli.epilog_vcs"),
        t("cli.epilog_subdir"),
        t("cli.epilog_git"),
        t("cli.epilog_svn"),
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]

    _configure_console_streams()

    addon_runtime = install_addon_runtime()
    invocation_review_packs = _extract_review_pack_paths(argv)
    install_review_registry(merge_review_pack_paths(invocation_review_packs) if invocation_review_packs else None)

    target_lang = _determine_target_lang(argv)
    set_locale(target_lang)

    if argv and argv[0] in TOOL_COMMANDS:
        parser = _build_tool_parser()
        args = parser.parse_args(argv)
        _setup_logging()
        return _run_tool_command(parser, args, target_lang)

    parser = argparse.ArgumentParser(
        description=t("cli.desc"),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=_build_epilog(),
    )

    # ── profile management ─────────────────────────────────────────────────
    parser.add_argument("--set-profile", metavar="PROFILE",
                        help=t("cli.help_set_profile"))
    parser.add_argument("--clear-profile", action="store_true",
                        help=t("cli.help_clear_profile"))

    # ── scope ──────────────────────────────────────────────────────────────
    parser.add_argument("--scope", choices=["project", "diff"], default="project",
                        help=t("cli.help_scope"))
    parser.add_argument("--diff-file", metavar="FILE",
                        help=t("cli.help_diff_file"))
    parser.add_argument("--commits", metavar="RANGE",
                        help=t("cli.help_commits"))

    # ── review ─────────────────────────────────────────────────────────────
    parser.add_argument("path", nargs="?",
                        help=t("cli.help_path"))
    parser.add_argument(
        "--type", dest="review_types", default="best_practices",
        help=t("cli.help_type"),
    )
    parser.add_argument(
        "--review-pack",
        action="append",
        default=[],
        metavar="FILE",
        help=t("cli.help_review_pack"),
    )
    parser.add_argument("--list-type-presets", action="store_true",
                        help=t("cli.help_list_type_presets"))
    parser.add_argument("--spec-file", metavar="FILE",
                        help=t("cli.help_spec_file"))

    # ── backend ────────────────────────────────────────────────────────────
    parser.add_argument("--backend", choices=get_backend_choices(),
                        default=None,
                        help=t("cli.help_backend"))

    # ── language ───────────────────────────────────────────────────────────
    parser.add_argument("--lang", choices=["en", "ja", "default"], default="default",
                        help=t("cli.help_lang"))

    # ── output ─────────────────────────────────────────────────────────────
    parser.add_argument("--output", metavar="FILE",
                        help=t("cli.help_output"))

    # ── metadata ───────────────────────────────────────────────────────────
    parser.add_argument("--programmers", nargs="+", metavar="NAME",
                        help=t("cli.help_programmers"))
    parser.add_argument("--reviewers", nargs="+", metavar="NAME",
                        help=t("cli.help_reviewers"))

    # ── flags ──────────────────────────────────────────────────────────────
    parser.add_argument("--dry-run", action="store_true",
                        help=t("cli.help_dry_run"))
    parser.add_argument("--recommend-types", action="store_true",
                        help=t("cli.help_recommend_types"))
    parser.add_argument("--gui", action="store_true",
                        help=t("cli.help_gui"))
    parser.add_argument("--check-connection", action="store_true",
                        help=t("cli.help_check_connection"))
    parser.add_argument("--list-addons", action="store_true",
                        help=t("cli.help_list_addons"))

    args = parser.parse_args(argv)

    # ── logging setup ──────────────────────────────────────────────────────
    _setup_logging()

    # ── GUI shortcut ───────────────────────────────────────────────────────
    if args.gui:
        return _launch_gui()

    # ── profile commands ───────────────────────────────────────────────────
    if args.set_profile:
        set_profile_name(args.set_profile)
        return 0
    if args.clear_profile:
        clear_profile()
        return 0

    # ── connection check ───────────────────────────────────────────────────
    if args.check_connection:
        return _check_connection(args.backend)
    if args.list_addons:
        return _print_addons(addon_runtime)
    if args.list_type_presets:
        return _print_review_type_presets()

    # ── parse review types ─────────────────────────────────────────────────
    review_types = [] if args.recommend_types else _parse_review_types(args.review_types)

    # ── validation ─────────────────────────────────────────────────────────
    _validate_review_args(parser, args, review_types)

    # ── run ────────────────────────────────────────────────────────────────
    return _run_review(args, review_types, target_lang)


def _validate_review_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    review_types: list[str],
) -> None:
    """Validate semantic constraints on parsed arguments."""
    if args.scope == "diff" and not args.diff_file and not args.commits:
        parser.error("--diff-file or --commits required for diff scope")
    if args.scope == "diff" and args.diff_file and args.commits:
        parser.error("Cannot use both --diff-file and --commits")
    if args.scope == "project" and not args.path:
        parser.error("path is required for project scope")
    if args.recommend_types:
        return
    if not args.dry_run:
        if not args.programmers:
            parser.error("--programmers is required for a review")
        if not args.reviewers:
            parser.error("--reviewers is required for a review")
    if "specification" in review_types and not args.spec_file:
        parser.error("--spec-file required when using specification type")


def _run_review(args: argparse.Namespace, review_types: list[str], target_lang: str) -> int:
    """Create the backend, load the spec file if needed, and execute the review."""
    backend_name = args.backend or "bedrock"

    client = None
    if not args.dry_run or args.recommend_types:
        try:
            client = create_backend(backend_name)
        except Exception as exc:
            logger.error("Failed to create backend '%s': %s", backend_name, exc)
            return 1

    if args.recommend_types:
        result = recommend_review_types(
            path=args.path,
            scope=args.scope,
            diff_file=args.diff_file,
            commits=args.commits,
            target_lang=target_lang,
            client=client,
        )
        _print_console(t("cli.recommendation_header"))
        if result.recommended_preset:
            _print_console(t("cli.recommendation_preset", preset=result.recommended_preset))
        _print_console(t("cli.recommendation_types", types=", ".join(result.review_types)))
        if result.project_signals:
            _print_console(t("cli.recommendation_signals", signals="; ".join(result.project_signals)))
        for item in result.rationale:
            _print_console(f"- {item.review_type}: {item.reason}")
        return 0

    spec_content = None
    if args.spec_file and not args.dry_run:
        try:
            with open(args.spec_file, "r", encoding="utf-8") as fh:
                spec_content = fh.read()
        except FileNotFoundError:
            logger.error(t("cli.spec_not_found", path=args.spec_file))
            return 1
        except Exception as exc:
            logger.error(t("cli.spec_read_error", error=exc))
            return 1

    if client is None and not args.dry_run:
        logger.error("Failed to create backend '%s'; cannot run review.", backend_name)
        return 1

    runner = AppRunner(client, scan_fn=scan_project_with_scope, backend_name=backend_name)
    runner.run(
        path=args.path,
        scope=args.scope,
        diff_file=args.diff_file,
        commits=args.commits,
        review_types=review_types,
        spec_content=spec_content,
        target_lang=target_lang,
        programmers=args.programmers or [],
        reviewers=args.reviewers or [],
        dry_run=args.dry_run,
        output_file=args.output,
    )
    return 0


def _build_tool_parser() -> argparse.ArgumentParser:
    """Build the non-interactive tool-mode parser."""
    parser = argparse.ArgumentParser(
        description="Non-interactive tool mode for AICodeReviewer",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    review_parser = subparsers.add_parser(
        "review",
        help="Run a non-interactive review and emit JSON",
    )
    _add_common_review_args(review_parser)
    _add_runtime_override_args(review_parser)

    health_parser = subparsers.add_parser(
        "health",
        help="Run backend health checks and emit JSON",
    )
    health_parser.add_argument(
        "--backend",
        choices=get_backend_choices(),
        default=None,
        help="Backend override",
    )
    health_parser.add_argument(
        "--lang",
        choices=["en", "ja", "default"],
        default="default",
        help="Output language",
    )
    health_parser.add_argument(
        "--json-out",
        metavar="FILE",
        help="Optional path to also write the JSON result",
    )
    _add_runtime_override_args(health_parser)

    fix_plan_parser = subparsers.add_parser(
        "fix-plan",
        help="Generate a non-interactive AI fix plan from a review artifact",
    )
    fix_plan_parser.add_argument("--report-file", required=True, metavar="FILE")
    fix_plan_parser.add_argument("--issue-id", action="append", dest="issue_ids", default=[])
    fix_plan_parser.add_argument(
        "--backend",
        choices=get_backend_choices(),
        default=None,
    )
    fix_plan_parser.add_argument("--lang", choices=["en", "ja", "default"], default="default")
    fix_plan_parser.add_argument("--json-out", metavar="FILE")
    _add_runtime_override_args(fix_plan_parser)

    apply_fixes_parser = subparsers.add_parser(
        "apply-fixes",
        help="Apply generated fixes from a fix-plan artifact",
    )
    apply_fixes_parser.add_argument("--plan-file", required=True, metavar="FILE")
    apply_fixes_parser.add_argument("--issue-id", action="append", dest="issue_ids", default=[])
    apply_fixes_parser.add_argument("--json-out", metavar="FILE")

    resume_parser = subparsers.add_parser(
        "resume",
        help="Normalize an existing tool artifact into resumable workflow state",
    )
    resume_parser.add_argument("--artifact-file", required=True, metavar="FILE")
    resume_parser.add_argument("--issue-id", action="append", dest="issue_ids", default=[])
    resume_parser.add_argument("--json-out", metavar="FILE")

    serve_api_parser = subparsers.add_parser(
        "serve-api",
        help="Run the local HTTP API service",
    )
    serve_api_parser.add_argument("--host", default="127.0.0.1", metavar="HOST")
    serve_api_parser.add_argument("--port", type=int, default=8765, metavar="PORT")
    serve_api_parser.add_argument("--max-concurrent-jobs", type=int, default=1, metavar="COUNT")
    serve_api_parser.add_argument("--review-pack", action="append", default=[], metavar="FILE")
    _add_runtime_override_args(serve_api_parser)

    analyze_repo_parser = subparsers.add_parser(
        "analyze-repo",
        help="Analyze a repository and generate a preview addon scaffold",
    )
    analyze_repo_parser.add_argument("path", metavar="PATH")
    analyze_repo_parser.add_argument("--output-dir", required=True, metavar="DIR")
    analyze_repo_parser.add_argument("--addon-id", metavar="ID")
    analyze_repo_parser.add_argument("--addon-name", metavar="NAME")
    analyze_repo_parser.add_argument("--json-out", metavar="FILE")

    return parser


def _add_common_review_args(parser: argparse.ArgumentParser) -> None:
    """Add shared review arguments for tool-mode commands."""
    parser.add_argument("path", nargs="?", help="Project directory for project-scope reviews")
    parser.add_argument("--scope", choices=["project", "diff"], default="project")
    parser.add_argument("--diff-file", metavar="FILE")
    parser.add_argument("--commits", metavar="RANGE")
    parser.add_argument("--type", dest="review_types", default="best_practices")
    parser.add_argument("--review-pack", action="append", default=[], metavar="FILE")
    parser.add_argument("--spec-file", metavar="FILE")
    parser.add_argument(
        "--backend",
        choices=get_backend_choices(),
        default=None,
    )
    parser.add_argument("--lang", choices=["en", "ja", "default"], default="default")
    parser.add_argument("--output", metavar="FILE")
    parser.add_argument("--programmers", nargs="+", metavar="NAME")
    parser.add_argument("--reviewers", nargs="+", metavar="NAME")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recommend-types", action="store_true")
    parser.add_argument("--json-out", metavar="FILE")
    parser.add_argument("--cancel-file", metavar="FILE")
    parser.add_argument("--timeout-seconds", type=float)


def _add_runtime_override_args(parser: argparse.ArgumentParser) -> None:
    """Add runtime configuration override flags for tool-mode commands."""
    parser.add_argument("--model", metavar="MODEL")
    parser.add_argument("--region", metavar="REGION")
    parser.add_argument("--api-url", metavar="URL")
    parser.add_argument("--api-type", metavar="TYPE")
    parser.add_argument("--local-model", metavar="MODEL")
    local_web_search_group = parser.add_mutually_exclusive_group()
    local_web_search_group.add_argument(
        "--local-enable-web-search",
        dest="local_enable_web_search",
        action="store_true",
        default=None,
        help="Enable Local LLM prompt enrichment with public web guidance for this invocation",
    )
    local_web_search_group.add_argument(
        "--local-disable-web-search",
        dest="local_enable_web_search",
        action="store_false",
        help="Disable Local LLM prompt enrichment with public web guidance for this invocation",
    )
    parser.add_argument("--copilot-model", metavar="MODEL")
    parser.add_argument("--kiro-cli-command", metavar="CMD")
    parser.add_argument("--timeout", type=float, metavar="SECONDS")


def _run_tool_command(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    target_lang: str,
) -> int:
    """Dispatch a tool-mode subcommand."""
    if args.command == "review":
        review_types = [] if args.recommend_types else _parse_review_types(args.review_types)
        _validate_review_args(parser, args, review_types)
        return _run_review_tool_mode(args, review_types, target_lang)
    if args.command == "health":
        return _run_health_tool_mode(args)
    if args.command == "fix-plan":
        return _run_fix_plan_tool_mode(args)
    if args.command == "apply-fixes":
        return _run_apply_fixes_tool_mode(args)
    if args.command == "resume":
        return _run_resume_tool_mode(args)
    if args.command == "serve-api":
        return _run_serve_api_tool_mode(args)
    if args.command == "analyze-repo":
        return _run_analyze_repo_tool_mode(args)
    raise ValueError(f"Unsupported tool command: {args.command}")


def _run_analyze_repo_tool_mode(args: argparse.Namespace) -> int:
    """Analyze a repository and emit a generated addon preview envelope."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "analyze-repo",
        "path": args.path,
        "output_dir": args.output_dir,
        "success": False,
        "exit_code": EXIT_FAILURE,
    }

    context_logger = logging.getLogger("aicodereviewer.context_collector")
    previous_context_level = context_logger.level
    try:
        context_logger.setLevel(logging.WARNING)
        preview = generate_addon_preview(
            args.path,
            args.output_dir,
            addon_id=args.addon_id,
            addon_name=args.addon_name,
        )
    except Exception as exc:
        payload.update({
            "status": "error",
            "error": _error_payload(str(exc), diagnostic=diagnostic_from_exception(exc, origin="analyze_repo")),
        })
        context_logger.setLevel(previous_context_level)
        _write_json_result(payload, args.json_out)
        return EXIT_FAILURE

    context_logger.setLevel(previous_context_level)
    payload.update({
        "status": "generated",
        "success": True,
        "exit_code": EXIT_OK,
        "addon_id": preview.addon_id,
        "addon_name": preview.addon_name,
        "addon_root": str(preview.addon_root),
        "manifest_path": str(preview.manifest_path),
        "review_pack_path": str(preview.review_pack_path),
        "capability_profile_path": str(preview.capability_profile_path),
        "summary_path": str(preview.summary_path),
        "generated_review_key": preview.review_key,
        "generated_preset_key": preview.preset_key,
        "profile": preview.profile.to_dict(),
        "preview_only": True,
    })
    _write_json_result(payload, args.json_out)
    return EXIT_OK


def _run_serve_api_tool_mode(args: argparse.Namespace) -> int:
    """Run the local HTTP API on the configured host and port."""
    _apply_runtime_overrides(args)
    app = create_local_http_app(max_concurrent_jobs=args.max_concurrent_jobs)
    logger.info("Starting local HTTP API on http://%s:%s", args.host, args.port)
    run_local_http_server(app, host=args.host, port=args.port)
    return 0


def _apply_runtime_overrides(args: argparse.Namespace) -> str:
    """Apply per-invocation config overrides and return the effective backend."""
    requested_backend = args.backend or config.get("backend", "type", "bedrock")
    backend_name, backend_overrides = resolve_backend_type(requested_backend)

    if args.backend or requested_backend != backend_name:
        config.set_value("backend", "type", backend_name)
    if backend_overrides.get("api_type"):
        config.set_value("local_llm", "api_type", backend_overrides["api_type"])
    if args.model:
        config.set_value("model", "model_id", args.model)
    if args.region:
        config.set_value("aws", "region", args.region)
    if args.api_url:
        config.set_value("local_llm", "api_url", args.api_url)
    if args.api_type:
        config.set_value("local_llm", "api_type", args.api_type)
    if args.local_model:
        config.set_value("local_llm", "model", args.local_model)
    if args.local_enable_web_search is not None:
        config.set_value(
            "local_llm",
            "enable_web_search",
            "true" if args.local_enable_web_search else "false",
        )
    if args.copilot_model:
        config.set_value("copilot", "model", args.copilot_model)
    if args.kiro_cli_command:
        config.set_value("kiro", "cli_command", args.kiro_cli_command)
    if args.timeout is not None:
        timeout_value = str(args.timeout)
        config.set_value("performance", "api_timeout_seconds", timeout_value)
        if backend_name == "kiro":
            config.set_value("kiro", "timeout", timeout_value)
        elif backend_name == "copilot":
            config.set_value("copilot", "timeout", timeout_value)
        elif backend_name == "local":
            config.set_value("local_llm", "timeout", timeout_value)

    return backend_name


def _build_cancel_check(
    cancel_file: str | None,
    timeout_seconds: float | None,
) -> tuple[Callable[[], bool], Callable[[], str | None]]:
    """Create a cancellable predicate backed by a file sentinel or timeout."""
    started_at = time.monotonic()
    cancel_path = Path(cancel_file) if cancel_file else None
    reason: str | None = None

    def check() -> bool:
        nonlocal reason
        if reason is not None:
            return True
        if cancel_path and cancel_path.exists():
            reason = f"cancel_file:{cancel_path}"
            return True
        if timeout_seconds is not None and (time.monotonic() - started_at) >= timeout_seconds:
            reason = "timeout"
            return True
        return False

    return check, lambda: reason


def _assign_issue_ids(issues: list[ReviewIssue]) -> None:
    """Assign stable issue IDs for machine-readable tool workflows."""
    for index, issue in enumerate(issues, 1):
        if issue.issue_id:
            continue
        issue.issue_id = f"issue-{index:04d}"


def _serialize_issue(issue: ReviewIssue) -> dict[str, Any]:
    """Convert a review issue into a JSON-safe dictionary."""
    payload = dict(issue.__dict__)
    if issue.resolved_at is not None:
        payload["resolved_at"] = issue.resolved_at.isoformat()
    return payload


def _load_json_artifact(artifact_path: str) -> dict[str, Any]:
    """Load a JSON artifact from disk."""
    with open(artifact_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Artifact must contain a JSON object: {artifact_path}")
    return cast(dict[str, Any], data)


def _load_report_from_artifact(artifact_path: str) -> ReviewReport:
    """Load a review report from either a raw report file or review envelope."""
    artifact = _load_json_artifact(artifact_path)
    if isinstance(artifact.get("report"), dict):
        return ReviewReport.from_dict(artifact["report"])
    if "issues_found" in artifact and "project_path" in artifact:
        return ReviewReport.from_dict(artifact)
    raise ValueError(f"Unsupported review artifact format: {artifact_path}")


def _artifact_kind(artifact: dict[str, Any]) -> str:
    """Infer the artifact kind from a loaded JSON object."""
    command = artifact.get("command")
    if isinstance(command, str) and command:
        return command
    if "issues_found" in artifact and "project_path" in artifact:
        return "review-report"
    raise ValueError("Unsupported artifact: command/type could not be determined")


def _flatten_issue_ids(raw_issue_ids: list[str] | None) -> list[str]:
    """Normalize repeated --issue-id flags into a clean list."""
    if not raw_issue_ids:
        return []
    return [issue_id.strip() for issue_id in raw_issue_ids if issue_id and issue_id.strip()]


def _select_issue_ids(issues: list[ReviewIssue], selected_ids: list[str]) -> list[ReviewIssue]:
    """Return either all issues or the selected issue subset."""
    _assign_issue_ids(issues)
    if not selected_ids:
        return issues
    selected = {issue_id for issue_id in selected_ids}
    return [issue for issue in issues if issue.issue_id in selected]


def _normalize_review_resume_state(
    artifact: dict[str, Any],
    selected_ids: list[str],
) -> dict[str, Any]:
    """Build canonical resume state from a review report or review envelope."""
    raw_report = artifact.get("report", artifact)
    if raw_report is None:
        return {
            "workflow_stage": "dry-run" if artifact.get("status") == "dry_run" else "reviewed",
            "next_command": None,
            "can_resume": False,
            "project_path": artifact.get("path"),
            "backend": artifact.get("backend"),
            "language": artifact.get("language"),
            "review_types": list(cast(list[str], artifact.get("review_types", []))),
            "issue_count": 0,
            "issues": [],
            "pending_issue_ids": [],
            "selected_issue_ids": selected_ids,
            "report": None,
            "files_scanned": artifact.get("files_scanned", 0),
            "target_paths": list(cast(list[str], artifact.get("target_paths", []))),
        }

    report = ReviewReport.from_dict(cast(dict[str, Any], raw_report))
    issues = list(report.issues_found)
    selected_issues = _select_issue_ids(issues, selected_ids)
    issue_payloads = [_serialize_issue(issue) for issue in selected_issues]
    pending_ids = [issue["issue_id"] for issue in issue_payloads if issue.get("status") == "pending"]

    return {
        "workflow_stage": "reviewed",
        "next_command": "fix-plan",
        "can_resume": True,
        "project_path": report.project_path,
        "backend": report.backend,
        "language": report.language,
        "review_types": list(report.review_types) if report.review_types else [report.review_type],
        "issue_count": len(issue_payloads),
        "issues": issue_payloads,
        "pending_issue_ids": pending_ids,
        "selected_issue_ids": selected_ids,
        "report": report.to_dict(),
    }


def _normalize_fix_plan_resume_state(
    artifact: dict[str, Any],
    selected_ids: list[str],
) -> dict[str, Any]:
    """Build canonical resume state from a fix-plan artifact."""
    fixes_raw = artifact.get("fixes", [])
    if not isinstance(fixes_raw, list):
        raise ValueError("Fix-plan artifact must contain a 'fixes' list")

    selected_set = set(selected_ids)
    fixes: list[dict[str, Any]] = []
    for item in cast(list[Any], fixes_raw):
        if not isinstance(item, dict):
            continue
        fix_item = cast(dict[str, Any], item)
        issue_id = fix_item.get("issue_id")
        if selected_set and issue_id not in selected_set:
            continue
        fixes.append(dict(fix_item))

    generated_ids = [str(fix.get("issue_id", "")) for fix in fixes if fix.get("status") == "generated"]
    failed_ids = [str(fix.get("issue_id", "")) for fix in fixes if fix.get("status") == "failed"]
    failed_diagnostics = _collect_failed_resume_diagnostics(fixes)

    return {
        "workflow_stage": "fix-planned",
        "next_command": "apply-fixes" if generated_ids else None,
        "can_resume": bool(generated_ids),
        "backend": artifact.get("backend"),
        "report_file": artifact.get("report_file"),
        "issue_count": len(fixes),
        "fix_count": len(fixes),
        "fixes": fixes,
        "generated_issue_ids": generated_ids,
        "failed_issue_ids": failed_ids,
        "failed_diagnostics": failed_diagnostics,
        "failed_diagnostic_categories": _summarize_failed_resume_categories(failed_diagnostics),
        "selected_issue_ids": selected_ids,
    }


def _normalize_apply_results_resume_state(
    artifact: dict[str, Any],
    selected_ids: list[str],
) -> dict[str, Any]:
    """Build canonical resume state from an apply-fixes artifact."""
    results_raw = artifact.get("results", [])
    if not isinstance(results_raw, list):
        raise ValueError("Apply-fixes artifact must contain a 'results' list")

    selected_set = set(selected_ids)
    results: list[dict[str, Any]] = []
    for item in cast(list[Any], results_raw):
        if not isinstance(item, dict):
            continue
        result_item = cast(dict[str, Any], item)
        issue_id = result_item.get("issue_id")
        if selected_set and issue_id not in selected_set:
            continue
        results.append(dict(result_item))

    applied_ids = [str(result.get("issue_id", "")) for result in results if result.get("status") == "applied"]
    failed_ids = [str(result.get("issue_id", "")) for result in results if result.get("status") == "failed"]
    failed_diagnostics = _collect_failed_resume_diagnostics(results)

    return {
        "workflow_stage": "fixes-applied",
        "next_command": None,
        "can_resume": False,
        "plan_file": artifact.get("plan_file"),
        "result_count": len(results),
        "results": results,
        "applied_issue_ids": applied_ids,
        "failed_issue_ids": failed_ids,
        "failed_diagnostics": failed_diagnostics,
        "failed_diagnostic_categories": _summarize_failed_resume_categories(failed_diagnostics),
        "selected_issue_ids": selected_ids,
    }


def _collect_failed_resume_diagnostics(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract compact failed-item diagnostics for resume output."""
    diagnostics: list[dict[str, Any]] = []
    for item in items:
        if item.get("status") != "failed":
            continue
        raw_diagnostic = item.get("diagnostic")
        if not isinstance(raw_diagnostic, dict):
            continue
        diagnostic = cast(dict[str, Any], raw_diagnostic)
        payload: dict[str, Any] = {
            "issue_id": item.get("issue_id"),
            "file_path": item.get("file_path"),
            "category": diagnostic.get("category"),
            "origin": diagnostic.get("origin"),
            "detail": diagnostic.get("detail"),
            "fix_hint": diagnostic.get("fix_hint"),
        }
        if diagnostic.get("exception_type") is not None:
            payload["exception_type"] = diagnostic.get("exception_type")
        if diagnostic.get("retryable") is not None:
            payload["retryable"] = bool(diagnostic.get("retryable"))
        if diagnostic.get("retry_delay_seconds") is not None:
            payload["retry_delay_seconds"] = diagnostic.get("retry_delay_seconds")
        diagnostics.append(payload)
    return diagnostics


def _summarize_failed_resume_categories(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize failed resume diagnostics by category for automation-friendly output."""
    counts: dict[str, int] = {}
    for diagnostic in diagnostics:
        category = str(diagnostic.get("category") or "provider")
        counts[category] = counts.get(category, 0) + 1
    return [
        {"category": category, "count": count}
        for category, count in sorted(counts.items())
    ]


def _serialize_health_report(report: HealthReport) -> dict[str, Any]:
    """Convert a backend health report to a JSON-safe dictionary."""
    return {
        "backend": report.backend,
        "ready": report.ready,
        "summary": report.summary,
        "failure_categories": list(getattr(report, "failure_categories", []) or []),
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "detail": check.detail,
                "fix_hint": check.fix_hint,
                "category": getattr(check, "category", "none"),
                "origin": getattr(check, "origin", "prerequisite"),
            }
            for check in report.checks
        ],
    }


def _write_json_result(payload: dict[str, Any], output_file: str | None = None) -> None:
    """Emit structured JSON to stdout and optionally persist a copy."""
    rendered = json.dumps(payload, ensure_ascii=False)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
    _print_console(rendered)


def _error_payload(message: str, *, diagnostic: FailureDiagnostic | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message}
    if diagnostic is not None:
        payload["diagnostic"] = diagnostic.to_dict()
    return payload


def _configuration_diagnostic(detail: str, *, origin: str) -> FailureDiagnostic:
    message = detail.strip() or "Configuration error"
    return FailureDiagnostic(
        category="configuration",
        origin=origin,
        detail=message,
        fix_hint=failure_fix_hint("configuration"),
    )


def _fix_item_payload(
    issue: ReviewIssue,
    *,
    status: str,
    proposed_content: str | None,
    diagnostic: FailureDiagnostic | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "issue_id": issue.issue_id,
        "file_path": issue.file_path,
        "issue_type": issue.issue_type,
        "severity": issue.severity,
        "description": issue.description,
        "status": status,
        "proposed_content": proposed_content,
    }
    if diagnostic is not None:
        payload["diagnostic"] = diagnostic.to_dict()
    return payload


def _apply_fix_to_file(file_path: str, fixed_content: str) -> str:
    """Write fixed content to disk after creating a .backup copy."""
    backup_path = f"{file_path}.backup"
    shutil.copy2(file_path, backup_path)
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(fixed_content)
    return backup_path


def _load_spec_content(spec_file: str | None, dry_run: bool) -> str | None:
    """Read specification review content when required."""
    if not spec_file or dry_run:
        return None

    try:
        with open(spec_file, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        logger.error(t("cli.spec_not_found", path=spec_file))
        return None
    except Exception as exc:
        logger.error(t("cli.spec_read_error", error=exc))
        return None


def _run_review_tool_mode(
    args: argparse.Namespace,
    review_types: list[str],
    target_lang: str,
) -> int:
    """Run non-interactive review mode and emit a structured JSON envelope."""
    backend_name = _apply_runtime_overrides(args)
    cancel_check, get_cancel_reason = _build_cancel_check(args.cancel_file, args.timeout_seconds)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "review",
        "backend": backend_name,
        "dry_run": bool(args.dry_run),
        "review_types": list(review_types),
        "scope": args.scope,
        "path": args.path,
        "success": False,
        "exit_code": EXIT_FAILURE,
    }

    client = None
    try:
        if not args.dry_run or args.recommend_types:
            client = create_backend(backend_name)

        if args.recommend_types:
            recommendation = recommend_review_types(
                path=args.path,
                scope=args.scope,
                diff_file=args.diff_file,
                commits=args.commits,
                target_lang=target_lang,
                client=client,
            )
            payload.update({
                "status": "recommended",
                "success": True,
                "exit_code": EXIT_OK,
                "recommended_review_types": list(recommendation.review_types),
                "recommended_preset": recommendation.recommended_preset,
                "project_signals": list(recommendation.project_signals),
                "rationale": [
                    {"review_type": item.review_type, "reason": item.reason}
                    for item in recommendation.rationale
                ],
                "source": recommendation.source,
                "review_types": list(recommendation.review_types),
            })
            _write_json_result(payload, args.json_out)
            return EXIT_OK

        spec_content = _load_spec_content(args.spec_file, args.dry_run)
        if args.spec_file and not args.dry_run and spec_content is None:
            message = f"Failed to read spec file: {args.spec_file}"
            payload.update({
                "status": "error",
                "error": _error_payload(
                    message,
                    diagnostic=_configuration_diagnostic(message, origin="review"),
                ),
            })
            _write_json_result(payload, args.json_out)
            return EXIT_FAILURE

        runner = AppRunner(client, scan_fn=scan_project_with_scope, backend_name=backend_name)
        result = runner.run(
            path=args.path,
            scope=args.scope,
            diff_file=args.diff_file,
            commits=args.commits,
            review_types=review_types,
            spec_content=spec_content,
            target_lang=target_lang,
            programmers=args.programmers or [],
            reviewers=args.reviewers or [],
            dry_run=args.dry_run,
            output_file=args.output,
            interactive=False,
            cancel_check=cancel_check,
        )

        if cancel_check():
            payload.update({
                "status": "cancelled",
                "success": False,
                "exit_code": EXIT_CANCELLED,
                "cancel_reason": get_cancel_reason(),
            })
            _write_json_result(payload, args.json_out)
            return EXIT_CANCELLED

        execution = getattr(runner, "last_execution", None)
        if callable(execution):
            execution = execution()

        run_state: dict[str, Any]
        if execution is not None:
            run_state = {
                "files_scanned": getattr(execution, "files_scanned", 0),
                "target_paths": list(getattr(execution, "target_paths", []) or []),
                "status": getattr(execution, "status", "completed"),
                "tool_access_audit": (
                    execution.tool_access_audit.to_dict()
                    if getattr(execution, "tool_access_audit", None) is not None
                    and hasattr(execution.tool_access_audit, "to_dict")
                    else getattr(execution, "tool_access_audit", None)
                ),
            }
        else:
            raw_run_state = getattr(runner, "execution_summary", None)
            if callable(raw_run_state):
                raw_run_state = raw_run_state()
            run_state = cast(dict[str, Any], raw_run_state or {})
        payload.update({
            "files_scanned": run_state.get("files_scanned", 0),
            "target_paths": run_state.get("target_paths", []),
            "status": run_state.get("status", "completed"),
            "tool_access_audit": run_state.get("tool_access_audit"),
        })

        if args.dry_run:
            payload.update({
                "success": True,
                "exit_code": EXIT_OK,
                "report_path": None,
                "issue_count": 0,
                "issues": [],
                "report": None,
            })
            _write_json_result(payload, args.json_out)
            return EXIT_OK

        if isinstance(result, list):
            _assign_issue_ids(result)
            report = runner.build_report(result)
            report_path = runner.generate_report(result, args.output) if args.output else None
            payload.update({
                "status": "completed",
                "success": True,
                "exit_code": EXIT_OK,
                "issue_count": len(result),
                "issues": [_serialize_issue(issue) for issue in result],
                "report": report.to_dict() if report is not None else None,
                "report_path": report_path,
            })
            _write_json_result(payload, args.json_out)
            return EXIT_OK

        payload.update({
            "success": True,
            "exit_code": EXIT_OK,
            "issue_count": 0,
            "issues": [],
            "report": None,
            "report_path": None,
        })
        _write_json_result(payload, args.json_out)
        return EXIT_OK
    except Exception as exc:
        logger.error("Tool review failed: %s", exc)
        diagnostic = diagnostic_from_exception(exc, origin="review")
        payload.update({
            "status": "error",
            "error": _error_payload(str(exc), diagnostic=diagnostic),
        })
        _write_json_result(payload, args.json_out)
        return EXIT_FAILURE


def _run_fix_plan_tool_mode(args: argparse.Namespace) -> int:
    """Generate AI fixes for issues in a review artifact without writing files."""
    backend_name = _apply_runtime_overrides(args)
    selected_ids = _flatten_issue_ids(args.issue_ids)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "fix-plan",
        "backend": backend_name,
        "report_file": args.report_file,
        "selected_issue_ids": selected_ids,
        "success": False,
        "exit_code": EXIT_FAILURE,
    }

    try:
        report = _load_report_from_artifact(args.report_file)
        issues = list(report.issues_found)
        selected_issues = _select_issue_ids(issues, selected_ids)
        if not selected_issues:
            payload.update({
                "status": "no_matching_issues",
                "issue_count": 0,
                "fixes": [],
            })
            _write_json_result(payload, args.json_out)
            return EXIT_FAILURE

        client = create_backend(backend_name)
        fixes: list[dict[str, Any]] = []
        generated_count = 0
        failed_count = 0

        for issue in selected_issues:
            review_type = issue.issue_type or (report.review_types[0] if report.review_types else report.review_type)
            fix_result = generate_ai_fix_result(issue, client, review_type, report.language)
            if fix_result.ok:
                generated_count += 1
                fixes.append(
                    _fix_item_payload(
                        issue,
                        status="generated",
                        proposed_content=fix_result.content,
                    )
                )
            else:
                failed_count += 1
                fixes.append(
                    _fix_item_payload(
                        issue,
                        status="failed",
                        proposed_content=None,
                        diagnostic=fix_result.diagnostic,
                    )
                )

        success = generated_count > 0
        payload.update({
            "status": "completed" if failed_count == 0 else "partial",
            "success": success,
            "exit_code": EXIT_OK if success else EXIT_FAILURE,
            "issue_count": len(selected_issues),
            "generated_count": generated_count,
            "failed_count": failed_count,
            "fixes": fixes,
        })
        _write_json_result(payload, args.json_out)
        return EXIT_OK if success else EXIT_FAILURE
    except Exception as exc:
        logger.error("Tool fix-plan failed: %s", exc)
        diagnostic = diagnostic_from_exception(exc, origin="fix_plan")
        payload.update({
            "status": "error",
            "error": _error_payload(str(exc), diagnostic=diagnostic),
        })
        _write_json_result(payload, args.json_out)
        return EXIT_FAILURE


def _run_apply_fixes_tool_mode(args: argparse.Namespace) -> int:
    """Apply selected fixes from a fix-plan artifact to disk with backups."""
    selected_ids = _flatten_issue_ids(args.issue_ids)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "apply-fixes",
        "plan_file": args.plan_file,
        "selected_issue_ids": selected_ids,
        "success": False,
        "exit_code": EXIT_FAILURE,
    }

    try:
        plan = _load_json_artifact(args.plan_file)
        fixes_raw = plan.get("fixes", [])
        if not isinstance(fixes_raw, list):
            raise ValueError("Fix-plan artifact must contain a 'fixes' list")

        selected_set = set(selected_ids)
        applicable_fixes: list[dict[str, Any]] = []
        for item in cast(list[Any], fixes_raw):
            if not isinstance(item, dict):
                continue
            fix_item = cast(dict[str, Any], item)
            issue_id = fix_item.get("issue_id")
            status = fix_item.get("status")
            if selected_set and issue_id not in selected_set:
                continue
            if status != "generated":
                continue
            applicable_fixes.append(fix_item)

        if not applicable_fixes:
            payload.update({
                "status": "no_applicable_fixes",
                "applied_count": 0,
                "results": [],
            })
            _write_json_result(payload, args.json_out)
            return EXIT_FAILURE

        results: list[dict[str, Any]] = []
        applied_count = 0
        failed_count = 0
        for item in applicable_fixes:
            issue_id = str(item.get("issue_id", ""))
            file_path = str(item.get("file_path", ""))
            proposed_content = item.get("proposed_content")
            try:
                if not file_path or not isinstance(proposed_content, str):
                    raise ValueError("Fix entry is missing file_path or proposed_content")
                backup_path = _apply_fix_to_file(file_path, proposed_content)
                applied_count += 1
                results.append({
                    "issue_id": issue_id,
                    "file_path": file_path,
                    "status": "applied",
                    "backup_path": backup_path,
                })
            except Exception as exc:
                failed_count += 1
                diagnostic = (
                    build_failure_diagnostic(
                        category="configuration",
                        origin="apply_fix_item",
                        detail=str(exc),
                        exception_type=type(exc).__name__,
                    )
                    if isinstance(exc, FileNotFoundError)
                    else diagnostic_from_exception(exc, origin="apply_fix_item")
                )
                results.append({
                    "issue_id": issue_id,
                    "file_path": file_path,
                    "status": "failed",
                    "error": str(exc),
                    "diagnostic": diagnostic.to_dict(),
                })

        success = applied_count > 0 and failed_count == 0
        payload.update({
            "status": "completed" if failed_count == 0 else "partial",
            "success": success,
            "exit_code": EXIT_OK if success else EXIT_FAILURE,
            "applied_count": applied_count,
            "failed_count": failed_count,
            "results": results,
        })
        _write_json_result(payload, args.json_out)
        return EXIT_OK if success else EXIT_FAILURE
    except Exception as exc:
        logger.error("Tool apply-fixes failed: %s", exc)
        diagnostic = diagnostic_from_exception(exc, origin="apply_fixes")
        payload.update({
            "status": "error",
            "error": _error_payload(str(exc), diagnostic=diagnostic),
        })
        _write_json_result(payload, args.json_out)
        return EXIT_FAILURE


def _run_health_tool_mode(args: argparse.Namespace) -> int:
    """Run backend health checks and emit a structured JSON envelope."""
    backend_name = _apply_runtime_overrides(args)

    try:
        report = check_backend(backend_name)
        exit_code = EXIT_OK if report.ready else EXIT_FAILURE
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "command": "health",
            "success": report.ready,
            "exit_code": exit_code,
            **_serialize_health_report(report),
        }
        _write_json_result(payload, args.json_out)
        return exit_code
    except Exception as exc:
        logger.error("Tool health check failed: %s", exc)
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "command": "health",
            "backend": backend_name,
            "success": False,
            "exit_code": EXIT_FAILURE,
            "status": "error",
            "error": {"message": str(exc)},
        }
        _write_json_result(payload, args.json_out)
        return EXIT_FAILURE


def _run_resume_tool_mode(args: argparse.Namespace) -> int:
    """Normalize an artifact into resumable tool-mode workflow state."""
    selected_ids = _flatten_issue_ids(args.issue_ids)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "command": "resume",
        "artifact_file": args.artifact_file,
        "selected_issue_ids": selected_ids,
        "success": False,
        "exit_code": EXIT_FAILURE,
    }

    try:
        artifact = _load_json_artifact(args.artifact_file)
        artifact_type = _artifact_kind(artifact)

        if artifact_type in {"review", "review-report"}:
            state = _normalize_review_resume_state(artifact, selected_ids)
        elif artifact_type == "fix-plan":
            state = _normalize_fix_plan_resume_state(artifact, selected_ids)
        elif artifact_type == "apply-fixes":
            state = _normalize_apply_results_resume_state(artifact, selected_ids)
        else:
            raise ValueError(f"Unsupported artifact type for resume: {artifact_type}")

        payload.update({
            "status": "completed",
            "success": True,
            "exit_code": EXIT_OK,
            "artifact_type": artifact_type,
            **state,
        })
        _write_json_result(payload, args.json_out)
        return EXIT_OK
    except Exception as exc:
        logger.error("Tool resume failed: %s", exc)
        payload.update({
            "status": "error",
            "error": {"message": str(exc)},
        })
        _write_json_result(payload, args.json_out)
        return EXIT_FAILURE


# ── helpers ────────────────────────────────────────────────────────────────

def _parse_review_types(raw: str) -> list[str]:
    """
    Parse a comma-separated (or 'all') review type string.

    Returns a validated and deduplicated list.
    """
    review_registry = get_review_registry()
    parts = [p.strip().lower() for p in raw.replace("+", ",").split(",") if p.strip()]
    if "all" in parts:
        return list(review_registry.visible_keys())
    seen: set[str] = set()
    result: list[str] = []
    for p in parts:
        try:
            preset_key = resolve_review_preset_key(p)
        except KeyError:
            preset_key = None
        if preset_key is not None:
            for review_type in REVIEW_TYPE_PRESETS[preset_key]:
                if review_type not in seen:
                    result.append(review_type)
                    seen.add(review_type)
            continue
        try:
            resolved_key = review_registry.resolve_key(p)
        except KeyError:
            logger.warning(t("cli.unknown_type", type=p))
            continue
        if resolved_key not in seen and review_registry.get(resolved_key).selectable:
            result.append(resolved_key)
            seen.add(resolved_key)
    return result or ["best_practices"]


def _check_connection(backend_name: str | None) -> int:
    """Test connectivity for the selected backend with diagnostic output."""
    from aicodereviewer.config import config as _cfg

    backend_name, _backend_overrides = resolve_backend_type(
        backend_name or _cfg.get("backend", "type", "bedrock")
    )
    _print_console(t("conn.checking", backend=backend_name))

    diagnostic: dict[str, Any] | None = None
    try:
        client = create_backend(backend_name)
        diagnostic_getter = getattr(client, "validate_connection_diagnostic", None)
        if callable(diagnostic_getter):
            raw_diagnostic = diagnostic_getter()
            diagnostic = cast(dict[str, Any], raw_diagnostic) if isinstance(raw_diagnostic, dict) else None
            ok = bool(diagnostic and diagnostic.get("ok"))
        else:
            ok = client.validate_connection()
    except Exception as exc:
        ok = False
        diagnostic = {
            "category": "provider",
            "detail": str(exc),
            "fix_hint": t("health.hint_conn_test"),
            "origin": "connection_test",
        }
        logger.error("%s", exc)

    if ok:
        _print_console(t("conn.success"))
        # Show extra details per backend
        if backend_name == "bedrock":
            model = _cfg.get("model", "model_id", "")
            region = _cfg.get("aws", "region", "")
            _print_console(t("conn.details_model", model=model))
            _print_console(t("conn.details_region", region=region))
        elif backend_name == "local":
            url = _cfg.get("local_llm", "api_url", "")
            model = _cfg.get("local_llm", "model", "")
            _print_console(t("conn.details_url", url=url))
            _print_console(t("conn.details_model", model=model))
        return 0
    else:
        _print_console(t("conn.failure"))
        if diagnostic:
            category = str(diagnostic.get("category") or "unknown")
            origin = str(diagnostic.get("origin") or "connection_test")
            detail = str(diagnostic.get("detail") or "").strip()
            fix_hint = str(diagnostic.get("fix_hint") or "").strip()
            retryable = bool(diagnostic.get("retryable"))
            retry_delay_seconds = diagnostic.get("retry_delay_seconds")
            _print_console(t("conn.category", category=category.replace("_", " ")))
            _print_console(t("conn.origin", origin=origin.replace("_", " ")))
            if detail:
                _print_console(t("conn.detail", detail=detail))
            if fix_hint:
                _print_console(t("conn.fix_hint", fix_hint=fix_hint))
            if retryable:
                if isinstance(retry_delay_seconds, int) and retry_delay_seconds > 0:
                    _print_console(t("conn.retry_after", seconds=retry_delay_seconds))
                else:
                    _print_console(t("conn.retry"))
        # Provide helpful hints
        if backend_name == "bedrock":
            _print_console(t("conn.hint_bedrock_sso"))
            _print_console(t("conn.hint_bedrock_profile"))
            _print_console(t("conn.hint_bedrock_model"))
        elif backend_name == "kiro":
            _print_console(t("conn.hint_kiro_wsl"))
            _print_console(t("conn.hint_kiro_cli"))
        elif backend_name == "copilot":
            _print_console(t("conn.hint_copilot_install"))
            _print_console(t("conn.hint_copilot_auth"))
        elif backend_name == "local":
            _print_console(t("conn.hint_local_url"))
            _print_console(t("conn.hint_local_model"))
            _print_console(t("conn.hint_local_api_type"))
        return 1


def _print_addons(runtime: AddonRuntime | None = None) -> int:
    runtime = runtime or get_active_addon_runtime()
    _print_console(t("cli.addons.header"))
    if runtime.manifests:
        for manifest in runtime.manifests:
            _print_console(
                t(
                    "cli.addons.manifest",
                    addon_id=manifest.addon_id,
                    version=manifest.addon_version,
                    name=manifest.name,
                )
            )
            if manifest.review_pack_paths:
                _print_console(
                    t("cli.addons.review_packs", count=len(manifest.review_pack_paths))
                )
            if manifest.backend_provider_specs:
                _print_console(
                    t("cli.addons.backend_providers", count=len(manifest.backend_provider_specs))
                )
                for provider in manifest.backend_provider_specs:
                    _print_console(
                        t(
                            "cli.addons.backend_provider_entry",
                            backend_key=provider.key,
                            display_name=provider.display_name,
                        )
                    )
            if manifest.ui_contributor_specs:
                _print_console(
                    t("cli.addons.ui_contributors", count=len(manifest.ui_contributor_specs))
                )
                for contributor in manifest.ui_contributor_specs:
                    _print_console(
                        t(
                            "cli.addons.ui_contributor_entry",
                            surface=contributor.surface,
                            title=contributor.title,
                        )
                    )
    else:
        _print_console(t("cli.addons.none"))

    if runtime.diagnostics:
        _print_console("")
        _print_console(t("cli.addons.diagnostics_header"))
        for diagnostic in runtime.diagnostics:
            _print_console(f"- {diagnostic.message}")
    else:
        _print_console("")
        _print_console(t("cli.addons.diagnostics_none"))
    return EXIT_OK


def _print_review_type_presets() -> int:
    _print_console(t("cli.epilog_presets"))
    for line in format_review_type_preset_lines():
        _print_console(line)
    return EXIT_OK


def _setup_logging():
    from logging.handlers import RotatingFileHandler

    from aicodereviewer.config import config as _cfg

    level_name = (_cfg.get("logging", "log_level", "INFO") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    audit_logger = logging.getLogger("aicodereviewer.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.handlers.clear()
    audit_logger.propagate = True

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console)

    try:
        if _cfg.get("logging", "enable_file_logging", False):
            log_file = _cfg.get("logging", "log_file", "aicodereviewer.log")
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(level)
            fh.setFormatter(
                logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
            )
            root.addHandler(fh)

        if _cfg.get("logging", "enable_api_audit_file_logging", True):
            audit_log_file = _cfg.get("logging", "api_audit_log_file", "aicodereviewer-audit.log")
            audit_max_bytes = int(_cfg.get("logging", "api_audit_log_max_bytes", 1048576) or 1048576)
            audit_backup_count = int(_cfg.get("logging", "api_audit_log_backup_count", 5) or 5)
            audit_handler = RotatingFileHandler(
                audit_log_file,
                maxBytes=max(1024, audit_max_bytes),
                backupCount=max(1, audit_backup_count),
                encoding="utf-8",
            )
            audit_handler.setLevel(logging.INFO)
            audit_handler.setFormatter(
                logging.Formatter("[%(asctime)s] %(levelname)s %(message)s")
            )
            audit_logger.addHandler(audit_handler)
    except Exception:
        pass


def _launch_gui() -> int:
    """Import and start the CustomTkinter GUI."""
    try:
        from aicodereviewer.gui.app import launch
        launch()
        return 0
    except ImportError as exc:
        logger.error("%s\n%s", t("cli.gui_missing"), exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
