# src/aicodereviewer/scanner.py
"""
File scanning and diff parsing utilities for AICodeReviewer.

This module provides functionality for discovering source files in projects
and parsing diff files to identify changed code for targeted reviews.

Functions:
    scan_project: Recursively find source files by extension
    parse_diff_file: Parse unified diff format to extract changed files
    get_diff_from_commits: Generate diff from git commit range
    scan_project_with_scope: Main entry point for scoped file discovery
"""
import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional


def scan_project(directory: str) -> List[Path]:
    """
    Find source files for common programming languages in a directory.

    Recursively scans the given directory for files with extensions commonly
    used in software development, excluding common build/dependency directories.

    Supported languages and frameworks:
    - Python, JavaScript/TypeScript, Java, C/C++, C#, Go, Ruby, PHP, Rust
    - Swift, Kotlin, Objective-C, React (.jsx/.tsx), Vue, Svelte, Astro
    - Web technologies: HTML, CSS, Sass, Less, JSON, XML, YAML

    Args:
        directory (str): Root directory path to scan

    Returns:
        List[Path]: List of Path objects for discovered source files
    """
    # Add or remove extensions based on your needs
    # Supports: Python, JavaScript/TypeScript, Java, C/C++, C#, Go, Ruby, PHP, Rust, Swift, Kotlin, Objective-C
    # Frameworks: React (.jsx, .tsx), Laravel (.blade.php)
    # Web: HTML, CSS, Sass, Less, Vue, Svelte, Astro, JSON, XML, YAML
    valid_extensions = frozenset({
        '.py', '.js', '.ts', '.java', '.cpp', '.c', '.cs',
        '.go', '.rb', '.php', '.rs', '.swift', '.kt', '.m', '.h', '.mm',
        '.blade.php', '.jsx', '.tsx', '.html', '.css', '.scss', '.sass',
        '.less', '.vue', '.svelte', '.astro', '.json', '.xml', '.yaml', '.yml'
    })
    ignore_dirs = frozenset({'.git', '.venv', '__pycache__', 'node_modules', 'bin', 'obj', 'dist'})

    files = []
    for root, dirs, filenames in os.walk(directory):
        # Filter directories in-place for efficiency
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for filename in filenames:
            if Path(filename).suffix.lower() in valid_extensions:
                files.append(Path(root) / filename)
    return files


def parse_diff_file(diff_content: str) -> List[Dict[str, str]]:
    """
    Parse unified diff content and extract changed files with their content.

    Processes diff output to identify files that were modified, extracting
    the added and context lines for each changed file.

    Args:
        diff_content (str): Raw diff content in unified format

    Returns:
        List[Dict[str, str]]: List of dictionaries with 'filename' and 'content' keys
    """
    files = []
    lines = diff_content.splitlines()  # More efficient than split('\n')
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Check for file header (unified diff format)
        if line.startswith('+++ '):
            # Extract filename from +++ b/path/to/file
            match = re.match(r'\+\+\+ [ab]/(.+)', line)
            if match:
                filename = match.group(1)
                content_lines = []

                # Skip to next hunk or end
                i += 1
                while i < n:
                    hunk_line = lines[i]
                    if hunk_line.startswith('@@'):
                        # Process hunk content
                        i += 1
                        while i < n:
                            content_line = lines[i]
                            if content_line.startswith(('+++', '---', '@@')):
                                break
                            elif content_line.startswith(('+', ' ')):
                                # Added or context line
                                content_lines.append(content_line[1:])  # Remove prefix
                            # Skip removed lines (start with -)
                            i += 1
                        break
                    i += 1

                if content_lines:  # Only add if there's actual content
                    files.append({
                        'filename': filename,
                        'content': '\n'.join(content_lines)
                    })
        else:
            i += 1

    return files


def get_diff_from_commits(project_path: str, commit_range: str) -> Optional[str]:
    """
    Generate diff content from a git commit range.

    Uses git diff to extract changes between commits for targeted code review.

    Args:
        project_path (str): Path to the git repository
        commit_range (str): Git commit range (e.g., 'HEAD~1..HEAD' or 'abc123..def456')

    Returns:
        Optional[str]: Diff content as string, or None if git command fails
    """
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
    """
    Scan project files based on the specified review scope.

    Main entry point for file discovery that handles both full project scans
    and diff-based targeted reviews.

    Args:
        directory (str): Root directory path to scan
        scope (str): Review scope ('project' or 'diff')
        diff_file (Optional[str]): Path to diff file for diff scope
        commits (Optional[str]): Git commit range for diff scope

    Returns:
        List[Any]: For project scope: List[Path] of file paths
                   For diff scope: List[Dict] with file info and changed content
    """
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