import logging
from datetime import datetime
from typing import Optional, List, Any

from .backup import cleanup_old_backups
from .scanner import scan_project_with_scope as default_scan
from .reviewer import collect_review_issues
from .interactive import interactive_review_confirmation
from .reporter import generate_review_report
from .models import ReviewReport, ReviewIssue, calculate_quality_score

logger = logging.getLogger(__name__)


class AppRunner:
    def __init__(self, client, scan_fn=default_scan):
        self.client = client
        self.scan_fn = scan_fn

    def run(
        self,
        path: Optional[str],
        scope: str,
        diff_file: Optional[str],
        commits: Optional[str],
        review_type: str,
        spec_content: Optional[str],
        target_lang: str,
        programmers: List[str],
        reviewers: List[str],
        dry_run: bool = False,
    ) -> Optional[str]:
        # Clean old backups
        if path and not dry_run:
            cleanup_old_backups(path)

        scope_desc = "entire project" if scope == 'project' else f"changes ({diff_file or commits})"
        logger.info(f"Scanning {path} - Scope: {scope_desc} (Output Language: {target_lang})...")
        target_files: List[Any] = self.scan_fn(path, scope, diff_file, commits)

        if not target_files:
            logger.info("No files found to review.")
            return None

        num_files = len(target_files)
        estimated_time = num_files * 8
        logger.info(f"Found {num_files} files to review (estimated time: {estimated_time // 60}m {estimated_time % 60}s)")

        # Dry-run mode: show files and exit without API calls
        if dry_run:
            logger.info("\n=== DRY RUN MODE - Files that would be analyzed ===")
            for i, file_info in enumerate(target_files, 1):
                file_path = file_info.get('path', file_info) if isinstance(file_info, dict) else file_info
                logger.info(f"  {i}. {file_path}")
            logger.info(f"\nTotal: {num_files} files")
            logger.info(f"Review type: {review_type}")
            logger.info(f"Language: {target_lang}")
            logger.info("\nNo API calls made. Use without --dry-run to perform actual analysis.")
            return None

        logger.info(f"Collecting review issues from {num_files} files...")
        issues: List[ReviewIssue] = collect_review_issues(target_files, review_type, self.client, target_lang, spec_content)

        if not issues:
            logger.info("No review issues found!")
            return None

        logger.info(f"Found {len(issues)} review issues. Starting interactive confirmation...")
        resolved_issues = interactive_review_confirmation(issues, self.client, review_type, target_lang)

        quality_score = calculate_quality_score(resolved_issues)

        diff_source = diff_file or commits if scope == 'diff' else None
        report = ReviewReport(
            project_path=path or "",
            review_type=review_type,
            scope=scope,
            total_files_scanned=len(target_files),
            issues_found=resolved_issues,
            generated_at=datetime.now(),
            language=target_lang,
            diff_source=diff_source,
            quality_score=quality_score,
            programmers=programmers,
            reviewers=reviewers,
        )

        output_file = generate_review_report(report)
        logger.info(f"Review complete! Report saved to: {output_file}")
        logger.info(f"Summary: {output_file.replace('.json', '_summary.txt')}")
        return output_file
