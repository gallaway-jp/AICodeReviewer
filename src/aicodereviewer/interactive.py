# src/aicodereviewer/interactive.py
import shutil
from datetime import datetime
from typing import List

from .models import ReviewIssue
from .reviewer import verify_issue_resolved
from .fixer import apply_ai_fix


def get_valid_choice(prompt: str, valid_options: List[str]) -> str:
    """Get validated user input"""
    while True:
        try:
            choice = input(prompt).strip()
            if choice in valid_options:
                return choice
            print(f"Invalid choice. Please select from: {', '.join(valid_options)}")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return "cancel"
        except EOFError:
            print("\nInput stream ended. Operation cancelled.")
            return "cancel"


def interactive_review_confirmation(issues: List[ReviewIssue], client, review_type: str, lang: str) -> List[ReviewIssue]:
    """Interactive process to confirm and resolve each review issue"""

    for i, issue in enumerate(issues, 1):
        print(f"\n{'='*80}")
        print(f"ISSUE {i}/{len(issues)}")
        print(f"{'='*80}")
        print(f"File: {issue.file_path}")
        print(f"Type: {issue.issue_type}")
        print(f"Severity: {issue.severity}")
        print(f"Code snippet:\n{issue.code_snippet}")
        print(f"\nAI Feedback:\n{issue.ai_feedback}")
        print(f"\nStatus: {issue.status}")

        while issue.status == "pending":
            print(f"\nActions:")
            print(f"  1. RESOLVED - Mark as resolved (program will verify)")
            print(f"  2. IGNORE - Ignore this issue (requires reason)")
            print(f"  3. AI FIX - Let AI fix the code")
            print(f"  4. VIEW CODE - Show full file content")

            choice = get_valid_choice("Choose action (1-4): ", ["1", "2", "3", "4"])
            if choice == "cancel":
                break

            if choice == "1":
                # RESOLVED - verify the issue is actually resolved
                if verify_issue_resolved(issue, client, review_type, lang):
                    issue.status = "resolved"
                    issue.resolved_at = datetime.now()
                    print("✅ Issue marked as resolved!")
                else:
                    print("❌ Issue verification failed. Issue may not be fully resolved.")

            elif choice == "2":
                # IGNORE - require reason
                reason = input("Enter reason for ignoring this issue: ").strip()
                if reason and len(reason) >= 3:  # Minimum 3 characters for a valid reason
                    issue.status = "ignored"
                    issue.resolution_reason = reason
                    issue.resolved_at = datetime.now()
                    print("✅ Issue ignored with reason provided.")
                else:
                    print("❌ Reason must be at least 3 characters long.")

            elif choice == "3":
                # AI FIX - apply AI-generated fix with confirmation
                fix_result = apply_ai_fix(issue, client, review_type, lang)
                if fix_result:
                    print("\n🤖 AI suggests the following fix:")
                    print("=" * 50)
                    print(fix_result)
                    print("=" * 50)

                    confirm = get_valid_choice("Apply this AI fix? (y/n): ", ["y", "n", "yes", "no"])
                    if confirm.lower() in ["y", "yes"]:
                        # Create backup before applying
                        backup_path = f"{issue.file_path}.backup"
                        try:
                            shutil.copy2(issue.file_path, backup_path)
                            print(f"📁 Backup created: {backup_path}")

                            # Apply the fix
                            with open(issue.file_path, "w", encoding="utf-8") as f:
                                f.write(fix_result)

                            issue.status = "ai_fixed"
                            issue.ai_fix_applied = fix_result
                            issue.resolved_at = datetime.now()
                            print("✅ AI fix applied successfully!")
                        except Exception as e:
                            print(f"❌ Error applying fix: {e}")
                    else:
                        print("❌ AI fix cancelled by user.")
                else:
                    print("❌ AI fix could not be generated.")

            elif choice == "4":
                # VIEW CODE - show full file content
                try:
                    with open(issue.file_path, "r", encoding="utf-8", errors="ignore") as f:
                        full_content = f.read()
                    print(f"\nFull file content ({issue.file_path}):")
                    print(f"{'-'*50}")
                    print(full_content)
                    print(f"{'-'*50}")
                except Exception as e:
                    print(f"Error reading file: {e}")

            else:
                print("Invalid choice. Please select 1-4.")

    return issues