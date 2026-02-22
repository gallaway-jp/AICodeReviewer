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
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import config

__all__ = [
    "scan_project",
    "parse_diff_file",
    "parse_diff_file_enhanced",
    "detect_vcs_type",
    "get_diff_from_commits",
    "get_commit_messages",
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


# ── Diff hunk data structures ──────────────────────────────────────────────

@dataclass
class DiffHunk:
    """A single hunk within a file diff.

    Attributes:
        header:          Raw ``@@`` header string.
        function_name:   Function/class name extracted from the hunk header
                         (e.g. ``def authenticate_user()``), or ``None``.
        old_start:       Start line in the original file.
        new_start:       Start line in the new file.
        added:           List of ``(line_no, text)`` for ``+``-marked lines.
        removed:         List of ``(line_no, text)`` for ``-``-marked lines.
        context_before:  Unchanged lines *above* the first change in this hunk.
        context_after:   Unchanged lines *below* the last change in this hunk.
    """

    header: str = ""
    function_name: Optional[str] = None
    old_start: int = 0
    new_start: int = 0
    added: List[Tuple[int, str]] = field(default_factory=list)
    removed: List[Tuple[int, str]] = field(default_factory=list)
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)


@dataclass
class EnhancedDiffFile:
    """Enhanced diff result for a single file.

    Carries the same ``filename`` / ``content`` fields that the legacy
    :func:`parse_diff_file` returns **plus** rich per-hunk data.
    """

    filename: str
    content: str  # merged added+context lines (backward-compatible)
    hunks: List[DiffHunk] = field(default_factory=list)


# ── Hunk header regex ──────────────────────────────────────────────────────
_HUNK_RE = re.compile(
    r"^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@\s*(.*)"
)


def _extract_function_from_hunk_ctx(header_ctx: str) -> Optional[str]:
    """Extract a function/class name from the optional hunk-header context.

    Git often appends the nearest enclosing function/class after the
    ``@@`` range, e.g. ``@@ -42,10 +42,15 @@ def authenticate_user():``
    """
    if not header_ctx:
        return None
    header_ctx = header_ctx.strip()
    # Python: def foo(…) / class Foo
    m = re.match(r"((?:def|class|async\s+def)\s+\w+[^:]*)", header_ctx)
    if m:
        return m.group(1).strip()
    # JS/TS: function foo / const foo = / export function
    m = re.match(r"((?:export\s+)?(?:async\s+)?(?:function\*?|const|let|var)\s+\w+[^{]*)", header_ctx)
    if m:
        return m.group(1).strip()
    # Java/C#: access modifier + type + name
    m = re.match(r"((?:public|private|protected|static|final|virtual|override|abstract)\s+.*\w+\s*\([^)]*\))", header_ctx)
    if m:
        return m.group(1).strip()
    # Anything else with parens looks like a function signature
    m = re.match(r"(\w[\w\s<>]*\w\s*\([^)]*\))", header_ctx)
    if m:
        return m.group(1).strip()
    return header_ctx if len(header_ctx) > 2 else None


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


def parse_diff_file_enhanced(
    diff_content: str,
    context_lines: int = 20,
) -> List[EnhancedDiffFile]:
    """Parse unified diff preserving rich per-hunk metadata.

    Unlike :func:`parse_diff_file`, this function keeps:

    * **Added / removed lines** with their line numbers.
    * **Function/class context** extracted from the ``@@`` hunk header.
    * **Surrounding unchanged context** (up to *context_lines* before
      and after the changed region within each hunk).

    The returned :class:`EnhancedDiffFile` objects also carry a
    ``content`` field identical to what :func:`parse_diff_file` produces
    so callers that don't need hunk-level detail remain compatible.

    Args:
        diff_content: Raw unified-diff text.
        context_lines: Maximum unchanged lines to keep before/after
                       the first/last change in each hunk (default 20).

    Returns:
        List of :class:`EnhancedDiffFile` — one per file in the diff.
    """
    results_map: Dict[str, EnhancedDiffFile] = {}  # filename → result
    lines = diff_content.splitlines()
    current_file: Optional[str] = None
    current_hunk: Optional[DiffHunk] = None
    # For backward-compatible content field
    content_accumulator: Dict[str, List[str]] = {}

    # Track line numbers while walking the diff
    old_lineno = 0
    new_lineno = 0
    # Buffer of context lines seen *before* any change in the current hunk
    pre_change_buf: List[str] = []
    # Buffer of context lines seen *after* the last change
    post_change_buf: List[str] = []
    seen_change_in_hunk = False

    def _flush_post_context() -> None:
        """Attach accumulated post-change context to the current hunk."""
        nonlocal post_change_buf
        if current_hunk is not None and post_change_buf:
            current_hunk.context_after = post_change_buf[:context_lines]
        post_change_buf = []

    def _flush_pre_context() -> None:
        """Attach accumulated pre-change context to the current hunk."""
        nonlocal pre_change_buf
        if current_hunk is not None and pre_change_buf:
            current_hunk.context_before = pre_change_buf[-context_lines:]
        pre_change_buf = []

    for line in lines:
        # ── File header ────────────────────────────────────────────────
        if line.startswith('+++ '):
            _flush_post_context()
            m = re.match(r'\+\+\+ [ab]/(.+)', line)
            current_file = m.group(1) if m else None
            if current_file and current_file not in results_map:
                results_map[current_file] = EnhancedDiffFile(
                    filename=current_file, content=""
                )
                content_accumulator[current_file] = []
            current_hunk = None
            seen_change_in_hunk = False
            pre_change_buf = []
            post_change_buf = []
            continue

        if line.startswith('--- '):
            continue

        # ── Hunk header ────────────────────────────────────────────────
        m_hunk = _HUNK_RE.match(line) if line.startswith('@@') else None
        if m_hunk:
            # Flush context from previous hunk
            _flush_post_context()
            if current_hunk is not None and not seen_change_in_hunk:
                _flush_pre_context()

            old_lineno = int(m_hunk.group(1))
            new_lineno = int(m_hunk.group(2))
            func_ctx = m_hunk.group(3).strip() if m_hunk.group(3) else ""
            func_name = _extract_function_from_hunk_ctx(func_ctx)

            current_hunk = DiffHunk(
                header=line,
                function_name=func_name,
                old_start=old_lineno,
                new_start=new_lineno,
            )
            if current_file and current_file in results_map:
                results_map[current_file].hunks.append(current_hunk)
            seen_change_in_hunk = False
            pre_change_buf = []
            post_change_buf = []
            continue

        # ── Diff body lines ────────────────────────────────────────────
        if current_file is None or current_hunk is None:
            continue

        if line.startswith('+'):
            if not seen_change_in_hunk:
                _flush_pre_context()
                seen_change_in_hunk = True
            elif post_change_buf:
                # More changes after some context → those context lines
                # are really *between* changes, keep them as post of the
                # prior change *and* pre of this change.
                _flush_post_context()
            text = line[1:]
            current_hunk.added.append((new_lineno, text))
            new_lineno += 1
            content_accumulator.setdefault(current_file, []).append(text)

        elif line.startswith('-'):
            if not seen_change_in_hunk:
                _flush_pre_context()
                seen_change_in_hunk = True
            elif post_change_buf:
                _flush_post_context()
            text = line[1:]
            current_hunk.removed.append((old_lineno, text))
            old_lineno += 1

        elif line.startswith(' '):
            text = line[1:]
            if not seen_change_in_hunk:
                pre_change_buf.append(text)
            else:
                post_change_buf.append(text)
            old_lineno += 1
            new_lineno += 1
            content_accumulator.setdefault(current_file, []).append(text)

    # Flush trailing context for the very last hunk
    _flush_post_context()

    # Build backward-compatible content field
    result: List[EnhancedDiffFile] = []
    for fname, edf in results_map.items():
        parts = content_accumulator.get(fname, [])
        edf.content = '\n'.join(parts) if parts else ''
        if edf.content or edf.hunks:
            result.append(edf)
    return result


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


def get_commit_messages(
    project_path: str,
    commit_range: str,
) -> Optional[str]:
    """Retrieve commit messages for a Git/SVN revision range.

    Args:
        project_path: Path to the repository directory.
        commit_range: Commit/revision range (Git or SVN format).

    Returns:
        Concatenated commit messages, or *None* on failure/unsupported VCS.
    """
    vcs_type = detect_vcs_type(project_path)
    if vcs_type is None:
        return None

    try:
        repo_root = _find_vcs_root(project_path, vcs_type)
        cwd = project_path if repo_root is None else str(repo_root)

        if vcs_type == 'git':
            normalized = _normalize_commit_range(vcs_type, commit_range)
            cmd = ['git', 'log', '--format=%B', normalized]
            result = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, check=True,
                encoding='utf-8', errors='replace',
            )
            return result.stdout.strip() or None
        elif vcs_type == 'svn':
            rev_range = _normalize_commit_range(vcs_type, commit_range)
            cmd = ['svn', 'log', '-r', rev_range]
            result = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, check=True,
                encoding='utf-8', errors='replace',
            )
            return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.debug("Could not retrieve commit messages: %s", exc)
    return None


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

        # Parse diff using enhanced parser to get hunk-level detail
        diff_context_lines = config.get('processing', 'diff_context_lines', 20)
        enhanced_files = parse_diff_file_enhanced(diff_content, context_lines=diff_context_lines)

        # Retrieve commit messages when available
        commit_messages: Optional[str] = None
        include_msgs = config.get('processing', 'include_commit_messages', True)
        if include_msgs and commits and directory:
            commit_messages = get_commit_messages(directory, commits)
            if commit_messages:
                logger.info("Retrieved commit messages for diff context")

        # Convert to file info dicts (backward-compatible + enhanced)
        for edf in enhanced_files:
            if directory:
                file_path = Path(directory) / edf.filename
            else:
                file_path = Path(edf.filename)  # relative path

            entry: Dict[str, Any] = {
                'path': file_path,
                'content': edf.content,
                'filename': edf.filename,
                # ── Diff-aware fields ──────────────────────────────────
                'is_diff': True,
                'hunks': edf.hunks,
            }
            if commit_messages:
                entry['commit_messages'] = commit_messages

            changed_files.append(entry)

        return changed_files

    return []