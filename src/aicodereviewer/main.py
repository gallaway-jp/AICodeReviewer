# src/aicodereviewer/main.py
import os
import argparse
import locale
from pathlib import Path
from aicodereviewer.auth import get_profile_name, set_profile_name, clear_profile
from aicodereviewer.bedrock import BedrockClient

def get_system_language():
    """Detects if the system language is Japanese, defaults to English."""
    try:
        lang, _ = locale.getdefaultlocale()
        if lang and lang.startswith('ja'):
            return 'ja'
    except:
        pass
    return 'en'

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
    
    # Continue with normal code review...

    # Determine final language
    target_lang = args.lang
    if target_lang == 'default':
        target_lang = get_system_language()

    profile = get_profile_name()
    client = BedrockClient(profile)

    scope_desc = "entire project" if args.scope == 'project' else f"changes ({args.diff_file or args.commits})"
    print(f"Scanning {args.path} - Scope: {scope_desc} (Output Language: {target_lang})...")
    target_files = scan_project_with_scope(args.path, args.scope, args.diff_file, args.commits)
    
    if args.scope == 'project':
        # Original logic for project scope
        for file_path in target_files:
            print(f"\n[Reviewing] {file_path}")
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read()
                    # Pass the target language to the Bedrock client
                    feedback = client.get_review(code, review_type=args.type, lang=target_lang)
                    print(feedback)
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
    else:
        # Diff scope logic
        if not target_files:
            print("No changed files found in the diff.")
            return
            
        for file_info in target_files:
            print(f"\n[Reviewing] {file_info['filename']}")
            try:
                code = file_info['content']
                if code.strip():  # Only review if there's content
                    feedback = client.get_review(code, review_type=args.type, lang=target_lang)
                    print(feedback)
                else:
                    print("No content to review in this file.")
            except Exception as e:
                print(f"Error processing file {file_info['filename']}: {e}")

if __name__ == "__main__":
    main()
