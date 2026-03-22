"""Compare two review report artifacts and emit a structured delta summary."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two AICodeReviewer report artifacts or tool-mode review envelopes.",
    )
    parser.add_argument("before_report", help="Path to the baseline report or review envelope")
    parser.add_argument("after_report", help="Path to the comparison report or review envelope")
    parser.add_argument("--json-out", metavar="FILE")
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _extract_issues(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("report"), dict):
        report = payload["report"]
        if isinstance(report.get("issues_found"), list):
            return [issue for issue in report["issues_found"] if isinstance(issue, dict)]
    if isinstance(payload.get("issues_found"), list):
        return [issue for issue in payload["issues_found"] if isinstance(issue, dict)]
    if isinstance(payload.get("issues"), list):
        return [issue for issue in payload["issues"] if isinstance(issue, dict)]
    return []


def _normalize_token(value: str | None) -> str:
    if not value:
        return ""
    return "_".join(value.lower().replace("/", " ").replace("-", " ").split())


def _issue_brief(issue: dict[str, Any]) -> dict[str, Any]:
    file_path = str(issue.get("file_path", ""))
    related_files = [Path(str(path)).name for path in issue.get("related_files", []) if path]
    return {
        "file": Path(file_path).name if file_path else "",
        "line": issue.get("line_number"),
        "issue_type": issue.get("issue_type", ""),
        "severity": issue.get("severity", ""),
        "context_scope": issue.get("context_scope", ""),
        "related_files": sorted(related_files),
        "description": issue.get("description", ""),
    }


def _issue_fingerprint(issue: dict[str, Any]) -> tuple[str, str, str, tuple[str, ...]]:
    file_name = Path(str(issue.get("file_path", ""))).name.lower()
    issue_type = _normalize_token(str(issue.get("issue_type", "")))
    context_scope = _normalize_token(str(issue.get("context_scope", "")))
    related = tuple(sorted(Path(str(path)).name.lower() for path in issue.get("related_files", []) if path))
    return file_name, issue_type, context_scope, related


def _issue_type_counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(_normalize_token(str(issue.get("issue_type", ""))) or "unknown" for issue in issues)
    return dict(sorted(counts.items()))


def _severity_counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(issue.get("severity", "") or "unknown").lower() for issue in issues)
    return dict(sorted(counts.items()))


def _cross_scope_counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(issue.get("context_scope", "") or "unknown").lower() for issue in issues)
    return dict(sorted(counts.items()))


def compare_reports(before_path: Path, after_path: Path) -> dict[str, Any]:
    before_payload = _load_json(before_path)
    after_payload = _load_json(after_path)
    before_issues = _extract_issues(before_payload)
    after_issues = _extract_issues(after_payload)

    before_map: dict[tuple[str, str, str, tuple[str, ...]], list[dict[str, Any]]] = {}
    after_map: dict[tuple[str, str, str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for issue in before_issues:
        before_map.setdefault(_issue_fingerprint(issue), []).append(issue)
    for issue in after_issues:
        after_map.setdefault(_issue_fingerprint(issue), []).append(issue)

    all_keys = sorted(set(before_map) | set(after_map))
    unchanged: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []

    for key in all_keys:
        before_group = before_map.get(key, [])
        after_group = after_map.get(key, [])
        shared_count = min(len(before_group), len(after_group))
        unchanged.extend(_issue_brief(issue) for issue in after_group[:shared_count])
        added.extend(_issue_brief(issue) for issue in after_group[shared_count:])
        removed.extend(_issue_brief(issue) for issue in before_group[shared_count:])

    return {
        "before_report": str(before_path),
        "after_report": str(after_path),
        "before": {
            "issue_count": len(before_issues),
            "severity_counts": _severity_counts(before_issues),
            "issue_type_counts": _issue_type_counts(before_issues),
            "context_scope_counts": _cross_scope_counts(before_issues),
        },
        "after": {
            "issue_count": len(after_issues),
            "severity_counts": _severity_counts(after_issues),
            "issue_type_counts": _issue_type_counts(after_issues),
            "context_scope_counts": _cross_scope_counts(after_issues),
        },
        "delta": {
            "issue_count": len(after_issues) - len(before_issues),
            "unchanged_count": len(unchanged),
            "added_count": len(added),
            "removed_count": len(removed),
            "added": added,
            "removed": removed,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = compare_reports(Path(args.before_report), Path(args.after_report))
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())