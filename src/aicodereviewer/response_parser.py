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
from pathlib import PurePath
from typing import Any, Dict, List, Optional, Sequence, cast

from .models import ReviewIssue

__all__ = [
    "parse_review_response",
    "parse_single_file_response",
]

logger = logging.getLogger(__name__)
_PROJECT_SCOPE_CATEGORY_MARKERS = {
    "architecture",
    "layer-leak",
    "layer-leakage",
    "layer_leak",
    "layer_leakage",
    "dependency",
    "missing-repository",
    "missing_repository",
    "incomplete-refactor",
    "incomplete_refactor",
}

_PROJECT_SCOPE_TEXT_MARKERS = (
    "architecture",
    "architectural",
    "layering",
    "layer violation",
    "service layer",
    "presentation layer",
    "data layer",
    "dependency direction",
    "separation of concerns",
    "mvc",
    "hexagonal",
)

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

def _normalize_context_scope(
    context_scope: str,
    category: str,
    related_files: List[str],
    systemic_impact: Optional[str],
    evidence_basis: Optional[str],
) -> str:
    """Promote obviously broader findings to the matching scope."""
    normalized = context_scope
    if normalized == "local" and related_files:
        normalized = "cross_file"

    category_normalized = category.strip().lower()
    evidence_text = " ".join(
        part for part in (systemic_impact, evidence_basis) if part
    ).lower()
    if normalized == "cross_file" and (
        category_normalized in _PROJECT_SCOPE_CATEGORY_MARKERS
        or any(marker in evidence_text for marker in _PROJECT_SCOPE_TEXT_MARKERS)
    ):
        normalized = "project"

    return normalized


def _infer_related_files_from_text(
    current_filename: str,
    file_entries: List[Dict[str, Any]],
    texts: Sequence[str | None],
) -> List[str]:
    """Infer related files when evidence text explicitly names another file."""
    haystack = "\n".join(part for part in texts if part).lower()
    if not haystack:
        return []

    current_name = current_filename.lower()
    inferred: List[str] = []
    seen: set[str] = set()

    for entry in file_entries:
        entry_name = str(entry.get("name") or entry.get("path") or "").strip()
        if not entry_name:
            continue
        entry_name_lower = entry_name.lower()
        if entry_name_lower == current_name:
            continue

        candidates = {
            entry_name_lower,
            PurePath(entry_name_lower).name,
        }
        entry_path = str(entry.get("path") or "").strip().lower()
        if entry_path:
            candidates.add(entry_path)
            candidates.add(PurePath(entry_path).name)

        if any(candidate and candidate in haystack for candidate in candidates):
            if entry_name not in seen:
                inferred.append(entry_name)
                seen.add(entry_name)

    return inferred


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
    allowed_scopes = {"local", "cross_file", "project"}
    allowed_confidence = {"high", "medium", "low"}

    raw_files_list = data.get("files") or data.get("results") or []
    if isinstance(data, list):
        # Some models return a flat array of findings
        files_list: list[Any] = [{"filename": "<unknown>", "findings": data}]
    elif isinstance(raw_files_list, list):
        files_list = raw_files_list
    else:
        files_list = []

    for file_block_any in files_list:
        if not isinstance(file_block_any, dict):
            continue
        file_block = cast(Dict[str, Any], file_block_any)
        filename = file_block.get("filename") or file_block.get("file") or ""
        findings = file_block.get("findings") or file_block.get("issues") or []
        if not isinstance(filename, str):
            filename = str(filename)
        if not isinstance(findings, list):
            continue

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

        entry_content = entry.get("content")
        if not isinstance(entry_content, str):
            entry_content = ""

        for finding_any in findings:
            if not isinstance(finding_any, dict):
                continue
            finding = cast(Dict[str, Any], finding_any)
            severity = _normalize_severity(
                str(finding.get("severity") or finding.get("level") or "medium")
            )
            line_num = finding.get("line") or finding.get("line_number")
            if isinstance(line_num, str):
                try:
                    line_num = int(line_num)
                except ValueError:
                    line_num = None
            elif not isinstance(line_num, int):
                line_num = None
            category = str(finding.get("category") or review_type)
            title = str(finding.get("title") or "")
            desc = str(finding.get("description") or "")
            suggestion = str(finding.get("suggestion") or finding.get("recommendation") or "")
            code_ctx = str(finding.get("code_context") or finding.get("code_snippet") or "")
            context_scope = str(finding.get("context_scope") or "local").strip().lower()
            if context_scope not in allowed_scopes:
                context_scope = "local"
            related_files_raw = finding.get("related_files") or []
            related_files = [
                str(path).strip()
                for path in related_files_raw
                if isinstance(path, str) and path.strip()
            ] if isinstance(related_files_raw, list) else []
            systemic_impact = finding.get("systemic_impact")
            if systemic_impact is not None:
                systemic_impact = str(systemic_impact).strip() or None
            confidence = finding.get("confidence")
            if confidence is not None:
                confidence = str(confidence).strip().lower() or None
            if confidence not in allowed_confidence:
                confidence = None
            evidence_basis = finding.get("evidence_basis")
            if evidence_basis is not None:
                evidence_basis = str(evidence_basis).strip() or None
            inferred_related_files = _infer_related_files_from_text(
                str(entry.get("name") or filename),
                file_entries,
                [title, desc, systemic_impact, evidence_basis],
            )
            for inferred_path in inferred_related_files:
                if inferred_path not in related_files:
                    related_files.append(inferred_path)
            context_scope = _normalize_context_scope(
                context_scope,
                category,
                related_files,
                systemic_impact,
                evidence_basis,
            )

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
            if context_scope != "local":
                feedback_parts.append(f"Context Scope: {context_scope}")
            if related_files:
                feedback_parts.append(f"Related Files: {', '.join(related_files)}")
            if systemic_impact:
                feedback_parts.append(f"Systemic Impact: {systemic_impact}")
            if confidence:
                feedback_parts.append(f"Confidence: {confidence}")
            if evidence_basis:
                feedback_parts.append(f"Evidence Basis: {evidence_basis}")
            # Include extra fields the model may have added
            cwe = str(finding.get("cwe_id") or finding.get("cwe") or "")
            if cwe:
                feedback_parts.append(f"CWE: {cwe}")

            ai_feedback = "\n\n".join(feedback_parts) if feedback_parts else str(finding)

            # Fallback code snippet from entry content
            code_snippet = code_ctx or (
                entry_content[:200] + ("…" if len(entry_content) > 200 else "")
                if entry_content else ""
            )

            issues.append(ReviewIssue(
                file_path=entry.get("path", filename),
                line_number=line_num,
                issue_type=category,
                severity=severity,
                description=description[:200],
                code_snippet=code_snippet,
                ai_feedback=ai_feedback,
                context_scope=context_scope,
                related_files=related_files,
                systemic_impact=systemic_impact,
                confidence=confidence,
                evidence_basis=evidence_basis,
                issue_id=(str(finding.get("issue_id")).strip() or None) if finding.get("issue_id") else None,
                related_issues=[
                    int(index)
                    for index in (finding.get("related_issues") or [])
                    if isinstance(index, int)
                ] if isinstance(finding.get("related_issues"), list) else [],
                interaction_summary=(
                    str(finding.get("interaction_summary")).strip() or None
                ) if finding.get("interaction_summary") is not None else None,
            ))

    _promote_cache_findings_from_related_context(issues)
    return issues


def _promote_cache_findings_from_related_context(issues: List[ReviewIssue]) -> None:
    """Promote local cache findings when sibling findings prove cross-file context."""
    cache_issue_types = {
        "cache_invalidation",
        "missing_cache_invalidation",
        "cache_consistency",
        "caching",
        "stale_cache",
    }

    for issue in issues:
        if issue.context_scope != "local":
            continue
        if issue.issue_type.lower() not in cache_issue_types:
            continue
        if not issue.related_issues:
            continue

        sibling_paths: list[str] = []
        for related_index in issue.related_issues:
            if related_index < 0 or related_index >= len(issues):
                continue
            sibling = issues[related_index]
            if sibling.context_scope == "local":
                continue
            if sibling.file_path != issue.file_path and sibling.file_path not in sibling_paths:
                sibling_paths.append(sibling.file_path)
            for related_file in sibling.related_files:
                if related_file != issue.file_path and related_file not in sibling_paths:
                    sibling_paths.append(related_file)

        if not sibling_paths:
            continue

        issue.context_scope = "cross_file"
        for sibling_path in sibling_paths:
            if sibling_path not in issue.related_files:
                issue.related_files.append(sibling_path)

        feedback_parts = [issue.ai_feedback] if issue.ai_feedback else []
        if "Context Scope:" not in issue.ai_feedback:
            feedback_parts.append("Context Scope: cross_file")
        if issue.related_files and "Related Files:" not in issue.ai_feedback:
            feedback_parts.append(f"Related Files: {', '.join(issue.related_files)}")
        issue.ai_feedback = "\n\n".join(part for part in feedback_parts if part)


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


def _iter_embedded_json_candidates(response: str) -> Sequence[Any]:
    """Yield embedded JSON payloads decoded from arbitrary response text.

    This recovers model outputs that contain valid structured JSON with extra
    preamble or trailing commentary, without attempting broad JSON repair.
    """
    decoder = json.JSONDecoder()
    seen_ranges: set[tuple[int, int]] = set()

    for match in re.finditer(r"[\[{]", response):
        start = match.start()
        try:
            payload, end = decoder.raw_decode(response[start:])
        except json.JSONDecodeError:
            continue

        span = (start, start + end)
        if span in seen_ranges:
            continue
        seen_ranges.add(span)
        yield payload


def _try_embedded_json_parse(
    response: str,
    file_entries: List[Dict[str, Any]],
    review_type: str,
) -> List[ReviewIssue]:
    """Recover JSON findings embedded inside otherwise malformed text output."""
    for payload in _iter_embedded_json_candidates(response):
        data = payload
        if isinstance(data, list):
            data = {"files": [{"filename": "<combined>", "findings": data}]}
        if not isinstance(data, dict):
            continue
        issues = _json_to_issues(data, file_entries, review_type)
        if issues:
            return issues
    raise ValueError("No embedded JSON payload produced structured findings")


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
        _try_embedded_json_parse,
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
