# src/aicodereviewer/context_collector.py
"""
Lightweight project context builder.

Scans the project root for framework markers, import graphs, and
structural conventions, then produces a compact summary string (~500
tokens) that is injected into every AI review prompt so the model has
broader codebase awareness.

Also detects specific frameworks (Django, FastAPI, React …) so
framework-tailored prompt supplements can be appended.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import config

__all__ = [
    "collect_project_context",
    "detect_frameworks",
    "ProjectContext",
]

logger = logging.getLogger(__name__)

# ── Project type markers ───────────────────────────────────────────────────

_LANGUAGE_MARKERS: Dict[str, List[str]] = {
    "Python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
    "JavaScript": ["package.json"],
    "TypeScript": ["tsconfig.json"],
    "Rust": ["Cargo.toml"],
    "Go": ["go.mod"],
    "Java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "C#": ["*.csproj", "*.sln"],
    "Ruby": ["Gemfile"],
    "PHP": ["composer.json"],
    "Swift": ["Package.swift"],
    "Kotlin": ["build.gradle.kts"],
}

# Framework detection: (marker_files, marker_imports/content)
_FRAMEWORK_MARKERS: Dict[str, Dict[str, Any]] = {
    # Python frameworks
    "django": {
        "files": ["manage.py"],
        "content_markers": {"settings.py": "INSTALLED_APPS"},
        "import_pattern": r"(?:from|import)\s+django",
    },
    "flask": {
        "files": [],
        "import_pattern": r"(?:from|import)\s+flask",
    },
    "fastapi": {
        "files": [],
        "import_pattern": r"(?:from|import)\s+fastapi",
    },
    "pytest": {
        "files": ["pytest.ini", "conftest.py"],
        "content_markers": {"pyproject.toml": "[tool.pytest"},
        "import_pattern": r"(?:from|import)\s+pytest",
    },
    # JavaScript / TypeScript frameworks
    "react": {
        "content_markers": {"package.json": '"react"'},
        "import_pattern": r"(?:from|import)\s+['\"]react['\"]",
    },
    "next.js": {
        "files": ["next.config.js", "next.config.mjs", "next.config.ts"],
        "content_markers": {"package.json": '"next"'},
    },
    "express": {
        "content_markers": {"package.json": '"express"'},
        "import_pattern": r"require\(['\"]express['\"]\)",
    },
    "vue": {
        "content_markers": {"package.json": '"vue"'},
        "import_pattern": r"(?:from|import)\s+['\"]vue['\"]",
    },
    "angular": {
        "files": ["angular.json"],
        "content_markers": {"package.json": '"@angular/core"'},
    },
    # Java
    "spring_boot": {
        "import_pattern": r"org\.springframework\.boot",
        "content_markers": {"pom.xml": "spring-boot"},
    },
    # Ruby
    "rails": {
        "files": ["config/routes.rb", "Rakefile"],
        "content_markers": {"Gemfile": "rails"},
    },
}

# Tools / linters / CI
_TOOL_MARKERS: Dict[str, List[str]] = {
    "ruff": ["ruff.toml", ".ruff.toml"],
    "black": [],  # detected via pyproject.toml [tool.black]
    "eslint": [".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml"],
    "prettier": [".prettierrc", ".prettierrc.json", ".prettierrc.js"],
    "mypy": ["mypy.ini", ".mypy.ini"],
    "flake8": [".flake8"],
    "github_actions": [".github/workflows"],
    "gitlab_ci": [".gitlab-ci.yml"],
    "docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
}


# ── Data structure ─────────────────────────────────────────────────────────

class ProjectContext:
    """Holds collected project context data."""

    def __init__(self) -> None:
        self.languages: List[str] = []
        self.frameworks: List[str] = []
        self.tools: List[str] = []
        self.dir_structure: str = ""
        self.dependency_edges: List[Tuple[str, str]] = []
        self.naming_convention: str = "unknown"
        self.file_counts: Dict[str, int] = {}
        self.total_files: int = 0

    def to_prompt_string(self, max_tokens: int = 500) -> str:
        """Render a compact prompt block (~*max_tokens* tokens)."""
        parts: List[str] = ["PROJECT CONTEXT:\n"]

        if self.languages:
            parts.append(f"Language(s): {', '.join(self.languages)}")
        if self.frameworks:
            parts.append(f"Framework(s): {', '.join(self.frameworks)}")
        if self.tools:
            parts.append(f"Tools: {', '.join(self.tools)}")

        if self.dir_structure:
            parts.append(f"\nStructure:\n{self.dir_structure}")

        if self.dependency_edges:
            parts.append("\nDependencies (top edges):")
            for src, dst in self.dependency_edges[:20]:
                parts.append(f"  {src} → {dst}")

        if self.naming_convention != "unknown":
            parts.append(f"\nNaming: {self.naming_convention}")

        text = "\n".join(parts)
        # Rough token estimate: 1 token ≈ 4 chars
        char_limit = max_tokens * 4
        if len(text) > char_limit:
            text = text[:char_limit] + "\n… (truncated)"
        return text


# ── Core collector ─────────────────────────────────────────────────────────

def collect_project_context(
    project_path: str,
    scanned_files: Optional[List[str]] = None,
) -> ProjectContext:
    """Build a :class:`ProjectContext` for the given project root.

    Args:
        project_path:  Absolute path to the project root.
        scanned_files: Optional list of already-scanned file paths.
                       If provided, import analysis is limited to these.

    Returns:
        Populated :class:`ProjectContext`.
    """
    ctx = ProjectContext()
    root = Path(project_path)

    if not root.is_dir():
        logger.warning("Project path %s is not a directory", project_path)
        return ctx

    # 1. Detect languages
    ctx.languages = _detect_languages(root)

    # 2. Detect frameworks
    ctx.frameworks = detect_frameworks(root, scanned_files)

    # 3. Detect tools
    ctx.tools = _detect_tools(root)

    # 4. Directory structure (top 2 levels)
    ctx.dir_structure = _build_dir_tree(root, max_depth=2)

    # 5. Import graph (limited to scanned files or src/)
    files_for_graph = scanned_files or _find_source_files(root)
    ctx.dependency_edges = _build_import_graph(files_for_graph, root)

    # 6. Naming convention
    ctx.naming_convention = _detect_naming(files_for_graph)

    # 7. File counts
    ctx.file_counts, ctx.total_files = _count_files(root)

    logger.info(
        "Project context: %s, frameworks=%s, %d files",
        "+".join(ctx.languages) or "unknown",
        ctx.frameworks,
        ctx.total_files,
    )
    return ctx


# ── Language detection ─────────────────────────────────────────────────────

def _detect_languages(root: Path) -> List[str]:
    detected: List[str] = []
    for lang, markers in _LANGUAGE_MARKERS.items():
        for marker in markers:
            if "*" in marker:
                if list(root.glob(marker)):
                    detected.append(lang)
                    break
            elif (root / marker).exists():
                detected.append(lang)
                break
    return detected


# ── Framework detection ────────────────────────────────────────────────────

def detect_frameworks(
    root: Path,
    scanned_files: Optional[List[str]] = None,
) -> List[str]:
    """Detect frameworks from marker files and import patterns."""
    detected: List[str] = []

    for fw, spec in _FRAMEWORK_MARKERS.items():
        found = False

        # Check marker files
        for marker_file in spec.get("files", []):
            if (root / marker_file).exists():
                found = True
                break

        # Check content markers (look for specific text in specific files)
        if not found:
            for fpath, needle in spec.get("content_markers", {}).items():
                target = root / fpath
                if target.exists():
                    try:
                        text = target.read_text(encoding="utf-8", errors="ignore")[:10_000]
                        if needle in text:
                            found = True
                            break
                    except OSError:
                        pass

        # Check import patterns in scanned source files
        if not found and spec.get("import_pattern") and scanned_files:
            pattern = re.compile(spec["import_pattern"])
            for fpath in scanned_files[:50]:  # limit to avoid scanning entire project
                try:
                    text = Path(fpath).read_text(encoding="utf-8", errors="ignore")[:5_000]
                    if pattern.search(text):
                        found = True
                        break
                except OSError:
                    pass

        if found:
            detected.append(fw)

    return detected


# ── Tool / linter detection ────────────────────────────────────────────────

def _detect_tools(root: Path) -> List[str]:
    detected: List[str] = []
    for tool, markers in _TOOL_MARKERS.items():
        for marker in markers:
            path = root / marker
            if path.exists():
                detected.append(tool)
                break

    # Also check pyproject.toml for tool sections
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8", errors="ignore")
            for tool_name in ("black", "ruff", "mypy", "isort", "flake8"):
                if f"[tool.{tool_name}]" in text and tool_name not in detected:
                    detected.append(tool_name)
        except OSError:
            pass

    return detected


# ── Directory tree ─────────────────────────────────────────────────────────

def _build_dir_tree(root: Path, max_depth: int = 2) -> str:
    """Build a compact directory tree string (top N levels)."""
    lines: List[str] = []
    _SKIP_DIRS = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".mypy_cache", ".pytest_cache", ".tox", "dist", "build",
        ".eggs", "*.egg-info",
    }

    def _walk(path: Path, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        dirs = [e for e in entries if e.is_dir() and e.name not in _SKIP_DIRS and not e.name.startswith(".")]
        files = [e for e in entries if e.is_file()]

        # Show up to 8 files per dir
        for f in files[:8]:
            lines.append(f"{prefix}{f.name}")
        if len(files) > 8:
            lines.append(f"{prefix}… ({len(files) - 8} more files)")

        for d in dirs[:10]:
            lines.append(f"{prefix}{d.name}/")
            _walk(d, depth + 1, prefix + "  ")

    _walk(root, 0, "  ")
    return "\n".join(lines[:60])  # hard limit on output lines


# ── Import graph ───────────────────────────────────────────────────────────

_PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)


def _build_import_graph(
    files: List[str], root: Path
) -> List[Tuple[str, str]]:
    """Parse imports from source files and return (src, dst) edges."""
    edges: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()

    for fpath in files[:100]:  # limit for performance
        try:
            p = Path(fpath)
            rel = str(p.relative_to(root)).replace("\\", "/")
            text = p.read_text(encoding="utf-8", errors="ignore")[:8_000]
        except (OSError, ValueError):
            continue

        suffix = p.suffix
        if suffix == ".py":
            for m in _PY_IMPORT_RE.finditer(text):
                target = (m.group(1) or m.group(2)).split(".")[0]
                edge = (rel, target)
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)
        elif suffix in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
            for m in _JS_IMPORT_RE.finditer(text):
                target = m.group(1) or m.group(2)
                if target.startswith("."):
                    target = target.rsplit("/", 1)[-1] if "/" in target else target
                edge = (rel, target)
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)

    return edges[:30]  # keep top 30 edges


# ── Naming convention ──────────────────────────────────────────────────────

def _detect_naming(files: List[str]) -> str:
    """Heuristic: look at function/variable naming in a few files."""
    snake = 0
    camel = 0
    for fpath in files[:10]:
        try:
            text = Path(fpath).read_text(encoding="utf-8", errors="ignore")[:3_000]
        except OSError:
            continue
        snake += len(re.findall(r"\b[a-z]+_[a-z]+\b", text))
        camel += len(re.findall(r"\b[a-z]+[A-Z][a-z]+\b", text))

    if snake > camel * 2:
        return "snake_case (functions/variables)"
    elif camel > snake * 2:
        return "camelCase (functions/variables)"
    elif snake and camel:
        return "mixed (snake_case + camelCase)"
    return "unknown"


# ── File counting ──────────────────────────────────────────────────────────

_COUNT_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache",
}


def _count_files(root: Path) -> Tuple[Dict[str, int], int]:
    counts: Dict[str, int] = {}
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _COUNT_SKIP_DIRS]
        for fname in filenames:
            ext = Path(fname).suffix or "(no ext)"
            counts[ext] = counts.get(ext, 0) + 1
            total += 1
    return counts, total


# ── Helper: discover source files ─────────────────────────────────────────

_SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs",
    ".java", ".kt", ".go", ".rs", ".rb", ".php",
    ".cs", ".swift", ".c", ".cpp", ".h", ".hpp",
}


def _find_source_files(root: Path) -> List[str]:
    """Walk the project and return paths of source files."""
    result: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _COUNT_SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            if Path(fname).suffix in _SOURCE_EXTENSIONS:
                result.append(os.path.join(dirpath, fname))
    return result[:500]  # hard limit
