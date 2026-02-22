# src/aicodereviewer/response_parser.py
"""
Multi-strategy response parser for AI review output.

Tries structured JSON first, then falls back through progressively
looser strategies to maximise reliable parsing regardless of model
output format.

Strategy chain:
  1. Raw JSON (ideal — from structured prompt)
  2. Markdown-fenced JSON (```json ... ```)
  3. Delimiter-based (=== FILE: / --- FINDING ---)
  4. Heuristic line-by-line (last resort)
"""
from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence

from .models import ReviewIssue

__all__ = [
    "parse_review_response",
    "parse_single_file_response",
]

logger = logging.getLogger(__name__)

# ── Severity normalisation ─────────────────────────────────────────────────

_SEVERITY_MAP: Dict[str, str] = {
    "critical": "critical",
    "crit": "critical",
    "high": "high",
    "severe": "high",
    "major": "high",
    "medium": "medium",
    "med": "medium",
    "moderate": "medium",
    "low": "low",
    "minor": "low",
    "trivial": "low",
    "info": "info",
    "informational": "info",
    "note": "info",
    "suggestion": "info",
}


def _normalize_severity(severity_str: str) -> str:
    """Normalise a severity string through a strict allow-list."""
    normalized = _SEVERITY_MAP.get(severity_str.lower().strip())
    if not normalized:
        logger.debug("Unknown severity '%s', defaulting to 'medium'", severity_str)
        return "medium"
    return normalized


# ── Line-number extraction ─────────────────────────────────────────────────

_LINE_PATTERNS = [
    re.compile(r"(?:line|at line|on line)\s+(\d+)", re.IGNORECASE),
    re.compile(r"[Ll](\d+)\b"),
    re.compile(r":(\d+):"),
]


def _extract_line_number(text: str) -> Optional[int]:
    """Extract a line number from common patterns in *text*."""
    for pattern in _LINE_PATTERNS:
        match = pattern.search(text)
        if match:
            num = int(match.group(1))
            if 0 < num < 100_000:  # sanity bound
                return num
    return None


# ── Description extraction ─────────────────────────────────────────────────

def _extract_description(text: str, fallback: str) -> str:
    """Return a concise description from the first meaningful line."""
    for line in text.splitlines():
        stripped = line.strip().strip("*-#>:").strip()
        if stripped and len(stripped) > 5:
            return stripped[:200]
    return fallback


# ── Deduplication ──────────────────────────────────────────────────────────

def _text_similarity(a: str, b: str) -> float:
    """Quick token-level similarity ratio."""
    return SequenceMatcher(None, a.lower().split(), b.lower().split()).ratio()


def _deduplicate_issues(issues: List[ReviewIssue]) -> List[ReviewIssue]:
    """Remove near-duplicate findings (same file + similar description)."""
    if len(issues) <= 1:
        return issues

    unique: List[ReviewIssue] = []
    for issue in issues:
        is_dup = False
        for existing in unique:
            if issue.file_path != existing.file_path:
                continue
            if _text_similarity(issue.description, existing.description) > 0.70:
                # Keep the more detailed version
                if len(issue.ai_feedback) > len(existing.ai_feedback):
                    unique.remove(existing)
                    unique.append(issue)
                is_dup = True
                break
        if not is_dup:
            unique.append(issue)

    removed = len(issues) - len(unique)
    if removed:
        logger.info("Deduplicated %d near-duplicate issue(s)", removed)
    return unique


# ── JSON → ReviewIssue mapping ─────────────────────────────────────────────

def _json_to_issues(
    data: Dict[str, Any],
    file_entries: List[Dict[str, Any]],
    review_type: str,
) -> List[ReviewIssue]:
    """Convert a parsed JSON object (following the expected schema) to issues.

    Expected schema::

        {
          "files": [
            {
              "filename": "...",
              "findings": [
                {
                  "severity": "...",
                  "line": 42,
                  "category": "...",
                  "title": "...",
                  "description": "...",
                  "code_context": "...",
                  "suggestion": "...",
                  ...
                }
              ]
            }
          ]
        }
    """
    issues: List[ReviewIssue] = []
    entry_map = {e["name"]: e for e in file_entries}

    files_list = data.get("files") or data.get("results") or []
    if isinstance(data, list):
        # Some models return a flat array of findings
        files_list = [{"filename": "<unknown>", "findings": data}]

    for file_block in files_list:
        filename = file_block.get("filename") or file_block.get("file") or ""
        findings = file_block.get("findings") or file_block.get("issues") or []

        # Resolve entry for this file
        entry = entry_map.get(filename)
        if not entry:
            for ename, edata in entry_map.items():
                if filename in ename or ename in filename:
                    entry = edata
                    break
        if not entry and file_entries:
            entry = file_entries[0]
        elif not entry:
            entry = {"name": filename, "path": filename, "content": ""}

        for finding in findings:
            severity = _normalize_severity(
                finding.get("severity") or finding.get("level") or "medium"
            )
            line_num = finding.get("line") or finding.get("line_number")
            if isinstance(line_num, str):
                try:
                    line_num = int(line_num)
                except ValueError:
                    line_num = None
            category = finding.get("category") or review_type
            title = finding.get("title") or ""
            desc = finding.get("description") or ""
            suggestion = finding.get("suggestion") or finding.get("recommendation") or ""
            code_ctx = finding.get("code_context") or finding.get("code_snippet") or ""

            # Build human-readable description
            description = title
            if desc:
                description = f"{title}: {desc}" if title else desc

            # Build full ai_feedback from all JSON fields
            feedback_parts: List[str] = []
            if title:
                feedback_parts.append(f"**{title}**")
            if desc:
                feedback_parts.append(desc)
            if code_ctx:
                feedback_parts.append(f"Code: {code_ctx}")
            if suggestion:
                feedback_parts.append(f"Suggestion: {suggestion}")
            # Include extra fields the model may have added
            cwe = finding.get("cwe_id") or finding.get("cwe") or ""
            if cwe:
                feedback_parts.append(f"CWE: {cwe}")

            ai_feedback = "\n\n".join(feedback_parts) if feedback_parts else str(finding)

            # Fallback code snippet from entry content
            code_snippet = code_ctx or (
                entry["content"][:200] + ("…" if len(entry["content"]) > 200 else "")
                if entry.get("content") else ""
            )

            issues.append(ReviewIssue(
                file_path=entry.get("path", filename),
                line_number=line_num,
                issue_type=category,
                severity=severity,
                description=description[:200],
                code_snippet=code_snippet,
                ai_feedback=ai_feedback,
            ))

    return issues


# ── Strategy 1: raw JSON ──────────────────────────────────────────────────

def _try_json_parse(
    response: str,
    file_entries: List[Dict[str, Any]],
    review_type: str,
) -> List[ReviewIssue]:
    """Parse the response as a raw JSON document."""
    stripped = response.strip()
    # Quick reject — must start with { or [
    if not stripped or stripped[0] not in ("{", "["):
        raise ValueError("Response does not start with JSON")
    data = json.loads(stripped)
    if isinstance(data, list):
        data = {"files": [{"filename": "<combined>", "findings": data}]}
    return _json_to_issues(data, file_entries, review_type)


# ── Strategy 2: markdown-fenced JSON ──────────────────────────────────────

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```",
    re.IGNORECASE,
)


def _try_markdown_json_parse(
    response: str,
    file_entries: List[Dict[str, Any]],
    review_type: str,
) -> List[ReviewIssue]:
    """Extract JSON from markdown code fences."""
    matches = _JSON_FENCE_RE.findall(response)
    if not matches:
        raise ValueError("No JSON code block found")

    # Try each match — the longest one is most likely the main payload
    matches.sort(key=len, reverse=True)
    last_err: Exception = ValueError("empty")
    for candidate in matches:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            if isinstance(data, list):
                data = {"files": [{"filename": "<combined>", "findings": data}]}
            issues = _json_to_issues(data, file_entries, review_type)
            if issues:
                return issues
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            last_err = exc
    raise last_err


# ── Strategy 3: delimiter-based (legacy) ──────────────────────────────────

_FILE_DELIMITER_RE = re.compile(r"===\s*FILE:\s*(.+?)\s*===")
_FINDING_DELIMITER_RE = re.compile(
    r"---\s*FINDING\s*\[?\s*(critical|high|medium|low|info)\s*\]?\s*---",
    re.IGNORECASE,
)


def _try_delimiter_parse(
    response: str,
    file_entries: List[Dict[str, Any]],
    review_type: str,
) -> List[ReviewIssue]:
    """Parse using ``=== FILE:`` / ``--- FINDING [severity] ---`` delimiters."""
    issues: List[ReviewIssue] = []
    entry_map = {e["name"]: e for e in file_entries}

    parts = re.split(r"===\s*FILE:\s*(.+?)\s*===", response)
    if len(parts) < 3:
        raise ValueError("No === FILE: === delimiters found")

    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if not body:
            continue

        entry = entry_map.get(name)
        if not entry:
            for ename, edata in entry_map.items():
                if name in ename or ename in name:
                    entry = edata
                    break
        if not entry and file_entries:
            entry = file_entries[0]
        elif not entry:
            entry = {"name": name, "path": name, "content": ""}

        # Split into individual findings
        finding_parts = _FINDING_DELIMITER_RE.split(body)

        if len(finding_parts) >= 3:
            # preamble, severity1, text1, severity2, text2 …
            preamble = finding_parts[0].strip()
            if preamble and len(preamble) > 20:
                issues.append(ReviewIssue(
                    file_path=entry.get("path", name),
                    line_number=_extract_line_number(preamble),
                    issue_type=review_type,
                    severity=_normalize_severity(
                        _infer_severity_keyword(preamble)
                    ),
                    description=_extract_description(preamble, entry.get("name", name)),
                    code_snippet=_snippet_from_entry(entry),
                    ai_feedback=preamble,
                ))

            for j in range(1, len(finding_parts), 2):
                sev = finding_parts[j].strip().lower()
                finding_text = (
                    finding_parts[j + 1].strip() if j + 1 < len(finding_parts) else ""
                )
                if not finding_text:
                    continue
                issues.append(ReviewIssue(
                    file_path=entry.get("path", name),
                    line_number=_extract_line_number(finding_text),
                    issue_type=review_type,
                    severity=_normalize_severity(sev),
                    description=_extract_description(finding_text, entry.get("name", name)),
                    code_snippet=_snippet_from_entry(entry),
                    ai_feedback=finding_text,
                ))
        else:
            # No FINDING delimiters — one issue for the whole file section
            issues.append(ReviewIssue(
                file_path=entry.get("path", name),
                line_number=_extract_line_number(body),
                issue_type=review_type,
                severity=_normalize_severity(_infer_severity_keyword(body)),
                description=_extract_description(body, entry.get("name", name)),
                code_snippet=_snippet_from_entry(entry),
                ai_feedback=body,
            ))

    if not issues:
        raise ValueError("Delimiter parsing found no issues")
    return issues


# ── Strategy 4: heuristic / free-text ─────────────────────────────────────

_BULLET_SEVERITY_RE = re.compile(
    r"^\s*[-*•]\s*\*?\*?\[?\s*(critical|high|medium|low|info"
    r"|severe|major|minor|trivial)\s*\]?\s*:?\s*\*?\*?\s*(.+)",
    re.IGNORECASE,
)

_NUMBERED_ITEM_RE = re.compile(
    r"^\s*\d+[.)]\s+(.+)", re.IGNORECASE
)

_HEADING_FILE_RE = re.compile(
    r"^#{1,4}\s+(?:File:\s*)?(.+?\.\w{1,5})\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _try_heuristic_parse(
    response: str,
    file_entries: List[Dict[str, Any]],
    review_type: str,
) -> List[ReviewIssue]:
    """Line-by-line heuristic parsing for unstructured AI output."""
    issues: List[ReviewIssue] = []
    entry_map = {e["name"]: e for e in file_entries}
    current_entry = file_entries[0] if file_entries else {
        "name": "<unknown>", "path": "<unknown>", "content": "",
    }

    # Try to detect file section headings
    current_finding_lines: List[str] = []
    current_severity: Optional[str] = None

    def _flush_finding() -> None:
        nonlocal current_finding_lines, current_severity
        text = "\n".join(current_finding_lines).strip()
        if not text or len(text) < 10:
            current_finding_lines = []
            current_severity = None
            return
        sev = current_severity or _infer_severity_keyword(text)
        issues.append(ReviewIssue(
            file_path=current_entry.get("path", current_entry.get("name", "")),
            line_number=_extract_line_number(text),
            issue_type=review_type,
            severity=_normalize_severity(sev),
            description=_extract_description(text, current_entry.get("name", "")),
            code_snippet=_snippet_from_entry(current_entry),
            ai_feedback=text,
        ))
        current_finding_lines = []
        current_severity = None

    for line in response.splitlines():
        # Check if this line is a file heading
        heading_m = _HEADING_FILE_RE.match(line)
        if heading_m:
            _flush_finding()
            fname = heading_m.group(1).strip()
            entry = entry_map.get(fname)
            if not entry:
                for ename, edata in entry_map.items():
                    if fname in ename or ename in fname:
                        entry = edata
                        break
            if entry:
                current_entry = entry
            continue

        # Check for bullet with severity marker
        bullet_m = _BULLET_SEVERITY_RE.match(line)
        if bullet_m:
            _flush_finding()
            current_severity = bullet_m.group(1).strip()
            current_finding_lines.append(bullet_m.group(2).strip())
            continue

        # Check for numbered item (new finding boundary)
        num_m = _NUMBERED_ITEM_RE.match(line)
        if num_m:
            _flush_finding()
            current_finding_lines.append(num_m.group(1).strip())
            continue

        # Continuation of current finding
        stripped = line.strip()
        if stripped:
            current_finding_lines.append(stripped)

    _flush_finding()

    if not issues:
        raise ValueError("Heuristic parsing found no structured findings")
    return issues


# ── Helpers ────────────────────────────────────────────────────────────────

_SEVERITY_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "critical": ("critical", "critically"),
    "high": ("high", "severe", "major"),
    "medium": ("medium", "moderate"),
    "low": ("low", "minor", "trivial"),
    "info": ("info", "informational", "note", "suggestion"),
}


def _infer_severity_keyword(text: str) -> str:
    """Infer severity from keyword presence in free text."""
    lower = text.lower()
    for level, kws in _SEVERITY_KEYWORDS.items():
        if any(kw in lower for kw in kws):
            return level
    return "medium"


def _snippet_from_entry(entry: Dict[str, Any]) -> str:
    """Return a truncated snippet from *entry*'s content."""
    content = entry.get("content", "")
    if not content:
        return ""
    return content[:200] + ("…" if len(content) > 200 else "")


# ── Generic fallback ──────────────────────────────────────────────────────

def _create_generic_issues(
    file_entries: List[Dict[str, Any]],
    response: str,
    review_type: str,
) -> List[ReviewIssue]:
    """Last-resort fallback: create one issue per file with the full response."""
    if not file_entries:
        return [
            ReviewIssue(
                file_path="<unknown>",
                issue_type=review_type,
                severity=_normalize_severity(_infer_severity_keyword(response)),
                description="Review feedback (unparsed)",
                ai_feedback=response,
            )
        ]

    issues: List[ReviewIssue] = []
    # If only one file, assign entire response to it
    if len(file_entries) == 1:
        entry = file_entries[0]
        issues.append(ReviewIssue(
            file_path=entry.get("path", entry.get("name", "")),
            issue_type=review_type,
            severity=_normalize_severity(_infer_severity_keyword(response)),
            description=_extract_description(response, entry.get("name", "")),
            code_snippet=_snippet_from_entry(entry),
            ai_feedback=response,
        ))
    else:
        # Assign to first file as combined feedback
        entry = file_entries[0]
        issues.append(ReviewIssue(
            file_path=entry.get("path", entry.get("name", "")),
            issue_type=review_type,
            severity=_normalize_severity(_infer_severity_keyword(response)),
            description="Review feedback (combined batch)",
            code_snippet=_snippet_from_entry(entry),
            ai_feedback=response,
        ))
    return issues


# ── Public API ─────────────────────────────────────────────────────────────

def parse_review_response(
    response: str,
    file_entries: List[Dict[str, Any]],
    review_type: str,
    *,
    deduplicate: bool = True,
) -> List[ReviewIssue]:
    """Parse an AI review response using a strategy chain with fallback.

    Tries (in order):
      1. Raw JSON
      2. Markdown-fenced JSON
      3. ``=== FILE:`` / ``--- FINDING ---`` delimiters
      4. Heuristic bullet/numbered-list parsing
      5. Generic one-issue-per-file fallback

    Args:
        response:     Raw AI response text.
        file_entries:  List of ``{"name": ..., "path": ..., "content": ...}`` dicts.
        review_type:  The review type key (e.g. ``"security"``).
        deduplicate:  Whether to run deduplication (default ``True``).

    Returns:
        List of :class:`ReviewIssue` instances (never empty if *response*
        is non-empty).
    """
    if not response or not response.strip():
        logger.warning("Empty AI response — no issues to parse")
        return []

    strategies = [
        _try_json_parse,
        _try_markdown_json_parse,
        _try_delimiter_parse,
        _try_heuristic_parse,
    ]

    for strategy in strategies:
        try:
            issues = strategy(response, file_entries, review_type)
            if issues:
                logger.info(
                    "Parsed %d issue(s) via %s", len(issues), strategy.__name__
                )
                if deduplicate:
                    issues = _deduplicate_issues(issues)
                return issues
        except Exception as exc:
            logger.debug("Strategy %s failed: %s", strategy.__name__, exc)
            continue

    # Ultimate fallback
    logger.warning("All parsing strategies failed — creating generic issues")
    return _create_generic_issues(file_entries, response, review_type)


def parse_single_file_response(
    response: str,
    file_path: str,
    display_name: str,
    code_content: str,
    review_type: str,
) -> List[ReviewIssue]:
    """Parse an AI response for a single-file review.

    Convenience wrapper around :func:`parse_review_response` that
    builds the ``file_entries`` list from scalar arguments.
    """
    file_entries = [
        {"name": display_name, "path": file_path, "content": code_content},
    ]
    return parse_review_response(response, file_entries, review_type)
