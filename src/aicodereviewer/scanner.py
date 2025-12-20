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
    """Parse diff content and return list of changed files with their content."""
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