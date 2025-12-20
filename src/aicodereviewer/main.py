# src/aicodereviewer/main.py
import json
import os
import argparse
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

from .auth import get_profile_name, set_profile_name, clear_profile, get_system_language
from .bedrock import BedrockClient

@dataclass
class ReviewIssue:
    """Represents a single code review issue"""
    file_path: str
    line_number: Optional[int]
    issue_type: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    description: str
    code_snippet: str
    ai_feedback: str
    status: str = "pending"  # 'pending', 'resolved', 'ignored', 'ai_fixed'
    resolution_reason: Optional[str] = None
    resolved_at: Optional[datetime] = None
    ai_fix_applied: Optional[str] = None

@dataclass
class ReviewReport:
    """Complete review report with all issues and metadata"""
    project_path: str
    review_type: str
    scope: str
    total_files_scanned: int
    issues_found: List[ReviewIssue]
    generated_at: datetime
    language: str
    diff_source: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data['generated_at'] = self.generated_at.isoformat()
        for issue in data['issues_found']:
            if issue['resolved_at']:
                issue['resolved_at'] = datetime.fromisoformat(issue['resolved_at']).isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReviewReport':
        """Create from dictionary (for loading saved reports)"""
        # Convert ISO strings back to datetime objects
        data['generated_at'] = datetime.fromisoformat(data['generated_at'])
        for issue in data['issues_found']:
            if issue['resolved_at']:
                issue['resolved_at'] = datetime.fromisoformat(issue['resolved_at'])
        return cls(**data)
from aicodereviewer.auth import get_profile_name, set_profile_name, clear_profile
from aicodereviewer.bedrock import BedrockClient

def scan_project(directory):
    """Finds source files for most common programming languages."""
    # Add or remove extensions based on your needs
    # Supports: Python, JavaScript/TypeScript, Java, C/C++, C#, Go, Ruby, PHP, Rust, Swift, Kotlin, Objective-C
    # Frameworks: React (.jsx, .tsx), Laravel (.blade.php)
    # Web: HTML, CSS, Sass, Less, Vue, Svelte, Astro, JSON, XML, YAML
    valid_extensions = {
        '.py', '.js', '.ts', '.java', '.cpp', '.c', '.cs', 
        '.go', '.rb', '.php', '.rs', '.swift', '.kt', '.m', '.h', '.mm',
        '.blade.php', '.jsx', '.tsx', '.html', '.css', '.scss', '.sass', 
        '.less', '.vue', '.svelte', '.astro', '.json', '.xml', '.yaml', '.yml'
    }
    files = []
    ignore_dirs = {'.git', '.venv', '__pycache__', 'node_modules', 'bin', 'obj', 'dist'}
    
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for f in filenames:
            ext = Path(f).suffix.lower()
            if ext in valid_extensions:
                files.append(Path(root) / f)
    return files

def parse_diff_file(diff_content):
    """Parse diff content and return list of changed files with their content."""
    import re
    
    files = []
    current_file = None
    current_content = []
    
    lines = diff_content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check for file header (unified diff format)
        if line.startswith('+++ '):
            # Save previous file if exists
            if current_file and current_content:
                files.append({
                    'filename': current_file,
                    'content': '\n'.join(current_content)
                })
            
            # Extract filename from +++ b/path/to/file
            match = re.match(r'\+\+\+ [ab]/(.+)', line)
            if match:
                current_file = match.group(1)
                current_content = []
        
        # Check for diff hunks
        elif line.startswith('@@') and current_file:
            # Skip hunk header, start collecting content
            i += 1
            while i < len(lines) and not (lines[i].startswith('+++') or lines[i].startswith('---') or lines[i].startswith('@@')):
                line = lines[i]
                if line.startswith('+'):
                    # Added line
                    current_content.append(line[1:])  # Remove the + prefix
                elif line.startswith(' '):
                    # Context line
                    current_content.append(line[1:])  # Remove the space prefix
                # Skip removed lines (start with -)
                i += 1
            continue
            
        i += 1
    
    # Save the last file
    if current_file and current_content:
        files.append({
            'filename': current_file,
            'content': '\n'.join(current_content)
        })
    
    return files

def get_diff_from_commits(project_path, commit_range):
    """Generate diff content from git commit range."""
    import subprocess
    
    try:
        result = subprocess.run(
            ['git', 'diff', commit_range],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error getting diff from commits: {e}")
        return None
    except FileNotFoundError:
        print("Git not found. Please ensure git is installed and in PATH.")
        return None

def scan_project_with_scope(directory, scope='project', diff_file=None, commits=None):
    """Scan project files based on review scope."""
    if scope == 'project':
        return scan_project(directory)
    elif scope == 'diff':
        changed_files = []
        
        # Get diff content
        if diff_file:
            try:
                with open(diff_file, 'r', encoding='utf-8') as f:
                    diff_content = f.read()
            except FileNotFoundError:
                print(f"Diff file not found: {diff_file}")
                return []
        elif commits:
            diff_content = get_diff_from_commits(directory, commits)
            if diff_content is None:
                return []
        else:
            return []
        
        # Parse diff and get changed files
        diff_files = parse_diff_file(diff_content)
        
        # Convert to file paths relative to project
        for diff_file_info in diff_files:
            file_path = Path(directory) / diff_file_info['filename']
            if file_path.exists():
                # Create a temporary file-like object with the changed content
                changed_files.append({
                    'path': file_path,
                    'content': diff_file_info['content'],
                    'filename': diff_file_info['filename']
                })
        
        return changed_files
    
    return []


def collect_review_issues(target_files, review_type: str, client, lang: str) -> List[ReviewIssue]:
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


def interactive_review_confirmation(issues: List[ReviewIssue], client, review_type: str, lang: str) -> List[ReviewIssue]:
    """Interactive process to confirm and resolve each review issue"""
    
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
                            import shutil
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


def generate_review_report(report: ReviewReport, output_file: str = None) -> str:
    """Generate and save a review report"""
    if not output_file:
        timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
        output_file = f"review_report_{timestamp}.json"
    
    # Save JSON report
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
    
    # Generate human-readable summary
    summary_file = output_file.replace('.json', '_summary.txt')
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(f"AI Code Review Report\n")
        f.write(f"{'='*50}\n\n")
        f.write(f"Project: {report.project_path}\n")
        f.write(f"Review Type: {report.review_type}\n")
        f.write(f"Scope: {report.scope}\n")
        f.write(f"Files Scanned: {report.total_files_scanned}\n")
        f.write(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Language: {report.language}\n")
        if report.diff_source:
            f.write(f"Diff Source: {report.diff_source}\n")
        f.write(f"\nIssues Summary:\n")
        f.write(f"{'-'*30}\n")
        
        status_counts = {}
        for issue in report.issues_found:
            status_counts[issue['status']] = status_counts.get(issue['status'], 0) + 1
        
        for status, count in status_counts.items():
            f.write(f"{status.capitalize()}: {count}\n")
        
        f.write(f"\nDetailed Issues:\n")
        f.write(f"{'='*50}\n")
        
        for i, issue in enumerate(report.issues_found, 1):
            f.write(f"\nIssue {i}:\n")
            f.write(f"  File: {issue['file_path']}\n")
            f.write(f"  Type: {issue['issue_type']}\n")
            f.write(f"  Severity: {issue['severity']}\n")
            f.write(f"  Status: {issue['status']}\n")
            if issue['resolution_reason']:
                f.write(f"  Resolution: {issue['resolution_reason']}\n")
            f.write(f"  AI Feedback: {issue['ai_feedback'][:200]}...\n")
    
def cleanup_old_backups(project_path: str, max_age_hours: int = 24):
    """Clean up old backup files to prevent disk space issues"""
    import glob
    import time
    
    try:
        backup_pattern = os.path.join(project_path, "**", "*.backup")
        backup_files = glob.glob(backup_pattern, recursive=True)
        
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for backup_file in backup_files:
            if os.path.getmtime(backup_file) < current_time - max_age_seconds:
                try:
                    os.remove(backup_file)
                    print(f"🗑️ Cleaned up old backup: {backup_file}")
                except OSError:
                    pass  # Ignore if can't delete
    except Exception:
        pass  # Don't fail if cleanup doesn't work


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
    
    # Collect all review issues
    print(f"\nCollecting review issues from {len(target_files)} files...")
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
