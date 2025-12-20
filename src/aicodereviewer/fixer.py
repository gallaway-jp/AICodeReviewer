# src/aicodereviewer/fixer.py
"""
AI-powered code fix generation.

This module handles the generation of automated code fixes using AI analysis.
It includes size validation, focused prompts, and error handling to ensure
safe and effective fix generation.

Functions:
    apply_ai_fix: Generate AI-powered fixes for code issues
"""
import os
from typing import Optional
from botocore.exceptions import ClientError

from .models import ReviewIssue
from .config import config


def apply_ai_fix(issue: ReviewIssue, client, review_type: str, lang: str) -> Optional[str]:
    """
    Generate an AI-powered fix for a code review issue.

    Creates a focused prompt for the AI to generate a complete corrected version
    of the code. Includes multiple size and content validations to prevent
    issues with large files or excessive API usage.

    Args:
        issue (ReviewIssue): The issue to generate a fix for
        client: AI review client instance
        review_type (str): Type of review the issue came from
        lang (str): Language for AI responses ('en' or 'ja')

    Returns:
        Optional[str]: The fixed code as a string, or None if fix generation failed

    Note:
        This function only generates the fix - it does not apply it to the file.
        Size limits prevent processing of very large files to avoid API issues.
    """
    try:
        # Check file size before processing
        file_size = os.path.getsize(issue.file_path)
        max_fix_size = config.get('performance', 'max_fix_file_size_mb')
        if file_size > max_fix_size:
            print(f"Warning: File too large for AI fix: {issue.file_path} ({file_size} bytes > {max_fix_size} bytes)")
            return None

        with open(issue.file_path, "r", encoding="utf-8", errors="ignore") as f:
            current_code = f.read()

        # Skip if file is empty or too large for the model
        max_fix_content = config.get('performance', 'max_fix_content_length')
        if not current_code or len(current_code) > max_fix_content:
            print(f"Warning: File content too large for AI processing: {issue.file_path} ({len(current_code)} chars > {max_fix_content})")
            return None

        # Create a more focused prompt for the AI to generate a fix
        fix_prompt = f"""You are an expert code fixer. Fix this specific issue in the code:

ISSUE TYPE: {review_type}
FEEDBACK: {issue.ai_feedback}

CODE TO FIX:
{current_code}

Return ONLY the complete corrected code, no explanations or markdown."""

        # Use the bedrock client to get the fix
        fix_result = client.get_review(fix_prompt, review_type="fix", lang=lang)

        if fix_result and not fix_result.startswith("Error:"):
            return fix_result.strip()  # Remove extra whitespace

        return None

    except (OSError, UnicodeDecodeError, ClientError) as e:
        print(f"Error generating AI fix: {e}")
        return None
    except Exception as e:
        print(f"Error generating AI fix: {e}")
        return None