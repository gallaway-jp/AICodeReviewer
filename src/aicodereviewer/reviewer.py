# src/aicodereviewer/reviewer.py
"""
Code review issue collection with multi-type support.

Handles file reading, AI-powered analysis across one or more review types,
and structured issue parsing.
"""
import os
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
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
]

# Type aliases
ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]
FileInfo = Union[Path, Dict[str, Any]]

logger = logging.getLogger(__name__)


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

    # ── Build project context (once per session) ───────────────────────────
    enable_context = config.get("processing", "enable_project_context", True)
    if enable_context:
        try:
            # Determine project root from target_files
            if target_files:
                sample = target_files[0]
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
                for f in target_files
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
    total_work = len(target_files)
    done = 0

    enable_parallel = config.get("processing", "enable_parallel_processing", False)
    enable_adaptive = config.get("processing", "enable_adaptive_batching", True)

    type_label = ", ".join(review_types)

    if enable_adaptive:
        max_batch_tokens = config.get("processing", "max_batch_token_budget", 80_000)
        max_batch_files = config.get("processing", "batch_size", 10)
        batches = _build_adaptive_batches(target_files, max_batch_tokens, max_batch_files)
        logger.info(
            "Adaptive batching: %d file(s) → %d batch(es)",
            len(target_files), len(batches),
        )
    else:
        batch_size = config.get("processing", "batch_size", 5)
        batches = [
            target_files[i : i + batch_size]
            for i in range(0, len(target_files), batch_size)
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

    logger.info(
        "Review session: %d API call(s), %d succeeded, %d failed, %d issue(s)",
        session.total_api_calls,
        session.successful_batches,
        session.failed_batches,
        len(issues),
    )
    return issues


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
                feedback = client.get_review(
                    diff_msg, review_type=review_type, lang=lang, spec_content=spec_content
                )
            else:
                feedback = client.get_review(
                    code, review_type=review_type, lang=lang, spec_content=spec_content
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
        feedback = client.get_review(
            combined_code, review_type=review_type, lang=lang, spec_content=spec_content
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

    # Parse combined feedback using the multi-strategy response parser
    return parse_review_response(feedback, file_entries, review_type)


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
