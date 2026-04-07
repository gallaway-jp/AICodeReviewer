from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _stringify_path(value: str) -> str:
    return value.replace("\\", "/")


@dataclass(frozen=True)
class ToolReviewTarget:
    """One file the model may inspect through tool-mediated access."""

    path: str
    is_diff: bool = False
    hunk_count: int = 0
    commit_messages: str | None = None

    def prompt_line(self) -> str:
        line = f"- {self.path}"
        details: list[str] = []
        if self.is_diff:
            details.append(f"diff-focused, {self.hunk_count} hunk(s)")
        if self.commit_messages:
            details.append(f"commit context: {self.commit_messages}")
        if details:
            line += f" ({'; '.join(details)})"
        return line


@dataclass(frozen=True)
class ToolReviewContext:
    """Workspace-scoped tool-access context for a review request."""

    workspace_root: str
    targets: tuple[ToolReviewTarget, ...]

    @property
    def target_paths(self) -> tuple[str, ...]:
        return tuple(target.path for target in self.targets)

    def prompt_block(self) -> str:
        return "\n".join(target.prompt_line() for target in self.targets)


@dataclass(frozen=True)
class ToolAccessAuditEntry:
    """One audited tool-access decision or result."""

    phase: str
    tool_name: str | None
    decision: str | None
    decision_reason: str | None
    requested_path: str | None
    relative_path: str | None
    sensitive: bool = False
    args_summary: str | None = None
    result_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "tool_name": self.tool_name,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "requested_path": self.requested_path,
            "relative_path": self.relative_path,
            "sensitive": self.sensitive,
            "args_summary": self.args_summary,
            "result_summary": self.result_summary,
        }


@dataclass
class ToolAccessAudit:
    """Aggregate per-review tool-access audit metadata."""

    backend_name: str
    model_name: str | None
    enabled: bool
    used_tool_access: bool = False
    file_read_count: int = 0
    denied_request_count: int = 0
    fallback_reason: str | None = None
    entries: list[ToolAccessAuditEntry] = field(default_factory=list)

    def add_entry(self, entry: ToolAccessAuditEntry) -> None:
        self.entries.append(entry)
        decision = (entry.decision or "").lower()
        if decision == "allow" and entry.relative_path:
            self.used_tool_access = True
            if entry.phase == "pre_tool_use":
                self.file_read_count += 1
        elif decision == "deny":
            self.denied_request_count += 1

    def merge(self, other: ToolAccessAudit | None) -> None:
        if other is None:
            return
        self.used_tool_access = self.used_tool_access or other.used_tool_access
        self.file_read_count += other.file_read_count
        self.denied_request_count += other.denied_request_count
        if self.fallback_reason is None:
            self.fallback_reason = other.fallback_reason
        self.entries.extend(other.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "model": self.model_name,
            "enabled": self.enabled,
            "used_tool_access": self.used_tool_access,
            "file_read_count": self.file_read_count,
            "denied_request_count": self.denied_request_count,
            "fallback_reason": self.fallback_reason,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def summarize_tool_payload(value: Any, *, limit: int = 200) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def extract_tool_path(tool_args: Any) -> str | None:
    path_keys = ("path", "filePath", "filepath", "relativePath", "uri", "file")
    if isinstance(tool_args, str):
        text = tool_args.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                return extract_tool_path(parsed)
    if isinstance(tool_args, dict):
        values = (tool_args.get(key) for key in path_keys)
    else:
        values = (getattr(tool_args, key, None) for key in path_keys)

    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            if text.startswith("file://"):
                return text[7:]
            return text
    return None


def normalize_relative_path(path: str, workspace_root: str) -> tuple[str | None, str | None]:
    root = Path(workspace_root).expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return _stringify_path(str(candidate)), None
    return _stringify_path(str(candidate)), _stringify_path(str(relative))


def path_matches_globs(path: str | None, globs: list[str]) -> bool:
    if not path:
        return False
    candidate = Path(path)
    normalized = _stringify_path(str(candidate)).lower()
    parts = [part.lower() for part in candidate.parts]
    for pattern in globs:
        glob = pattern.strip().lower()
        if not glob:
            continue
        if candidate.match(pattern) or candidate.name.lower() == glob:
            return True
        if glob in parts or normalized.endswith(glob):
            return True
    return False