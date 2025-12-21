# src/aicodereviewer/reviewer.py
"""
Code review issue collection and verification.

This module handles the core review process including file content reading,
AI-powered issue detection, and resolution verification with performance
optimizations like file caching and size limits.

Functions:
    _read_file_content: Cached file reading with size validation
    collect_review_issues: Main function to gather issues from files
    verify_issue_resolved: Check if previously identified issues are fixed
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from .models import ReviewIssue
from .config import config

# Cache for file contents to avoid re-reading large files
_file_content_cache = {}


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
            print(f"Warning: Skipping large file {file_path} ({file_size} bytes > {max_size} bytes)")
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
        print(f"Error reading file {file_path}: {e}")
        return ""


def collect_review_issues(target_files: List[Any], review_type: str, client, lang: str, spec_content: Optional[str] = None) -> List[ReviewIssue]:
    """
    Collect all review issues from target files using AI analysis.

    Processes each file through the AI review client to identify code quality
    issues. Handles both project-wide scans and diff-based reviews.

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

        print(f"Analyzing {display_name}...")

        try:
            feedback = client.get_review(code, review_type=review_type, lang=lang, spec_content=spec_content)

            # Parse AI feedback into structured issues
            if feedback and not feedback.startswith("Error:"):
                # Create a review issue from the feedback
                issue = ReviewIssue(
                    file_path=str(file_path),
                    line_number=None,  # Could be enhanced to extract line numbers
                    issue_type=review_type,
                    severity='medium',  # Could be enhanced to detect severity
                    description=f"Review feedback for {display_name}",
                    code_snippet=code[:200] + "..." if len(code) > 200 else code,
                    ai_feedback=feedback
                )
                issues.append(issue)

        except Exception as e:
            print(f"Error analyzing {display_name}: {e}")

    return issues


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

        print(f"New analysis still shows issues: {new_feedback}")
        return False

    except Exception as e:
        print(f"Error verifying resolution: {e}")
        return False