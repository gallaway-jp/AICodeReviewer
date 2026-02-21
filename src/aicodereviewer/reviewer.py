# src/aicodereviewer/reviewer.py
"""
Code review issue collection with multi-type support.

Handles file reading, AI-powered analysis across one or more review types,
and structured issue parsing.
"""
import os
import logging
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import ReviewIssue
from .config import config
from .backends.base import AIBackend

__all__ = [
    "ProgressCallback",
    "CancelCheck",
    "FileInfo",
    "clear_file_cache",
    "collect_review_issues",
    "verify_issue_resolved",
]

# Type aliases
ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]
FileInfo = Union[Path, Dict[str, Any]]

logger = logging.getLogger(__name__)


# ── file content cache ─────────────────────────────────────────────────────

class _BoundedCache:
    """Simple bounded LRU cache for file contents.

    Evicts the oldest entry when *maxsize* is reached, preventing
    unbounded memory growth during large project reviews.
    """

    def __init__(self, maxsize: int = 100):
        self._data: OrderedDict[str, str] = OrderedDict()
        self.maxsize = maxsize

    def get(self, key: str) -> Optional[str]:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: str, value: str) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        else:
            if len(self._data) >= self.maxsize:
                self._data.popitem(last=False)
        self._data[key] = value

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            return dict(self._data) == other
        if isinstance(other, _BoundedCache):
            return self._data == other._data
        return NotImplemented


_file_content_cache = _BoundedCache()


def clear_file_cache() -> None:
    """Clear the file-content cache (useful between review sessions)."""
    _file_content_cache.clear()


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
    # Always one pass over files — multiple review types are merged into one prompt
    combined_type = "+".join(review_types) if len(review_types) > 1 else review_types[0]
    total_work = len(target_files)
    done = 0

    batch_size = config.get("processing", "batch_size", 5)
    enable_parallel = config.get("processing", "enable_parallel_processing", False)

    type_label = ", ".join(review_types)
    batches = [
        target_files[i : i + batch_size]
        for i in range(0, len(target_files), batch_size)
    ]

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
                done += len(futures[future])
                if progress_callback:
                    progress_callback(done, total_work, f"[{type_label}]")
    else:
        for batch in batches:
            batch_issues = _process_file_batch(
                batch, combined_type, client, lang, spec_content, cancel_check
            )
            issues.extend(batch_issues)
            done += len(batch)
            if progress_callback:
                progress_callback(done, total_work, f"[{type_label}]")

    logger.debug("Collected %d issues across %d review type(s).", len(issues), len(review_types))
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


def _process_files_individually(
    target_files: Sequence[FileInfo],
    review_type: str,
    client: AIBackend,
    lang: str,
    spec_content: Optional[str] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> List[ReviewIssue]:
    """Original one-file-per-request approach."""
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
            feedback = client.get_review(
                code, review_type=review_type, lang=lang, spec_content=spec_content
            )
            if feedback and not feedback.startswith("Error:"):
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
    """Combine multiple files into a single AI prompt and parse results."""
    # Prepare file info list
    file_entries: List[Dict[str, Any]] = []
    for file_info in target_files:
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
        file_entries.append({
            "path": str(file_path),
            "name": display_name,
            "content": code,
        })

    if not file_entries:
        return []

    # If only one file left after filtering, use single-file path
    if len(file_entries) == 1:
        return _process_files_individually(target_files, review_type, client, lang, spec_content, cancel_check)

    names = [f["name"] for f in file_entries]
    logger.info("Combined review of %d files [%s]: %s",
                len(file_entries), review_type, ", ".join(names))

    # Build combined user message via the backend helper
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

    # Parse combined feedback into per-file sections
    return _split_combined_feedback(feedback, file_entries, review_type)


def _split_combined_feedback(
    feedback: str,
    file_entries: List[Dict[str, Any]],
    review_type: str,
) -> List[ReviewIssue]:
    """Split a combined multi-file AI response into per-file, per-finding issues.

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
