# src/aicodereviewer/reviewer.py
from pathlib import Path
from typing import List, Dict, Any

from .models import ReviewIssue


def collect_review_issues(target_files: List[Any], review_type: str, client, lang: str) -> List[ReviewIssue]:
    """Collect all review issues from files without immediate output"""
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
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read()
                display_name = str(file_path)
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
                continue

        print(f"Analyzing {display_name}...")

        try:
            feedback = client.get_review(code, review_type=review_type, lang=lang)

            # Parse AI feedback into structured issues
            # This is a simplified parsing - in practice, you'd want more sophisticated parsing
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
    """Verify that a previously identified issue has been resolved"""
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