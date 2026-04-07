"""Shared failure diagnostic helpers for health, runtime, and tool-mode surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FailureDiagnostic:
    """Structured failure metadata shared across execution surfaces."""

    category: str
    origin: str
    detail: str
    fix_hint: str = ""
    exception_type: str | None = None
    retryable: bool = False
    retry_delay_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "category": self.category,
            "origin": self.origin,
            "detail": self.detail,
            "fix_hint": self.fix_hint,
        }
        if self.exception_type is not None:
            payload["exception_type"] = self.exception_type
        if self.retryable:
            payload["retryable"] = True
        if self.retry_delay_seconds is not None:
            payload["retry_delay_seconds"] = self.retry_delay_seconds
        return payload


def failure_category_from_exception(exc: Exception) -> str:
    """Map an exception into the shared failure category vocabulary."""
    text = str(exc).lower()
    if any(token in text for token in ("credential", "token", "auth", "login", "unauthorized")):
        return "auth"
    if "forbidden" in text or "permission" in text or "access denied" in text:
        return "permission"
    if "timeout" in text:
        return "timeout"
    if any(token in text for token in ("connect", "connection", "network", "dns", "refused")):
        return "transport"
    if any(token in text for token in ("not found", "cli", "wsl", "unsupported", "compatib")):
        return "tool_compatibility"
    if any(token in text for token in ("config", "model", "api_type", "setting", "schema", "artifact")):
        return "configuration"
    return "provider"


def failure_category_from_http_status(status_code: int) -> str:
    """Map an HTTP status code into the shared failure category vocabulary."""
    if status_code in (401, 407):
        return "auth"
    if status_code == 403:
        return "permission"
    if status_code == 429:
        return "provider"
    if status_code == 408:
        return "timeout"
    if 400 <= status_code < 500:
        return "configuration"
    if status_code >= 500:
        return "provider"
    return "none"


def failure_retry_guidance(category: str, detail: str) -> tuple[bool, int | None]:
    """Return whether a failure is worth retrying, and an optional retry delay."""
    normalized_detail = detail.lower()
    if category == "timeout":
        return True, 5
    if category == "transport":
        return True, 3
    if category == "provider":
        if any(token in normalized_detail for token in ("throttl", "rate limit", "too many requests", "429")):
            return True, 30
        if any(token in normalized_detail for token in ("temporar", "unavailable", "overloaded", "503", "502", "504")):
            return True, 10
    return False, None


def failure_fix_hint(category: str) -> str:
    """Return a concise remediation hint for a classified failure category."""
    hints = {
        "auth": "Refresh credentials or sign in again, then retry.",
        "permission": "Verify the current account or token has access to the requested resource.",
        "timeout": "Increase the timeout or verify the backend is responsive before retrying.",
        "transport": "Check network connectivity and backend endpoint settings, then retry.",
        "configuration": "Check the active backend settings, selected model, and artifact inputs.",
        "tool_compatibility": "Verify the required CLI or runtime is installed and supported on this system.",
        "provider": "Check the backend service status or logs, then retry.",
    }
    return hints.get(category, "Review the error detail and backend state, then retry.")


def diagnostic_from_exception(exc: Exception, *, origin: str) -> FailureDiagnostic:
    """Build a structured diagnostic from an exception using the shared category model."""
    category = failure_category_from_exception(exc)
    detail = str(exc).strip() or type(exc).__name__
    retryable, retry_delay_seconds = failure_retry_guidance(category, detail)
    return FailureDiagnostic(
        category=category,
        origin=origin,
        detail=detail,
        fix_hint=failure_fix_hint(category),
        exception_type=type(exc).__name__,
        retryable=retryable,
        retry_delay_seconds=retry_delay_seconds,
    )


def build_failure_diagnostic(
    *,
    category: str,
    origin: str,
    detail: str,
    exception_type: str | None = None,
    fix_hint: str | None = None,
    retryable: bool | None = None,
    retry_delay_seconds: int | None = None,
) -> FailureDiagnostic:
    """Build a structured diagnostic from explicit category and detail inputs."""
    normalized_detail = detail.strip() or exception_type or "Failure"
    inferred_retryable, inferred_retry_delay_seconds = failure_retry_guidance(category, normalized_detail)
    return FailureDiagnostic(
        category=category,
        origin=origin,
        detail=normalized_detail,
        fix_hint=failure_fix_hint(category) if fix_hint is None else fix_hint,
        exception_type=exception_type,
        retryable=inferred_retryable if retryable is None else retryable,
        retry_delay_seconds=inferred_retry_delay_seconds if retry_delay_seconds is None else retry_delay_seconds,
    )


def serialize_failure_diagnostic(diagnostic: FailureDiagnostic | None) -> dict[str, Any] | None:
    """Serialize a failure diagnostic when one is present."""
    if diagnostic is None:
        return None
    return diagnostic.to_dict()