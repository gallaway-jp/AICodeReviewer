# src/aicodereviewer/main.py
import argparse
from datetime import datetime

from .auth import get_profile_name, set_profile_name, clear_profile, get_system_language
from .bedrock import BedrockClient
from .backup import cleanup_old_backups
from .scanner import scan_project_with_scope
from .reviewer import collect_review_issues
from .interactive import interactive_review_confirmation
from .reporter import generate_review_report
from .models import ReviewReport


def main():
    parser = argparse.ArgumentParser(description="AICodeReviewer - Multi-language AI Review")

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
                        help="Commit range for diff (e.g., 'HEAD~1..HEAD' or 'abc123..def456')")

    # Code review options
    parser.add_argument("path", nargs="?", help="Path to the project folder")
    parser.add_argument("--type", choices=['security', 'performance', 'best_practices', 'maintainability', 'documentation', 'testing', 'accessibility', 'scalability', 'compatibility', 'error_handling', 'complexity', 'architecture', 'license'],
                        default='best_practices')
    # Manual language override
    parser.add_argument("--lang", choices=['en', 'ja', 'default'], default='default',
                        help="Review language (en: English, ja: Japanese)")

    # Report output options
    parser.add_argument("--output", metavar="FILE",
                        help="Output file path for the review report (JSON format)")

    args = parser.parse_args()

    # Handle profile management commands
    if args.set_profile:
        set_profile_name(args.set_profile)
        return
    elif args.clear_profile:
        clear_profile()
        return

    # Validate scope and diff options
    if args.scope == 'diff':
        if not args.diff_file and not args.commits:
            parser.error("--diff-file or --commits is required when using --scope diff")
        if args.diff_file and args.commits:
            parser.error("Cannot specify both --diff-file and --commits")

    # Require path for code review
    if not args.path:
        parser.error("path is required for code review (or use --set-profile or --clear-profile)")

    # Determine final language
    target_lang = args.lang
    if target_lang == 'default':
        target_lang = get_system_language()

    profile = get_profile_name()
    client = BedrockClient(profile)

    # Clean up old backup files
    cleanup_old_backups(args.path)

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

    # Collect all review issues
    print(f"\nCollecting review issues from {num_files} files...")
    issues = collect_review_issues(target_files, args.type, client, target_lang)

    if not issues:
        print("No review issues found!")
        return

    print(f"\nFound {len(issues)} review issues. Starting interactive confirmation...")

    # Interactive review confirmation
    resolved_issues = interactive_review_confirmation(issues, client, args.type, target_lang)

    # Create review report
    diff_source = args.diff_file or args.commits if args.scope == 'diff' else None
    report = ReviewReport(
        project_path=args.path,
        review_type=args.type,
        scope=args.scope,
        total_files_scanned=len(target_files),
        issues_found=resolved_issues,
        generated_at=datetime.now(),
        language=target_lang,
        diff_source=diff_source
    )

    # Generate and save report
    output_file = generate_review_report(report, args.output)
    print(f"\n✅ Review complete! Report saved to: {output_file}")
    print(f"   Summary: {output_file.replace('.json', '_summary.txt')}")


if __name__ == "__main__":
    main()
