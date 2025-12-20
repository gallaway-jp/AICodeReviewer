# src/aicodereviewer/fixer.py
from typing import Optional

from .models import ReviewIssue


def apply_ai_fix(issue: ReviewIssue, client, review_type: str, lang: str) -> Optional[str]:
    """Generate an AI fix for the issue (does not apply it)"""
    try:
        with open(issue.file_path, "r", encoding="utf-8", errors="ignore") as f:
            current_code = f.read()

        # Create a prompt for the AI to generate a fix
        fix_prompt = f"""
You are an expert code fixer. The following code has an issue that needs to be resolved:

ISSUE TYPE: {review_type}
ORIGINAL FEEDBACK: {issue.ai_feedback}

CURRENT CODE:
{current_code}

Please provide the FIXED version of the entire file that resolves this issue.
Return ONLY the complete corrected code, no explanations or markdown.
"""

        # Use the bedrock client to get the fix
        fix_result = client.get_review(fix_prompt, review_type="fix", lang=lang)

        if fix_result and not fix_result.startswith("Error:"):
            return fix_result

        return None

    except Exception as e:
        print(f"Error generating AI fix: {e}")
        return None