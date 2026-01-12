# src/aicodereviewer/main.py
"""
Main entry point for AICodeReviewer.

This module provides the command-line interface and orchestrates the complete
code review workflow including file scanning, issue collection, interactive
review, and report generation.

The workflow follows these steps:
1. Parse command-line arguments
2. Validate scope and authentication
3. Scan project files or parse diffs
4. Collect review issues from AI analysis
5. Interactive review confirmation
6. Generate and save reports
"""
import argparse
import logging
from datetime import datetime

from aicodereviewer.auth import get_profile_name, set_profile_name, clear_profile, get_system_language
from aicodereviewer.bedrock import BedrockClient
from aicodereviewer.backup import cleanup_old_backups
from aicodereviewer.scanner import scan_project_with_scope
from aicodereviewer.orchestration import AppRunner
from aicodereviewer.orchestration import AppRunner
from aicodereviewer.models import ReviewReport, calculate_quality_score

logger = logging.getLogger(__name__)


def main():
    """
    Main entry point for AICodeReviewer.

    Parses command-line arguments, sets up AWS authentication, scans the codebase,
    performs AI-powered code review, and generates comprehensive reports.

    Command-line options support different review scopes (project vs diff),
    review types (security, performance, etc.), and output formats.
    """
    parser = argparse.ArgumentParser(
        description="AICodeReviewer - Multi-language AI Review",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "VCS diff behavior:\n"
            "- When you run from a subdirectory inside a repository, diffs are scoped to that directory.\n"
            "  Git (subdirectory): git diff RANGE -- .\n"
            "  Git (repo root):    git diff RANGE\n"
            "  SVN (subdirectory): svn diff -r REV1:REV2 .\n"
            "  SVN (repo root):    svn diff -r REV1:REV2\n"
            "- SVN ranges accept REV1..REV2 or REV1:REV2; both are normalized."
        )
    )

    # Profile management options
    parser.add_argument("--set-profile", metavar="PROFILE",
                        help="Set or change AWS profile name")
    parser.add_argument("--clear-profile", action="store_true",
                        help="Remove stored AWS profile from keyring")

    # Review scope options
    parser.add_argument("--scope", choices=['project', 'diff'], default='project',
                        help="Review scope: 'project' for entire project, 'diff' for changes only")
    parser.add_argument("--diff-file", metavar="FILE",
                        help="Path to diff file (TortoiseSVN/TortoiseGit format) for diff scope")
    parser.add_argument("--commits", metavar="RANGE",
                        help=(
                            "Commit/revision range for diff. Examples:\n"
                            "  Git: HEAD~1..HEAD or abc123..def456\n"
                            "  SVN: PREV:HEAD or 100:101 (also accepts 100..101)\n"
                            "Behavior: If run from a subdirectory, diff is scoped to that directory."
                        ))

    # Code review options
    parser.add_argument("path", nargs="?", help="Path to the project folder (required for project scope, optional for diff scope to provide additional context)")
    parser.add_argument("--type", choices=['security', 'performance', 'best_practices', 'maintainability', 'documentation', 'testing', 'accessibility', 'scalability', 'compatibility', 'error_handling', 'complexity', 'architecture', 'license', 'specification'],
                        default='best_practices')
    parser.add_argument("--spec-file", metavar="FILE",
                        help="Path to specification document file (required when using --type specification)")
    # Manual language override
    parser.add_argument("--lang", choices=['en', 'ja', 'default'], default='default',
                        help="Review language (en: English, ja: Japanese)")

    # Report output options
    parser.add_argument("--output", metavar="FILE",
                        help="Output file path for the review report (JSON format)")

    # Review metadata options
    parser.add_argument("--programmers", nargs='+', metavar="NAME",
                        help="Names of programmers who worked on the code (space-separated)")
    parser.add_argument("--reviewers", nargs='+', metavar="NAME",
                        help="Names of reviewers performing the review (space-separated)")

    args = parser.parse_args()

    # Configure logging: crisp console output for interactive UI
    try:
        log_level_name = 'INFO'
        from aicodereviewer.config import config as _config
        lvl = _config.get('logging', 'log_level', 'INFO')
        if isinstance(lvl, str):
            log_level_name = lvl.upper()

        level = getattr(logging, log_level_name, logging.INFO)
        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # Clear existing handlers to avoid duplicate logs
        root_logger.handlers.clear()

        # Console handler with minimal formatting to keep UI clean
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        root_logger.addHandler(console_handler)

        # Optional file handler for debugging with detailed format
        try:
            enable_file_logging = _config.get('logging', 'enable_file_logging', 'false').lower() == 'true'
            if enable_file_logging:
                log_file = _config.get('logging', 'log_file', 'aicodereviewer.log')
                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setLevel(level)
                file_handler.setFormatter(logging.Formatter(
                    '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                ))
                root_logger.addHandler(file_handler)
                logger.debug(f"File logging enabled: {log_file}")
        except Exception as e:
            logger.warning(f"Could not enable file logging: {e}")
    except Exception:
        logging.basicConfig(level=logging.INFO, format='%(message)s')

    # Handle profile management commands first
    if args.set_profile:
        set_profile_name(args.set_profile)
        return
    elif args.clear_profile:
        clear_profile()
        return

    # Validate scope and diff options for diff-based reviews
    if args.scope == 'diff':
        if not args.diff_file and not args.commits:
            parser.error("--diff-file or --commits is required when using --scope diff")
        if args.diff_file and args.commits:
            parser.error("Cannot specify both --diff-file and --commits")

    # Require path for project scope, optional for diff scope
    if args.scope == 'project' and not args.path:
        parser.error("path is required for project scope (or use --set-profile or --clear-profile)")

    # Require programmers and reviewers for code review operations
    if not args.programmers:
        parser.error("--programmers is required for code review")
    if not args.reviewers:
        parser.error("--reviewers is required for code review")

    # Require spec-file when using specification review type
    if args.type == 'specification' and not args.spec_file:
        parser.error("--spec-file is required when using --type specification")

    # Determine final language for AI responses
    target_lang = args.lang
    if target_lang == 'default':
        target_lang = get_system_language()

    # Initialize AWS Bedrock client with configured authentication
    client = BedrockClient()

    # Load specification document if provided
    spec_content = None
    if args.spec_file:
        try:
            with open(args.spec_file, 'r', encoding='utf-8') as f:
                spec_content = f.read()
        except FileNotFoundError:
            logger.error(f"Error: Specification file not found: {args.spec_file}")
            return
        except Exception as e:
            logger.error(f"Error reading specification file: {e}")
            return

    # Clean up old backup files to manage disk space
    cleanup_old_backups(args.path)

    # Run orchestration
    runner = AppRunner(client, scan_fn=scan_project_with_scope)
    runner.run(
        path=args.path,
        scope=args.scope,
        diff_file=args.diff_file,
        commits=args.commits,
        review_type=args.type,
        spec_content=spec_content,
        target_lang=target_lang,
        programmers=args.programmers,
        reviewers=args.reviewers,
    )

    # Orchestration handles reporting/logging


if __name__ == "__main__":
    main()
