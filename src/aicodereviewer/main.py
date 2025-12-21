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
from datetime import datetime

from aicodereviewer.auth import get_profile_name, set_profile_name, clear_profile, get_system_language
from aicodereviewer.bedrock import BedrockClient
from aicodereviewer.backup import cleanup_old_backups
from aicodereviewer.scanner import scan_project_with_scope
from aicodereviewer.reviewer import collect_review_issues
from aicodereviewer.interactive import interactive_review_confirmation
from aicodereviewer.reporter import generate_review_report
from aicodereviewer.models import ReviewReport, calculate_quality_score


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

    # Initialize AWS Bedrock client with configured profile
    profile = get_profile_name()
    client = BedrockClient(profile)

    # Clean up old backup files to manage disk space
    cleanup_old_backups(args.path)

    # Display scan configuration and start file discovery
    scope_desc = "entire project" if args.scope == 'project' else f"changes ({args.diff_file or args.commits})"
    print(f"Scanning {args.path} - Scope: {scope_desc} (Output Language: {target_lang})...")
    target_files = scan_project_with_scope(args.path, args.scope, args.diff_file, args.commits)

    if not target_files:
        print("No files found to review.")
        return

    # Estimate processing time and show progress
    num_files = len(target_files)
    estimated_time = num_files * 8  # Rough estimate: 8 seconds per file (6s API + 2s overhead)
    print(f"Found {num_files} files to review (estimated time: {estimated_time // 60}m {estimated_time % 60}s)")

    # Load specification document if provided
    spec_content = None
    if args.spec_file:
        try:
            with open(args.spec_file, 'r', encoding='utf-8') as f:
                spec_content = f.read()
        except FileNotFoundError:
            print(f"Error: Specification file not found: {args.spec_file}")
            return
        except Exception as e:
            print(f"Error reading specification file: {e}")
            return

    # Collect all review issues from AI analysis
    print(f"\nCollecting review issues from {num_files} files...")
    issues = collect_review_issues(target_files, args.type, client, target_lang, spec_content)

    if not issues:
        print("No review issues found!")
        return

    print(f"\nFound {len(issues)} review issues. Starting interactive confirmation...")

    # Interactive review confirmation and potential fixes
    resolved_issues = interactive_review_confirmation(issues, client, args.type, target_lang)

    # Calculate quality score
    quality_score = calculate_quality_score(resolved_issues)

    # Create comprehensive review report
    diff_source = args.diff_file or args.commits if args.scope == 'diff' else None
    report = ReviewReport(
        project_path=args.path,
        review_type=args.type,
        scope=args.scope,
        total_files_scanned=len(target_files),
        issues_found=resolved_issues,
        generated_at=datetime.now(),
        language=target_lang,
        diff_source=diff_source,
        quality_score=quality_score,
        programmers=args.programmers,
        reviewers=args.reviewers
    )

    # Generate and save report files
    output_file = generate_review_report(report, args.output)
    print(f"\n✅ Review complete! Report saved to: {output_file}")
    print(f"   Summary: {output_file.replace('.json', '_summary.txt')}")


if __name__ == "__main__":
    main()
