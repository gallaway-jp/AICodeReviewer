# src/aicodereviewer/scanner.py
import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional


def scan_project(directory: str) -> List[Path]:
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


def parse_diff_file(diff_content: str) -> List[Dict[str, str]]:
    """Parse diff content and return list of changed files with their content."""
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


def get_diff_from_commits(project_path: str, commit_range: str) -> Optional[str]:
    """Generate diff content from git commit range."""
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


def scan_project_with_scope(directory: str, scope: str = 'project', diff_file: Optional[str] = None, commits: Optional[str] = None) -> List[Any]:
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