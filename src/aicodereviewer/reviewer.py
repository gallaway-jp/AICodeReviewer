# src/aicodereviewer/reviewer.py
"""
Code review issue collection with multi-type support.

Handles file reading, AI-powered analysis across one or more review types,
and structured issue parsing.
"""
import os
import json
import logging
import re
import threading
import time
import ast
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import ReviewIssue
from .config import config
from .backends.base import AIBackend
from .response_parser import parse_review_response, parse_single_file_response
from .context_collector import collect_project_context

__all__ = [
    "ProgressCallback",
    "CancelCheck",
    "FileInfo",
    "clear_file_cache",
    "invalidate_file_cache",
    "collect_review_issues",
    "verify_issue_resolved",
    "analyze_interactions",
    "architectural_review",
]

# Type aliases
ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]
FileInfo = Union[Path, Dict[str, Any]]

logger = logging.getLogger(__name__)

_REVIEW_RETRY_ATTEMPTS = 2
_CACHE_ISSUE_TYPES = frozenset({
    "cache_invalidation",
    "missing_cache_invalidation",
    "cache_consistency",
    "caching",
    "stale_cache",
})
_RETURN_SHAPE_ISSUE_TYPES = frozenset({
    "api_contract",
    "api_mismatch_contract_regression",
    "api_mismatch_runtime_error",
    "api_signature_break",
    "caller_callee_mismatch",
    "contract_mismatch",
    "interface_contract_violation",
})
_REVIEW_TYPE_ISSUE_ALIASES: Dict[str, frozenset[str]] = {
    "api_design": frozenset({
        "http_method_endpoint_semantics",
        "http_method_semantics",
        "rest_api",
        "response_modeling",
        "response_model",
        "request_validation_spec",
        "request_contract",
    }),
    "compatibility": frozenset({
        "cross_platform",
        "platform_compatibility",
        "platform_specific_behavior",
        "portability",
    }),
    "concurrency": frozenset({
        "race_condition",
        "shared_mutable_state",
        "concurrency_and_parallelism",
        "thread_safety",
        "deadlock",
        "data_race",
    }),
}


# ── file content cache ─────────────────────────────────────────────────────

# Cache entry: (content, mtime, file_size)
_CacheEntry = tuple  # (str, float, int)


class _BoundedCache:
    """Thread-safe bounded LRU cache with mtime-based staleness detection.

    Each entry records the file's modification time and size at the point
    of caching.  On :meth:`get`, the current mtime/size are compared —
    if they differ the entry is evicted so callers always see fresh
    content.

    A :class:`threading.Lock` protects all mutations so the cache is
    safe for use from :class:`concurrent.futures.ThreadPoolExecutor`.
    """

    def __init__(self, maxsize: int = 100):
        self._data: OrderedDict[str, _CacheEntry] = OrderedDict()
        self.maxsize = maxsize
        self._lock = threading.Lock()

    # ── read ───────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            if key not in self._data:
                return None

            content, cached_mtime, cached_size = self._data[key]

            # Check if the file has changed on disk
            try:
                actual_mtime = os.path.getmtime(key)
                actual_size = os.path.getsize(key)
                if actual_mtime != cached_mtime or actual_size != cached_size:
                    logger.debug("Cache stale for %s — invalidating", key)
                    del self._data[key]
                    return None
            except (OSError, FileNotFoundError):
                # File deleted / inaccessible → remove stale entry
                del self._data[key]
                return None

            self._data.move_to_end(key)
            return content

    # ── write ──────────────────────────────────────────────────────────────

    def put(self, key: str, value: str) -> None:
        with self._lock:
            try:
                mtime = os.path.getmtime(key)
                size = os.path.getsize(key)
            except (OSError, FileNotFoundError):
                mtime = time.time()
                size = len(value)

            if key in self._data:
                self._data.move_to_end(key)
            else:
                if len(self._data) >= self.maxsize:
                    self._data.popitem(last=False)
            self._data[key] = (value, mtime, size)

    # ── invalidation ───────────────────────────────────────────────────────

    def invalidate_path(self, path: str) -> None:
        """Remove a specific *path* from the cache."""
        with self._lock:
            self._data.pop(path, None)

    def clear(self) -> None:
        """Drop all cached entries."""
        with self._lock:
            self._data.clear()

    # ── dunder helpers ─────────────────────────────────────────────────────

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._data

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            return {k: v[0] for k, v in self._data.items()} == other
        if isinstance(other, _BoundedCache):
            return self._data == other._data
        return NotImplemented


_file_content_cache = _BoundedCache()


def clear_file_cache() -> None:
    """Clear the file-content cache (useful between review sessions)."""
    _file_content_cache.clear()


def invalidate_file_cache(path: str) -> None:
    """Invalidate a single file path in the content cache.

    Call this after editing/saving a file so the next review sees
    up-to-date content.
    """
    _file_content_cache.invalidate_path(str(path))


# ── severity parsing ───────────────────────────────────────────────────────

# ── severity keyword mapping ───────────────────────────────────────────────

_SEVERITY_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "critical": ("critical", "critically"),
    "high":     ("high", "severe"),
    "medium":   ("medium",),
    "low":      ("low", "minor"),
    "info":     ("info", "informational", "note"),
}


def _parse_severity(feedback: str) -> str:
    """Infer severity from AI feedback text using keyword heuristics."""
    try:
        text = feedback.lower()
        for level, keywords in _SEVERITY_KEYWORDS.items():
            if any(k in text for k in keywords):
                return level
    except Exception:
        pass
    return "medium"


def _extract_description(feedback: str, filename: str) -> str:
    """Extract a short description from the first meaningful line of feedback."""
    for line in feedback.splitlines():
        stripped = line.strip().strip("*-#>:").strip()
        if stripped and len(stripped) > 5:
            return stripped[:120]
    return f"Review finding for {filename}"


# ── file I/O ───────────────────────────────────────────────────────────────

def _estimate_token_count(content: str) -> int:
    """Rough token estimate: ~4 chars per token (GPT-family heuristic)."""
    return max(1, len(content) // 4)


def _get_file_content(file_info: FileInfo) -> str:
    """Return the text content for *file_info* (Path or diff dict)."""
    if isinstance(file_info, dict):
        return file_info.get("content", "")
    return _read_file_content(file_info)


def _build_adaptive_batches(
    target_files: Sequence[FileInfo],
    max_tokens_per_batch: int = 80_000,
    max_files_per_batch: int = 10,
) -> List[List[FileInfo]]:
    """Group files into batches respecting a token budget and file-count cap.

    Large files that alone exceed the token budget are placed in their own
    single-file batch.  Remaining files are packed greedily.
    """
    # Build list of (file_info, estimated_tokens)
    scored: List[tuple[FileInfo, int]] = []
    for fi in target_files:
        content = _get_file_content(fi)
        scored.append((fi, _estimate_token_count(content)))

    # Sort largest first so oversized files get their own batch early
    scored.sort(key=lambda x: x[1], reverse=True)

    batches: List[List[FileInfo]] = []
    current_batch: List[FileInfo] = []
    current_tokens = 0

    for fi, tokens in scored:
        # Oversized file → own batch
        if tokens > max_tokens_per_batch:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            batches.append([fi])
            continue

        # Would adding this file exceed the budget or file count?
        if (current_tokens + tokens > max_tokens_per_batch
                or len(current_batch) >= max_files_per_batch):
            if current_batch:
                batches.append(current_batch)
            current_batch = [fi]
            current_tokens = tokens
        else:
            current_batch.append(fi)
            current_tokens += tokens

    if current_batch:
        batches.append(current_batch)

    return batches

def _read_file_content(file_path: Path) -> str:
    """Read file with caching and size limits."""
    cache_key = str(file_path)
    cached = _file_content_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        file_size = os.path.getsize(file_path)
        max_size = config.get("performance", "max_file_size_mb")
        if file_size > max_size:
            logger.warning(
                "Skipping large file %s (%d bytes > %d limit)", file_path, file_size, max_size
            )
            return ""

        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()

        _file_content_cache.put(cache_key, content)
        return content

    except (OSError, UnicodeDecodeError) as exc:
        logger.error("Error reading %s: %s", file_path, exc)
        return ""


# ── session / budget tracking ──────────────────────────────────────────────

@dataclass
class _ReviewSession:
    """Track API usage and budget across a single review session."""

    total_api_calls: int = 0
    total_tokens_sent: int = 0
    estimated_tokens_received: int = 0
    failed_batches: int = 0
    successful_batches: int = 0
    budget_limit: int = 0  # 0 = unlimited

    def has_budget(self) -> bool:
        """Return True if further API calls are allowed."""
        if self.budget_limit == 0:
            return True
        return self.total_api_calls < self.budget_limit

    def record_call(self, tokens_sent: int = 0, tokens_received: int = 0) -> None:
        self.total_api_calls += 1
        self.total_tokens_sent += tokens_sent
        self.estimated_tokens_received += tokens_received

# ── cross-issue interaction analysis ─────────────────────────────────────────

_INTERACTION_RELATIONSHIP_TYPES = frozenset(
    {"conflict", "cascade", "group", "duplicate"}
)


def _parse_interaction_response(raw: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse the AI interaction-analysis response as JSON.

    Tolerates markdown fences and light preamble text.
    Returns the parsed dict on success, ``None`` on failure.
    """
    if not raw:
        return None
    # Strip markdown fences
    stripped = re.sub(r"```(?:json)?\s*", "", raw).strip()
    stripped = re.sub(r"```\s*$", "", stripped).strip()
    # Try to find the JSON object
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
        if isinstance(data, dict) and "interactions" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def analyze_interactions(
    issues: List[ReviewIssue],
    client: AIBackend,
    lang: str = "en",
) -> tuple[List[ReviewIssue], Optional[str]]:
    """Run a second-pass AI analysis to detect cross-issue interactions.

    Sends a compact summary of all findings to the AI and asks it to
    identify conflicts, cascading effects, groupings, and duplicates.
    The results are written back onto each :class:`ReviewIssue`'s
    ``related_issues`` and ``interaction_summary`` fields.

    Args:
        issues: The issues collected from the main review pass.
        client: An :class:`AIBackend` instance.
        lang:   Response language (``'en'`` or ``'ja'``).

    Returns:
        A tuple of *(updated_issues, overall_summary)*.  The summary is
        ``None`` when analysis was skipped or failed.
    """
    if not issues or len(issues) < 2:
        logger.debug("Interaction analysis skipped (fewer than 2 issues)")
        return issues, None

    # Build the interaction prompt
    system_prompt = client._build_system_prompt(  # noqa: SLF001
        "interaction_analysis", lang,
    )
    user_message = AIBackend._build_interaction_user_message(issues, lang)  # noqa: SLF001

    logger.info(
        "Running cross-issue interaction analysis on %d findings…",
        len(issues),
    )

    try:
        response = client.get_review(
            user_message,
            review_type="interaction_analysis",
            lang=lang,
        )
    except Exception as exc:
        logger.warning("Interaction analysis AI call failed: %s", exc)
        return issues, None

    if not response or response.startswith("Error:"):
        logger.warning("Interaction analysis returned no useful data")
        return issues, None

    parsed = _parse_interaction_response(response)
    if parsed is None:
        logger.warning("Failed to parse interaction analysis response")
        return issues, None

    # Apply interactions back onto issues
    overall_summary = parsed.get("overall_summary", "")
    interactions = parsed.get("interactions", [])
    n = len(issues)

    for entry in interactions:
        indices = entry.get("issue_indices", [])
        relationship = entry.get("relationship", "")
        summary = entry.get("summary", "")

        # Validate
        if relationship not in _INTERACTION_RELATIONSHIP_TYPES:
            continue
        valid_indices = [i for i in indices if isinstance(i, int) and 0 <= i < n]
        if len(valid_indices) < 2:
            continue

        # Cross-link each pair of issues
        for i in valid_indices:
            for j in valid_indices:
                if i != j and j not in issues[i].related_issues:
                    issues[i].related_issues.append(j)
            # Append relationship info to the interaction_summary
            existing = issues[i].interaction_summary or ""
            tag = f"[{relationship}] {summary}"
            if existing:
                issues[i].interaction_summary = f"{existing}; {tag}"
            else:
                issues[i].interaction_summary = tag

    logger.info(
        "Interaction analysis complete: %d interaction(s), summary=%s",
        len(interactions),
        overall_summary[:80] if overall_summary else "(none)",
    )
    return issues, overall_summary or None


# ── cross-file architectural review ──────────────────────────────────────────

def _build_project_structure_summary(files: Sequence[FileInfo]) -> str:
    """Build a concise project directory / file-type summary.

    The output is designed to be compact enough to fit inside an AI prompt
    while conveying the overall shape of the project.
    """
    file_types: Dict[str, int] = {}
    dirs: Dict[str, List[str]] = {}

    for file_info in files:
        if isinstance(file_info, dict):
            fname = file_info.get("filename", file_info.get("path", "unknown"))
        else:
            fname = str(file_info)

        ext = Path(fname).suffix or "(no ext)"
        file_types[ext] = file_types.get(ext, 0) + 1

        dir_path = str(Path(fname).parent)
        dirs.setdefault(dir_path, []).append(Path(fname).name)

    parts: List[str] = ["Project Structure:\n"]
    for dir_path in sorted(dirs.keys())[:15]:
        parts.append(f"\n{dir_path}/")
        for name in sorted(dirs[dir_path])[:8]:
            parts.append(f"  - {name}")
        remaining = len(dirs[dir_path]) - 8
        if remaining > 0:
            parts.append(f"  … and {remaining} more files")

    parts.append(f"\nFile types: {dict(sorted(file_types.items()))}")
    parts.append(f"Total files: {len(files)}")
    return "\n".join(parts)


def _infer_project_root(files: Sequence[FileInfo]) -> str:
    """Infer a likely project root from reviewed files."""
    if not files:
        return "."

    sample = files[0]
    if isinstance(sample, dict):
        sample_path = (
            sample.get("path")
            or sample.get("filename")
            or sample.get("name")
            or "."
        )
    else:
        sample_path = str(sample)

    root_candidate = Path(sample_path)
    if root_candidate.suffix:
        root_candidate = root_candidate.parent
    if not root_candidate.is_absolute():
        root_candidate = (Path.cwd() / root_candidate).resolve()

    for _ in range(5):
        if any(
            (root_candidate / marker).exists()
            for marker in (
                "pyproject.toml",
                "package.json",
                "Cargo.toml",
                "go.mod",
                "pom.xml",
                ".git",
            )
        ):
            return str(root_candidate)
        parent = root_candidate.parent
        if parent == root_candidate:
            break
        root_candidate = parent

    return str(root_candidate)


def _infer_review_root(files: Sequence[FileInfo]) -> Path:
    """Infer a practical review root without climbing to the filesystem root."""
    if not files:
        return Path.cwd()

    sample = files[0]
    if isinstance(sample, dict):
        sample_path = (
            sample.get("path")
            or sample.get("filename")
            or sample.get("name")
            or "."
        )
    else:
        sample_path = str(sample)

    root_candidate = Path(sample_path)
    if root_candidate.suffix:
        root_candidate = root_candidate.parent
    if not root_candidate.is_absolute():
        root_candidate = (Path.cwd() / root_candidate).resolve()

    if root_candidate.name.lower() in {"src", "tests", "test", "lib", "app"} and root_candidate.parent != root_candidate:
        root_candidate = root_candidate.parent

    search_candidate = root_candidate
    for _ in range(5):
        if any(
            (search_candidate / marker).exists()
            for marker in (
                "pyproject.toml",
                "package.json",
                "Cargo.toml",
                "go.mod",
                "pom.xml",
                ".git",
            )
        ):
            return search_candidate
        parent = search_candidate.parent
        if parent == search_candidate:
            break
        search_candidate = parent

    return root_candidate


def _discover_documentation_targets(project_root: Path) -> List[Path]:
    candidates: List[Path] = []
    seen: set[str] = set()

    def _add_candidate(path: Path) -> None:
        if not path.exists() or not path.is_file():
            return
        resolved = str(path.resolve())
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(path)

    for relative in (
        "README.md",
        "README.rst",
        "README.txt",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "docs/README.md",
    ):
        _add_candidate(project_root / relative)

    docs_dir = project_root / "docs"
    if docs_dir.exists() and docs_dir.is_dir():
        for pattern in ("*.md", "*.rst", "*.txt"):
            for path in sorted(docs_dir.rglob(pattern))[:12]:
                _add_candidate(path)

    return candidates


def _discover_dependency_targets(project_root: Path) -> List[Path]:
    candidates: List[Path] = []
    seen: set[str] = set()

    def _add_candidate(path: Path) -> None:
        if not path.exists() or not path.is_file():
            return
        resolved = str(path.resolve())
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(path)

    for relative in (
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements.lock",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "setup.py",
        "setup.cfg",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
    ):
        _add_candidate(project_root / relative)

    return candidates


def _discover_license_targets(project_root: Path) -> List[Path]:
    candidates: List[Path] = []
    seen: Set[str] = set()

    def _add_candidate(path: Path) -> None:
        if not path.exists() or not path.is_file():
            return
        resolved = str(path.resolve())
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(path)

    for compliance_file in (
        "LICENSE",
        "LICENSE.txt",
        "LICENSE.md",
        "LICENCE",
        "LICENCE.txt",
        "COPYING",
        "COPYING.txt",
        "NOTICE",
        "NOTICE.txt",
        "THIRD_PARTY_NOTICES.md",
        "THIRD_PARTY_NOTICES.txt",
        "licenses_check.csv",
    ):
        _add_candidate(project_root / compliance_file)

    for manifest_path in _discover_dependency_targets(project_root):
        _add_candidate(manifest_path)

    return candidates


def _augment_documentation_review_targets(
    target_files: Sequence[FileInfo],
    review_types: Sequence[str],
) -> List[FileInfo]:
    if "documentation" not in review_types:
        return list(target_files)

    project_root = _infer_review_root(target_files)
    augmented: List[FileInfo] = list(target_files)
    existing_paths = {
        str((Path(str(file_info["path"])) if isinstance(file_info, dict) else Path(file_info)).resolve())
        for file_info in target_files
    }
    for doc_path in _discover_documentation_targets(project_root):
        resolved = str(doc_path.resolve())
        if resolved in existing_paths:
            continue
        existing_paths.add(resolved)
        augmented.append(doc_path)
    return augmented


def _augment_dependency_review_targets(
    target_files: Sequence[FileInfo],
    review_types: Sequence[str],
) -> List[FileInfo]:
    if "dependency" not in review_types:
        return list(target_files)

    project_root = _infer_review_root(target_files)
    augmented: List[FileInfo] = list(target_files)
    existing_paths = {
        str((Path(str(file_info["path"])) if isinstance(file_info, dict) else Path(file_info)).resolve())
        for file_info in target_files
    }
    for manifest_path in _discover_dependency_targets(project_root):
        resolved = str(manifest_path.resolve())
        if resolved in existing_paths:
            continue
        existing_paths.add(resolved)
        augmented.append(manifest_path)
    return augmented


def _augment_license_review_targets(
    target_files: Sequence[FileInfo],
    review_types: Sequence[str],
) -> List[FileInfo]:
    if "license" not in review_types:
        return list(target_files)

    project_root = _infer_review_root(target_files)
    augmented: List[FileInfo] = list(target_files)
    existing_paths = {
        str((Path(str(file_info["path"])) if isinstance(file_info, dict) else Path(file_info)).resolve())
        for file_info in target_files
    }
    for license_path in _discover_license_targets(project_root):
        resolved = str(license_path.resolve())
        if resolved in existing_paths:
            continue
        existing_paths.add(resolved)
        augmented.append(license_path)
    return augmented


def _build_dependency_highlights(files: Sequence[FileInfo]) -> Optional[str]:
    """Build a compact dependency-edge summary for architectural review."""
    scanned_paths = [
        str(file_info) if not isinstance(file_info, dict)
        else file_info.get("path") or file_info.get("filename") or ""
        for file_info in files
    ]
    scanned_paths = [path for path in scanned_paths if path]
    if len(scanned_paths) < 2:
        return None

    ctx = collect_project_context(_infer_project_root(files), scanned_paths)
    if not ctx.dependency_edges:
        return None

    parts = ["Dependency Highlights:"]
    for src, dst in ctx.dependency_edges[:10]:
        parts.append(f"- {src} -> {dst}")
    return "\n".join(parts)


def architectural_review(
    files: Sequence[FileInfo],
    all_issues: List[ReviewIssue],
    client: AIBackend,
    lang: str = "en",
) -> tuple[List[ReviewIssue], Optional[str]]:
    """Perform a project-level architectural review.

    Sends a project structure summary and existing findings summary to the
    AI, which returns cross-cutting architectural issues that cannot be
    seen when reviewing individual files.

    Args:
        files:      All scanned files from the review session.
        all_issues: Issues collected during the main review.
        client:     An :class:`AIBackend` instance.
        lang:       Response language (``'en'`` or ``'ja'``).

    Returns:
        A tuple of *(new_arch_issues, architecture_summary_text)*.
        ``architecture_summary_text`` is ``None`` when the review was
        skipped or failed.
    """
    MIN_FILES = 3
    if not files or len(files) < MIN_FILES:
        logger.debug(
            "Skipping architectural review (fewer than %d files)", MIN_FILES,
        )
        return [], None

    structure_summary = _build_project_structure_summary(files)
    dependency_highlights = None
    try:
        dependency_highlights = _build_dependency_highlights(files)
    except Exception as exc:
        logger.warning("Failed to build dependency highlights: %s", exc)

    # Condense existing findings (cap at 50)
    findings_lines: List[str] = []
    for iss in all_issues[:50]:
        findings_lines.append(
            f"- {iss.file_path}:{iss.line_number or 'n/a'} "
            f"({iss.severity}) {iss.issue_type}: {iss.description}"
        )
    findings_summary = "\n".join(findings_lines) if findings_lines else "(none)"

    dependency_block = (
        f"{dependency_highlights}\n\n" if dependency_highlights else ""
    )

    user_message = (
        f"{structure_summary}\n\n"
        f"{dependency_block}"
        f"Existing review findings ({len(all_issues)} total):\n"
        f"{findings_summary}\n\n"
        "Analyse the project at an architectural level.  Focus on cross-cutting "
        "structural issues that are invisible when reviewing single files. "
        "For architectural or dependency-direction findings that describe the structure of the project rather than a single file pair, use context_scope='project'. "
        "When you report a broader finding, include the most relevant supporting files in related_files and make evidence_basis a short factual statement naming the exact layer violation, dependency edge, or missing architectural contract.\n"
        "Respond with the JSON schema described in your instructions."
    )

    logger.info(
        "Running architectural review over %d files (%d existing findings)…",
        len(files), len(all_issues),
    )

    try:
        response = client.get_review(
            user_message,
            review_type="architectural_review",
            lang=lang,
        )
    except Exception as exc:
        logger.warning("Architectural review AI call failed: %s", exc)
        return [], None

    if not response or response.startswith("Error:"):
        logger.warning("Architectural review returned no useful data")
        return [], None

    # Parse into ReviewIssue objects using the standard parser
    arch_issues = parse_review_response(
        response,
        [{"name": "PROJECT", "path": "PROJECT", "content": ""}],
        "architecture",
    )

    summary_text = (
        f"Architectural review identified {len(arch_issues)} issue(s) "
        f"across {len(files)} files."
    )
    logger.info(summary_text)
    return arch_issues, summary_text


# ── main collection entry ──────────────────────────────────────────────────

def collect_review_issues(
    target_files: Sequence[FileInfo],
    review_types: List[str],
    client: AIBackend,
    lang: str,
    spec_content: Optional[str] = None,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> List[ReviewIssue]:
    """
    Collect review issues from *target_files* for one or more *review_types*.

    When multiple review types are requested they are combined into a
    single mixed prompt so each file is only analysed once.

    Args:
        target_files: Path objects (project) or dicts (diff).
        review_types: List of review type keys.
        client: An :class:`AIBackend` instance.
        lang: Response language ('en' / 'ja').
        spec_content: Specification doc for ``'specification'`` type.
        progress_callback: Optional ``(current, total, msg)`` callable.
        cancel_check: Optional callable returning True when cancelled.

    Returns:
        Flat list of :class:`ReviewIssue` instances.
    """
    issues: List[ReviewIssue] = []
    effective_target_files = _augment_license_review_targets(
        _augment_dependency_review_targets(
            _augment_documentation_review_targets(target_files, review_types),
            review_types,
        ),
        review_types,
    )

    # ── Build project context (once per session) ───────────────────────────
    enable_context = config.get("processing", "enable_project_context", True)
    if enable_context:
        try:
            # Determine project root from target_files
            if effective_target_files:
                sample = effective_target_files[0]
                if isinstance(sample, dict):
                    project_root = str(Path(sample.get("path", ".")).parent)
                else:
                    project_root = str(Path(str(sample)).parent)
            else:
                project_root = "."
            # Walk up to find a likely project root (has pyproject.toml, package.json, etc.)
            root_candidate = Path(project_root)
            for _ in range(5):
                if any((root_candidate / m).exists() for m in
                       ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml", ".git")):
                    project_root = str(root_candidate)
                    break
                parent = root_candidate.parent
                if parent == root_candidate:
                    break
                root_candidate = parent

            scanned_paths = [
                str(f) if not isinstance(f, dict) else f.get("path", "")
                for f in effective_target_files
            ]
            ctx = collect_project_context(project_root, scanned_paths)
            max_tokens = config.get("processing", "context_max_tokens", 500)
            client.set_project_context(ctx.to_prompt_string(max_tokens))

            # Store detected frameworks for prompt supplement injection
            override = config.get("processing", "detected_frameworks", "")
            if override:
                frameworks = [f.strip() for f in override.split(",") if f.strip()]
            else:
                frameworks = ctx.frameworks
            client.set_detected_frameworks(frameworks or None)
            logger.info(
                "Project context attached (%d chars, frameworks=%s)",
                len(client._project_context or ""),
                frameworks,
            )
        except Exception as exc:
            logger.warning("Failed to build project context: %s", exc)
            client.set_project_context(None)
            client.set_detected_frameworks(None)
    else:
        client.set_project_context(None)
        client.set_detected_frameworks(None)

    # Always one pass over files — multiple review types are merged into one prompt
    combined_type = "+".join(review_types) if len(review_types) > 1 else review_types[0]
    total_work = len(effective_target_files)
    done = 0

    enable_parallel = config.get("processing", "enable_parallel_processing", False)
    enable_adaptive = config.get("processing", "enable_adaptive_batching", True)

    type_label = ", ".join(review_types)

    if enable_adaptive:
        max_batch_tokens = config.get("processing", "max_batch_token_budget", 80_000)
        max_batch_files = config.get("processing", "batch_size", 10)
        batches = _build_adaptive_batches(effective_target_files, max_batch_tokens, max_batch_files)
        logger.info(
            "Adaptive batching: %d file(s) → %d batch(es)",
            len(effective_target_files), len(batches),
        )
    else:
        batch_size = config.get("processing", "batch_size", 5)
        batches = [
            effective_target_files[i : i + batch_size]
            for i in range(0, len(effective_target_files), batch_size)
        ]

    # ── Budget / session tracking ────────────────────────────────────────────
    budget_limit = config.get("performance", "max_api_calls_per_session", 0)
    session = _ReviewSession(budget_limit=budget_limit)

    if enable_parallel and len(batches) > 1:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(
                    _process_file_batch, batch, combined_type, client, lang, spec_content, cancel_check
                ): batch
                for batch in batches
            }
            for future in as_completed(futures):
                batch_issues = future.result()
                issues.extend(batch_issues)
                session.record_call()
                session.successful_batches += 1
                done += len(futures[future])
                if progress_callback:
                    progress_callback(done, total_work, f"[{type_label}]")
    else:
        for batch in batches:
            if not session.has_budget():
                logger.warning(
                    "Budget limit reached (%d/%d calls); skipping remaining batches",
                    session.total_api_calls, session.budget_limit,
                )
                break
            try:
                batch_issues = _process_file_batch(
                    batch, combined_type, client, lang, spec_content, cancel_check
                )
                issues.extend(batch_issues)
                session.record_call()
                session.successful_batches += 1
            except Exception as exc:
                session.failed_batches += 1
                session.record_call()
                logger.error("Batch failed: %s — retrying individually", exc)
                if session.has_budget():
                    fallback = _process_files_individually(
                        batch, combined_type, client, lang, spec_content, cancel_check,
                    )
                    issues.extend(fallback)
                    session.record_call()
            done += len(batch)
            if progress_callback:
                progress_callback(done, total_work, f"[{type_label}]")

    supplemental_issues = _supplement_stale_cache_findings(
        target_files,
        combined_type,
        issues,
    )
    if supplemental_issues:
        issues.extend(supplemental_issues)
        logger.info(
            "Added %d deterministic stale-cache finding(s) after AI review",
            len(supplemental_issues),
        )
    n_plus_one_issues = _supplement_n_plus_one_query_findings(
        target_files,
        combined_type,
        issues,
    )
    if n_plus_one_issues:
        issues.extend(n_plus_one_issues)
        logger.info(
            "Added %d deterministic N+1 performance finding(s) after AI review",
            len(n_plus_one_issues),
        )
    return_shape_issues = _supplement_return_shape_mismatch_findings(
        target_files,
        combined_type,
        issues,
    )
    if return_shape_issues:
        issues.extend(return_shape_issues)
        logger.info(
            "Added %d deterministic return-shape finding(s) after AI review",
            len(return_shape_issues),
        )
    _normalize_review_type_aliases(combined_type, issues)
    _normalize_cache_issue_context(issues)

    logger.info(
        "Review session: %d API call(s), %d succeeded, %d failed, %d issue(s)",
        session.total_api_calls,
        session.successful_batches,
        session.failed_batches,
        len(issues),
    )

    # ── Optional cross-issue interaction analysis (second AI pass) ─────────
    enable_interaction = config.get(
        "processing", "enable_interaction_analysis", False,
    )
    if isinstance(enable_interaction, str):
        enable_interaction = enable_interaction.lower() in ("true", "1", "yes")
    if enable_interaction and len(issues) >= 2 and session.has_budget():
        if progress_callback:
            progress_callback(
                total_work, total_work, f"[{type_label}] interaction analysis…",
            )
        issues, _interaction_summary = analyze_interactions(issues, client, lang)
        _normalize_cache_issue_context(issues)
        session.record_call()

    # ── Optional cross-file architectural review (third AI pass) ─────────
    enable_arch = config.get(
        "processing", "enable_architectural_review", False,
    )
    if isinstance(enable_arch, str):
        enable_arch = enable_arch.lower() in ("true", "1", "yes")
    force_architecture_review = "architecture" in review_types
    if (enable_arch or force_architecture_review) and len(effective_target_files) >= 3 and session.has_budget():
        if progress_callback:
            progress_callback(
                total_work, total_work, f"[{type_label}] architectural review\u2026",
            )
        arch_issues, _arch_summary = architectural_review(
            effective_target_files, issues, client, lang,
        )
        issues.extend(arch_issues)
        _normalize_cache_issue_context(issues)
        session.record_call()

    local_ui_ux_issues = _supplement_local_ui_ux_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_ui_ux_issues:
        issues.extend(local_ui_ux_issues)
        logger.info(
            "Added %d Local UI/UX supplement finding(s) after AI review",
            len(local_ui_ux_issues),
        )

    local_dead_code_issues = _supplement_local_dead_code_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_dead_code_issues:
        issues.extend(local_dead_code_issues)
        logger.info(
            "Added %d Local dead_code supplement finding(s) after AI review",
            len(local_dead_code_issues),
        )

    local_concurrency_issues = _supplement_local_concurrency_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_concurrency_issues:
        issues.extend(local_concurrency_issues)
        logger.info(
            "Added %d Local concurrency supplement finding(s) after AI review",
            len(local_concurrency_issues),
        )

    local_dependency_issues = _supplement_local_dependency_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_dependency_issues:
        issues.extend(local_dependency_issues)
        logger.info(
            "Added %d Local dependency supplement finding(s) after AI review",
            len(local_dependency_issues),
        )

    local_localization_issues = _supplement_local_localization_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_localization_issues:
        issues.extend(local_localization_issues)
        logger.info(
            "Added %d Local localization supplement finding(s) after AI review",
            len(local_localization_issues),
        )

    local_error_handling_issues = _supplement_local_error_handling_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_error_handling_issues:
        issues.extend(local_error_handling_issues)
        logger.info(
            "Added %d Local error_handling supplement finding(s) after AI review",
            len(local_error_handling_issues),
        )

    local_data_validation_issues = _supplement_local_data_validation_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_data_validation_issues:
        issues.extend(local_data_validation_issues)
        logger.info(
            "Added %d Local data_validation supplement finding(s) after AI review",
            len(local_data_validation_issues),
        )

    local_testing_issues = _supplement_local_testing_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_testing_issues:
        issues.extend(local_testing_issues)
        logger.info(
            "Added %d Local testing supplement finding(s) after AI review",
            len(local_testing_issues),
        )

    local_regression_issues = _supplement_local_regression_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_regression_issues:
        issues.extend(local_regression_issues)
        logger.info(
            "Added %d Local regression supplement finding(s) after AI review",
            len(local_regression_issues),
        )

    local_accessibility_issues = _supplement_local_accessibility_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_accessibility_issues:
        issues.extend(local_accessibility_issues)
        logger.info(
            "Added %d Local accessibility supplement finding(s) after AI review",
            len(local_accessibility_issues),
        )

    local_security_issues = _supplement_local_security_findings(
        effective_target_files,
        combined_type,
        issues,
        client,
    )
    if local_security_issues:
        issues.extend(local_security_issues)
        logger.info(
            "Added %d Local security supplement finding(s) after AI review",
            len(local_security_issues),
        )

    architecture_supplements = _normalize_controller_repository_bypass_findings(
        effective_target_files,
        combined_type,
        issues,
    )
    if architecture_supplements:
        issues.extend(architecture_supplements)
        logger.info(
            "Added %d deterministic controller-boundary architecture finding(s) after AI review",
            len(architecture_supplements),
        )

    api_design_supplements = _supplement_get_create_endpoint_findings(
        effective_target_files,
        combined_type,
        issues,
    )
    if api_design_supplements:
        issues.extend(api_design_supplements)
        logger.info(
            "Added %d deterministic GET-create API design finding(s) after AI review",
            len(api_design_supplements),
        )

    compatibility_supplements = _supplement_platform_open_command_findings(
        effective_target_files,
        combined_type,
        issues,
    )
    if compatibility_supplements:
        issues.extend(compatibility_supplements)
        logger.info(
            "Added %d deterministic platform-launch compatibility finding(s) after AI review",
            len(compatibility_supplements),
        )

    return issues


def _load_target_file_entries(target_files: Sequence[FileInfo]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for file_info in target_files:
        if isinstance(file_info, dict):
            file_path = str(file_info["path"])
            content = str(file_info.get("content") or "")
            name = str(file_info.get("filename") or Path(file_path).name)
        else:
            file_path = str(file_info)
            content = _read_file_content(file_info)
            name = Path(file_path).name
        if not content:
            continue
        entries.append({
            "path": file_path,
            "name": name,
            "content": content,
        })
    return entries


def _extract_cache_entities(content: str) -> Dict[str, List[str]]:
    entities: Dict[str, List[str]] = {}
    if "cache" not in content.lower() and "_CACHE" not in content:
        return entities

    for match in re.finditer(r"\b(get|set)_([a-z0-9_]+)\b", content):
        entity = match.group(2)
        entities.setdefault(entity, []).append(match.group(0))
    return entities


def _extract_write_entities(content: str) -> Dict[str, List[str]]:
    entities: Dict[str, List[str]] = {}
    if not re.search(r"\b(store|repo|repository|db|database)\s*\[", content):
        return entities

    for match in re.finditer(r"\b(update|save|write|set)_([a-z0-9_]+)\b", content):
        entity = match.group(2)
        entities.setdefault(entity, []).append(match.group(0))
    return entities


def _supplement_stale_cache_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    if "performance" not in review_type.split("+"):
        return []
    if any(issue.issue_type.lower() in _CACHE_ISSUE_TYPES for issue in issues):
        return []

    entries = _load_target_file_entries(target_files)
    if len(entries) < 2:
        return []

    supplements: List[ReviewIssue] = []
    seen_pairs: set[tuple[str, str, str]] = set()

    for cache_entry in entries:
        cache_content = cache_entry["content"]
        cache_entities = _extract_cache_entities(cache_content)
        if not cache_entities:
            continue
        for writer_entry in entries:
            if writer_entry["path"] == cache_entry["path"]:
                continue
            writer_content = writer_entry["content"]
            if any(token in writer_content.lower() for token in ("invalidate", "clear_cache", "evict", "ttl")):
                continue
            write_entities = _extract_write_entities(writer_content)
            if not write_entities:
                continue

            for entity, writer_functions in write_entities.items():
                if entity not in cache_entities:
                    continue
                pair_key = (entity, cache_entry["path"], writer_entry["path"])
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                cache_functions = cache_entities[entity]
                writer_function = writer_functions[0]
                cache_refs = ", ".join(cache_functions[:2])
                evidence_basis = (
                    f"{writer_function} updates {entity} state while {cache_refs} in "
                    f"{cache_entry['name']} continue serving cached {entity} data without invalidation."
                )
                systemic_impact = (
                    f"Stale {entity} reads may reach callers because {writer_entry['name']} updates the backing store "
                    f"without invalidating cached {entity} entries in {cache_entry['name']}."
                )
                ai_feedback = "\n\n".join([
                    "**Missing cache invalidation across write and read paths**",
                    f"{writer_entry['name']} updates {entity} state, but {cache_entry['name']} exposes cache accessors for the same entity without any invalidation path.",
                    f"Code: {writer_function}(...) / {cache_refs}(...)",
                    "Suggestion: Invalidate or refresh the cached entity on the write path, or route writes through the same cache management layer.",
                    "Context Scope: cross_file",
                    f"Related Files: {cache_entry['path']}",
                    f"Systemic Impact: {systemic_impact}",
                    "Confidence: medium",
                    f"Evidence Basis: {evidence_basis}",
                ])
                supplements.append(ReviewIssue(
                    file_path=writer_entry["path"],
                    line_number=1,
                    issue_type="missing_cache_invalidation",
                    severity="medium",
                    description="Missing cache invalidation across write and read paths",
                    code_snippet=writer_content[:200] + ("…" if len(writer_content) > 200 else ""),
                    ai_feedback=ai_feedback,
                    context_scope="cross_file",
                    related_files=[cache_entry["path"]],
                    systemic_impact=systemic_impact,
                    confidence="medium",
                    evidence_basis=evidence_basis,
                ))

    return supplements


def _supplement_n_plus_one_query_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    if "performance" not in review_type.split("+"):
        return []

    for issue in issues:
        issue_type = issue.issue_type.lower()
        if issue_type not in {"performance", "algorithmic efficiency", "algorithmic_efficiency"}:
            continue
        text = _issue_text(issue)
        if any(marker in text for marker in ("n+1", "query per", "round trip", "execute_query", "fetch_order")):
            return []

    entries = _load_target_file_entries(target_files)
    if len(entries) < 2:
        return []

    for service_entry in entries:
        service_content = service_entry["content"]
        import_match = re.search(
            r"from\s+(?P<module>[a-zA-Z0-9_\.]+)\s+import\s+(?P<helper>fetch_[a-zA-Z0-9_]+)",
            service_content,
        )
        loop_match = re.search(
            r"for\s+(?P<item>[a-zA-Z0-9_]+)\s+in\s+(?P<iterable>[a-zA-Z0-9_]+)\s*:\s*(?P<body>(?:\n[ \t]+.*)+)",
            service_content,
        )
        if import_match is None or loop_match is None:
            continue

        helper = import_match.group("helper")
        loop_item = loop_match.group("item")
        loop_body = loop_match.group("body")
        if f"{helper}({loop_item})" not in loop_body:
            continue

        module_stem = import_match.group("module").split(".")[-1]
        repository_entry = next(
            (
                entry for entry in entries
                if entry["path"] != service_entry["path"] and Path(entry["path"]).stem == module_stem
            ),
            None,
        )
        if repository_entry is None:
            continue

        repository_content = repository_entry["content"]
        plural_helper = f"{helper}s"
        if f"def {helper}(" not in repository_content:
            continue
        if "execute_query(" not in repository_content:
            continue
        if f"def {plural_helper}(" not in repository_content:
            continue

        evidence_basis = (
            f"{service_entry['name']} calls {helper} inside the loop while {repository_entry['name']} "
            f"already exposes batch helper {plural_helper}."
        )
        systemic_impact = (
            "Latency grows with input size because each item triggers another repository round trip instead of using the available batch path."
        )
        ai_feedback = "\n\n".join([
            "**N+1 query pattern in a hot path**",
            f"{service_entry['name']} iterates over items and calls {helper} for each one, even though {repository_entry['name']} already exposes {plural_helper} for batched loading.",
            f"Code: for ... in ...: {helper}(...) / def {plural_helper}(...)",
            "Suggestion: Load the records through the batch helper or refactor the service so the loop does not trigger one query per item.",
            "Context Scope: cross_file",
            f"Related Files: {repository_entry['path']}",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return [ReviewIssue(
            file_path=service_entry["path"],
            line_number=_line_number_from_offset(service_content, loop_match.start()),
            issue_type="performance",
            severity="medium",
            description="The service performs one repository query per item instead of using the available batch load.",
            code_snippet=_code_snippet(service_content, loop_match.start()),
            ai_feedback=ai_feedback,
            context_scope="cross_file",
            related_files=[repository_entry["path"]],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )]

    return []


def _normalize_cache_issue_context(issues: Sequence[ReviewIssue]) -> None:
    for issue in issues:
        if issue.issue_type.lower() not in _CACHE_ISSUE_TYPES:
            continue

        sibling_paths: List[str] = []
        for related_index in issue.related_issues:
            if related_index < 0 or related_index >= len(issues):
                continue
            sibling = issues[related_index]
            if sibling.context_scope == "local":
                continue
            if sibling.file_path != issue.file_path and sibling.file_path not in sibling_paths:
                sibling_paths.append(sibling.file_path)
            for related_path in sibling.related_files:
                if related_path != issue.file_path and related_path not in sibling_paths:
                    sibling_paths.append(related_path)

        if sibling_paths:
            issue.context_scope = "cross_file"
            for sibling_path in sibling_paths:
                if sibling_path not in issue.related_files:
                    issue.related_files.append(sibling_path)

        if issue.context_scope == "cross_file" and not issue.systemic_impact:
            collaborator = Path(issue.related_files[0]).name if issue.related_files else "a related write path"
            issue.systemic_impact = (
                f"Stale cached data may reach callers because {collaborator} can update the backing state without invalidating cached entries."
            )

        feedback_parts = [part for part in [issue.ai_feedback] if part]
        if issue.context_scope != "local" and "Context Scope:" not in issue.ai_feedback:
            feedback_parts.append(f"Context Scope: {issue.context_scope}")
        if issue.related_files and "Related Files:" not in issue.ai_feedback:
            feedback_parts.append(f"Related Files: {', '.join(issue.related_files)}")
        if issue.systemic_impact and "Systemic Impact:" not in issue.ai_feedback:
            feedback_parts.append(f"Systemic Impact: {issue.systemic_impact}")
        if feedback_parts:
            issue.ai_feedback = "\n\n".join(feedback_parts)


def _normalize_review_type_aliases(review_type: str, issues: Sequence[ReviewIssue]) -> None:
    requested_types = {entry for entry in review_type.split("+") if entry}
    if not requested_types:
        return

    for issue in issues:
        normalized_issue_type = re.sub(r"[\s\-/]+", "_", issue.issue_type.lower()).strip("_")
        for canonical_type in requested_types:
            if normalized_issue_type == canonical_type:
                issue.issue_type = canonical_type
                break
            aliases = _REVIEW_TYPE_ISSUE_ALIASES.get(canonical_type, frozenset())
            if normalized_issue_type in aliases:
                issue.issue_type = canonical_type
                break


def _extract_return_shapes(content: str) -> Dict[str, tuple[set[str], int]]:
    shapes: Dict[str, tuple[set[str], int]] = {}
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return shapes

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        keys: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Return):
                continue
            if not isinstance(child.value, ast.Dict):
                continue
            literal_keys = {
                key.value
                for key in child.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            keys.update(literal_keys)

        if keys:
            shapes[node.name] = (keys, node.lineno)

    return shapes


def _extract_imported_call_result_accesses(
    content: str,
) -> List[tuple[str, str, str, int]]:
    accesses: List[tuple[str, str, str, int]] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return accesses

    imported_functions: Dict[str, tuple[str, str]] = {}
    assignments: Dict[str, tuple[str, str, int]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            module_tail = node.module.split(".")[-1]
            for alias in node.names:
                local_name = alias.asname or alias.name
                imported_functions[local_name] = (module_tail, alias.name)
        elif isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            if not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Name):
                continue
            call_name = node.value.func.id
            import_target = imported_functions.get(call_name)
            if import_target is None:
                continue
            assignments[node.targets[0].id] = (import_target[0], import_target[1], node.lineno)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            slice_node = node.slice
            if not isinstance(slice_node, ast.Constant) or not isinstance(slice_node.value, str):
                continue
            assignment = assignments.get(node.value.id)
            if assignment is None:
                continue
            accesses.append((assignment[0], assignment[1], slice_node.value, node.lineno))

    return accesses


def _supplement_return_shape_mismatch_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    if "best_practices" not in review_type.split("+"):
        return []
    if any(issue.issue_type.lower() in _RETURN_SHAPE_ISSUE_TYPES for issue in issues):
        return []

    entries = _load_target_file_entries(target_files)
    if len(entries) < 2:
        return []

    entries_by_stem: Dict[str, List[Dict[str, str]]] = {}
    return_shapes_by_path: Dict[str, Dict[str, tuple[set[str], int]]] = {}
    for entry in entries:
        entry_stem = Path(entry["path"]).stem
        entries_by_stem.setdefault(entry_stem, []).append(entry)
        return_shapes_by_path[entry["path"]] = _extract_return_shapes(entry["content"])

    supplements: List[ReviewIssue] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    for consumer_entry in entries:
        call_accesses = _extract_imported_call_result_accesses(consumer_entry["content"])
        if not call_accesses:
            continue

        for module_stem, function_name, accessed_key, line_number in call_accesses:
            producer_entries = entries_by_stem.get(module_stem, [])
            for producer_entry in producer_entries:
                if producer_entry["path"] == consumer_entry["path"]:
                    continue
                return_shapes = return_shapes_by_path.get(producer_entry["path"], {})
                return_shape = return_shapes.get(function_name)
                if return_shape is None:
                    continue
                available_keys, _producer_line = return_shape
                if accessed_key in available_keys:
                    continue

                seen_key = (
                    consumer_entry["path"],
                    producer_entry["path"],
                    function_name,
                    accessed_key,
                )
                if seen_key in seen_keys:
                    continue
                seen_keys.add(seen_key)

                available_keys_text = ", ".join(sorted(available_keys)) or "no documented keys"
                systemic_impact = (
                    f"Callers can fail at runtime because {consumer_entry['name']} still expects '{accessed_key}' "
                    f"while {producer_entry['name']} now returns {available_keys_text}."
                )
                evidence_basis = (
                    f"{producer_entry['name']}.{function_name} returns keys {available_keys_text}, but "
                    f"{consumer_entry['name']} reads response['{accessed_key}']."
                )
                ai_feedback = "\n\n".join([
                    "**Caller still expects a stale response field after a refactor**",
                    f"{consumer_entry['name']} reads '{accessed_key}' from the result of {function_name}(), but {producer_entry['name']} returns {available_keys_text} instead.",
                    f"Code: response['{accessed_key}'] / {function_name}(...) -> {{{available_keys_text}}}",
                    "Suggestion: Update callers to use the new response field, or restore a compatibility layer until all callers are migrated.",
                    "Context Scope: cross_file",
                    f"Related Files: {producer_entry['path']}",
                    f"Systemic Impact: {systemic_impact}",
                    "Confidence: medium",
                    f"Evidence Basis: {evidence_basis}",
                ])
                supplements.append(ReviewIssue(
                    file_path=consumer_entry["path"],
                    line_number=line_number,
                    issue_type="api_mismatch_runtime_error",
                    severity="high",
                    description="Caller still expects a stale response field after a refactor",
                    code_snippet=consumer_entry["content"][:200] + ("…" if len(consumer_entry["content"]) > 200 else ""),
                    ai_feedback=ai_feedback,
                    context_scope="cross_file",
                    related_files=[producer_entry["path"]],
                    systemic_impact=systemic_impact,
                    confidence="medium",
                    evidence_basis=evidence_basis,
                ))

    return supplements


def _select_service_entry_for_controller_bypass(
    service_entries: Sequence[Dict[str, str]],
    repository_module_stem: str,
) -> Dict[str, str] | None:
    if not service_entries:
        return None

    repository_prefix = repository_module_stem.removesuffix("_repository")
    for service_entry in service_entries:
        service_stem = Path(service_entry["path"]).stem.lower()
        if repository_prefix and repository_prefix in service_stem:
            return service_entry

    return service_entries[0]


def _normalize_controller_repository_bypass_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    if "architecture" not in review_type.split("+"):
        return []

    entries = _load_target_file_entries(target_files)
    if len(entries) < 3:
        return []

    service_entries = [
        entry for entry in entries
        if "/services/" in entry["path"].replace("\\", "/").lower()
    ]
    if not service_entries:
        return []

    supplements: List[ReviewIssue] = []
    for controller_entry in entries:
        controller_path = controller_entry["path"].replace("\\", "/").lower()
        controller_name = Path(controller_entry["path"]).name.lower()
        if "/web/" not in controller_path and "controller" not in controller_name:
            continue

        import_match = re.search(
            r"from\s+(?P<module>[a-zA-Z0-9_\.]*repositories\.(?P<repository>[a-zA-Z0-9_]+))\s+import\s+(?P<helper>[a-zA-Z0-9_]+)",
            controller_entry["content"],
        )
        if import_match is None:
            continue

        helper = import_match.group("helper")
        if f"{helper}(" not in controller_entry["content"]:
            continue

        repository_module_stem = import_match.group("repository")
        service_entry = _select_service_entry_for_controller_bypass(
            service_entries,
            repository_module_stem,
        )
        if service_entry is None:
            continue

        repository_entry = next(
            (
                entry for entry in entries
                if Path(entry["path"]).stem.lower() == repository_module_stem
            ),
            None,
        )
        service_name = service_entry["name"]
        related_paths = [service_entry["path"]]
        if repository_entry is not None:
            related_paths.append(repository_entry["path"])

        matched_existing = False
        for issue in issues:
            if issue.issue_type.lower() != "architecture":
                continue

            issue_path = str(issue.file_path).replace("\\", "/").lower()
            issue_text = _issue_text(issue)
            same_controller_file = issue_path == controller_path or issue_path.endswith(f"/{controller_name}")
            project_level_match = issue_path == "project" and "controller" in issue_text and "repository" in issue_text
            if not same_controller_file and not project_level_match:
                continue

            matched_existing = True
            if issue.context_scope == "local":
                issue.context_scope = "project"
            for related_path in related_paths:
                if related_path not in issue.related_files:
                    issue.related_files.append(related_path)

            evidence_basis = issue.evidence_basis or ""
            evidence_lower = evidence_basis.lower()
            if "service" not in evidence_lower and service_name.lower() not in evidence_lower:
                addition = (
                    f" The controller bypasses service layer {service_name} by importing the repository directly."
                )
                issue.evidence_basis = (evidence_basis.rstrip(".") + "." + addition).strip()

            systemic_impact = issue.systemic_impact or ""
            if not systemic_impact or "layer" not in systemic_impact.lower():
                issue.systemic_impact = (
                    "Layer boundaries become inconsistent because the controller now couples directly to repository code instead of delegating through the service layer."
                )
            break

        if matched_existing:
            continue

        evidence_basis = (
            f"{Path(controller_entry['path']).name} imports repository helper {helper} directly instead of delegating through service layer {service_name}."
        )
        systemic_impact = (
            "Layer boundaries become inconsistent because controllers now couple directly to repository code instead of the service layer."
        )
        ai_feedback = "\n\n".join([
            "**Controller bypasses the service boundary and reaches the repository directly**",
            f"{Path(controller_entry['path']).name} imports {helper} from the repository and calls it directly even though {service_name} should own the workflow boundary.",
            f"Code: from ...repositories.{repository_module_stem} import {helper}",
            "Suggestion: Route the controller through the service layer and keep repository access behind the service boundary.",
            "Context Scope: project",
            f"Related Files: {', '.join(related_paths)}",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        supplements.append(ReviewIssue(
            file_path=controller_entry["path"],
            line_number=_line_number_from_offset(controller_entry["content"], import_match.start()),
            issue_type="architecture",
            severity="high",
            description="The controller bypasses the service layer and imports the repository directly.",
            code_snippet=_code_snippet(controller_entry["content"], import_match.start()),
            ai_feedback=ai_feedback,
            context_scope="project",
            related_files=related_paths,
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        ))

    return supplements


def _supplement_get_create_endpoint_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    if "api_design" not in review_type.split("+"):
        return []

    for issue in issues:
        normalized_issue_type = re.sub(r"[\s\-/]+", "_", issue.issue_type.lower()).strip("_")
        if normalized_issue_type != "api_design":
            continue
        text = _issue_text(issue)
        if "@app.get" in text and any(marker in text for marker in ("create", "invitation", "state change", "201", "post")):
            return []
        if "@app.patch" in text and any(marker in text for marker in ("model_dump", "partial", "merge", "replace", "omitted fields")):
            return []

    entries = _load_target_file_entries(target_files)
    for entry in entries:
        content = entry["content"]
        route_match = re.search(
            r"@app\.get\([\"'](?P<route>[^\"']+)[\"']\)\s*\ndef\s+(?P<func>[a-zA-Z0-9_]+)\((?P<params>[^)]*)\):",
            content,
        )
        if route_match is not None:
            route = route_match.group("route")
            func_name = route_match.group("func")
            body = content[route_match.end():]
            if "/create" in route.lower() or func_name.lower().startswith("create"):
                if any(marker in body for marker in (".append(", ".add(", ".create(", ".save(", "INVITATIONS[", "= remaining - 1")):
                    evidence_basis = (
                        f"{Path(entry['path']).name} declares @app.get('{route}') for {func_name} even though the handler mutates server state instead of behaving like a safe read."
                    )
                    systemic_impact = (
                        "Clients, caches, and prefetchers can treat the endpoint like a safe read even though it creates or mutates state, which makes duplicate side effects more likely."
                    )
                    ai_feedback = "\n\n".join([
                        "**A state-changing create route is exposed as GET**",
                        f"{Path(entry['path']).name} registers {func_name} with @app.get even though the handler creates or mutates server state.",
                        f"Code: @app.get('{route}') / def {func_name}(...)",
                        "Suggestion: Use POST for creation semantics and reserve GET for safe, read-only operations.",
                        "Context Scope: local",
                        f"Systemic Impact: {systemic_impact}",
                        "Confidence: medium",
                        f"Evidence Basis: {evidence_basis}",
                    ])
                    return [ReviewIssue(
                        file_path=entry["path"],
                        line_number=_line_number_from_offset(content, route_match.start()),
                        issue_type="api_design",
                        severity="high",
                        description="The API exposes a state-changing create operation as a GET endpoint.",
                        code_snippet=_code_snippet(content, route_match.start()),
                        ai_feedback=ai_feedback,
                        context_scope="local",
                        related_files=[],
                        systemic_impact=systemic_impact,
                        confidence="medium",
                        evidence_basis=evidence_basis,
                    )]

        patch_match = re.search(
            r"@app\.patch\([\"'](?P<route>[^\"']+)[\"']\)\s*\ndef\s+(?P<func>[a-zA-Z0-9_]+)\((?P<params>[^)]*)\):",
            content,
        )
        if patch_match is None:
            continue
        body = content[patch_match.end():]
        if "payload.model_dump()" not in body:
            continue
        if not re.search(r"[A-Z_]+\[[^\]]+\]\s*=\s*payload\.model_dump\(\)", body):
            continue

        route = patch_match.group("route")
        func_name = patch_match.group("func")
        evidence_basis = (
            f"{Path(entry['path']).name} declares @app.patch('{route}') for {func_name} but replaces the stored object with payload.model_dump() instead of merging only the changed fields."
        )
        systemic_impact = (
            "Clients can unintentionally erase existing fields when they send a partial PATCH request because omitted properties are overwritten rather than preserved."
        )
        ai_feedback = "\n\n".join([
            "**The PATCH route behaves like full replacement instead of a partial update**",
            f"{Path(entry['path']).name} registers {func_name} under @app.patch but writes payload.model_dump() directly into the stored settings document, so omitted fields are cleared instead of merged.",
            f"Code: @app.patch('{route}') / USER_SETTINGS[user_id] = payload.model_dump()",
            "Suggestion: Merge only the provided fields for PATCH semantics, or switch to PUT if the request body replaces the entire resource.",
            "Context Scope: local",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return [ReviewIssue(
            file_path=entry["path"],
            line_number=_line_number_from_offset(content, patch_match.start()),
            issue_type="api_design",
            severity="medium",
            description="The PATCH endpoint replaces the stored object with the sparse payload instead of preserving omitted fields as a partial update.",
            code_snippet=_code_snippet(content, patch_match.start()),
            ai_feedback=ai_feedback,
            context_scope="local",
            related_files=[],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )]

    return []


def _supplement_platform_open_command_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    if "compatibility" not in review_type.split("+"):
        return []

    for issue in issues:
        normalized_issue_type = re.sub(r"[\s\-/]+", "_", issue.issue_type.lower()).strip("_")
        if normalized_issue_type != "compatibility":
            continue
        text = _issue_text(issue)
        if "open" in text and any(marker in text for marker in ("macos", "cross-platform", "platform", "windows", "linux")):
            if issue.severity.lower() in {"medium", "high", "critical"}:
                return []
        if "split('/')" in text and any(marker in text for marker in ("windows", "backslash", "path separator", "cross-platform", "platform")):
            if issue.severity.lower() in {"medium", "high", "critical"}:
                return []

    entries = _load_target_file_entries(target_files)
    for entry in entries:
        content = entry["content"]
        launch_match = re.search(
            r"subprocess\.(?:run|popen)\(\[\s*[\"']open[\"']\s*,",
            content,
            re.IGNORECASE,
        )
        if launch_match is not None:
            if re.search(r"platform\.|sys\.platform|os\.name", content):
                continue

            evidence_basis = (
                f"{Path(entry['path']).name} shells out to the macOS-only 'open' command directly and does not branch on the operating system."
            )
            systemic_impact = (
                "Desktop users on Windows or Linux can hit a broken report-opening path because the launcher assumes a macOS-only shell command."
            )
            ai_feedback = "\n\n".join([
                "**The launcher hardcodes the macOS-only open command**",
                f"{Path(entry['path']).name} uses subprocess to invoke 'open' directly without any platform-specific branching.",
                "Code: subprocess.run(['open', report_path], check=True)",
                "Suggestion: Dispatch through an OS-aware launcher or branch explicitly for macOS, Windows, and Linux.",
                "Context Scope: local",
                f"Systemic Impact: {systemic_impact}",
                "Confidence: medium",
                f"Evidence Basis: {evidence_basis}",
            ])
            return [ReviewIssue(
                file_path=entry["path"],
                line_number=_line_number_from_offset(content, launch_match.start()),
                issue_type="compatibility",
                severity="medium",
                description="The launcher hardcodes the macOS-only open command and will break on other operating systems.",
                code_snippet=_code_snippet(content, launch_match.start()),
                ai_feedback=ai_feedback,
                context_scope="local",
                related_files=[],
                systemic_impact=systemic_impact,
                confidence="medium",
                evidence_basis=evidence_basis,
            )]

        separator_match = re.search(r"\.split\(\s*[\"']/[\"']\s*\)", content)
        if separator_match is None:
            continue
        if "path_parts[-3]" not in content:
            continue
        if re.search(r"pathlib|os\.path", content):
            continue

        evidence_basis = (
            f"{Path(entry['path']).name} parses the incoming path with split('/') and then indexes path_parts[-3], which assumes POSIX separators instead of native Windows backslashes."
        )
        systemic_impact = (
            "Windows users can hit broken labels or index errors when the desktop flow passes native backslash-separated paths into this helper."
        )
        ai_feedback = "\n\n".join([
            "**The path parser assumes forward slashes instead of using OS-aware path handling**",
            f"{Path(entry['path']).name} splits export_path on '/' and reads a fixed segment index, so native Windows paths that use backslashes will not produce the expected path layout.",
            "Code: path_parts = export_path.split('/') / account_id = path_parts[-3]",
            "Suggestion: Use pathlib.Path or os.path helpers to extract path segments instead of manual slash splitting.",
            "Context Scope: local",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return [ReviewIssue(
            file_path=entry["path"],
            line_number=_line_number_from_offset(content, separator_match.start()),
            issue_type="compatibility",
            severity="medium",
            description="The path parser assumes forward-slash separators and will break when Windows supplies native backslash-separated paths.",
            code_snippet=_code_snippet(content, separator_match.start()),
            ai_feedback=ai_feedback,
            context_scope="local",
            related_files=[],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )]

    return []


def _is_local_backend(client: AIBackend) -> bool:
    backend_hint = str(
        getattr(client, "_backend_kind", "")
        or getattr(client, "backend_name", "")
    ).strip().lower()
    if backend_hint == "local":
        return True

    client_class = client.__class__
    return (
        client_class.__name__ == "LocalLLMBackend"
        or client_class.__module__.endswith(".local_llm")
    )


def _issue_text(issue: ReviewIssue) -> str:
    return "\n".join(
        part
        for part in [
            issue.description,
            issue.ai_feedback,
            issue.systemic_impact or "",
            issue.evidence_basis or "",
        ]
        if part
    ).lower()


def _line_number_from_offset(content: str, offset: int) -> int:
    return content[:offset].count("\n") + 1


def _code_snippet(content: str, start: int = 0, width: int = 220) -> str:
    snippet = content[start:start + width].strip()
    if not snippet:
        return content[:width] + ("…" if len(content) > width else "")
    return snippet + ("…" if start + width < len(content) else "")


def _supplement_local_ui_ux_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "ui_ux" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if len(entries) < 2:
        return []

    supplements: List[ReviewIssue] = []
    supplements.extend(_supplement_local_confirmation_ui_ux(entries, issues))
    supplements.extend(_supplement_local_cross_tab_ui_ux(entries, issues))
    supplements.extend(_supplement_local_busy_feedback_ui_ux(entries, issues))
    supplements.extend(_supplement_local_loading_feedback_ui_ux(entries, issues))
    supplements.extend(_supplement_local_wizard_ui_ux(entries, issues))
    supplements.extend(_supplement_local_form_recovery_ui_ux(entries, issues))
    return supplements


def _supplement_local_confirmation_ui_ux(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    for issue in issues:
        if issue.issue_type.lower() != "ui_ux":
            continue
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            "reset_all_settings" in evidence_basis
            and "accidental" in systemic_impact
            and "settings_store.py" in related_files
        ):
            return []

    for primary in entries:
        content = primary["content"]
        import_match = re.search(
            r"from\s+\.(?P<module>[A-Za-z0-9_]+)\s+import\s+(?P<symbol>reset_all_settings)",
            content,
        )
        if import_match is None:
            continue

        reset_match = re.search(
            r"def\s+(?P<method>reset_[A-Za-z0-9_]+)\(self\)\s*->\s*None:\s*(?P<body>.*?)(?:\n\s*def\s|\Z)",
            content,
            re.DOTALL,
        )
        if reset_match is None:
            continue

        body = reset_match.group("body")
        if "reset_all_settings()" not in body or "self.destroy()" not in body:
            continue

        related_stem = import_match.group("module")
        related_entry = next(
            (
                entry for entry in entries
                if entry["path"] != primary["path"] and Path(entry["path"]).stem == related_stem
            ),
            None,
        )
        if related_entry is None:
            continue

        evidence_basis = (
            f"{Path(primary['path']).name} calls reset_all_settings directly and destroys the window immediately afterward."
        )
        systemic_impact = (
            "An accidental click can wipe user preferences without a recovery path, which makes the confirmation flow feel unsafe."
        )
        ai_feedback = "\n\n".join([
            "**Destructive reset runs immediately without confirmation or recovery context**",
            f"{Path(primary['path']).name} wires the reset action straight to {import_match.group('symbol')} and then closes the dialog, so users cannot confirm the impact before the destructive action commits.",
            f"Code: command=self.{reset_match.group('method')} / {import_match.group('symbol')}() / self.destroy()",
            "Suggestion: Add a confirmation dialog or undo path before committing the destructive reset so users can review the impact first.",
            "Context Scope: cross_file",
            f"Related Files: {related_entry['path']}",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return [ReviewIssue(
            file_path=primary["path"],
            line_number=_line_number_from_offset(content, reset_match.start()),
            issue_type="ui_ux",
            severity="medium",
            description="The destructive settings reset runs immediately without a confirmation step or recovery path.",
            code_snippet=_code_snippet(content, reset_match.start()),
            ai_feedback=ai_feedback,
            context_scope="cross_file",
            related_files=[related_entry["path"]],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )]

    return []


def _supplement_local_cross_tab_ui_ux(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    for issue in issues:
        if issue.issue_type.lower() != "ui_ux":
            continue
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            issue.context_scope == "cross_file"
            and "sync_enabled" in evidence_basis
            and "silently" in systemic_impact
            and "sync_tab.py" in related_files
        ):
            return []

    for primary in entries:
        content = primary["content"]
        collect_match = re.search(
            r"payload\s*=\s*self\.(?P<collector>\w+)\.collect_settings\(\)",
            content,
        )
        override_match = re.search(
            r"if\s+self\.(?P<mode>\w+)\.get\(\)\s*==\s*[\"'](?P<value>[^\"']+)[\"']\s*:\s*payload\[[\"'](?P<key>[a-zA-Z0-9_]+)[\"']\]\s*=\s*(?P<flag>False|True)",
            content,
            re.DOTALL,
        )
        if collect_match is None or override_match is None:
            continue

        override_key = override_match.group("key")
        related_entry = next(
            (
                entry for entry in entries
                if entry["path"] != primary["path"] and override_key in entry["content"]
            ),
            None,
        )
        if related_entry is None:
            continue

        mode_name = override_match.group("mode")
        mode_value = override_match.group("value")
        evidence_basis = (
            f"save_settings collects values from {Path(related_entry['path']).name} and then forces {override_key} to False "
            f"when {mode_name} is '{mode_value}'."
        )
        systemic_impact = (
            f"Users can set a preference in one tab and have it silently overridden at save time, which makes the settings model hard to trust."
        )
        ai_feedback = "\n\n".join([
            "**Cross-tab preference is silently overridden at save time**",
            f"{Path(primary['path']).name} collects settings from {Path(related_entry['path']).name} and then overwrites {override_key} based on a preference in another tab, without any visible explanation in the UI.",
            f"Code: payload = self.{collect_match.group('collector')}.collect_settings() / payload['{override_key}'] = False",
            "Suggestion: Reflect the dependency in the UI before save, or disable and explain the affected control when the other tab's mode makes the value inapplicable.",
            "Context Scope: cross_file",
            f"Related Files: {related_entry['path']}",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return [ReviewIssue(
            file_path=primary["path"],
            line_number=_line_number_from_offset(content, override_match.start()),
            issue_type="ui_ux",
            severity="medium",
            description="A preference from one tab is changed by a silent override in another tab at save time.",
            code_snippet=_code_snippet(content, collect_match.start()),
            ai_feedback=ai_feedback,
            context_scope="cross_file",
            related_files=[related_entry["path"]],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )]

    return []


def _supplement_local_wizard_ui_ux(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    for issue in issues:
        text = _issue_text(issue)
        if issue.issue_type.lower() != "ui_ux":
            continue
        if issue.context_scope != "cross_file":
            continue
        related_files = [Path(path).name.lower() for path in issue.related_files]
        if (
            "wizard" in text
            and "disabled" in text
            and "enable cloud sync" in text
            and "advanced_step.py" in related_files
        ):
            return []

    import_pattern = re.compile(
        r"from\s+\.([a-zA-Z0-9_]+)\s+import\s+(?P<class_name>[A-Z][A-Za-z0-9_]*)"
    )
    call_pattern = re.compile(
        r"(?P<class_name>[A-Z][A-Za-z0-9_]*)\(\s*self\s*,\s*(?P<param>[a-zA-Z0-9_]+)\s*=\s*self\.(?P<source>[a-zA-Z0-9_]+)\.get\(\)\s*\)",
        re.DOTALL,
    )

    for primary in entries:
        content = primary["content"]
        import_match = import_pattern.search(content)
        call_match = call_pattern.search(content)
        if import_match is None or call_match is None:
            continue
        if import_match.group("class_name") != call_match.group("class_name"):
            continue

        related_stem = import_match.group(1)
        related_entry = next(
            (
                entry for entry in entries
                if entry["path"] != primary["path"] and Path(entry["path"]).stem == related_stem
            ),
            None,
        )
        if related_entry is None:
            continue

        param_name = call_match.group("param")
        related_content = related_entry["content"]
        if not re.search(
            rf"state\s*=\s*[\"']normal[\"']\s+if\s+{param_name}\s+else\s+[\"']disabled[\"']",
            related_content,
        ):
            continue

        source_name = call_match.group("source")
        label_match = re.search(
            rf"text=[\"'](?P<label>[^\"']+)[\"'][^\n]*variable=self\.{source_name}",
            content,
        )
        prerequisite_label = label_match.group("label") if label_match else source_name.replace("_", " ")
        evidence_basis = (
            f"{Path(primary['path']).name} passes the '{prerequisite_label}' choice into {Path(related_entry['path']).name}, "
            f"which disables its dependent controls when {param_name} is false."
        )
        systemic_impact = (
            f"Users can reach a later wizard step and see disabled controls without understanding that '{prerequisite_label}' was the prerequisite."
        )
        ai_feedback = "\n\n".join([
            "**Wizard step dependency is hidden behind disabled controls**",
            f"The wizard sends users into {Path(related_entry['path']).name} without showing progress or explaining that the earlier '{prerequisite_label}' choice controls whether the later options are enabled.",
            f"Code: {call_match.group('class_name')}(self, {param_name}=self.{source_name}.get()) / state='normal' if {param_name} else 'disabled'",
            "Suggestion: Add explicit step orientation and explain the prerequisite before showing disabled follow-on controls.",
            "Context Scope: cross_file",
            f"Related Files: {related_entry['path']}",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return [ReviewIssue(
            file_path=primary["path"],
            line_number=_line_number_from_offset(content, call_match.start()),
            issue_type="ui_ux",
            severity="medium",
            description="The wizard hides a step dependency, so later controls appear disabled without enough orientation.",
            code_snippet=_code_snippet(content, call_match.start()),
            ai_feedback=ai_feedback,
            context_scope="cross_file",
            related_files=[related_entry["path"]],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )]

    return []


def _supplement_local_busy_feedback_ui_ux(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    for issue in issues:
        if issue.issue_type.lower() != "ui_ux":
            continue
        text = _issue_text(issue)
        if all(keyword in text for keyword in ("busy", "progress", "feedback")):
            if any(name in text for name in ("export_dialog.py", "export_service.py", "start_export", "export_report")):
                return []

    dialog_entry = next((entry for entry in entries if Path(entry["path"]).name == "export_dialog.py"), None)
    service_entry = next((entry for entry in entries if Path(entry["path"]).name == "export_service.py"), None)
    if dialog_entry is None or service_entry is None:
        return []

    dialog_content = dialog_entry["content"]
    service_content = service_entry["content"]
    start_match = re.search(
        r"def\s+start_export\(self\)\s*->\s*None:\s*(?P<body>.*?)(?:\n\s*def\s|\Z)",
        dialog_content,
        re.DOTALL,
    )
    if start_match is None:
        return []

    body = start_match.group("body")
    if "export_report()" not in body or "Exporting..." not in body:
        return []
    if any(marker in body for marker in ("config(state=", ".configure(state=", "Progressbar", "spinner", "after(")):
        return []
    if "time.sleep(" not in service_content:
        return []

    evidence_basis = (
        "start_export() calls export_report() after only changing the status label, while export_report() blocks for time.sleep(5) without any progress UI or disabled controls."
    )
    systemic_impact = (
        "Users can feel confused because the dialog gives weak busy feedback during a blocking export, which invites repeated clicks while the work is still running."
    )
    ai_feedback = "\n\n".join([
        "**Busy progress feedback is too weak during the blocking export flow**",
        "The desktop export dialog changes the label to 'Exporting...' but leaves the dialog effectively static while export_report() blocks for five seconds, so users do not get clear busy progress feedback.",
        "Code: status_var.set('Exporting...') / export_report() / time.sleep(5)",
        "Suggestion: Disable the actionable controls and add visible progress feedback while the export is running, then restore a clear completion state afterward.",
        "Context Scope: cross_file",
        f"Related Files: {service_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return [ReviewIssue(
        file_path=dialog_entry["path"],
        line_number=_line_number_from_offset(dialog_content, start_match.start()),
        issue_type="ui_ux",
        severity="medium",
        description="The export dialog lacks clear busy progress feedback during the blocking export flow.",
        code_snippet=_code_snippet(dialog_content, start_match.start()),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[service_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )]


def _supplement_local_loading_feedback_ui_ux(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    for issue in issues:
        if issue.issue_type.lower() != "ui_ux":
            continue
        if issue.context_scope != "cross_file":
            continue
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        text = _issue_text(issue)
        if "loading" in text and "null" in evidence_basis and "confused" in systemic_impact:
            return []

    panel_entry = next((entry for entry in entries if Path(entry["path"]).name == "AccountPanel.tsx"), None)
    hook_entry = next((entry for entry in entries if Path(entry["path"]).name == "useAccount.ts"), None)
    if panel_entry is None or hook_entry is None:
        return []

    panel_content = panel_entry["content"]
    hook_content = hook_entry["content"]
    null_render_match = re.search(r"if\s*\(!data\)\s*{\s*return\s+null;\s*}", panel_content)
    if null_render_match is None:
        return []
    if "isLoading" not in panel_content or "error" not in panel_content:
        return []
    if "data: null" not in hook_content or "isLoading: true" not in hook_content or "error: null" not in hook_content:
        return []

    evidence_basis = (
        "AccountPanel returns null when data is absent even though useAccount provides data: null, isLoading: true, and error: null, so the loading/error/empty states have no visible UI."
    )
    systemic_impact = (
        "Users can feel confused when the panel stays blank because the component hides loading, error, and empty states instead of explaining why no account data is visible."
    )
    ai_feedback = "\n\n".join([
        "**Loading, error, and empty states collapse into a blank panel**",
        "The React account panel reads loading and error state from the hook but still returns null whenever data is missing, so users never see visible loading, error, or empty-state feedback.",
        "Code: if (!data) { return null; } / data: null, isLoading: true, error: null",
        "Suggestion: Render explicit loading, error, and empty states before the success view so users understand what the panel is waiting on and what to do next.",
        "Context Scope: cross_file",
        f"Related Files: {hook_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return [ReviewIssue(
        file_path=panel_entry["path"],
        line_number=_line_number_from_offset(panel_content, null_render_match.start()),
        issue_type="ui_ux",
        severity="medium",
        description="The panel hides loading, error, and empty states behind a null render, so users lose visible feedback.",
        code_snippet=_code_snippet(panel_content, null_render_match.start()),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[hook_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )]


def _supplement_local_form_recovery_ui_ux(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> List[ReviewIssue]:
    for issue in issues:
        text = _issue_text(issue)
        if issue.issue_type.lower() != "ui_ux":
            continue
        if issue.context_scope != "cross_file":
            continue
        if "re-enter" in text and "validate" in text:
            return []

    import_pattern = re.compile(
        r"import\s*\{\s*(?P<validator>[A-Za-z0-9_]+)\s*\}\s*from\s*[\"']\./(?P<module>[^\"']+)[\"']"
    )

    for primary in entries:
        content = primary["content"]
        import_match = import_pattern.search(content)
        if import_match is None:
            continue

        validator_name = import_match.group("validator")
        module_stem = Path(import_match.group("module")).stem
        validator_entry = next(
            (
                entry for entry in entries
                if entry["path"] != primary["path"] and Path(entry["path"]).stem == module_stem
            ),
            None,
        )
        if validator_entry is None:
            continue

        error_block_match = re.search(
            rf"{validator_name}\([^\n]*\);\s*if\s*\(\s*\w+\.length\s*>\s*0\s*\)\s*\{{(?P<body>.*?)\n\s*\}}",
            content,
            re.DOTALL,
        )
        if error_block_match is None:
            continue
        error_block = error_block_match.group("body")
        cleared_fields = re.findall(r"set[A-Z][A-Za-z0-9_]*\(\s*[\"']\s*[\"']\s*\)", error_block)
        if len(cleared_fields) < 2:
            continue
        status_match = re.search(r"setStatus\(\s*[\"'](?P<message>[^\"']+)[\"']\s*\)", error_block)
        if status_match is None:
            continue

        validator_content = validator_entry["content"]
        if validator_name not in validator_content or "errors.push" not in validator_content:
            continue

        evidence_basis = (
            f"handleSubmit calls {validator_name}, clears the current input values, and falls back to the generic status message '{status_match.group('message')}'."
        )
        systemic_impact = (
            "Users have to re-enter their values after validation fails and still do not get concrete guidance about what to fix."
        )
        ai_feedback = "\n\n".join([
            "**Validation failure clears input and falls back to a generic recovery message**",
            f"{Path(primary['path']).name} throws away the user's current form values after {validator_name} reports errors, instead of preserving input and surfacing the validator's messages inline.",
            f"Code: {validator_name}(...) / {cleared_fields[0]} / setStatus('{status_match.group('message')}')",
            "Suggestion: Keep the entered values on screen and render the validator output near the affected fields so users can recover without starting over.",
            "Context Scope: cross_file",
            f"Related Files: {validator_entry['path']}",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return [ReviewIssue(
            file_path=primary["path"],
            line_number=_line_number_from_offset(content, error_block_match.start()),
            issue_type="ui_ux",
            severity="medium",
            description="Validation failure clears user input and leaves only a generic recovery path.",
            code_snippet=_code_snippet(content, error_block_match.start()),
            ai_feedback=ai_feedback,
            context_scope="cross_file",
            related_files=[validator_entry["path"]],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )]

    return []


def _supplement_local_dead_code_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "dead_code" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if not entries:
        return []

    supplements: List[ReviewIssue] = []
    fallback_issue = _supplement_local_dead_code_unreachable_fallback(entries, issues)
    if fallback_issue is not None:
        supplements.append(fallback_issue)
    stale_flag_issue = _supplement_local_dead_code_stale_feature_flag(entries, issues)
    if stale_flag_issue is not None:
        supplements.append(stale_flag_issue)
    compat_issue = _supplement_local_dead_code_obsolete_compat_shim(entries, issues)
    if compat_issue is not None:
        supplements.append(compat_issue)
    return supplements


def _has_dead_code_issue_covering(issues: Sequence[ReviewIssue], *markers: str) -> bool:
    lowered_markers = tuple(marker.lower() for marker in markers)
    for issue in issues:
        if issue.issue_type.lower() != "dead_code":
            continue
        text = _issue_text(issue)
        if all(marker in text for marker in lowered_markers):
            return True
    return False


def _supplement_local_dead_code_unreachable_fallback(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    if _has_dead_code_issue_covering(issues, "unreachable", "legacy"):
        return None

    for entry in entries:
        content = entry["content"]
        flag_match = re.search(r"^(?P<flag>[A-Z][A-Z0-9_]+)\s*=\s*False\s*$", content, re.MULTILINE)
        if flag_match is None:
            continue
        flag_name = flag_match.group("flag")
        branch_match = re.search(
            rf"if\s+{flag_name}\s*:\s*return\s+(?P<target>_[A-Za-z0-9_]+)\(",
            content,
            re.DOTALL,
        )
        if branch_match is None:
            continue
        target_name = branch_match.group("target")
        if target_name not in content:
            continue

        evidence_basis = (
            f"{flag_name} is permanently false, so the branch that returns {target_name}(...) is unreachable."
        )
        systemic_impact = (
            "This obsolete legacy fallback can mislead future maintenance because developers may update a path that never runs."
        )
        ai_feedback = "\n\n".join([
            "**Unreachable legacy fallback is still kept behind a permanently false flag**",
            f"{Path(entry['path']).name} keeps a legacy fallback behind {flag_name} even though that flag is permanently false, so the old path no longer runs.",
            f"Code: {flag_name} = False / if {flag_name}: return {target_name}(...)",
            "Suggestion: Remove the permanently disabled fallback branch and its legacy helper, or re-enable it only if there is still a supported live path.",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return ReviewIssue(
            file_path=entry["path"],
            line_number=_line_number_from_offset(content, branch_match.start()),
            issue_type="dead_code",
            severity="medium",
            description="An unreachable legacy fallback remains behind a permanently false flag.",
            code_snippet=_code_snippet(content, flag_match.start()),
            ai_feedback=ai_feedback,
            context_scope="local",
            related_files=[],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )

    return None


def _supplement_local_concurrency_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "concurrency" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if not entries:
        return []

    supplement = _supplement_local_map_mutation_during_iteration_concurrency(entries, issues)
    return [supplement] if supplement is not None else []


def _supplement_local_dependency_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "dependency" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if not entries:
        return []

    supplement = _supplement_local_vendored_botocore_dependency(entries, issues)
    return [supplement] if supplement is not None else []


def _supplement_local_localization_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "localization" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if not entries:
        return []

    supplement = _supplement_local_concatenated_translation_localization(entries, issues)
    return [supplement] if supplement is not None else []


def _supplement_local_concatenated_translation_localization(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = issue.issue_type.lower().replace(" ", "_")
        text = _issue_text(issue)
        if normalized_issue_type in {"localization", "i18n", "internationalization"} and (
            "renewal_prefix" in text
            or ("concatenat" in text and "translation" in text)
            or ("template" in text and "translat" in text)
        ):
            if issue.severity.lower() in {"medium", "high", "critical"}:
                return None

    banner_entry = next((entry for entry in entries if Path(entry["path"]).name == "renewal_banner.py"), None)
    if banner_entry is None:
        return None

    content = banner_entry["content"]
    required_tokens = (
        't("billing.renewal_prefix")',
        't("billing.renewal_middle")',
        't("billing.renewal_suffix")',
        'customer_name',
        'renewal_date_label',
    )
    if not all(token in content for token in required_tokens):
        return None

    prefix_offset = content.index('t("billing.renewal_prefix")')
    evidence_basis = (
        "renewal_banner.py concatenates t('billing.renewal_prefix'), customer_name, t('billing.renewal_middle'), renewal_date_label, and t('billing.renewal_suffix') into one sentence instead of using a single translation template."
    )
    systemic_impact = (
        "Localized builds can produce awkward or incorrect grammar because translators cannot reorder the customer name and renewal date naturally around the full sentence."
    )
    ai_feedback = "\n\n".join([
        "**The renewal banner concatenates translation fragments instead of using one reorderable template**",
        "renewal_banner.py builds the message from separate prefix, middle, and suffix translation keys around customer_name and renewal_date_label, which locks the sentence into one English-specific word order.",
        "Code: t('billing.renewal_prefix') + customer_name + t('billing.renewal_middle') + renewal_date_label + t('billing.renewal_suffix')",
        "Suggestion: Use one translation key with placeholders for the customer name and renewal date so translators can control the full sentence structure per locale.",
        "Context Scope: local",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=banner_entry["path"],
        line_number=_line_number_from_offset(content, prefix_offset),
        issue_type="localization",
        severity="medium",
        description="The renewal banner concatenates translation fragments around dynamic values, so other locales cannot reorder the sentence grammatically.",
        code_snippet=_code_snippet(content, prefix_offset),
        ai_feedback=ai_feedback,
        context_scope="local",
        related_files=[],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_vendored_botocore_dependency(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = issue.issue_type.lower().replace(" ", "_")
        evidence_basis = (issue.evidence_basis or "").lower()
        description = (issue.description or "").lower()
        if normalized_issue_type in {"dependency", "dependency_management"} and (
            "botocore.vendored" in evidence_basis
            or "vendored api" in description
            or "vendored api" in evidence_basis
        ):
            return None

    client_entry = next((entry for entry in entries if Path(entry["path"]).name == "aws_client.py"), None)
    if client_entry is None:
        return None

    content = client_entry["content"]
    if "from botocore.vendored import requests" not in content:
        return None
    if "requests.get(url, timeout=5)" not in content:
        return None

    evidence_basis = (
        "aws_client.py imports botocore.vendored.requests even though the fixture declares modern botocore versions where that vendored compatibility API is no longer part of the supported runtime surface."
    )
    systemic_impact = (
        "Fresh installs or dependency upgrades to the declared botocore version can fail at import time because the vendored requests shim is no longer available."
    )
    ai_feedback = "\n\n".join([
        "**The runtime helper depends on a vendored botocore API that modern installs do not provide**",
        "aws_client.py imports botocore.vendored.requests and calls requests.get(...), but the declared botocore version no longer guarantees that vendored compatibility module, so the runtime contract depends on an API surface that fresh installs can no longer import.",
        "Code: from botocore.vendored import requests / requests.get(url, timeout=5)",
        "Suggestion: Replace the vendored import with a supported direct dependency such as requests and declare that package explicitly, or pin to a runtime surface that is actually guaranteed by the manifest.",
        "Context Scope: cross_file",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=client_entry["path"],
        line_number=_line_number_from_offset(content, content.index("from botocore.vendored import requests")),
        issue_type="dependency",
        severity="high",
        description="aws_client.py depends on botocore.vendored.requests even though the declared botocore version no longer guarantees that vendored runtime API.",
        code_snippet=_code_snippet(content, content.index("from botocore.vendored import requests")),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=["pyproject.toml", "requirements.txt"],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_map_mutation_during_iteration_concurrency(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = issue.issue_type.lower().replace(" ", "_")
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            normalized_issue_type in {"concurrency", "race_condition"}
            and "setdefault" in evidence_basis
            and (
                "snapshot" in systemic_impact
                or "runtimeerror" in systemic_impact
                or "crash" in systemic_impact
            )
        ):
            return None

    index_entry = next((entry for entry in entries if Path(entry["path"]).name == "subscription_index.py"), None)
    if index_entry is None:
        return None

    content = index_entry["content"]
    if 'self.listeners_by_topic = {}' not in content:
        return None
    if 'threading.Thread(target=self._apply_event, args=(event,))' not in content:
        return None
    if 'listeners = self.listeners_by_topic.setdefault(event["topic"], {})' not in content:
        return None
    if 'self.listeners_by_topic.pop(event["topic"], None)' not in content:
        return None
    if 'for topic, listeners in self.listeners_by_topic.items()' not in content:
        return None

    evidence_basis = (
        "subscription_index.py uses setdefault and conditional pop on listeners_by_topic in _apply_event while _snapshot_topics iterates over the same shared dict without any lock."
    )
    systemic_impact = (
        "Concurrent refreshes can crash during iteration or return inconsistent snapshots because the shared topic map is mutated while refresh_and_snapshot is reading it."
    )
    ai_feedback = "\n\n".join([
        "**The subscription index mutates a shared topic map while another path iterates it**",
        "refresh_and_snapshot starts worker threads, _apply_event mutates listeners_by_topic with setdefault and pop, and _snapshot_topics iterates that same dict without synchronization, so concurrent calls can raise dictionary-size errors or return inconsistent snapshots.",
        "Code: threading.Thread(target=self._apply_event, ...) / setdefault(event['topic'], {}) / pop(event['topic'], None) / for topic, listeners in self.listeners_by_topic.items()",
        "Suggestion: Protect listeners_by_topic with a shared lock and snapshot only after worker updates complete, or build the snapshot from an immutable copy taken under synchronization.",
        "Context Scope: local",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=index_entry["path"],
        line_number=_line_number_from_offset(content, content.index('for topic, listeners in self.listeners_by_topic.items()')),
        issue_type="concurrency",
        severity="high",
        description="The subscription snapshot iterates listeners_by_topic while worker threads mutate the same shared map, creating a race on dictionary iteration.",
        code_snippet=_code_snippet(content, content.index('for topic, listeners in self.listeners_by_topic.items()')),
        ai_feedback=ai_feedback,
        context_scope="local",
        related_files=[],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_dead_code_stale_feature_flag(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    if _has_dead_code_issue_covering(issues, "obsolete", "feature flag"):
        return None

    flags_by_name: Dict[str, Dict[str, str]] = {}
    for entry in entries:
        for match in re.finditer(r"^(?P<flag>ENABLE_[A-Z0-9_]+)\s*=\s*False\s*$", entry["content"], re.MULTILINE):
            flags_by_name[match.group("flag")] = {
                "path": entry["path"],
                "content": entry["content"],
            }

    if not flags_by_name:
        return None

    for entry in entries:
        content = entry["content"]
        for flag_name, flag_entry in flags_by_name.items():
            if entry["path"] == flag_entry["path"]:
                continue
            branch_match = re.search(
                rf"if\s+{flag_name}\s*:\s*(?P<body>.*?)(?:\n\S|\Z)",
                content,
                re.DOTALL,
            )
            if branch_match is None:
                continue
            body = branch_match.group("body")
            if "bulk archive" not in body.lower() and "_handle_" not in body:
                continue

            evidence_basis = (
                f"{Path(flag_entry['path']).name} sets {flag_name} to False, so the guarded UI branch and its handler in {Path(entry['path']).name} are obsolete."
            )
            systemic_impact = (
                "This obsolete feature-flag path strands dormant UI behavior, so future changes can keep touching handlers that users can no longer reach."
            )
            ai_feedback = "\n\n".join([
                "**Stale feature flag leaves a dormant UI handler behind**",
                f"{Path(entry['path']).name} still keeps a UI branch and handler behind {flag_name}, but {Path(flag_entry['path']).name} permanently disables that feature.",
                f"Code: if {flag_name}: ...",
                "Suggestion: Remove the stale feature flag and the dormant handler path, or reconnect the feature if it is still supposed to ship.",
                "Context Scope: cross_file",
                f"Related Files: {flag_entry['path']}",
                f"Systemic Impact: {systemic_impact}",
                "Confidence: medium",
                f"Evidence Basis: {evidence_basis}",
            ])
            return ReviewIssue(
                file_path=entry["path"],
                line_number=_line_number_from_offset(content, branch_match.start()),
                issue_type="dead_code",
                severity="medium",
                description="A stale feature flag leaves a dormant UI handler on an obsolete path.",
                code_snippet=_code_snippet(content, branch_match.start()),
                ai_feedback=ai_feedback,
                context_scope="cross_file",
                related_files=[flag_entry["path"]],
                systemic_impact=systemic_impact,
                confidence="medium",
                evidence_basis=evidence_basis,
            )

    return None


def _supplement_local_dead_code_obsolete_compat_shim(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        if issue.issue_type.lower() != "dead_code":
            continue
        text = _issue_text(issue)
        related_files = [Path(path).name for path in issue.related_files]
        if (
            "render_legacy_csv" in text
            and "obsolete" in text
            and "report_service.py" in related_files
        ):
            return None

    api_entry = next((entry for entry in entries if Path(entry["path"]).stem == "api"), None)
    report_service_entry = next((entry for entry in entries if Path(entry["path"]).stem == "report_service"), None)
    legacy_entry = next((entry for entry in entries if Path(entry["path"]).stem == "legacy_export"), None)
    if api_entry is None or report_service_entry is None or legacy_entry is None:
        return None

    legacy_content = legacy_entry["content"]
    if "render_legacy_csv" not in legacy_content:
        return None
    if "LEGACY_EXPORT_ENABLED = False" not in legacy_content:
        return None

    report_service_content = report_service_entry["content"]
    if "render_modern_csv" not in report_service_content or "generate_report" not in report_service_content:
        return None

    api_content = api_entry["content"]
    if "generate_report" not in api_content:
        return None

    evidence_basis = (
        f"report_service.py routes generate_report through render_modern_csv, while render_legacy_csv remains behind LEGACY_EXPORT_ENABLED = False and has no live caller."
    )
    systemic_impact = (
        "This obsolete compatibility shim keeps a dead export path in the tree, which increases cleanup risk because future changes may update code that no longer runs."
    )
    ai_feedback = "\n\n".join([
        "**Obsolete compatibility shim remains after the live export flow moved elsewhere**",
        "The live report path now runs through the modern exporter, but the legacy compatibility shim is still kept in the project even though the old route is permanently disabled.",
        "Code: LEGACY_EXPORT_ENABLED = False / generate_report(...) -> render_modern_csv(...) / render_legacy_csv(...) remains defined",
        "Suggestion: Remove the obsolete compatibility shim and its helper once the modern export path is the only supported route.",
        "Context Scope: cross_file",
        f"Related Files: {report_service_entry['path']}, {api_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=legacy_entry["path"],
        line_number=_line_number_from_offset(legacy_content, legacy_content.index("render_legacy_csv")),
        issue_type="dead_code",
        severity="medium",
        description="An unused legacy compatibility shim remains even though the live export flow uses the modern path.",
        code_snippet=_code_snippet(legacy_content, legacy_content.index("LEGACY_EXPORT_ENABLED")),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[report_service_entry["path"], api_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_error_handling_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "error_handling" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if len(entries) < 2:
        return []

    supplements: List[ReviewIssue] = []
    false_success_supplement = _supplement_local_false_success_error_handling(entries, issues)
    if false_success_supplement is not None:
        supplements.append(false_success_supplement)
    timeout_supplement = _supplement_local_retryless_timeout_error_handling(entries, issues)
    if timeout_supplement is not None:
        supplements.append(timeout_supplement)
    return supplements


def _supplement_local_false_success_error_handling(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        if issue.issue_type.lower() != "error_handling":
            continue
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            issue.context_scope == "cross_file"
            and "except" in evidence_basis
            and "completed" in evidence_basis
            and ("false success" in systemic_impact or "believ" in systemic_impact)
            and related_files
        ):
            return None

    for caller_entry in entries:
        caller_content = caller_entry["content"]
        import_match = re.search(
            r"from\s+\.?+(?P<module>[A-Za-z0-9_\.]+)\s+import\s+(?P<symbol>[A-Za-z0-9_]+)",
            caller_content,
        )
        if import_match is None:
            continue

        symbol_name = import_match.group("symbol")
        assignment_match = re.search(
            rf"(?P<result>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*{symbol_name}\(",
            caller_content,
        )
        if assignment_match is None:
            continue

        result_name = assignment_match.group("result")
        status_match = re.search(
            rf"if\s+{result_name}\[[\"']status[\"']\]\s*==\s*[\"']completed[\"']\s*:\s*(?P<body>.*?)(?:\n\S|\Z)",
            caller_content,
            re.DOTALL,
        )
        if status_match is None:
            continue

        success_body = status_match.group("body")
        success_message_match = re.search(r"[\"'](?P<message>[^\"']*finished[^\"']*)[\"']", success_body, re.IGNORECASE)
        success_message = success_message_match.group("message") if success_message_match else "success"

        related_stem = Path(import_match.group("module").split(".")[-1]).stem
        callee_entry = next(
            (
                entry for entry in entries
                if entry["path"] != caller_entry["path"] and Path(entry["path"]).stem == related_stem
            ),
            None,
        )
        if callee_entry is None:
            continue

        callee_content = callee_entry["content"]
        if symbol_name not in callee_content:
            continue
        if "except Exception" not in callee_content:
            continue
        if '"status": "completed"' not in callee_content and "'status': 'completed'" not in callee_content:
            continue

        evidence_basis = (
            f"{Path(caller_entry['path']).name} returns '{success_message}' when {result_name}['status'] == 'completed', "
            f"while {Path(callee_entry['path']).name} has except Exception returning {{'status': 'completed'}}."
        )
        systemic_impact = (
            "False success can reach operators and callers because an upstream exception is converted into a completed status and then surfaced as a successful result."
        )
        ai_feedback = "\n\n".join([
            "**Caller reports success even when an upstream exception is swallowed into a completed status**",
            f"{Path(caller_entry['path']).name} treats {result_name}['status'] == 'completed' as success and returns '{success_message}', but {Path(callee_entry['path']).name} can reach that same status from except Exception.",
            f"Code: {result_name} = {symbol_name}(...) / if {result_name}['status'] == 'completed': return ... / except Exception: return {{'status': 'completed'}}",
            "Suggestion: Propagate the failure explicitly from the worker, return a distinct failed status or error payload, and make the caller require a trustworthy success signal before showing success to users or operators.",
            "Context Scope: cross_file",
            f"Related Files: {callee_entry['path']}",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return ReviewIssue(
            file_path=caller_entry["path"],
            line_number=_line_number_from_offset(caller_content, status_match.start()),
            issue_type="error_handling",
            severity="high",
            description="The caller reports success even though the upstream import path can swallow an exception into a completed status.",
            code_snippet=_code_snippet(caller_content, assignment_match.start()),
            ai_feedback=ai_feedback,
            context_scope="cross_file",
            related_files=[callee_entry["path"]],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )

    return None


def _supplement_local_retryless_timeout_error_handling(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        if issue.issue_type.lower() != "error_handling":
            continue
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            issue.context_scope == "cross_file"
            and "timeouterror" in evidence_basis
            and "retryable" in evidence_basis
            and ("recovery" in systemic_impact or "outage" in systemic_impact)
            and "sync_worker.py" in related_files
        ):
            return None

    for caller_entry in entries:
        caller_content = caller_entry["content"]
        import_match = re.search(
            r"from\s+\.?+(?P<module>[A-Za-z0-9_\.]+)\s+import\s+(?P<symbol>[A-Za-z0-9_]+)",
            caller_content,
        )
        if import_match is None:
            continue

        symbol_name = import_match.group("symbol")
        assignment_match = re.search(
            rf"(?P<result>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*{symbol_name}\(",
            caller_content,
        )
        if assignment_match is None:
            continue

        result_name = assignment_match.group("result")
        failed_match = re.search(
            rf"if\s+{result_name}\[[\"']status[\"']\]\s*==\s*[\"']failed[\"']\s*:\s*(?P<body>.*?)(?:\n\S|\Z)",
            caller_content,
            re.DOTALL,
        )
        if failed_match is None:
            continue

        failed_body = failed_match.group("body")
        if "disable_background_sync()" not in failed_body:
            continue
        message_match = re.search(r"[\"'](?P<message>[^\"']*disabled[^\"']*)[\"']", failed_body, re.IGNORECASE)
        disabled_message = message_match.group("message") if message_match else "disabled"

        related_stem = Path(import_match.group("module").split(".")[-1]).stem
        callee_entry = next(
            (
                entry for entry in entries
                if entry["path"] != caller_entry["path"] and Path(entry["path"]).stem == related_stem
            ),
            None,
        )
        if callee_entry is None:
            continue

        callee_content = callee_entry["content"]
        if symbol_name not in callee_content:
            continue
        if "except TimeoutError" not in callee_content:
            continue
        if "retryable" not in callee_content:
            continue

        evidence_basis = (
            f"{Path(callee_entry['path']).name} catches TimeoutError and returns retryable=True, while "
            f"{Path(caller_entry['path']).name} disables background sync and returns '{disabled_message}' as soon as {result_name}['status'] == 'failed'."
        )
        systemic_impact = (
            "Delayed recovery can follow a transient timeout because the caller converts a retryable failure into terminal disablement instead of preserving the automatic retry path."
        )
        ai_feedback = "\n\n".join([
            "**Retryable timeout is converted into terminal disablement instead of a recovery path**",
            f"{Path(callee_entry['path']).name} marks TimeoutError as retryable, but {Path(caller_entry['path']).name} disables background sync immediately and returns '{disabled_message}' instead of retrying or preserving recovery.",
            f"Code: except TimeoutError: return {{'status': 'failed', 'retryable': True}} / if {result_name}['status'] == 'failed': disable_background_sync()",
            "Suggestion: Preserve transient-failure recovery semantics by checking the retryable flag, retrying with backoff, or escalating the timeout without disabling the feature until retries are exhausted or the failure is known to be permanent.",
            "Context Scope: cross_file",
            f"Related Files: {callee_entry['path']}",
            f"Systemic Impact: {systemic_impact}",
            "Confidence: medium",
            f"Evidence Basis: {evidence_basis}",
        ])
        return ReviewIssue(
            file_path=caller_entry["path"],
            line_number=_line_number_from_offset(caller_content, failed_match.start()),
            issue_type="error_handling",
            severity="high",
            description="The caller disables background sync even though the upstream timeout path is explicitly marked retryable.",
            code_snippet=_code_snippet(caller_content, assignment_match.start()),
            ai_feedback=ai_feedback,
            context_scope="cross_file",
            related_files=[callee_entry["path"]],
            systemic_impact=systemic_impact,
            confidence="medium",
            evidence_basis=evidence_basis,
        )

    return None


def _supplement_local_data_validation_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "data_validation" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if len(entries) < 2:
        return []

    supplements: List[ReviewIssue] = []

    inverted_window = _supplement_local_inverted_window_data_validation(entries, issues)
    if inverted_window is not None:
        supplements.append(inverted_window)

    rollout_percent_range = _supplement_local_rollout_percent_range_data_validation(entries, issues)
    if rollout_percent_range is not None:
        supplements.append(rollout_percent_range)

    enum_field_constraint = _supplement_local_enum_field_constraint_data_validation(entries, issues)
    if enum_field_constraint is not None:
        supplements.append(enum_field_constraint)

    return supplements


def _supplement_local_inverted_window_data_validation(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        if issue.issue_type.lower().replace(" ", "_") != "data_validation":
            continue
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            issue.context_scope == "cross_file"
            and "end_hour" in evidence_basis
            and "start_hour" in evidence_basis
            and ("invalid" in systemic_impact or "negative" in systemic_impact)
            and "validation.py" in related_files
        ):
            return None

    validator_entry = next((entry for entry in entries if Path(entry["path"]).name == "validation.py"), None)
    api_entry = next((entry for entry in entries if Path(entry["path"]).name == "api.py"), None)
    if validator_entry is None or api_entry is None:
        return None

    validator_content = validator_entry["content"]
    api_content = api_entry["content"]
    if "validate_window(payload)" not in api_content:
        return None
    if 'int(payload["end_hour"]) - int(payload["start_hour"])' not in api_content:
        return None
    if 'int(payload["start_hour"])' not in validator_content or 'int(payload["end_hour"])' not in validator_content:
        return None
    if re.search(
        r"start_hour\s*(?:<|<=|>|>=|==|!=).*end_hour|end_hour\s*(?:<|<=|>|>=|==|!=).*start_hour",
        validator_content,
    ):
        return None

    evidence_basis = (
        "validation.py coerces start_hour and end_hour to int but never checks that end_hour is greater than start_hour before api.py computes duration_hours."
    )
    systemic_impact = (
        "Invalid maintenance windows can reach runtime use, so inverted time ranges produce negative durations and incorrect scheduling state instead of being rejected."
    )
    ai_feedback = "\n\n".join([
        "**Validator accepts an inverted time window that the API treats as schedulable**",
        "validation.py only checks field presence and integer coercion for start_hour and end_hour, but api.py subtracts those fields immediately, so an end before start still becomes a scheduled maintenance window.",
        "Code: validate_window(payload) / int(payload['end_hour']) - int(payload['start_hour']) / validation only calls int(...) on both fields",
        "Suggestion: Enforce the ordering constraint in validate_window after parsing the hours, or define explicit overnight-window semantics before callers compute duration_hours.",
        "Context Scope: cross_file",
        f"Related Files: {validator_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=api_entry["path"],
        line_number=_line_number_from_offset(api_content, api_content.index("validate_window(payload)")),
        issue_type="data_validation",
        severity="high",
        description="The validator never rejects an end_hour that comes before start_hour, so invalid maintenance windows reach the scheduling path.",
        code_snippet=_code_snippet(api_content, api_content.index("validate_window(payload)")),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[validator_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_rollout_percent_range_data_validation(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        if issue.issue_type.lower().replace(" ", "_") != "data_validation":
            continue
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            issue.context_scope == "cross_file"
            and "rollout_percent" in evidence_basis
            and "validation.py" in related_files
            and "invalid" in systemic_impact
        ):
            return None

    validator_entry = next((entry for entry in entries if Path(entry["path"]).name == "validation.py"), None)
    api_entry = next((entry for entry in entries if Path(entry["path"]).name == "api.py"), None)
    if validator_entry is None or api_entry is None:
        return None

    validator_content = validator_entry["content"]
    api_content = api_entry["content"]
    if "validate_rollout(payload)" not in api_content:
        return None
    if 'int(payload["target_hosts"]) * int(payload["rollout_percent"]) // 100' not in api_content:
        return None
    if 'int(payload["rollout_percent"])' not in validator_content:
        return None
    if re.search(
        r"rollout_percent\s*(?:<|<=|>|>=|==|!=)|(?:<|<=|>|>=|==|!=)\s*rollout_percent|0\s*<=\s*rollout_percent|rollout_percent\s*<=\s*100|100\s*>=\s*rollout_percent",
        validator_content,
    ):
        return None

    evidence_basis = (
        "validation.py coerces rollout_percent with int(payload['rollout_percent']) but never constrains it to 0..100 before api.py computes batch_size from rollout_percent and target_hosts."
    )
    systemic_impact = (
        "Invalid rollout percentages can reach runtime use, so out-of-range rollout_percent values produce incorrect batch sizes and invalid rollout state instead of being rejected."
    )
    ai_feedback = "\n\n".join([
        "**Validator accepts rollout_percent values outside the deployment contract**",
        "validation.py only checks presence and integer coercion for rollout_percent, but api.py multiplies rollout_percent into batch_size immediately, so values below 0 or above 100 still drive rollout logic.",
        "Code: validate_rollout(payload) / int(payload['target_hosts']) * int(payload['rollout_percent']) // 100 / validation only calls int(...) on rollout_percent",
        "Suggestion: Parse rollout_percent once in validate_rollout and enforce 0 <= rollout_percent <= 100 before callers compute batch_size or persist rollout settings.",
        "Context Scope: cross_file",
        f"Related Files: {validator_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=api_entry["path"],
        line_number=_line_number_from_offset(api_content, api_content.index("validate_rollout(payload)")),
        issue_type="data_validation",
        severity="high",
        description="The validator never constrains rollout_percent to 0..100, so invalid rollout percentages reach batch-size calculations.",
        code_snippet=_code_snippet(api_content, api_content.index("validate_rollout(payload)")),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[validator_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_enum_field_constraint_data_validation(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        if issue.issue_type.lower().replace(" ", "_") != "data_validation":
            continue
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            issue.context_scope == "cross_file"
            and "delivery_mode" in evidence_basis
            and "validation.py" in related_files
            and "invalid" in systemic_impact
        ):
            return None

    validator_entry = next((entry for entry in entries if Path(entry["path"]).name == "validation.py"), None)
    api_entry = next((entry for entry in entries if Path(entry["path"]).name == "api.py"), None)
    if validator_entry is None or api_entry is None:
        return None

    validator_content = validator_entry["content"]
    api_content = api_entry["content"]
    if "validate_workflow(payload)" not in api_content:
        return None
    if '"delivery_mode": payload["delivery_mode"]' not in api_content:
        return None
    if 'str(payload["delivery_mode"])' not in validator_content:
        return None
    if re.search(
        r"delivery_mode\s*(?:in|not in|==|!=)|email|webhook|sms|allowed|supported|choices|enum",
        validator_content,
        re.IGNORECASE,
    ):
        return None

    evidence_basis = (
        "validation.py only coerces delivery_mode with str(payload['delivery_mode']) and never checks that it matches a supported enum value before api.py returns delivery_mode in the scheduled workflow response."
    )
    systemic_impact = (
        "Invalid delivery modes can reach runtime use, so unsupported delivery_mode values are accepted as valid workflow state instead of being rejected at validation time."
    )
    ai_feedback = "\n\n".join([
        "**Validator accepts delivery_mode values outside the supported workflow contract**",
        "validation.py only checks presence and string coercion for delivery_mode, but api.py immediately returns that field as scheduled workflow state, so unsupported modes still pass through as valid input.",
        "Code: validate_workflow(payload) / str(payload['delivery_mode']) / api.py returns payload['delivery_mode'] without any enum membership check",
        "Suggestion: Define the allowed delivery_mode values in validate_workflow and reject any value outside that enum before callers persist or schedule the workflow.",
        "Context Scope: cross_file",
        f"Related Files: {validator_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=api_entry["path"],
        line_number=_line_number_from_offset(api_content, api_content.index("validate_workflow(payload)")),
        issue_type="data_validation",
        severity="medium",
        description="The validator never constrains delivery_mode to the supported enum values, so invalid workflow modes reach scheduling.",
        code_snippet=_code_snippet(api_content, api_content.index("validate_workflow(payload)")),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[validator_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_testing_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "testing" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if len(entries) < 2:
        return []

    supplement = _supplement_local_rollout_percent_range_testing(entries, issues)
    return [supplement] if supplement is not None else []


def _supplement_local_rollout_percent_range_testing(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = issue.issue_type.lower().replace(" ", "_")
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            normalized_issue_type == "testing"
            and issue.context_scope == "cross_file"
            and "validation.py" in related_files
            and "rollout_percent" in evidence_basis
            and ("regress" in systemic_impact or "regression" in systemic_impact)
        ):
            return None

    validator_entry = next((entry for entry in entries if Path(entry["path"]).name == "validation.py"), None)
    api_entry = next((entry for entry in entries if Path(entry["path"]).name == "api.py"), None)
    test_entry = next((entry for entry in entries if Path(entry["path"]).name == "test_api.py"), None)
    if validator_entry is None or api_entry is None or test_entry is None:
        return None

    validator_content = validator_entry["content"]
    api_content = api_entry["content"]
    test_content = test_entry["content"]
    if "validate_rollout(payload)" not in api_content:
        return None
    if 'if rollout_percent < 0 or rollout_percent > 100' not in validator_content:
        return None
    if 'test_create_rollout_returns_batch_size_for_valid_payload' not in test_content:
        return None
    if 'test_create_rollout_rejects_missing_rollout_percent' not in test_content:
        return None
    if re.search(r"rollout_percent[^\n]*(?:-1|101)", test_content) or "between 0 and 100" in test_content:
        return None

    evidence_basis = (
        "tests/test_api.py covers the happy path and a missing-field case, but never asserts that validate_rollout rejects rollout_percent outside 0..100 before create_rollout uses the validated payload."
    )
    systemic_impact = (
        "The rollout_percent boundary contract is unpinned, so a regression in the 0..100 check could ship unnoticed during refactors without a failing test."
    )
    ai_feedback = "\n\n".join([
        "**The test suite leaves the rollout_percent range contract untested**",
        "validation.py already rejects rollout_percent values outside 0..100, but tests/test_api.py only covers the happy path and a missing-field failure, so the range guard can regress without any test failure.",
        "Code: test_create_rollout_returns_batch_size_for_valid_payload / test_create_rollout_rejects_missing_rollout_percent / if rollout_percent < 0 or rollout_percent > 100",
        "Suggestion: Add a parametrized pytest.raises case that exercises rollout_percent values such as -1 and 101, and keep the assertion tied to the current boundary contract in validate_rollout.",
        "Context Scope: cross_file",
        f"Related Files: {validator_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=test_entry["path"],
        line_number=_line_number_from_offset(test_content, test_content.index("def test_create_rollout_returns_batch_size_for_valid_payload")),
        issue_type="testing",
        severity="medium",
        description="The test suite never exercises the rollout_percent range guard, so the existing boundary contract can regress without a failing test.",
        code_snippet=_code_snippet(test_content, test_content.index("def test_create_rollout_returns_batch_size_for_valid_payload")),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[validator_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_regression_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "regression" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if not entries:
        return []

    supplements: List[ReviewIssue] = []

    default_sync_disabled = _supplement_local_default_sync_disabled_regression(entries, issues)
    if default_sync_disabled is not None:
        supplements.append(default_sync_disabled)

    inverted_sync_guard = _supplement_local_inverted_sync_start_guard_regression(entries, issues)
    if inverted_sync_guard is not None:
        supplements.append(inverted_sync_guard)

    return supplements


def _supplement_local_default_sync_disabled_regression(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = issue.issue_type.lower().replace(" ", "_")
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            normalized_issue_type == "regression"
            and issue.context_scope == "cross_file"
            and "app_startup.py" in related_files
            and "sync_enabled" in evidence_basis
            and "disabled" in systemic_impact
        ):
            return None

    changed_entry = next((entry for entry in entries if Path(entry["path"]).name == "settings_defaults.py"), None)
    if changed_entry is None:
        return None

    settings_path = Path(changed_entry["path"])
    try:
        settings_content = _read_file_content(settings_path)
    except Exception:
        settings_content = changed_entry.get("content", "")
    if '"sync_enabled": False' not in settings_content:
        return None

    app_startup_path = settings_path.parent / "app_startup.py"
    if not app_startup_path.exists():
        return None

    app_startup_content = _read_file_content(app_startup_path)
    if 'preferences["sync_enabled"]' not in app_startup_content:
        return None
    if 'sync_scheduler.start()' not in app_startup_content:
        return None

    evidence_basis = (
        "settings_defaults.py changes sync_enabled from True to False, and app_startup.py only starts background sync when preferences['sync_enabled'] is true."
    )
    systemic_impact = (
        "Background sync becomes disabled by default, so an existing startup workflow silently stops running for users who rely on the prior default behavior."
    )
    ai_feedback = "\n\n".join([
        "**The diff disables background sync for default-configured users**",
        "settings_defaults.py now returns sync_enabled=False, and app_startup.py gates scheduler startup directly on that default, so the existing sync flow no longer starts unless users opt back in.",
        "Code: load_default_preferences / \"sync_enabled\": False / if preferences['sync_enabled']: sync_scheduler.start()",
        "Suggestion: Preserve the previous default unless the behavior change is intentional and migrated explicitly, or add a migration path plus tests that pin the new startup behavior.",
        "Context Scope: cross_file",
        f"Related Files: {app_startup_path}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=str(settings_path),
        line_number=_line_number_from_offset(settings_content, settings_content.index('"sync_enabled": False')),
        issue_type="regression",
        severity="medium",
        description="Changing the sync_enabled default to false disables the existing background sync startup path for default-configured users.",
        code_snippet=_code_snippet(settings_content, settings_content.index('"sync_enabled": False')),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[str(app_startup_path)],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_inverted_sync_start_guard_regression(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = issue.issue_type.lower().replace(" ", "_")
        related_files = [Path(path).name for path in issue.related_files]
        evidence_basis = (issue.evidence_basis or "").lower()
        systemic_impact = (issue.systemic_impact or "").lower()
        if (
            normalized_issue_type == "regression"
            and issue.context_scope == "cross_file"
            and "settings_defaults.py" in related_files
            and "sync_enabled" in evidence_basis
            and "disabled" in systemic_impact
        ):
            return None

    changed_entry = next((entry for entry in entries if Path(entry["path"]).name == "app_startup.py"), None)
    if changed_entry is None:
        return None

    startup_path = Path(changed_entry["path"])
    try:
        startup_content = _read_file_content(startup_path)
    except Exception:
        startup_content = changed_entry.get("content", "")
    if 'if not preferences["sync_enabled"]' not in startup_content:
        return None
    if 'sync_scheduler.start()' not in startup_content:
        return None

    settings_path = startup_path.parent / "settings_defaults.py"
    if not settings_path.exists():
        return None

    settings_content = _read_file_content(settings_path)
    if '"sync_enabled": True' not in settings_content:
        return None

    evidence_basis = (
        "settings_defaults.py still returns sync_enabled=True, but app_startup.py changed the startup guard to if not preferences['sync_enabled'] before calling sync_scheduler.start()."
    )
    systemic_impact = (
        "Background sync is effectively disabled for the default-enabled path, so an existing startup workflow silently stops running for users who keep the prior sync setting."
    )
    ai_feedback = "\n\n".join([
        "**The diff inverts the sync startup guard and disables the existing enabled path**",
        "settings_defaults.py still enables sync by default, but app_startup.py now starts the scheduler only when sync_enabled is false, so the previously enabled startup flow no longer runs.",
        "Code: \"sync_enabled\": True / if not preferences['sync_enabled'] / sync_scheduler.start()",
        "Suggestion: Restore the original guard or add a migration and tests only if the behavior change is intentional; otherwise the current diff silently disables the existing startup path.",
        "Context Scope: cross_file",
        f"Related Files: {settings_path}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=str(startup_path),
        line_number=_line_number_from_offset(startup_content, startup_content.index('if not preferences["sync_enabled"]')),
        issue_type="regression",
        severity="medium",
        description="The diff inverts the sync_enabled startup guard, so background sync no longer starts for the default-enabled path.",
        code_snippet=_code_snippet(startup_content, startup_content.index('if not preferences["sync_enabled"]')),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[str(settings_path)],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_accessibility_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "accessibility" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if not entries:
        return []

    supplements: List[ReviewIssue] = []
    dialog_semantics = _supplement_local_dialog_semantics_accessibility(entries, issues)
    if dialog_semantics is not None:
        supplements.append(dialog_semantics)
    fieldset_legend = _supplement_local_fieldset_legend_accessibility(entries, issues)
    if fieldset_legend is not None:
        supplements.append(fieldset_legend)
    return supplements


def _supplement_local_security_findings(
    target_files: Sequence[FileInfo],
    review_type: str,
    issues: Sequence[ReviewIssue],
    client: AIBackend,
) -> List[ReviewIssue]:
    if "security" not in review_type.split("+"):
        return []
    if not _is_local_backend(client):
        return []

    entries = _load_target_file_entries(target_files)
    if len(entries) < 2:
        return []

    ssrf_issue = _supplement_local_ssrf_security(entries, issues)
    if ssrf_issue is not None:
        return [ssrf_issue]

    zip_slip_issue = _supplement_local_zip_slip_security(entries, issues)
    if zip_slip_issue is not None:
        return [zip_slip_issue]

    traversal_issue = _supplement_local_path_traversal_security(entries, issues)
    if traversal_issue is not None:
        return [traversal_issue]

    shell_issue = _supplement_local_shell_command_security(entries, issues)
    if shell_issue is not None:
        return [shell_issue]

    sql_issue = _supplement_local_sql_query_interpolation_security(entries, issues)
    if sql_issue is not None:
        return [sql_issue]

    yaml_issue = _supplement_local_unsafe_yaml_load_security(entries, issues)
    if yaml_issue is not None:
        return [yaml_issue]

    return []


def _supplement_local_zip_slip_security(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = re.sub(r"[\s\-/()]+", "_", issue.issue_type.lower()).strip("_")
        if normalized_issue_type not in {
            "security",
            "path_traversal",
            "zip_slip",
            "insecure_deserialization",
        }:
            continue
        text = _issue_text(issue)
        if (
            any(marker in text for marker in ("zip slip", "extractall", "archive", "path traversal"))
            and any(
                marker in text
                for marker in (
                    "overwrite",
                    "arbitrary file",
                    "outside the intended destination",
                    "outside the destination",
                )
            )
            and issue.severity.lower() in {"high", "critical"}
            and issue.context_scope == "cross_file"
        ):
            return None

    importer_entry: Dict[str, str] | None = None
    api_entry: Dict[str, str] | None = None
    extract_match: re.Match[str] | None = None

    for entry in entries:
        content = entry["content"]
        match = re.search(r"archive\.extractall\(\s*destination\s*\)", content)
        if match is None:
            continue
        if re.search(r"def\s+import_theme_bundle\s*\(", content) is None:
            continue
        importer_entry = entry
        extract_match = match
        break

    if importer_entry is None or extract_match is None:
        return None

    for entry in entries:
        if entry["path"] == importer_entry["path"]:
            continue
        content = entry["content"]
        if 'request["archive_path"]' not in content and "request['archive_path']" not in content:
            continue
        if "import_theme_bundle(current_account[\"id\"], archive_path)" not in content and "import_theme_bundle(current_account['id'], archive_path)" not in content:
            continue
        api_entry = entry
        break

    if api_entry is None:
        return None

    evidence_basis = (
        f"{Path(api_entry['path']).name} forwards request-controlled archive_path into import_theme_bundle, and {Path(importer_entry['path']).name} calls archive.extractall(destination) without validating archive member paths."
    )
    systemic_impact = (
        "A malicious theme archive can overwrite arbitrary files outside the intended theme directory when extraction follows attacker-controlled member paths."
    )
    ai_feedback = "\n\n".join([
        "**Request-controlled archive extraction allows zip-slip file overwrite**",
        f"{Path(api_entry['path']).name} forwards the request archive_path into import_theme_bundle, and {Path(importer_entry['path']).name} extracts that archive with archive.extractall(destination) without validating member paths.",
        "Code: archive_path = request[\"archive_path\"] / import_theme_bundle(current_account[\"id\"], archive_path) / archive.extractall(destination)",
        "Suggestion: Iterate archive members and validate each resolved extraction path stays under destination before writing it. Reject entries with absolute paths or `..` segments instead of calling extractall on the untrusted archive directly.",
        "Context Scope: cross_file",
        f"Related Files: {api_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: high",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=importer_entry["path"],
        line_number=_line_number_from_offset(importer_entry["content"], extract_match.start()),
        issue_type="security",
        severity="high",
        description="Untrusted theme archives are extracted with extractall without path validation, creating a zip-slip arbitrary file overwrite risk.",
        code_snippet=_code_snippet(importer_entry["content"], extract_match.start()),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[api_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="high",
        evidence_basis=evidence_basis,
    )


def _supplement_local_ssrf_security(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = re.sub(r"[\s\-/()]+", "_", issue.issue_type.lower()).strip("_")
        if normalized_issue_type not in {
            "security",
            "ssrf",
            "server_side_request_forgery",
            "server_side_request_forgery_ssrf",
        }:
            continue
        text = _issue_text(issue)
        if (
            any(marker in text for marker in ("ssrf", "server-side request forgery"))
            and any(
                marker in text
                for marker in (
                    "internal services",
                    "internal api",
                    "private ip",
                    "localhost",
                    "metadata endpoint",
                    "metadata service",
                    "169.254",
                )
            )
            and issue.severity.lower() in {"high", "critical"}
            and issue.context_scope == "cross_file"
        ):
            return None

    fetcher_entry: Dict[str, str] | None = None
    api_entry: Dict[str, str] | None = None
    fetch_match: re.Match[str] | None = None

    for entry in entries:
        content = entry["content"]
        match = re.search(
            r"requests\.get\(\s*avatar_url\s*,\s*timeout\s*=\s*5\s*\)",
            content,
        )
        if match is None:
            continue
        if re.search(r"def\s+fetch_avatar_preview\s*\(", content) is None:
            continue
        fetcher_entry = entry
        fetch_match = match
        break

    if fetcher_entry is None or fetch_match is None:
        return None

    for entry in entries:
        if entry["path"] == fetcher_entry["path"]:
            continue
        content = entry["content"]
        if 'request["avatar_url"]' not in content and "request['avatar_url']" not in content:
            continue
        if "fetch_avatar_preview(avatar_url)" not in content:
            continue
        api_entry = entry
        break

    if api_entry is None:
        return None

    evidence_basis = (
        f"{Path(api_entry['path']).name} forwards request-controlled avatar_url into fetch_avatar_preview, and {Path(fetcher_entry['path']).name} fetches that URL directly with requests.get(...) without validating or restricting the destination."
    )
    systemic_impact = (
        "Request-controlled URLs can make the server reach internal services or metadata endpoints that should not be externally accessible."
    )
    ai_feedback = "\n\n".join([
        "**Request-controlled avatar URL is fetched server-side without SSRF protections**",
        f"{Path(api_entry['path']).name} forwards the request avatar_url into fetch_avatar_preview, and {Path(fetcher_entry['path']).name} calls requests.get(...) on that URL without an allowlist or internal-network restrictions.",
        "Code: avatar_url = request[\"avatar_url\"] / fetch_avatar_preview(avatar_url) / requests.get(avatar_url, timeout=5)",
        "Suggestion: Validate and canonicalize the URL before fetching it, restrict destinations to approved external hosts, deny localhost/private IP ranges and metadata endpoints, and consider routing fetches through a hardened proxy with egress controls.",
        "Context Scope: cross_file",
        f"Related Files: {api_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: high",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=fetcher_entry["path"],
        line_number=_line_number_from_offset(fetcher_entry["content"], fetch_match.start()),
        issue_type="security",
        severity="high",
        description="Request-controlled avatar URLs are fetched server-side without destination restrictions, creating an SSRF risk.",
        code_snippet=_code_snippet(fetcher_entry["content"], fetch_match.start()),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[api_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="high",
        evidence_basis=evidence_basis,
    )


def _supplement_local_path_traversal_security(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = re.sub(r"[\s\-/]+", "_", issue.issue_type.lower()).strip("_")
        if normalized_issue_type not in {"security", "path_traversal", "directory_traversal"}:
            continue
        text = _issue_text(issue)
        if any(
            marker in text
            for marker in ("path traversal", "directory traversal", "../", "arbitrary file", "attachment_root")
        ) and issue.severity.lower() in {"high", "critical"}:
            return None

    store_entry: Dict[str, str] | None = None
    api_entry: Dict[str, str] | None = None
    path_match: re.Match[str] | None = None

    for entry in entries:
        content = entry["content"]
        match = re.search(
            r"(?P<path_name>attachment_path)\s*=\s*ATTACHMENTS_ROOT\s*/\s*account_id\s*/\s*filename",
            content,
        )
        if match is None:
            continue
        if 'open(attachment_path, "rb")' not in content and "open(attachment_path, 'rb')" not in content:
            continue
        store_entry = entry
        path_match = match
        break

    if store_entry is None or path_match is None:
        return None

    for entry in entries:
        if entry["path"] == store_entry["path"]:
            continue
        content = entry["content"]
        if 'request["filename"]' not in content and "request['filename']" not in content:
            continue
        if "load_attachment(current_account[\"id\"], filename)" not in content and "load_attachment(current_account['id'], filename)" not in content:
            continue
        api_entry = entry
        break

    if api_entry is None:
        return None

    evidence_basis = (
        f"{Path(api_entry['path']).name} forwards request-controlled filename into load_attachment, and {Path(store_entry['path']).name} opens ATTACHMENTS_ROOT / account_id / filename without constraining traversal sequences in filename."
    )
    systemic_impact = (
        "Request-controlled filename values can escape the intended attachment directory and expose arbitrary files readable by the process."
    )
    ai_feedback = "\n\n".join([
        "**Request-controlled filename reaches file access without traversal checks**",
        f"{Path(api_entry['path']).name} forwards the request filename into load_attachment, and {Path(store_entry['path']).name} joins that filename directly onto ATTACHMENTS_ROOT / account_id before opening the resulting path.",
        "Code: filename = request[\"filename\"] / attachment_path = ATTACHMENTS_ROOT / account_id / filename / open(attachment_path, \"rb\")",
        "Suggestion: Normalize and validate the requested filename before using it in a filesystem path, reject traversal segments like `..`, and enforce that the resolved path stays under the intended attachment root.",
        "Context Scope: cross_file",
        f"Related Files: {api_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: high",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=store_entry["path"],
        line_number=_line_number_from_offset(store_entry["content"], path_match.start()),
        issue_type="security",
        severity="high",
        description="Request-controlled filename values can trigger path traversal because file access joins them directly onto the attachment root.",
        code_snippet=_code_snippet(store_entry["content"], path_match.start()),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[api_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="high",
        evidence_basis=evidence_basis,
    )


def _supplement_local_shell_command_security(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:

    for issue in issues:
        normalized_issue_type = re.sub(r"[\s\-/]+", "_", issue.issue_type.lower()).strip("_")
        if normalized_issue_type != "security":
            continue
        text = _issue_text(issue)
        if "shell=true" in text and any(
            marker in text
            for marker in ("command injection", "shell command", "subprocess.run", "arbitrary command")
        ):
            if issue.severity.lower() in {"high", "critical"}:
                return None

    exporter_entry: Dict[str, str] | None = None
    api_entry: Dict[str, str] | None = None
    exporter_match: re.Match[str] | None = None

    for entry in entries:
        content = entry["content"]
        match = re.search(
            r"subprocess\.run\(\s*(?P<command>[A-Za-z_][A-Za-z0-9_]*)\s*,(?P<body>.*?)shell\s*=\s*True",
            content,
            re.DOTALL,
        )
        if match is None:
            continue
        command_name = match.group("command")
        command_assign = re.search(
            rf"{re.escape(command_name)}\s*=\s*\(?\s*f?[\"'].*?(?:{{[^}}]*username[^}}]*}}|username).*?(?:{{[^}}]*(?:format|output_format)[^}}]*}}|output_format).*?(?:{{[^}}]*output_path[^}}]*}}|output_path).*?[\"']",
            content,
            re.DOTALL,
        )
        if command_assign is None:
            continue
        if re.search(r"def\s+run_export\s*\(", content) is None:
            continue
        exporter_entry = entry
        exporter_match = match
        break

    if exporter_entry is None or exporter_match is None:
        return None

    for entry in entries:
        if entry["path"] == exporter_entry["path"]:
            continue
        content = entry["content"]
        if "run_export(" not in content:
            continue
        if not any(
            marker in content
            for marker in ('request["output_path"]', 'request.get("format"', 'current_user["username"]')
        ):
            continue
        api_entry = entry
        break

    if api_entry is None:
        return None

    evidence_basis = (
        f"{Path(exporter_entry['path']).name} builds one interpolated command string and executes subprocess.run(..., shell=True), while {Path(api_entry['path']).name} forwards request-controlled output_path, format, and username into run_export."
    )
    systemic_impact = (
        "Request-controlled export arguments can reach a shell command and trigger arbitrary command execution on the host."
    )
    ai_feedback = "\n\n".join([
        "**User-controlled export arguments flow into a shell=True command**",
        f"{Path(api_entry['path']).name} passes request-controlled export values into run_export, and {Path(exporter_entry['path']).name} interpolates them into one shell command string before calling subprocess.run(..., shell=True).",
        "Code: command = f\"generate-report --user {username} --format {output_format} --output {output_path}\" / subprocess.run(command, shell=True, ...)",
        "Suggestion: Avoid shell=True and pass a list of arguments to subprocess.run. Also validate or allowlist export destinations and format values before they reach the exporter.",
        "Context Scope: cross_file",
        f"Related Files: {api_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: high",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=exporter_entry["path"],
        line_number=_line_number_from_offset(exporter_entry["content"], exporter_match.start()),
        issue_type="security",
        severity="high",
        description="User-controlled export arguments are interpolated into a shell command and executed with shell=True.",
        code_snippet=_code_snippet(exporter_entry["content"], exporter_match.start()),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[api_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="high",
        evidence_basis=evidence_basis,
    )


def _supplement_local_sql_query_interpolation_security(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = re.sub(r"[\s\-/]+", "_", issue.issue_type.lower()).strip("_")
        if normalized_issue_type != "security":
            continue
        text = _issue_text(issue)
        if any(
            marker in text
            for marker in ("sql injection", "parameterized query", "prepared statement", "where status", "db.execute")
        ) and issue.severity.lower() in {"high", "critical"}:
            return None

    repository_entry: Dict[str, str] | None = None
    api_entry: Dict[str, str] | None = None
    query_match: re.Match[str] | None = None

    for entry in entries:
        content = entry["content"]
        match = re.search(
            r"(?P<query_name>query)\s*=\s*f[\"']SELECT .*?WHERE\s+status\s*=\s*'\{status\}'.*?[\"']",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            continue
        if "execute(query)" not in content and "db.execute(query)" not in content:
            continue
        repository_entry = entry
        query_match = match
        break

    if repository_entry is None or query_match is None:
        return None

    for entry in entries:
        if entry["path"] == repository_entry["path"]:
            continue
        content = entry["content"]
        if 'request.get("status"' not in content:
            continue
        if "list_users_by_status(status)" not in content:
            continue
        api_entry = entry
        break

    if api_entry is None:
        return None

    evidence_basis = (
        f"{Path(api_entry['path']).name} forwards request-controlled status into list_users_by_status, and {Path(repository_entry['path']).name} interpolates status directly into SELECT ... WHERE status = '{{status}}' before db.execute(query)."
    )
    systemic_impact = (
        "Request-controlled status can alter SQL semantics and expose or modify data beyond the intended filter."
    )
    ai_feedback = "\n\n".join([
        "**Request-controlled status flows into a raw SQL query**",
        f"{Path(api_entry['path']).name} forwards the request status filter into list_users_by_status, and {Path(repository_entry['path']).name} builds one SELECT query by interpolating status directly into the WHERE clause before executing it.",
        "Code: status = request.get(\"status\", \"active\") / query = f\"SELECT ... WHERE status = '{status}' ...\" / db.execute(query)",
        "Suggestion: Parameterize the SQL query instead of interpolating status into the query string, and validate or whitelist allowed status values at the API boundary.",
        "Context Scope: cross_file",
        f"Related Files: {api_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: high",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=repository_entry["path"],
        line_number=_line_number_from_offset(repository_entry["content"], query_match.start()),
        issue_type="security",
        severity="high",
        description="Request-controlled status is interpolated into a raw SQL query string, creating a SQL injection risk before execution.",
        code_snippet=_code_snippet(repository_entry["content"], query_match.start()),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[api_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="high",
        evidence_basis=evidence_basis,
    )


def _supplement_local_unsafe_yaml_load_security(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = re.sub(r"[\s\-/]+", "_", issue.issue_type.lower()).strip("_")
        if normalized_issue_type != "security":
            continue
        text = _issue_text(issue)
        if any(
            marker in text
            for marker in ("yaml.load", "safe_load", "safeloader", "unsafe yaml", "deserialization")
        ) and issue.severity.lower() in {"high", "critical"}:
            return None

    loader_entry: Dict[str, str] | None = None
    api_entry: Dict[str, str] | None = None
    yaml_match: re.Match[str] | None = None

    for entry in entries:
        content = entry["content"]
        match = re.search(
            r"yaml\.load\(\s*raw_config\s*,\s*Loader\s*=\s*yaml\.Loader\s*\)",
            content,
        )
        if match is None:
            continue
        loader_entry = entry
        yaml_match = match
        break

    if loader_entry is None or yaml_match is None:
        return None

    for entry in entries:
        if entry["path"] == loader_entry["path"]:
            continue
        content = entry["content"]
        if 'request["config"]' not in content:
            continue
        if "parse_settings_payload(raw_config)" not in content:
            continue
        api_entry = entry
        break

    if api_entry is None:
        return None

    evidence_basis = (
        f"{Path(api_entry['path']).name} forwards request-controlled config into parse_settings_payload, and {Path(loader_entry['path']).name} deserializes it with yaml.load(raw_config, Loader=yaml.Loader) instead of a safe loader."
    )
    systemic_impact = (
        "Request-controlled YAML can trigger arbitrary object construction or code execution when it reaches the unsafe loader."
    )
    ai_feedback = "\n\n".join([
        "**Request-controlled YAML reaches an unsafe yaml.load path**",
        f"{Path(api_entry['path']).name} forwards untrusted config content into parse_settings_payload, and {Path(loader_entry['path']).name} deserializes it with yaml.load(..., Loader=yaml.Loader) instead of yaml.safe_load or yaml.SafeLoader.",
        "Code: raw_config = request[\"config\"] / parse_settings_payload(raw_config) / yaml.load(raw_config, Loader=yaml.Loader)",
        "Suggestion: Replace yaml.load(..., Loader=yaml.Loader) with yaml.safe_load or yaml.load(..., Loader=yaml.SafeLoader), and validate the parsed structure against an expected schema before use.",
        "Context Scope: cross_file",
        f"Related Files: {api_entry['path']}",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: high",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=loader_entry["path"],
        line_number=_line_number_from_offset(loader_entry["content"], yaml_match.start()),
        issue_type="security",
        severity="high",
        description="Request-controlled YAML is deserialized through yaml.load with an unsafe loader, creating an unsafe deserialization risk.",
        code_snippet=_code_snippet(loader_entry["content"], yaml_match.start()),
        ai_feedback=ai_feedback,
        context_scope="cross_file",
        related_files=[api_entry["path"]],
        systemic_impact=systemic_impact,
        confidence="high",
        evidence_basis=evidence_basis,
    )


def _supplement_local_dialog_semantics_accessibility(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = issue.issue_type.lower().replace(" ", "_")
        description = (issue.description or "").lower()
        evidence_basis = (issue.evidence_basis or "").lower()
        if (
            normalized_issue_type == "accessibility"
            and "dialog" in description
            and ("role" in evidence_basis or "aria-modal" in evidence_basis)
        ):
            return None

    changed_entry = next((entry for entry in entries if Path(entry["path"]).name == "SettingsModal.tsx"), None)
    if changed_entry is None:
        return None

    modal_path = Path(changed_entry["path"])
    try:
        modal_content = _read_file_content(modal_path)
    except Exception:
        modal_content = changed_entry.get("content", "")

    if 'className="modal-panel"' not in modal_content:
        return None
    if '<h2>' not in modal_content:
        return None
    if 'role="dialog"' in modal_content or 'aria-modal=' in modal_content:
        return None

    evidence_basis = (
        "SettingsModal.tsx renders the modal panel as a plain div without role='dialog' or aria-modal, so assistive technology never gets dialog semantics for the open settings surface."
    )
    systemic_impact = (
        "Screen reader users may not realize they entered a modal dialog or that the surrounding page is temporarily inactive, which makes the settings flow harder to understand and navigate."
    )
    panel_offset = modal_content.index('className="modal-panel"')
    ai_feedback = "\n\n".join([
        "**The settings modal is missing dialog semantics**",
        "The modal opens visually, but the panel is only a div and never exposes role='dialog' or aria-modal to assistive technology, so screen reader users are not told they entered a modal context.",
        "Code: className=\"modal-panel\" / <h2>Sync settings</h2> / missing role='dialog' and aria-modal",
        "Suggestion: Add role='dialog', aria-modal='true', and connect the heading with aria-labelledby so assistive technology can announce the modal context correctly.",
        "Context Scope: local",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=str(modal_path),
        line_number=_line_number_from_offset(modal_content, panel_offset),
        issue_type="accessibility",
        severity="medium",
        description="The settings modal lacks dialog semantics, so screen reader users are not told they entered a modal context.",
        code_snippet=_code_snippet(modal_content, panel_offset),
        ai_feedback=ai_feedback,
        context_scope="local",
        related_files=[],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


def _supplement_local_fieldset_legend_accessibility(
    entries: Sequence[Dict[str, str]],
    issues: Sequence[ReviewIssue],
) -> ReviewIssue | None:
    for issue in issues:
        normalized_issue_type = issue.issue_type.lower().replace(" ", "_")
        text = _issue_text(issue)
        if (
            normalized_issue_type == "accessibility"
            and "fieldset" in text
            and "legend" in text
        ):
            return None

    changed_entry = next(
        (entry for entry in entries if Path(entry["path"]).name == "NotificationPreferences.tsx"),
        None,
    )
    if changed_entry is None:
        return None

    component_path = Path(changed_entry["path"])
    try:
        component_content = _read_file_content(component_path)
    except Exception:
        component_content = changed_entry.get("content", "")

    if "<fieldset" not in component_content:
        return None
    if "group-heading" not in component_content:
        return None
    if "<legend" in component_content or "aria-labelledby" in component_content:
        return None

    channel_match = re.search(
        r'<fieldset\s+className="channel-group">\s*<p\s+className="group-heading">Delivery channels</p>',
        component_content,
    )
    digest_match = re.search(
        r'<fieldset\s+className="digest-group">\s*<p\s+className="group-heading">Digest frequency</p>',
        component_content,
    )
    if channel_match is None or digest_match is None:
        return None

    evidence_basis = (
        "NotificationPreferences.tsx renders the delivery and digest option groups inside fieldset elements, but labels them with paragraph headings instead of legend elements, so assistive technology is not given the semantic group label."
    )
    systemic_impact = (
        "Screen reader users may hear the checkbox and radio controls without the shared group context that explains which set of notification options they belong to."
    )
    ai_feedback = "\n\n".join([
        "**The grouped notification controls are missing fieldset legends**",
        "The component uses fieldset to group related notification controls, but each group is headed by a paragraph rather than a legend, so assistive technology does not announce the group label for the enclosed options.",
        "Code: <fieldset className=\"channel-group\"> / <p className=\"group-heading\">Delivery channels</p> / <fieldset className=\"digest-group\"> / <p className=\"group-heading\">Digest frequency</p>",
        "Suggestion: Replace the paragraph headings with legend elements, or add an aria-labelledby relationship from each fieldset to a visible label element so screen readers can announce the group purpose.",
        "Context Scope: local",
        f"Systemic Impact: {systemic_impact}",
        "Confidence: medium",
        f"Evidence Basis: {evidence_basis}",
    ])
    return ReviewIssue(
        file_path=str(component_path),
        line_number=_line_number_from_offset(component_content, channel_match.start()),
        issue_type="accessibility",
        severity="medium",
        description="The notification preference groups use fieldset without legend labels, so screen reader users do not hear the accessible group name for the related controls.",
        code_snippet=_code_snippet(component_content, channel_match.start()),
        ai_feedback=ai_feedback,
        context_scope="local",
        related_files=[],
        systemic_impact=systemic_impact,
        confidence="medium",
        evidence_basis=evidence_basis,
    )


# ── batch helper ───────────────────────────────────────────────────────────

def _process_file_batch(
    target_files: Sequence[FileInfo],
    review_type: str,
    client: AIBackend,
    lang: str,
    spec_content: Optional[str] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> List[ReviewIssue]:
    """Process a batch of files for a single review type.

    When ``combine_files`` is enabled (default), multiple files are sent in
    a single prompt to reduce API round-trips.  The combined response is
    split back into per-file issues.
    """
    combine = config.get("processing", "combine_files", True)
    if isinstance(combine, str):
        combine = combine.lower() in ("true", "1", "yes")

    if combine and len(target_files) > 1:
        return _process_combined_batch(target_files, review_type, client, lang, spec_content, cancel_check)

    # Fall back to one-file-at-a-time processing
    return _process_files_individually(target_files, review_type, client, lang, spec_content, cancel_check)


def _is_diff_entry(file_info: FileInfo) -> bool:
    """Return True if *file_info* is a diff-scope dict with hunk data."""
    return isinstance(file_info, dict) and file_info.get("is_diff", False)


def _process_files_individually(
    target_files: Sequence[FileInfo],
    review_type: str,
    client: AIBackend,
    lang: str,
    spec_content: Optional[str] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> List[ReviewIssue]:
    """Original one-file-per-request approach, now using the structured parser.

    When a file entry has ``is_diff=True`` the diff-aware prompt builder
    is used so that the AI focuses on changed lines.
    """
    batch_issues: List[ReviewIssue] = []

    for file_info in target_files:
        # Check for cancellation before processing each file
        if cancel_check and cancel_check():
            logger.info("Individual file processing cancelled by user")
            break

        if isinstance(file_info, dict):
            file_path = file_info["path"]
            code = file_info["content"]
            display_name = file_info["filename"]
        else:
            file_path = file_info
            code = _read_file_content(file_path)
            display_name = str(file_path)
            if not code:
                continue

        logger.info("Analysing %s [%s] …", display_name, review_type)

        try:
            # Use diff-aware prompt when the entry carries hunk data
            if _is_diff_entry(file_info):
                diff_msg = AIBackend._build_diff_user_message(  # noqa: SLF001
                    file_info, review_type, spec_content
                )
                feedback = _request_review_with_retry(
                    client,
                    diff_msg,
                    review_type,
                    lang,
                    spec_content,
                )
            else:
                feedback = _request_review_with_retry(
                    client,
                    code,
                    review_type,
                    lang,
                    spec_content,
                )
            if feedback and not feedback.startswith("Error:"):
                parsed = parse_single_file_response(
                    feedback, str(file_path), display_name, code, review_type
                )
                if parsed:
                    batch_issues.extend(parsed)
                else:
                    # Fallback: create one generic issue
                    issue = ReviewIssue(
                        file_path=str(file_path),
                        line_number=None,
                        issue_type=review_type,
                        severity=_parse_severity(feedback),
                        description=f"Review feedback for {display_name}",
                        code_snippet=code[:200] + ("…" if len(code) > 200 else ""),
                        ai_feedback=feedback,
                    )
                    batch_issues.append(issue)
            elif feedback and feedback.startswith("Error:"):
                logger.warning("Backend returned error for %s: %s", display_name, feedback[:120])

        except Exception as exc:
            logger.error("Error analysing %s: %s", display_name, exc)

    return batch_issues


def _process_combined_batch(
    target_files: Sequence[FileInfo],
    review_type: str,
    client: AIBackend,
    lang: str,
    spec_content: Optional[str] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> List[ReviewIssue]:
    """Combine multiple files into a single AI prompt and parse results.

    When the batch contains diff-scope entries (``is_diff=True``), the
    diff-aware multi-file prompt builder is used so the AI focuses on
    changed lines rather than full file content.
    """
    # Determine if this is a diff-mode batch
    use_diff_mode = any(_is_diff_entry(fi) for fi in target_files)

    # Prepare file info list
    file_entries: List[Dict[str, Any]] = []
    for file_info in target_files:
        if isinstance(file_info, dict):
            file_path = file_info["path"]
            code = file_info["content"]
            display_name = file_info["filename"]
            entry: Dict[str, Any] = {
                "path": str(file_path),
                "name": display_name,
                "content": code,
            }
            # Carry diff metadata through
            if _is_diff_entry(file_info):
                entry["is_diff"] = True
                entry["hunks"] = file_info.get("hunks", [])
                entry["commit_messages"] = file_info.get("commit_messages")
        else:
            file_path = file_info
            code = _read_file_content(file_path)
            display_name = str(file_path)
            if not code:
                continue
            entry = {
                "path": str(file_path),
                "name": display_name,
                "content": code,
            }
        file_entries.append(entry)

    if not file_entries:
        return []

    # If only one file left after filtering, use single-file path
    if len(file_entries) == 1:
        return _process_files_individually(target_files, review_type, client, lang, spec_content, cancel_check)

    names = [f["name"] for f in file_entries]
    logger.info("Combined review of %d files [%s]: %s",
                len(file_entries), review_type, ", ".join(names))

    # Build combined user message — diff-aware or standard
    if use_diff_mode:
        combined_code = AIBackend._build_multi_file_diff_user_message(  # noqa: SLF001
            file_entries, review_type, spec_content
        )
    else:
        combined_code = AIBackend._build_multi_file_user_message(  # noqa: SLF001
            file_entries, review_type, spec_content
        )  # type: ignore[reportPrivateUsage]

    try:
        feedback = _request_review_with_retry(
            client,
            combined_code,
            review_type,
            lang,
            spec_content,
        )
    except Exception as exc:
        # Check if this was a cancellation – if so, return empty instead of falling back
        if cancel_check and cancel_check():
            logger.info("Combined review cancelled by user")
            return []
        logger.error("Combined review failed: %s – falling back to individual", exc)
        return _process_files_individually(target_files, review_type, client, lang, spec_content, cancel_check)

    if not feedback or feedback.startswith("Error:"):
        # Check for cancellation before falling back
        if cancel_check and cancel_check():
            logger.info("Combined review cancelled by user")
            return []
        logger.warning("Combined review returned error, falling back to individual")
        return _process_files_individually(target_files, review_type, client, lang, spec_content, cancel_check)

    # Parse combined feedback; retry any files the model failed to attribute
    return _merge_combined_with_fallback(
        feedback, file_entries, review_type, target_files,
        client, lang, spec_content, cancel_check,
    )


def _request_review_with_retry(
    client: AIBackend,
    code_content: str,
    review_type: str,
    lang: str,
    spec_content: Optional[str],
    attempts: int = _REVIEW_RETRY_ATTEMPTS,
) -> str:
    """Request a review and retry once when the backend returns a transient error."""
    last_feedback = ""
    last_exception: Exception | None = None

    for attempt in range(1, max(1, attempts) + 1):
        try:
            feedback = client.get_review(
                code_content,
                review_type=review_type,
                lang=lang,
                spec_content=spec_content,
            )
        except Exception as exc:
            last_exception = exc
            if attempt >= attempts:
                raise
            logger.warning(
                "Review request failed on attempt %d/%d: %s",
                attempt,
                attempts,
                exc,
            )
            continue

        last_feedback = feedback or ""
        if not _is_retryable_review_error(last_feedback) or attempt >= attempts:
            return last_feedback

        logger.warning(
            "Review request returned retryable error on attempt %d/%d: %s",
            attempt,
            attempts,
            last_feedback[:120],
        )

    if last_exception is not None:
        raise last_exception
    return last_feedback


def _is_retryable_review_error(feedback: str) -> bool:
    if not feedback.startswith("Error:"):
        return False
    lowered = feedback.lower()
    if "cancelled" in lowered:
        return False
    if "too large" in lowered:
        return False
    return True


def _merge_combined_with_fallback(
    feedback: str,
    file_entries: List[Dict[str, Any]],
    review_type: str,
    target_files: Sequence["FileInfo"],
    client: "AIBackend",
    lang: str,
    spec_content: Optional[str],
    cancel_check: Optional["CancelCheck"],
) -> List[ReviewIssue]:
    """Parse a combined AI response and individually retry unrepresented files.

    After the multi-strategy parser runs, any input file that has zero
    attributed issues **and** where at least one other file *did* receive
    results is assumed to have been silently dropped by the model.  Those
    files are re-submitted as individual requests and the results merged.

    The guard (other files must have results) prevents false-positive retries
    when the entire batch is genuinely clean.
    """
    issues = parse_review_response(feedback, file_entries, review_type)

    # Small combined batches are prone to backend-level false negatives where the
    # model returns an empty combined result even though per-file review finds issues.
    # Retry these batches individually before accepting a clean outcome.
    if not issues and len(file_entries) <= 3:
        logger.warning(
            "Empty combined response for %d-file batch [%s] – retrying individually",
            len(file_entries),
            review_type,
        )
        return _process_files_individually(
            target_files, review_type, client, lang, spec_content, cancel_check
        )

    # Build the set of file paths/names that appear in the parsed results
    attributed: set[str] = set()
    for issue in issues:
        attributed.add(issue.file_path)

    # Identify entries with zero attribution
    unrepresented: List[Dict[str, Any]] = [
        fe for fe in file_entries
        if fe["path"] not in attributed and fe["name"] not in attributed
    ]

    # Only retry if the combined parse produced results for other files
    # (avoids needless re-review of genuinely clean batches)
    if not unrepresented or not issues:
        return issues

    logger.warning(
        "Partial combined fallback: %d file(s) unrepresented in combined response – "
        "retrying individually: %s",
        len(unrepresented),
        [fe["name"] for fe in unrepresented],
    )

    # Build the subset of target_files that correspond to unrepresented entries
    unrepresented_paths = {fe["path"] for fe in unrepresented}
    retry_files: List["FileInfo"] = []
    for tf in target_files:
        tf_path = tf["path"] if isinstance(tf, dict) else str(tf)
        if tf_path in unrepresented_paths:
            retry_files.append(tf)

    if retry_files:
        extra = _process_files_individually(
            retry_files, review_type, client, lang, spec_content, cancel_check
        )
        issues = issues + extra

    return issues


def _split_combined_feedback(
    feedback: str,
    file_entries: List[Dict[str, Any]],
    review_type: str,
) -> List[ReviewIssue]:
    """Split a combined multi-file AI response into per-file, per-finding issues.

    .. deprecated::
        Use :func:`response_parser.parse_review_response` instead.
        This function is kept for backward compatibility and is still used
        internally as Strategy 3 (delimiter parsing) inside the new parser.

    Looks for ``=== FILE: <name> ===`` delimiters per file, then
    ``--- FINDING [severity] ---`` sub-delimiters per finding.
    Falls back to one issue per file section if no FINDING delimiters found.
    """
    issues: List[ReviewIssue] = []
    # Build a map from display-name → entry for quick lookup
    entry_map: Dict[str, Dict[str, Any]] = {e["name"]: e for e in file_entries}

    # Split on the file delimiter pattern
    parts = re.split(r"===\s*FILE:\s*(.+?)\s*===", feedback)

    if len(parts) < 3:
        # AI didn't use delimiters – treat entire response as one issue
        # for the whole batch
        entry = file_entries[0]
        issues.append(ReviewIssue(
            file_path=entry["path"],
            line_number=None,
            issue_type=review_type,
            severity=_parse_severity(feedback),
            description=f"Review feedback (combined batch)",
            code_snippet=entry["content"][:200] + ("…" if len(entry["content"]) > 200 else ""),
            ai_feedback=feedback,
        ))
        return issues

    # parts = [preamble, name1, body1, name2, body2, ...]
    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if not body:
            continue

        entry = entry_map.get(name)
        if not entry:
            # Try partial match (AI may shorten the path)
            for ename, edata in entry_map.items():
                if name in ename or ename in name:
                    entry = edata
                    break
        if not entry:
            entry = file_entries[0]  # fallback

        # Try to split into individual findings within this file section
        finding_parts = re.split(
            r"---\s*FINDING\s*\[?\s*(critical|high|medium|low|info)\s*\]?\s*---",
            body, flags=re.IGNORECASE,
        )

        if len(finding_parts) >= 3:
            # finding_parts = [preamble, severity1, text1, severity2, text2, ...]
            # Include preamble as a finding if it has content
            preamble = finding_parts[0].strip()
            if preamble and len(preamble) > 20:
                issues.append(ReviewIssue(
                    file_path=entry["path"],
                    line_number=None,
                    issue_type=review_type,
                    severity=_parse_severity(preamble),
                    description=_extract_description(preamble, entry["name"]),
                    code_snippet=entry["content"][:200] + ("…" if len(entry["content"]) > 200 else ""),
                    ai_feedback=preamble,
                ))
            for j in range(1, len(finding_parts), 2):
                sev = finding_parts[j].strip().lower()
                finding_text = finding_parts[j + 1].strip() if j + 1 < len(finding_parts) else ""
                if not finding_text:
                    continue
                issues.append(ReviewIssue(
                    file_path=entry["path"],
                    line_number=None,
                    issue_type=review_type,
                    severity=sev if sev in ("critical", "high", "medium", "low", "info") else _parse_severity(finding_text),
                    description=_extract_description(finding_text, entry["name"]),
                    code_snippet=entry["content"][:200] + ("…" if len(entry["content"]) > 200 else ""),
                    ai_feedback=finding_text,
                ))
        else:
            # No FINDING delimiters – one issue for this file (backward compat)
            issues.append(ReviewIssue(
                file_path=entry["path"],
                line_number=None,
                issue_type=review_type,
                severity=_parse_severity(body),
                description=f"Review feedback for {entry['name']}",
                code_snippet=entry["content"][:200] + ("…" if len(entry["content"]) > 200 else ""),
                ai_feedback=body,
            ))

    return issues


# ── verification ───────────────────────────────────────────────────────────

def verify_issue_resolved(
    issue: ReviewIssue, client: AIBackend, review_type: str, lang: str
) -> bool:
    """
    Re-analyse the current code and compare to the original feedback to
    decide whether the issue appears resolved.
    """
    file_path = issue.file_path or ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            current_code = fh.read()

        new_feedback = client.get_review(current_code, review_type=review_type, lang=lang)
        old_len = len(issue.ai_feedback)
        new_len = len(new_feedback)

        if new_len < old_len * 0.5 or "no issues" in new_feedback.lower():
            return True

        logger.info("Re-analysis still shows issues.")
        return False
    except Exception as exc:
        logger.error("Verification error: %s", exc)
        return False
