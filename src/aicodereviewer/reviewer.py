# src/aicodereviewer/reviewer.py
"""
Code review issue collection with multi-type support.

Handles file reading, AI-powered analysis across one or more review types,
and structured issue parsing.
"""
import os
import logging
from pathlib import Path
from typing import List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import ReviewIssue
from .config import config

logger = logging.getLogger(__name__)

# Cache for file contents
_file_content_cache: dict = {}


# ── severity parsing ───────────────────────────────────────────────────────

def _parse_severity(feedback: str) -> str:
    """Infer severity from AI feedback text using keyword heuristics."""
    try:
        text = feedback.lower()
        if any(k in text for k in ("critical", "critically")):
            return "critical"
        if any(k in text for k in ("high", "severe")):
            return "high"
        if "medium" in text:
            return "medium"
        if any(k in text for k in ("low", "minor")):
            return "low"
        if any(k in text for k in ("info", "informational", "note")):
            return "info"
    except Exception:
        pass
    return "medium"


# ── file I/O ───────────────────────────────────────────────────────────────

def _read_file_content(file_path: Path) -> str:
    """Read file with caching and size limits."""
    cache_key = str(file_path)
    if cache_key in _file_content_cache:
        return _file_content_cache[cache_key]

    try:
        file_size = os.path.getsize(file_path)
        max_size = config.get("performance", "max_file_size_mb")
        if file_size > max_size:
            logger.warning(
                "Skipping large file %s (%d bytes > %d limit)", file_path, file_size, max_size
            )
            return ""

        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()

        cache_limit = config.get("performance", "file_cache_size")
        if len(_file_content_cache) < cache_limit:
            _file_content_cache[cache_key] = content
        return content

    except (OSError, UnicodeDecodeError) as exc:
        logger.error("Error reading %s: %s", file_path, exc)
        return ""


# ── main collection entry ──────────────────────────────────────────────────

def collect_review_issues(
    target_files: List[Any],
    review_types: List[str],
    client,
    lang: str,
    spec_content: Optional[str] = None,
    progress_callback=None,
) -> List[ReviewIssue]:
    """
    Collect review issues from *target_files* for one or more *review_types*.

    When multiple review types are requested the same file is analysed once
    per type, producing separate issues tagged with their category.

    Args:
        target_files: Path objects (project) or dicts (diff).
        review_types: List of review type keys.
        client: An :class:`AIBackend` instance.
        lang: Response language ('en' / 'ja').
        spec_content: Specification doc for ``'specification'`` type.
        progress_callback: Optional ``(current, total, msg)`` callable.

    Returns:
        Flat list of :class:`ReviewIssue` instances.
    """
    issues: List[ReviewIssue] = []
    total_work = len(target_files) * len(review_types)
    done = 0

    batch_size = config.get("processing", "batch_size", 5)
    enable_parallel = config.get("processing", "enable_parallel_processing", False)

    for review_type in review_types:
        batches = [
            target_files[i : i + batch_size]
            for i in range(0, len(target_files), batch_size)
        ]

        if enable_parallel and len(batches) > 1:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {
                    pool.submit(
                        _process_file_batch, batch, review_type, client, lang, spec_content
                    ): batch
                    for batch in batches
                }
                for future in as_completed(futures):
                    batch_issues = future.result()
                    issues.extend(batch_issues)
                    done += len(futures[future])
                    if progress_callback:
                        progress_callback(done, total_work, f"[{review_type}]")
        else:
            for batch in batches:
                batch_issues = _process_file_batch(
                    batch, review_type, client, lang, spec_content
                )
                issues.extend(batch_issues)
                done += len(batch)
                if progress_callback:
                    progress_callback(done, total_work, f"[{review_type}]")

    logger.debug("Collected %d issues across %d review type(s).", len(issues), len(review_types))
    return issues


# ── batch helper ───────────────────────────────────────────────────────────

def _process_file_batch(
    target_files: List[Any],
    review_type: str,
    client,
    lang: str,
    spec_content: Optional[str] = None,
) -> List[ReviewIssue]:
    """Process a batch of files for a single review type."""
    batch_issues: List[ReviewIssue] = []

    for file_info in target_files:
        if isinstance(file_info, dict):
            file_path = file_info["path"]
            code = file_info["content"]
            display_name = file_info["filename"]
        else:
            file_path = file_info
            code = _read_file_content(file_path)
            display_name = str(file_path)
            if not code:
                continue

        logger.info("Analysing %s [%s] …", display_name, review_type)

        try:
            feedback = client.get_review(
                code, review_type=review_type, lang=lang, spec_content=spec_content
            )
            if feedback and not feedback.startswith("Error:"):
                issue = ReviewIssue(
                    file_path=str(file_path),
                    line_number=None,
                    issue_type=review_type,
                    severity=_parse_severity(feedback),
                    description=f"Review feedback for {display_name}",
                    code_snippet=code[:200] + ("…" if len(code) > 200 else ""),
                    ai_feedback=feedback,
                )
                batch_issues.append(issue)
            elif feedback and feedback.startswith("Error:"):
                logger.warning("Backend returned error for %s: %s", display_name, feedback[:120])

        except Exception as exc:
            logger.error("Error analysing %s: %s", display_name, exc)

    return batch_issues


# ── verification ───────────────────────────────────────────────────────────

def verify_issue_resolved(
    issue: ReviewIssue, client, review_type: str, lang: str
) -> bool:
    """
    Re-analyse the current code and compare to the original feedback to
    decide whether the issue appears resolved.
    """
    try:
        with open(issue.file_path, "r", encoding="utf-8", errors="ignore") as fh:
            current_code = fh.read()

        new_feedback = client.get_review(current_code, review_type=review_type, lang=lang)
        old_len = len(issue.ai_feedback)
        new_len = len(new_feedback)

        if new_len < old_len * 0.5 or "no issues" in new_feedback.lower():
            return True

        logger.info("Re-analysis still shows issues.")
        return False
    except Exception as exc:
        logger.error("Verification error: %s", exc)
        return False
