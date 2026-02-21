# src/aicodereviewer/scanner.py
"""
File scanning and diff parsing utilities for AICodeReviewer.

This module provides functionality for discovering source files in projects
and parsing diff files to identify changed code for targeted reviews.

Functions:
    scan_project: Recursively find source files by extension
    parse_diff_file: Parse unified diff format to extract changed files
    detect_vcs_type: Detect whether project uses Git or SVN
    get_diff_from_commits: Generate diff from Git or SVN commit/revision range
    scan_project_with_scope: Main entry point for scoped file discovery
"""
import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import config

__all__ = [
    "scan_project",
    "parse_diff_file",
    "detect_vcs_type",
    "get_diff_from_commits",
    "scan_project_with_scope",
]

logger = logging.getLogger(__name__)


def scan_project(directory: str) -> List[Path]:
    """
    Find source files for common programming languages in a directory.

    Recursively scans the given directory for files with extensions commonly
    used in software development, excluding common build/dependency directories.
    Supports parallel scanning when enable_parallel_processing is true.

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

    # Check if parallel processing is enabled
    enable_parallel = config.get('processing', 'enable_parallel_processing', False)
    
    files = []
    
    # Collect per-directory batches (common to both paths)
    dir_batches: List = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        if filenames:
            dir_batches.append((root, filenames))

    if enable_parallel and dir_batches:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(_scan_directory_batch, root, fns, valid_extensions)
                for root, fns in dir_batches
            ]
            for future in as_completed(futures):
                files.extend(future.result())
        logger.debug("Parallel scan complete: %d files found", len(files))
    else:
        for root, fns in dir_batches:
            files.extend(_scan_directory_batch(root, fns, valid_extensions))
    
    return files


def _scan_directory_batch(root: str, filenames: List[str], valid_extensions: frozenset) -> List[Path]:
    """
    Scan a single directory batch for matching files (helper for parallel scanning).
    
    Args:
        root (str): Root directory path
        filenames (List[str]): List of filenames in the directory
        valid_extensions (frozenset): Set of valid file extensions
    
    Returns:
        List[Path]: List of matching files in this batch
    """
    batch_files = []
    for filename in filenames:
        if Path(filename).suffix.lower() in valid_extensions:
            batch_files.append(Path(root) / filename)
    return batch_files


def parse_diff_file(diff_content: str) -> List[Dict[str, str]]:
    """
    Parse unified diff content and extract changed files with their content.

    Supports multiple hunks per file and collects added ('+') and
    context (' ') lines while skipping removed ('-') lines.

    Args:
        diff_content (str): Raw diff content in unified format

    Returns:
        List[Dict[str, str]]: List of dictionaries with 'filename' and 'content' keys
    """
    files: List[Dict[str, str]] = []
    lines = diff_content.splitlines()
    current_file: Optional[str] = None
    content_accumulator: Dict[str, List[str]] = {}
    in_hunk = False

    for line in lines:
        if line.startswith('+++ '):
            # Start of file header; extract filename
            m = re.match(r'\+\+\+ [ab]/(.+)', line)
            current_file = m.group(1) if m else None
            if current_file and current_file not in content_accumulator:
                content_accumulator[current_file] = []
            in_hunk = False
            continue

        if line.startswith('@@'):
            # Enter a hunk for the current file
            in_hunk = True
            continue

        if current_file and in_hunk:
            if line.startswith(('+++', '---', '@@')):
                # Header or next hunk marker
                if line.startswith('@@'):
                    in_hunk = True
                else:
                    in_hunk = False
                continue
            if line.startswith(('+', ' ')):
                content_accumulator[current_file].append(line[1:])
            # skip removed lines starting with '-'

    for fname, parts in content_accumulator.items():
        if parts:
            files.append({'filename': fname, 'content': '\n'.join(parts)})

    return files


def detect_vcs_type(project_path: str) -> Optional[str]:
    """
    Detect the version control system used in the project.

    Searches upward from the provided path for the presence of a .git or .svn
    directory to determine whether the project uses Git or SVN. This allows
    passing a subdirectory within a repository and still detecting the VCS.

    Args:
        project_path (str): Path to the project directory (or subdirectory)

    Returns:
        Optional[str]: 'git', 'svn', or None if no VCS detected
    """
    p = Path(project_path)
    for candidate in [p] + list(p.parents):
        git_dir = candidate / '.git'
        if git_dir.exists():
            return 'git'
        svn_dir = candidate / '.svn'
        if svn_dir.exists():
            return 'svn'
    return None


def _find_vcs_root(project_path: str, vcs_type: str) -> Optional[Path]:
    """Find the repository root directory for the given VCS by walking upward."""
    p = Path(project_path)
    marker = '.git' if vcs_type == 'git' else '.svn'
    for candidate in [p] + list(p.parents):
        if (candidate / marker).exists():
            return candidate
    return None


def _normalize_commit_range(vcs_type: str, commit_range: str) -> str:
    """
    Normalize commit/revision range across VCS tools.

    - Git: pass through (e.g., 'HEAD~1..HEAD', 'abc..def').
    - SVN: accept 'REV1:REV2', 'REV1..REV2', or keywords like 'PREV:HEAD'.
      Convert '..' to ':' for SVN.
    """
    if vcs_type == 'svn':
        return commit_range if ':' in commit_range else commit_range.replace('..', ':')
    return commit_range


def get_diff_from_commits(project_path: str, commit_range: str) -> Optional[str]:
    """
    Generate diff content from a commit/revision range.

    Automatically detects whether the project uses Git or SVN and uses
    the appropriate diff command to extract changes for targeted code review.

    Args:
        project_path (str): Path to the repository (Git or SVN)
        commit_range (str): Commit/revision range
            - Git format: 'HEAD~1..HEAD' or 'abc123..def456'
            - SVN format: 'PREV:HEAD' or '100:101' (will be converted to -r format)

    Returns:
        Optional[str]: Diff content as string, or None if command fails
    """
    vcs_type = detect_vcs_type(project_path)

    if vcs_type is None:
        logger.warning("No version control system detected in %s", project_path)
        logger.info("Please ensure the project is a Git or SVN repository.")
        return None

    try:
        repo_root = _find_vcs_root(project_path, vcs_type)
        cwd = project_path if repo_root is None else str(repo_root)
        in_subdir = repo_root is not None and Path(project_path) != repo_root

        if vcs_type == 'git':
            # Limit diff scope only when running from a subdirectory
            base_cmd = ['git', 'diff', _normalize_commit_range(vcs_type, commit_range)]
            cmd = base_cmd + (['--', '.'] if in_subdir else [])
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8", errors="replace",
            )
        elif vcs_type == 'svn':
            # SVN expects '-r REV1:REV2'; only limit to '.' when in a subdirectory
            rev_range = _normalize_commit_range(vcs_type, commit_range)
            base_cmd = ['svn', 'diff', '-r', rev_range]
            cmd = base_cmd + (['.'] if in_subdir else [])
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8", errors="replace",
            )
        else:
            logger.error("Unsupported VCS type: %s", vcs_type)
            return None

        return result.stdout

    except subprocess.CalledProcessError as e:
        logger.error("Error getting diff from %s: %s", vcs_type.upper(), e)
        return None
    except FileNotFoundError:
        logger.error("%s not found. Please ensure %s is installed and in PATH.", vcs_type.upper(), vcs_type)
        return None


def scan_project_with_scope(directory: Optional[str], scope: str = 'project', diff_file: Optional[str] = None, commits: Optional[str] = None) -> List[Any]:
    """
    Scan project files based on the specified review scope.

    Main entry point for file discovery that handles both full project scans
    and diff-based targeted reviews.

    Args:
        directory (Optional[str]): Root directory path to scan (optional for diff scope)
        scope (str): Review scope ('project' or 'diff')
        diff_file (Optional[str]): Path to diff file for diff scope
        commits (Optional[str]): Git/SVN commit/revision range for diff scope

    Returns:
        List[Any]: For project scope: List[Path] of file paths
                   For diff scope: List[Dict] with file info and content (full file if directory provided, else diff content)
    """
    if scope == 'project':
        assert directory is not None, "directory is required for project scope"
        return scan_project(directory)
    elif scope == 'diff':
        changed_files = []

        # Get diff content
        if diff_file:
            try:
                with open(diff_file, 'r', encoding='utf-8') as f:
                    diff_content = f.read()
            except FileNotFoundError:
                logger.error("Diff file not found: %s", diff_file)
                return []
        elif commits:
            if directory is None:
                logger.error("Directory is required when using --commits for diff scope")
                return []
            diff_content = get_diff_from_commits(directory, commits)
            if diff_content is None:
                return []
        else:
            return []

        # Parse diff and get changed files
        diff_files = parse_diff_file(diff_content)

        # Convert to file paths relative to project
        for diff_file_info in diff_files:
            if directory:
                file_path = Path(directory) / diff_file_info['filename']
            else:
                file_path = Path(diff_file_info['filename'])  # relative path

            # Always use diff content so only changed code is reviewed
            content = diff_file_info['content']

            changed_files.append({
                'path': file_path,
                'content': content,
                'filename': diff_file_info['filename']
            })

        return changed_files

    return []