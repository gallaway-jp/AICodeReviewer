# src/aicodereviewer/orchestration.py
"""
High-level orchestration for a code review session.

Coordinates scanning, multi-type review collection, interactive
confirmation, and report generation.
"""
import logging
from datetime import datetime
from typing import Optional, List, Any, Callable, Dict, Union, cast

from .backup import cleanup_old_backups
from .scanner import scan_project_with_scope as default_scan
from .reviewer import collect_review_issues
from .interactive import interactive_review_confirmation
from .reporter import generate_review_report
from .models import ReviewReport, ReviewIssue, calculate_quality_score
from .i18n import t
from .backends.base import AIBackend

__all__ = [
    "ScanFunction",
    "ProgressCallback",
    "CancelCheck",
    "AppRunner",
]

# Type aliases for complex callables
ScanFunction = Callable[
    [Optional[str], str, Optional[str], Optional[str]],
    List[Dict[str, Any]]
]
ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]

logger = logging.getLogger(__name__)


def _target_file_path(target_file: Any) -> str:
    """Extract a displayable path from a scan result item."""
    if isinstance(target_file, dict):
        mapping = cast(dict[str, object], target_file)
        raw_path = mapping.get("path")
        if raw_path is not None:
            return str(raw_path)
        return str(mapping)
    return str(cast(object, target_file))


class AppRunner:
    """
    Orchestrates a complete review session.

    Args:
        client: An :class:`AIBackend` instance.
        scan_fn: File-scanning function (default: ``scan_project_with_scope``).
        backend_name: Name of the active backend for report metadata.
    """

    client: AIBackend | None
    scan_fn: ScanFunction
    backend_name: str

    def __init__(
        self,
        client: AIBackend | None,
        *,
        scan_fn: Optional[ScanFunction] = None,
        backend_name: str = "bedrock",
    ) -> None:
        self.client = client
        self.scan_fn = scan_fn or default_scan
        self.backend_name = backend_name
        self._last_run_state: dict[str, Any] = {}

    def run(
        self,
        path: Optional[str],
        scope: str,
        diff_file: Optional[str],
        commits: Optional[str],
        review_types: List[str],
        spec_content: Optional[str],
        target_lang: str,
        programmers: List[str],
        reviewers: List[str],
        dry_run: bool = False,
        output_file: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        interactive: bool = True,
        cancel_check: Optional[CancelCheck] = None,
    ) -> Union[Optional[str], List[ReviewIssue]]:
        """
        Execute a full review session and return the report path (or None).

        Args:
            review_types: One or more review type keys.
            progress_callback: Optional ``(current, total, message)`` callable
                               used by the GUI progress bar.
            interactive: If *False* skip the CLI interactive-review step
                         (used by the GUI which has its own issue cards).
            cancel_check: Optional callable returning *True* when the user
                          has requested cancellation.
        """
        # Clean old backups
        if path and not dry_run:
            cleanup_old_backups(path)

        diff_source = (diff_file or commits) if scope == "diff" else None

        type_label = ", ".join(review_types)
        scope_desc = (
            t("orch.scope_project") if scope == "project"
            else t("orch.scope_diff", source=diff_file or commits)
        )
        logger.info(
            t("orch.scanning", path=path, scope=scope_desc, types=type_label, language=target_lang),
        )

        target_files: List[Any] = self.scan_fn(path, scope, diff_file, commits)
        target_paths = [_target_file_path(fi) for fi in target_files]
        if not target_files:
            self._set_last_run_state(
                status="no_files",
                project_path=path or "",
                scope=scope,
                diff_source=diff_source,
                files_scanned=0,
                target_paths=[],
                issue_count=0,
                review_types=list(review_types),
                language=target_lang,
                backend=self.backend_name,
                dry_run=dry_run,
            )
            logger.info(t("orch.no_files"))
            return None

        num_files = len(target_files)
        est = num_files * len(review_types) * 8
        logger.info(
            t("orch.found_files", files=num_files, types=len(review_types),
              minutes=est // 60, seconds=est % 60),
        )

        # ── dry run ───────────────────────────────────────────────────────
        if dry_run:
            self._set_last_run_state(
                status="dry_run",
                project_path=path or "",
                scope=scope,
                diff_source=diff_source,
                files_scanned=num_files,
                target_paths=target_paths,
                issue_count=0,
                review_types=list(review_types),
                language=target_lang,
                backend=self.backend_name,
                dry_run=True,
            )
            logger.info(t("orch.dry_run_header"))
            for i, fi in enumerate(target_files, 1):
                fp = _target_file_path(fi)
                logger.info("  %d. %s", i, fp)
            logger.info(t("orch.dry_run_total", count=num_files))
            logger.info(t("orch.dry_run_types", types=type_label))
            logger.info(t("orch.dry_run_lang", language=target_lang))
            logger.info(t("orch.dry_run_no_api"))
            return None

        if self.client is None:
            raise RuntimeError("AI backend client is required for non-dry-run review")

        # ── collect issues ────────────────────────────────────────────────
        logger.info(t("orch.collecting"))
        issues: List[ReviewIssue] = collect_review_issues(
            target_files,
            review_types,
            self.client,
            target_lang,
            spec_content,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

        if not issues:
            self._set_last_run_state(
                status="no_issues",
                project_path=path or "",
                scope=scope,
                diff_source=diff_source,
                files_scanned=num_files,
                target_paths=target_paths,
                issue_count=0,
                review_types=list(review_types),
                language=target_lang,
                backend=self.backend_name,
                dry_run=False,
            )
            logger.info(t("orch.no_issues"))
            return None

        logger.info(t("orch.found_issues", count=len(issues)))

        self._set_last_run_state(
            status="issues_found",
            project_path=path or "",
            scope=scope,
            diff_source=diff_source,
            files_scanned=num_files,
            target_paths=target_paths,
            issue_count=len(issues),
            review_types=list(review_types),
            language=target_lang,
            backend=self.backend_name,
            dry_run=False,
        )

        if cancel_check and cancel_check():
            return None

        # Store metadata for deferred report generation
        self._pending_report_meta = dict(
            project_path=path or "",
            review_types=list(review_types),
            scope=scope,
            total_files_scanned=num_files,
            language=target_lang,
            diff_source=diff_source,
            programmers=programmers,
            reviewers=reviewers,
            backend=self.backend_name,
        )
        self._pending_issues = issues

        # When interactive=False (GUI mode), return issues without saving
        # a report — the GUI will invoke generate_report() after the user
        # has finished the interactive review.
        if not interactive:
            return issues

        # The interactive step uses the first review_type for verification
        # prompts; individual issues carry their own issue_type.
        resolved_issues = interactive_review_confirmation(
            issues, self.client, review_types[0], target_lang
        )

        return self.generate_report(resolved_issues, output_file)

    # ── Deferred report generation (called by GUI after review) ────────
    def generate_report(
        self,
        issues: Optional[List[ReviewIssue]] = None,
        output_file: Optional[str] = None,
    ) -> Optional[str]:
        """Generate and save the report. Called by the GUI on Finalize."""
        report = self.build_report(issues)
        if report is None:
            return None

        out = generate_review_report(report, output_file)
        logger.info(t("orch.complete", path=out))
        return out

    def build_report(
        self,
        issues: Optional[List[ReviewIssue]] = None,
    ) -> Optional[ReviewReport]:
        """Build a review report object without writing it to disk."""
        meta = getattr(self, "_pending_report_meta", None)
        if not meta:
            return None
        if issues is None:
            pending: List[ReviewIssue] = getattr(self, "_pending_issues", [])
            issues = pending

        quality_score = calculate_quality_score(issues)

        return ReviewReport(
            project_path=meta["project_path"],
            review_type=", ".join(meta["review_types"]),
            scope=meta["scope"],
            total_files_scanned=meta["total_files_scanned"],
            issues_found=issues,
            generated_at=datetime.now(),
            language=meta["language"],
            review_types=meta["review_types"],
            diff_source=meta["diff_source"],
            quality_score=quality_score,
            programmers=meta["programmers"],
            reviewers=meta["reviewers"],
            backend=meta["backend"],
        )

    def _set_last_run_state(self, **state: Any) -> None:
        """Persist summary state for callers that need structured results."""
        self._last_run_state = dict(state)
