# src/aicodereviewer/reviewer.py
"""
Code review issue collection and verification.

This module handles the core review process including file content reading,
AI-powered issue detection, and resolution verification with performance
optimizations like file caching, size limits, and batch processing.

Functions:
    _read_file_content: Cached file reading with size validation
    collect_review_issues: Main function to gather issues from files
    verify_issue_resolved: Check if previously identified issues are fixed
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import ReviewIssue
from .config import config

# Cache for file contents to avoid re-reading large files
_file_content_cache = {}
logger = logging.getLogger(__name__)
def _parse_severity(feedback: str) -> str:
    """Infer severity from AI feedback text using simple keyword heuristics."""
    try:
        text = feedback.lower()
        if any(k in text for k in ["critical", "critically"]):
            return "critical"
        if "high" in text or "severe" in text:
            return "high"
        if "medium" in text:
            return "medium"
        if "low" in text or "minor" in text:
            return "low"
        if "info" in text or "informational" in text:
            return "info"
    except Exception:
        pass
    return "medium"


def _read_file_content(file_path: Path) -> str:
    """
    Read file content with caching and size limits.

    Implements performance optimizations including content caching to avoid
    re-reading files and size limits to prevent memory issues with large files.

    Args:
        file_path (Path): Path to the file to read

    Returns:
        str: File content as string, or empty string if file is too large or unreadable
    """
    cache_key = str(file_path)

    # Check cache first
    if cache_key in _file_content_cache:
        return _file_content_cache[cache_key]

    try:
        # Check file size before reading
        file_size = os.path.getsize(file_path)
        max_size = config.get('performance', 'max_file_size_mb')
        if file_size > max_size:
            logger.warning(f"Skipping large file {file_path} ({file_size} bytes > {max_size} bytes)")
            return ""

        # Read file efficiently
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Cache the content (limit cache size)
        cache_limit = config.get('performance', 'file_cache_size')
        if len(_file_content_cache) < cache_limit:
            _file_content_cache[cache_key] = content

        return content

    except (OSError, UnicodeDecodeError) as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return ""


def collect_review_issues(target_files: List[Any], review_type: str, client, lang: str, spec_content: Optional[str] = None) -> List[ReviewIssue]:
    """
    Collect all review issues from target files using AI analysis.

    Processes each file through the AI review client to identify code quality
    issues. Handles both project-wide scans and diff-based reviews.
    Supports batch processing when enabled in config.

    Args:
        target_files (List[Any]): Files to review - either Path objects (project scope)
                                or dicts with path/content (diff scope)
        review_type (str): Type of review to perform (e.g., 'security', 'performance')
        client: AI review client instance
        lang (str): Language for AI responses ('en' or 'ja')
        spec_content (Optional[str]): Specification document content for specification review

    Returns:
        List[ReviewIssue]: List of identified review issues
    """
    issues = []
    
    # Check if batch processing is enabled
    batch_size = config.get('processing', 'batch_size', 5)
    enable_parallel = config.get('processing', 'enable_parallel_processing', False)
    
    # Prepare file batches
    batches = [target_files[i:i + batch_size] for i in range(0, len(target_files), batch_size)]
    
    if enable_parallel and len(batches) > 1:
        # Process batches in parallel
        logger.debug(f"Processing {len(target_files)} files in {len(batches)} batches (parallel mode)")
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_process_file_batch, batch, review_type, client, lang, spec_content) 
                      for batch in batches]
            for future in as_completed(futures):
                batch_issues = future.result()
                issues.extend(batch_issues)
    else:
        # Sequential batch processing
        for batch in batches:
            batch_issues = _process_file_batch(batch, review_type, client, lang, spec_content)
            issues.extend(batch_issues)
    
    logger.debug(f"Collected {len(issues)} review issues from {len(target_files)} files")
    return issues


def _process_file_batch(target_files: List[Any], review_type: str, client, lang: str, spec_content: Optional[str] = None) -> List[ReviewIssue]:
    """
    Process a batch of files and collect review issues (helper for batch processing).
    
    Args:
        target_files (List[Any]): Files to review in this batch
        review_type (str): Type of review to perform
        client: AI review client instance
        lang (str): Language for AI responses
        spec_content (Optional[str]): Specification document content
    
    Returns:
        List[ReviewIssue]: Identified review issues for this batch
    """
    batch_issues = []

    for file_info in target_files:
        if isinstance(file_info, dict):
            # Diff scope - file_info is a dict with path, content, filename
            file_path = file_info['path']
            code = file_info['content']
            display_name = file_info['filename']
        else:
            # Project scope - file_info is a Path object
            file_path = file_info
            code = _read_file_content(file_path)
            display_name = str(file_path)

            if not code:  # Skip empty or unreadable files
                continue

        logger.info(f"Analyzing {display_name}...")

        try:
            feedback = client.get_review(code, review_type=review_type, lang=lang, spec_content=spec_content)

            # Parse AI feedback into structured issues
            if feedback and not feedback.startswith("Error:"):
                # Create a review issue from the feedback
                issue = ReviewIssue(
                    file_path=str(file_path),
                    line_number=None,  # Could be enhanced to extract line numbers
                    issue_type=review_type,
                    severity=_parse_severity(feedback),
                    description=f"Review feedback for {display_name}",
                    code_snippet=code[:200] + "..." if len(code) > 200 else code,
                    ai_feedback=feedback
                )
                batch_issues.append(issue)

        except Exception as e:
            logger.error(f"Error analyzing {display_name}: {e}")

    return batch_issues


def verify_issue_resolved(issue: ReviewIssue, client, review_type: str, lang: str) -> bool:
    """
    Verify that a previously identified issue has been resolved.

    Re-analyzes the current code to check if the issue still exists.
    Uses heuristic comparison of feedback length and content.

    Args:
        issue (ReviewIssue): The issue to verify
        client: AI review client instance
        review_type (str): Type of review performed
        lang (str): Language for AI responses

    Returns:
        bool: True if issue appears to be resolved, False otherwise
    """
    try:
        with open(issue.file_path, "r", encoding="utf-8", errors="ignore") as f:
            current_code = f.read()

        # Re-run analysis on current code
        new_feedback = client.get_review(current_code, review_type=review_type, lang=lang)

        # Simple check - if the new feedback is significantly different/shorter, assume resolved
        # In practice, you'd want more sophisticated comparison
        old_feedback_length = len(issue.ai_feedback)
        new_feedback_length = len(new_feedback)

        # If new feedback is much shorter or indicates no issues, consider it resolved
        if new_feedback_length < old_feedback_length * 0.5 or "no issues" in new_feedback.lower():
            return True

        logger.info(f"New analysis still shows issues: {new_feedback}")
        return False

    except Exception as e:
        logger.error(f"Error verifying resolution: {e}")
        return False