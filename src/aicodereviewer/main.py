# src/aicodereviewer/main.py
"""
CLI entry point for AICodeReviewer.

Supports:
- Multiple review types per session (``--type security,performance``)
- Backend selection (``--backend bedrock|kiro|copilot|local``)
- Full-project and diff-based scopes
- Dry-run mode
- Profile management
- Connection testing (``--check-connection``)
- GUI launcher (``--gui``)
"""
import argparse
import logging
import sys

from aicodereviewer.auth import get_system_language, set_profile_name, clear_profile
from aicodereviewer.backends import create_backend
from aicodereviewer.backends.base import REVIEW_TYPE_KEYS, REVIEW_TYPE_META
from aicodereviewer.backup import cleanup_old_backups
from aicodereviewer.scanner import scan_project_with_scope
from aicodereviewer.orchestration import AppRunner
from aicodereviewer.i18n import t, set_locale

logger = logging.getLogger(__name__)


def _build_epilog() -> str:
    """Generate CLI epilog with review type listing."""
    lines = [
        t("cli.epilog_types"),
    ]
    for key in REVIEW_TYPE_KEYS:
        meta = REVIEW_TYPE_META.get(key, {})
        label = meta.get("label", key)
        group = meta.get("group", "")
        lines.append(f"  {key:20s}  {label}  [{group}]")

    lines += [
        "",
        t("cli.epilog_vcs"),
        t("cli.epilog_subdir"),
        t("cli.epilog_git"),
        t("cli.epilog_svn"),
    ]
    return "\n".join(lines)


def main():
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
    parser.add_argument("--spec-file", metavar="FILE",
                        help=t("cli.help_spec_file"))

    # ── backend ────────────────────────────────────────────────────────────
    parser.add_argument("--backend", choices=["bedrock", "kiro", "copilot", "local"],
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
    parser.add_argument("--gui", action="store_true",
                        help=t("cli.help_gui"))
    parser.add_argument("--check-connection", action="store_true",
                        help=t("cli.help_check_connection"))

    args = parser.parse_args()

    # ── logging setup ──────────────────────────────────────────────────────
    _setup_logging()

    # ── language / locale ──────────────────────────────────────────────────
    target_lang = args.lang if args.lang != "default" else get_system_language()
    set_locale(target_lang)

    # ── GUI shortcut ───────────────────────────────────────────────────────
    if args.gui:
        _launch_gui()
        return

    # ── profile commands ───────────────────────────────────────────────────
    if args.set_profile:
        set_profile_name(args.set_profile)
        return
    if args.clear_profile:
        clear_profile()
        return

    # ── connection check ───────────────────────────────────────────────────
    if args.check_connection:
        _check_connection(args.backend)
        return

    # ── parse review types ─────────────────────────────────────────────────
    review_types = _parse_review_types(args.review_types)

    # ── validation ─────────────────────────────────────────────────────────
    _validate_args(parser, args, review_types)

    # ── run ────────────────────────────────────────────────────────────────
    _run_review(args, review_types, target_lang)


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace, review_types: list) -> None:
    """Validate semantic constraints on parsed arguments."""
    if args.scope == "diff" and not args.diff_file and not args.commits:
        parser.error("--diff-file or --commits required for diff scope")
    if args.scope == "diff" and args.diff_file and args.commits:
        parser.error("Cannot use both --diff-file and --commits")
    if args.scope == "project" and not args.path:
        parser.error("path is required for project scope")
    if not args.dry_run:
        if not args.programmers:
            parser.error("--programmers is required for a review")
        if not args.reviewers:
            parser.error("--reviewers is required for a review")
    if "specification" in review_types and not args.spec_file:
        parser.error("--spec-file required when using specification type")


def _run_review(args: argparse.Namespace, review_types: list, target_lang: str) -> None:
    """Create the backend, load the spec file if needed, and execute the review."""
    backend_name = args.backend or "bedrock"

    client = None
    if not args.dry_run:
        client = create_backend(backend_name)

    spec_content = None
    if args.spec_file and not args.dry_run:
        try:
            with open(args.spec_file, "r", encoding="utf-8") as fh:
                spec_content = fh.read()
        except FileNotFoundError:
            logger.error(t("cli.spec_not_found", path=args.spec_file))
            return
        except Exception as exc:
            logger.error(t("cli.spec_read_error", error=exc))
            return

    if client is None:
        logger.error("Failed to create backend '%s'; cannot run review.", backend_name)
        return

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


# ── helpers ────────────────────────────────────────────────────────────────

def _parse_review_types(raw: str) -> list:
    """
    Parse a comma-separated (or 'all') review type string.

    Returns a validated and deduplicated list.
    """
    parts = [p.strip().lower() for p in raw.replace("+", ",").split(",") if p.strip()]
    if "all" in parts:
        return list(REVIEW_TYPE_KEYS)
    seen = set()
    result = []
    for p in parts:
        if p in REVIEW_TYPE_KEYS and p not in seen:
            result.append(p)
            seen.add(p)
        elif p not in REVIEW_TYPE_KEYS:
            logger.warning(t("cli.unknown_type", type=p))
    return result or ["best_practices"]


def _check_connection(backend_name: str | None):
    """Test connectivity for the selected backend with diagnostic output."""
    from aicodereviewer.config import config as _cfg

    backend_name = backend_name or _cfg.get("backend", "type", "bedrock")
    print(t("conn.checking", backend=backend_name))

    try:
        client = create_backend(backend_name)
        ok = client.validate_connection()
    except Exception as exc:
        ok = False
        logger.error("%s", exc)

    if ok:
        print(t("conn.success"))
        # Show extra details per backend
        if backend_name == "bedrock":
            model = _cfg.get("model", "model_id", "")
            region = _cfg.get("aws", "region", "")
            print(t("conn.details_model", model=model))
            print(t("conn.details_region", region=region))
        elif backend_name == "local":
            url = _cfg.get("local_llm", "api_url", "")
            model = _cfg.get("local_llm", "model", "")
            print(t("conn.details_url", url=url))
            print(t("conn.details_model", model=model))
    else:
        print(t("conn.failure"))
        # Provide helpful hints
        if backend_name == "bedrock":
            print(t("conn.hint_bedrock_sso"))
            print(t("conn.hint_bedrock_profile"))
            print(t("conn.hint_bedrock_model"))
        elif backend_name == "kiro":
            print(t("conn.hint_kiro_wsl"))
            print(t("conn.hint_kiro_cli"))
        elif backend_name == "copilot":
            print(t("conn.hint_copilot_install"))
            print(t("conn.hint_copilot_auth"))
        elif backend_name == "local":
            print(t("conn.hint_local_url"))
            print(t("conn.hint_local_model"))
            print(t("conn.hint_local_api_type"))


def _setup_logging():
    from aicodereviewer.config import config as _cfg

    level_name = (_cfg.get("logging", "log_level", "INFO") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

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
    except Exception:
        pass


def _launch_gui():
    """Import and start the CustomTkinter GUI."""
    try:
        from aicodereviewer.gui.app import launch
        launch()
    except ImportError as exc:
        logger.error("%s\n%s", t("cli.gui_missing"), exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
