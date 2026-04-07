"""Benchmark fixtures and evaluation helpers for holistic review quality."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from aicodereviewer.registries import get_review_registry


_SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


_ISSUE_TYPE_ALIASES = {
    "architecture": {
        "architecture",
        "layer-leak",
        "layer-leakage",
        "layer_leakage",
        "layer-separation",
        "layer_separation",
        "layering_violation",
        "dependency_misalignment",
        "dependency misalignment",
        "separation_of_concerns",
        "separation of concerns",
        "framework_coupling",
        "framework coupling",
        "dependency",
        "dependency-direction",
        "dependency_direction",
        "missing-repository",
        "missing_repository",
    },
    "security": {
        "security",
        "authentication",
        "authentication bypass",
        "authentication_bypass",
        "authorization",
        "open redirect",
        "open_redirect",
        "injection",
        "ssrf",
        "server side request forgery",
        "server_side_request_forgery",
        "server-side request forgery",
        "server-side request forgery (ssrf)",
        "path traversal",
        "path_traversal",
        "path traversal (zip slip)",
        "zip slip",
        "zip_slip",
        "directory traversal",
        "directory_traversal",
        "deserialization",
        "unsafe deserialization",
        "unsafe_deserialization",
        "insecure deserialization",
        "insecure_deserialization",
        "insecure-deserialization",
        "sql injection",
        "sql_injection",
        "command injection",
        "command_injection",
        "os command injection",
        "os_command_injection",
        "validation",
        "input_validation",
        "input_validation_runtime_error",
        "incomplete_validation",
        "injection_risk",
        "insecure_configuration",
        "sensitive_data_exposure",
        "cryptographic weakness",
        "cryptographic_weakness",
        "cryptographic-weakness",
    },
    "performance": {
        "performance",
        "cache",
        "caching",
        "algorithmic efficiency",
        "algorithmic_efficiency",
        "missing_cache_invalidation",
        "cache_invalidation",
        "n+1",
        "n_plus_one",
        "query_efficiency",
        "stale_cache",
        "redundant_work",
        "cache_consistency",
        "integration_consistency",
    },
    "best_practices": {
        "best_practices",
        "api_contract",
        "api_mismatch_contract_regression",
        "api_mismatch_runtime_error",
        "api_signature_break",
        "api_signature_change",
        "caller_callee_mismatch",
        "encapsulation",
        "encapsulation_violation",
        "interface_contract_violation",
        "contract_mismatch",
        "layer-leakage",
        "layer_leakage",
        "signature_change",
        "transaction-boundary",
        "transaction_boundary",
        "transactional_safety",
        "transaction_integrity",
        "type_safety",
        "validation_contract_violation",
        "validation_drift",
        "dependency",
        "missing-repository",
        "missing_repository",
    },
    "dead_code": {
        "dead_code",
        "dead code",
        "dead-code",
        "unused_code",
        "unused code",
        "obsolete_code",
        "obsolete code",
        "unreachable_code",
        "unreachable code",
        "dormant_code",
        "dormant code",
    },
    "specification": {
        "specification",
        "spec mismatch",
        "spec_mismatch",
        "behavior_mismatch",
        "behavior mismatch",
        "contract_mismatch",
        "contract mismatch",
        "requirements_gap",
        "requirements gap",
        "functionality",
        "atomicity_violation",
        "atomicity violation",
        "spec_mismatch_return_value",
        "spec mismatch return value",
    },
    "error_handling": {
        "error_handling",
        "error handling",
        "error-handling",
        "exception_handling",
        "exception handling",
        "exception-handling",
        "error_reporting",
        "error reporting",
        "error-reporting",
        "failure_handling",
        "failure handling",
        "failure-handling",
    },
    "data_validation": {
        "data_validation",
        "data validation",
        "data-validation",
        "validation",
        "validation_contract",
        "validation/contract",
        "input_validation",
        "boundary_checks",
        "boundary checks",
        "type_handling",
        "type handling",
    },
    "testing": {
        "testing",
        "test coverage",
        "test_coverage",
        "insufficient test coverage",
        "insufficient_test_coverage",
        "missing tests",
        "missing_tests",
        "testability",
        "error_paths",
        "error paths",
    },
    "documentation": {
        "documentation",
        "documentation mismatch",
        "documentation_mismatch",
        "docs drift",
        "docs_drift",
        "outdated documentation",
        "outdated_documentation",
        "outdated docs",
        "outdated_docs",
        "command example",
        "command_example",
        "cli contract",
        "cli_contract",
        "documentation mismatch / cli contract",
        "outdated documentation / command example",
    },
    "maintainability": {
        "maintainability",
        "duplicated_code",
        "duplicated code",
        "duplicate code",
        "duplicate_logic",
        "duplicate logic",
        "code_reuse",
        "code reuse",
        "technical debt",
        "technical_debt",
        "low cohesion",
        "low_cohesion",
        "god class",
        "god_class",
        "god object",
        "god_object",
        "mixed responsibilities",
        "mixed_responsibilities",
        "separation of concerns",
        "separation_of_concerns",
    },
    "complexity": {
        "complexity",
        "cyclomatic complexity",
        "cyclomatic_complexity",
        "cognitive complexity",
        "cognitive_complexity",
        "nesting",
        "deep nesting",
        "large_method",
        "large method",
        "maintainability",
    },
    "concurrency": {
        "concurrency",
        "race condition",
        "race_condition",
        "thread safety",
        "thread_safety",
        "shared state",
        "shared_state",
        "synchronization",
        "atomicity",
        "concurrent iteration",
        "concurrent_iteration",
        "inconsistent snapshot",
        "inconsistent_snapshot",
    },
    "regression": {
        "regression",
        "behavioral change",
        "behavioral_change",
        "behavior change",
        "behavior_change",
        "cross_file behavioral impact",
        "cross_file_behavioral_impact",
        "breaking change",
        "breaking_change",
    },
    "api_design": {
        "api_design",
        "api design",
        "rest",
        "rest api",
        "rest_api",
        "endpoint design",
        "endpoint_design",
        "http method",
        "http_method",
        "http method / endpoint semantics",
        "http_method_endpoint_semantics",
        "endpoint semantics",
        "endpoint_semantics",
        "request contract",
        "request_contract",
        "request validation spec",
        "request_validation_spec",
        "response modeling",
        "response_modeling",
        "status code",
        "status_code",
    },
    "compatibility": {
        "compatibility",
        "platform compatibility",
        "platform_compatibility",
        "cross-platform",
        "cross_platform",
        "os-specific",
        "os_specific",
        "runtime compatibility",
        "runtime_compatibility",
    },
    "scalability": {
        "scalability",
        "stateful-component",
        "stateful_component",
        "stateful component",
        "throughput bottleneck",
        "throughput_bottleneck",
        "scaling bottleneck",
        "scaling_bottleneck",
        "horizontal scaling",
        "horizontal_scaling",
        "capacity planning",
        "capacity_planning",
        "queue growth",
        "queue_growth",
        "unbounded queue",
        "unbounded_queue",
        "backpressure",
        "deployment configuration",
        "deployment_configuration",
    },
    "dependency": {
        "dependency",
        "dependency management",
        "dependency_management",
        "missing dependency",
        "missing_dependency",
        "undeclared dependency",
        "undeclared_dependency",
        "package declaration",
        "package_declaration",
    },
    "license": {
        "license",
        "license compliance",
        "license_compliance",
        "licensing",
        "license conflict",
        "license_conflict",
        "license compatibility",
        "license_compatibility",
        "license attribution",
        "license_attribution",
        "license declaration",
        "license_declaration",
        "dependency license",
        "dependency_license",
        "third party notice",
        "third_party_notice",
        "attribution",
        "notice requirements",
        "notice_requirements",
    },
    "localization": {
        "localization",
        "i18n",
        "internationalization",
        "internationalisation",
        "hardcoded strings",
        "hardcoded_strings",
        "translation readiness",
        "translation_readiness",
        "locale formatting",
        "locale_formatting",
    },
}

_TEXT_EXPECTATION_ALIASES = {
    "enable cloud sync": (
        "enable cloud sync",
        "cloud sync",
        "cloud_sync_enabled",
        "self.cloud_sync_enabled.get()",
    ),
    "aria-label": (
        "aria-label",
        "aria label",
        "aria labels",
        "aria-labelledby",
        "accessible name",
        "accessible names",
    ),
    "cache": ("cache", "caching", "cached", "キャッシュ"),
    "latency": (
        "latency",
        "response time",
        "response times",
        "throughput",
        "performance degradation",
        "degradation",
        "slower",
        "slowdown",
        "round trip",
        "round trips",
    ),
    "caller": (
        "callers",
        "caller",
        "consumer",
        "consumer expectations",
        "downstream code",
        "downstream payloads",
        "呼び出し元",
        "利用側",
        "下流",
        "コンシューマ",
    ),
    "callers": (
        "callers",
        "caller",
        "consumer",
        "consumer expectations",
        "downstream code",
        "downstream payloads",
        "呼び出し元",
        "利用側",
        "下流",
        "コンシューマ",
    ),
    "commit": (
        "commit",
        "_commit",
        "begin/commit",
        "transaction wrapper",
        "transaction boundary",
        "save_order",
    ),
    "controller": ("controller", "controllers", "コントローラー", "controller.py"),
    "database": ("database", "db", "databases", "データベース", "db.py"),
    "db": ("db", "database", "データベース", "db.py", "execute_query"),
    "confused": (
        "confused",
        "confusion",
        "blank",
        "unclear",
    ),
    "drift": (
        "drift",
        "divergent",
        "diverge",
        "inconsistent",
        "inconsistencies",
        "multiple places",
        "stay synchronized",
        "stay in sync",
    ),
    "disabled": (
        "disabled",
        "disable",
        "disabled by default",
        "turned off",
        "stops working",
        "no longer runs",
        "break",
        "breaks",
        "broken",
    ),
        "build_retry_delay": (
            "build_retry_delay",
            "signature changed in src/retry_policy.py",
            "retry_policy.py changes build_retry_delay",
            "(retry_count, network_profile) to (network_profile, retry_count)",
        ),
    "except exception": (
        "except exception",
        "except returns status 'completed'",
        "except returns status completed",
        "except block in run_import catches all exceptions and returns",
        "returns status 'completed'",
        "returns completed even on exception",
    ),
    "full_name": ("full_name", "display_name"),
    "horizontal": (
        "horizontal",
        "horizontally",
        "global",
        "distributed",
        "different workers",
        "multiple workers",
        "multiple instances",
        "across workers",
        "across instances",
    ),
    "user_profile": (
        "user_profile",
        "get_user_profile",
        "set_user_profile",
        "update_user_profile",
        "profile",
        "profiles",
    ),
    "email": ("email", "emails"),
    "invoice_id": (
        "invoice_id",
        "invoice id",
        "account_id",
        "account id",
        "ownership",
        "belongs to the current account",
        "belongs to the requesting account",
    ),
    "invalid": (
        "invalid",
        "unvalidated",
        "incompletely validated",
        "impossible state",
        "negative duration",
        "negative durations",
        "incorrect scheduling",
        "bad data",
    ),
    "operator": (
        "operator",
        "operators",
        "user",
        "users",
        "automation",
        "workflow",
        "workflows",
        "documentation-led workflows",
        "tutorial",
        "tutorials",
        "ci",
        "mislead",
        "misleading",
    ),
    "invalidate": (
        "invalidate",
        "invalidates",
        "invalidated",
        "invalidating",
        "invalidation",
        "evict",
        "eviction",
        "refresh",
        "refreshes",
    ),
    "layer": (
        "layer",
        "layered",
        "layer boundary",
        "layer boundaries",
        "boundary",
        "boundaries",
        "coupled",
        "coupling",
        "tightly coupled",
        "dependency direction",
        "separation of concerns",
        "architecture",
        "アーキテクチャ",
        "レイヤー",
        "依存関係ルール",
    ),
    "privilege": (
        "privilege",
        "authorization",
        "unauthorized",
        "admin",
        "access control",
        "権限",
        "認可",
        "アクセス制御",
        "管理者",
    ),
    "recovery": (
        "recovery",
        "recover",
        "recovers",
        "delayed recovery",
        "automatic recovery",
        "retry",
        "retries",
        "retryable",
        "outage",
        "prolonged outage",
        "missed syncs",
    ),
    "regression": (
        "regression",
        "regress",
        "regresses",
        "regressions",
        "regress silently",
        "ship unnoticed",
        "ship unnoticed because",
        "unpinned",
        "without a failing test",
    ),
    "require_admin": ("require_admin", "admin guard", "guard", "管理者ガード", "ガード"),
    "transaction": ("transaction", "transactional", "トランザクション"),
    "signature verification": (
        "signature verification",
        "verify_signature",
        "verifying signature",
        "without verifying signature",
        "signature verification disabled",
        "signature checks",
        "signature validation",
    ),
    "unvalidated": (
        "unvalidated",
        "not validated",
        "never validated",
        "validation gap",
        "invalid emails",
        "malformed input",
        "malformed inputs",
        "malformed data",
        "without email",
        "missing email",
        "未検証",
        "検証されていない",
        "検証不足",
        "バリデーション漏れ",
    ),
    "obsolete": (
        "obsolete",
        "unused",
        "unreachable",
        "dormant",
        "deprecated",
        "permanently disabled",
        "no callers",
        "no live caller",
        "no live wiring",
    ),
    "unused": (
        "unused",
        "obsolete",
        "unreachable",
        "dormant",
        "deprecated",
        "no callers",
        "no live caller",
        "no live wiring",
        "effectively dead code",
    ),
    "validation": ("validation", "validate", "validator", "検証", "バリデーション"),
}


@dataclass(frozen=True)
class BenchmarkExpectation:
    """Expected finding characteristics for a benchmark fixture."""

    id: str
    description_keywords: list[str] = field(default_factory=list)
    file_path_contains: str | None = None
    file_path_contains_any: list[str] = field(default_factory=list)
    issue_type: str | None = None
    minimum_severity: str | None = None
    context_scope: str | None = None
    related_files_contains: list[str] = field(default_factory=list)
    systemic_impact_contains: str | None = None
    evidence_basis_contains: str | None = None


@dataclass(frozen=True)
class BenchmarkFixture:
    """Structured definition for a holistic review benchmark scenario."""

    id: str
    title: str
    description: str
    scope: str
    review_types: list[str]
    minimum_score: float
    manifest_path: Path
    project_dir: Path | None
    diff_file: Path | None
    spec_file: Path | None
    expected_findings: list[BenchmarkExpectation]


@dataclass(frozen=True)
class ExpectationEvaluation:
    """Match result for a single expectation."""

    expectation_id: str
    matched: bool
    matched_issue_id: str | None = None
    matched_file_path: str | None = None
    reason: str | None = None
    failed_checks: list[str] = field(default_factory=list)
    best_candidate_issue_id: str | None = None
    best_candidate_file_path: str | None = None


@dataclass(frozen=True)
class FixtureEvaluation:
    """Aggregate evaluation result for a fixture/report pair."""

    fixture_id: str
    title: str
    report_path: str | None
    passed: bool
    score: float
    minimum_score: float
    matched_expectations: int
    total_expectations: int
    missing_report: bool
    expectation_results: list[ExpectationEvaluation]
    benchmark_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _resolve_fixture_path(
    manifest_path: Path,
    raw_path: Any,
    *,
    field_name: str,
    allowed_root: Path | None = None,
) -> Path | None:
    if not raw_path:
        return None
    candidate = Path(str(raw_path)).expanduser()
    base_dir = manifest_path.parent
    resolved = candidate.resolve() if candidate.is_absolute() else (base_dir / candidate).resolve()
    if allowed_root is not None:
        resolved_root = allowed_root.expanduser().resolve()
        if not (resolved == resolved_root or resolved.is_relative_to(resolved_root)):
            raise ValueError(
                f"Benchmark fixture '{manifest_path}' field '{field_name}' must stay within the fixtures root"
            )
    return resolved


def load_fixture(manifest_path: Path, *, allowed_root: Path | None = None) -> BenchmarkFixture:
    """Load a single benchmark fixture manifest."""
    payload = _load_json(manifest_path)
    expectations = [
        BenchmarkExpectation(
            id=str(item["id"]),
            description_keywords=[str(keyword) for keyword in item.get("description_keywords", [])],
            file_path_contains=(str(item["file_path_contains"]) if item.get("file_path_contains") else None),
            file_path_contains_any=[str(entry) for entry in item.get("file_path_contains_any", [])],
            issue_type=(str(item["issue_type"]) if item.get("issue_type") else None),
            minimum_severity=(str(item["minimum_severity"]) if item.get("minimum_severity") else None),
            context_scope=(str(item["context_scope"]) if item.get("context_scope") else None),
            related_files_contains=[str(entry) for entry in item.get("related_files_contains", [])],
            systemic_impact_contains=(
                str(item["systemic_impact_contains"])
                if item.get("systemic_impact_contains")
                else None
            ),
            evidence_basis_contains=(
                str(item["evidence_basis_contains"])
                if item.get("evidence_basis_contains")
                else None
            ),
        )
        for item in payload.get("expected_findings", [])
    ]
    return BenchmarkFixture(
        id=str(payload["id"]),
        title=str(payload["title"]),
        description=str(payload["description"]),
        scope=str(payload.get("scope", "project")),
        review_types=[str(entry) for entry in payload.get("review_types", [])],
        minimum_score=float(payload.get("minimum_score", 1.0)),
        manifest_path=manifest_path,
        project_dir=_resolve_fixture_path(
            manifest_path,
            payload.get("project_dir"),
            field_name="project_dir",
            allowed_root=allowed_root,
        ),
        diff_file=_resolve_fixture_path(
            manifest_path,
            payload.get("diff_file"),
            field_name="diff_file",
            allowed_root=allowed_root,
        ),
        spec_file=_resolve_fixture_path(
            manifest_path,
            payload.get("spec_file"),
            field_name="spec_file",
            allowed_root=allowed_root,
        ),
        expected_findings=expectations,
    )


def discover_fixtures(fixtures_root: Path) -> list[BenchmarkFixture]:
    """Discover all benchmark fixture manifests below *fixtures_root*."""
    resolved_root = fixtures_root.expanduser().resolve()
    manifests = sorted(resolved_root.rglob("fixture.json"))
    return [load_fixture(path, allowed_root=resolved_root) for path in manifests]


def _extract_report(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("report"), dict):
        return payload["report"]
    if isinstance(payload.get("issues_found"), list):
        return payload
    if isinstance(payload.get("issues"), list):
        return {"issues_found": payload["issues"]}
    raise ValueError("Benchmark report input must be a raw review report or a tool-mode envelope with a 'report' object")


def load_report(path: Path) -> dict[str, Any]:
    """Load a raw review report or tool-mode review envelope."""
    return _extract_report(_load_json(path))


def _resolve_related_issue_paths(issue: dict[str, Any], raw_issues: Sequence[dict[str, Any]]) -> list[str]:
    related_paths: list[str] = []
    raw_related = issue.get("related_issues")
    if not isinstance(raw_related, list):
        return related_paths

    file_path = str(issue.get("file_path") or issue.get("file") or "")
    issue_id_lookup = {
        str(candidate.get("issue_id") or ""): candidate
        for candidate in raw_issues
        if isinstance(candidate, dict)
    }

    for entry in raw_related:
        candidate: dict[str, Any] | None = None
        if isinstance(entry, int) and 0 <= entry < len(raw_issues):
            raw_candidate = raw_issues[entry]
            candidate = raw_candidate if isinstance(raw_candidate, dict) else None
        elif isinstance(entry, str):
            candidate = issue_id_lookup.get(entry)

        if not candidate:
            continue

        candidate_path = str(candidate.get("file_path") or candidate.get("file") or "")
        if candidate_path and candidate_path != file_path and candidate_path not in related_paths:
            related_paths.append(candidate_path)

    return related_paths


def _path_match_keys(path: str) -> set[str]:
    if not path:
        return set()
    normalized = path.replace("\\", "/").lower()
    return {normalized, Path(normalized).name}


def _participates_in_explicit_cross_file_chain(
    file_path: str,
    related_files: Sequence[str],
    raw_issues: Sequence[dict[str, Any]],
) -> bool:
    current_keys = _path_match_keys(file_path)
    if not current_keys:
        return False

    current_related_keys = {
        key
        for entry in related_files
        for key in _path_match_keys(str(entry))
    }

    for candidate in raw_issues:
        if not isinstance(candidate, dict):
            continue
        candidate_path = str(candidate.get("file_path") or candidate.get("file") or "")
        candidate_keys = _path_match_keys(candidate_path)
        if not candidate_keys or candidate_keys == current_keys:
            continue

        candidate_related = candidate.get("related_files")
        candidate_related_files = [str(entry) for entry in candidate_related] if isinstance(candidate_related, list) else []
        for resolved_path in _resolve_related_issue_paths(candidate, raw_issues):
            if resolved_path not in candidate_related_files:
                candidate_related_files.append(resolved_path)
        candidate_related_keys = {
            key
            for entry in candidate_related_files
            for key in _path_match_keys(str(entry))
        }

        if current_keys & candidate_related_keys:
            return True
        if candidate_keys & current_related_keys:
            return True

    return False


def _normalize_issue(issue: dict[str, Any], raw_issues: Sequence[dict[str, Any]]) -> dict[str, Any]:
    related_files = issue.get("related_files")
    if not isinstance(related_files, list):
        related_files = []
    resolved_related_paths = _resolve_related_issue_paths(issue, raw_issues)
    normalized_related_files = [str(entry) for entry in related_files if entry]
    for candidate_path in resolved_related_paths:
        if candidate_path not in normalized_related_files:
            normalized_related_files.append(candidate_path)

    normalized_issue_type = re.sub(
        r"[\s\-/]+",
        "_",
        str(issue.get("issue_type") or "").lower(),
    ).strip("_")
    raw_context_scope = str(issue.get("context_scope") or "local").lower()
    normalized_context_scope = (
        "cross_file"
        if raw_context_scope == "local" and resolved_related_paths
        else raw_context_scope
    )

    normalized_file_path = str(issue.get("file_path") or issue.get("file") or "")
    file_name = Path(normalized_file_path).name.lower()
    related_names = {
        Path(entry).name.lower()
        for entry in normalized_related_files
        if isinstance(entry, str) and entry
    }
    if (
        normalized_context_scope == "cross_file"
        and related_names
        and related_names == {file_name}
    ):
        normalized_context_scope = "local"
    if (
        normalized_context_scope == "project"
        and related_names
        and related_names != {file_name}
        and normalized_issue_type != "architecture"
    ):
        normalized_context_scope = "cross_file"
    if (
        normalized_context_scope == "local"
        and _participates_in_explicit_cross_file_chain(
            normalized_file_path,
            normalized_related_files,
            raw_issues,
        )
    ):
        normalized_context_scope = "cross_file"

    return {
        "issue_id": str(issue.get("issue_id") or ""),
        "file_path": normalized_file_path,
        "issue_type": str(issue.get("issue_type") or issue.get("type") or ""),
        "severity": str(issue.get("severity") or "medium").lower(),
        "description": str(issue.get("description") or ""),
        "ai_feedback": str(issue.get("ai_feedback") or issue.get("feedback") or ""),
        "context_scope": normalized_context_scope,
        "related_files": normalized_related_files,
        "systemic_impact": str(issue.get("systemic_impact") or ""),
        "evidence_basis": str(issue.get("evidence_basis") or ""),
    }


def _severity_meets(actual: str, minimum: str) -> bool:
    return _SEVERITY_ORDER.get(actual.lower(), -1) >= _SEVERITY_ORDER.get(minimum.lower(), -1)


def _contains_all(text: str, substrings: list[str]) -> bool:
    return all(_contains_expected_phrase(text, substring) for substring in substrings)


def _contains_expected_phrase(text: str, expected: str) -> bool:
    haystack = text.lower()
    normalized_expected = expected.lower()
    aliases = _TEXT_EXPECTATION_ALIASES.get(normalized_expected, (normalized_expected,))
    return any(alias in haystack for alias in aliases)


def _related_files_match(
    file_path: str,
    related_files: list[str],
    expected_substrings: list[str],
) -> bool:
    lowered = [file_path.lower(), *[entry.lower() for entry in related_files]]
    return all(any(expected.lower() in entry for entry in lowered) for expected in expected_substrings)


def _issue_type_matches(expected: str, actual: str) -> bool:
    expected_normalized = re.sub(r"[\s\-\|/]+", "_", expected.lower().strip())
    actual_normalized = re.sub(r"[\s\-\|/]+", "_", actual.lower().strip())
    if expected_normalized == actual_normalized:
        return True
    aliases = {
        re.sub(r"[\s\-\|/]+", "_", alias.lower().strip())
        for alias in _ISSUE_TYPE_ALIASES.get(expected_normalized, set())
    }
    try:
        aliases.update(
            re.sub(r"[\s\-\|/]+", "_", alias.lower().strip())
            for alias in get_review_registry().get(expected_normalized).category_aliases
        )
    except (KeyError, RuntimeError):
        pass
    actual_parts = {part for part in actual_normalized.split("_") if part}
    if aliases is not None and (
        actual_normalized in aliases
        or any(alias in actual_parts for alias in aliases)
    ):
        return True
    return False


def _issue_match_diagnostics(issue: dict[str, Any], expectation: BenchmarkExpectation) -> dict[str, bool]:
    """Return per-criterion pass/fail details for an issue against an expectation."""
    file_path = issue["file_path"]
    combined_text = "\n".join(
        [
            issue["description"],
            issue["ai_feedback"],
            issue["systemic_impact"],
            issue["evidence_basis"],
        ]
    )
    return {
        "file_path_contains": (
            True if not expectation.file_path_contains
            else expectation.file_path_contains.lower() in file_path.lower()
        ),
        "file_path_contains_any": (
            True if not expectation.file_path_contains_any
            else any(entry.lower() in file_path.lower() for entry in expectation.file_path_contains_any)
        ),
        "issue_type": (
            True if not expectation.issue_type
            else _issue_type_matches(expectation.issue_type, issue["issue_type"])
        ),
        "minimum_severity": (
            True if not expectation.minimum_severity
            else _severity_meets(issue["severity"], expectation.minimum_severity)
        ),
        "context_scope": (
            True if not expectation.context_scope
            else expectation.context_scope.lower() == issue["context_scope"].lower()
        ),
        "related_files_contains": (
            True if not expectation.related_files_contains
            else _related_files_match(
                issue["file_path"],
                issue["related_files"],
                expectation.related_files_contains,
            )
        ),
        "description_keywords": (
            True if not expectation.description_keywords
            else _contains_all(combined_text, expectation.description_keywords)
        ),
        "systemic_impact_contains": (
            True if not expectation.systemic_impact_contains
            else _contains_expected_phrase(issue["systemic_impact"], expectation.systemic_impact_contains)
        ),
        "evidence_basis_contains": (
            True if not expectation.evidence_basis_contains
            else _contains_expected_phrase(issue["evidence_basis"], expectation.evidence_basis_contains)
        ),
    }


def _issue_matches(issue: dict[str, Any], expectation: BenchmarkExpectation) -> bool:
    return all(_issue_match_diagnostics(issue, expectation).values())


def _string_list_metadata(value: Any) -> list[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        return [entry.strip() for entry in value if isinstance(entry, str) and entry.strip()]
    return []


def collect_benchmark_metadata(review_types: Sequence[str]) -> dict[str, Any]:
    """Aggregate registry-backed benchmark metadata for selected review types."""
    try:
        registry = get_review_registry()
    except RuntimeError:
        return {}

    review_type_entries: list[dict[str, Any]] = []
    fixture_tags: list[str] = []
    expected_focus: list[str] = []
    seen_review_types: set[str] = set()
    seen_tags: set[str] = set()
    seen_focus: set[str] = set()

    for raw_review_type in review_types:
        try:
            canonical_key = registry.resolve_key(raw_review_type)
            definition = registry.get(canonical_key)
        except KeyError:
            continue
        if canonical_key in seen_review_types:
            continue
        seen_review_types.add(canonical_key)
        metadata = dict(definition.benchmark_metadata)
        if not metadata:
            continue

        review_type_entries.append(
            {
                "key": canonical_key,
                "label": definition.label,
                "group": definition.group,
                "metadata": metadata,
            }
        )

        for tag in _string_list_metadata(metadata.get("fixture_tags")):
            normalized_tag = tag.lower()
            if normalized_tag not in seen_tags:
                fixture_tags.append(tag)
                seen_tags.add(normalized_tag)

        for focus in _string_list_metadata(metadata.get("expected_focus")):
            normalized_focus = focus.lower()
            if normalized_focus not in seen_focus:
                expected_focus.append(focus)
                seen_focus.add(normalized_focus)

    aggregated: dict[str, Any] = {}
    if fixture_tags:
        aggregated["fixture_tags"] = fixture_tags
    if expected_focus:
        aggregated["expected_focus"] = expected_focus
    if review_type_entries:
        aggregated["review_types"] = review_type_entries
    return aggregated


def _summarize_benchmark_metadata(results: Sequence[FixtureEvaluation]) -> dict[str, Any]:
    fixture_tags: list[str] = []
    expected_focus: list[str] = []
    review_type_entries: list[dict[str, Any]] = []
    seen_tags: set[str] = set()
    seen_focus: set[str] = set()
    seen_review_types: set[str] = set()

    for result in results:
        metadata = result.benchmark_metadata
        if not metadata:
            continue

        for tag in _string_list_metadata(metadata.get("fixture_tags")):
            normalized_tag = tag.lower()
            if normalized_tag not in seen_tags:
                fixture_tags.append(tag)
                seen_tags.add(normalized_tag)

        for focus in _string_list_metadata(metadata.get("expected_focus")):
            normalized_focus = focus.lower()
            if normalized_focus not in seen_focus:
                expected_focus.append(focus)
                seen_focus.add(normalized_focus)

        raw_review_types = metadata.get("review_types")
        if not isinstance(raw_review_types, list):
            continue
        for entry in raw_review_types:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or "").strip().lower()
            if not key or key in seen_review_types:
                continue
            review_type_entries.append(entry)
            seen_review_types.add(key)

    aggregated: dict[str, Any] = {}
    if fixture_tags:
        aggregated["fixture_tags"] = fixture_tags
    if expected_focus:
        aggregated["expected_focus"] = expected_focus
    if review_type_entries:
        aggregated["review_types"] = review_type_entries
    return aggregated


def _best_candidate_match(
    issues: Sequence[dict[str, Any]],
    expectation: BenchmarkExpectation,
    used_indices: set[int],
) -> tuple[int | None, list[str]]:
    """Return the closest unmatched issue index and the checks it failed."""
    best_index: int | None = None
    best_failures: list[str] = []
    best_score = -1
    best_issue_type_match = False
    best_context_scope_match = False

    for index, issue in enumerate(issues):
        if index in used_indices:
            continue
        diagnostics = _issue_match_diagnostics(issue, expectation)
        passed_count = sum(1 for passed in diagnostics.values() if passed)
        failures = [name for name, passed in diagnostics.items() if not passed]
        issue_type_match = diagnostics.get("issue_type", True)
        context_scope_match = diagnostics.get("context_scope", True)
        if (
            passed_count > best_score
            or (passed_count == best_score and issue_type_match and not best_issue_type_match)
            or (
                passed_count == best_score
                and issue_type_match == best_issue_type_match
                and context_scope_match
                and not best_context_scope_match
            )
        ):
            best_index = index
            best_failures = failures
            best_score = passed_count
            best_issue_type_match = issue_type_match
            best_context_scope_match = context_scope_match

    return best_index, best_failures


def evaluate_fixture(fixture: BenchmarkFixture, report: dict[str, Any], report_path: Path | None = None) -> FixtureEvaluation:
    """Evaluate a single report against a benchmark fixture."""
    raw_issues = report.get("issues_found", [])
    if not isinstance(raw_issues, list):
        raise ValueError("Report must contain an 'issues_found' list")
    issues = [_normalize_issue(issue, raw_issues) for issue in raw_issues if isinstance(issue, dict)]
    benchmark_metadata = collect_benchmark_metadata(fixture.review_types)

    used_indices: set[int] = set()
    expectation_results: list[ExpectationEvaluation] = []
    matched_count = 0

    for expectation in fixture.expected_findings:
        matched_index = None
        for index, issue in enumerate(issues):
            if index in used_indices:
                continue
            if _issue_matches(issue, expectation):
                matched_index = index
                break

        if matched_index is None:
            best_index, failed_checks = _best_candidate_match(issues, expectation, used_indices)
            best_issue = issues[best_index] if best_index is not None else None
            expectation_results.append(
                ExpectationEvaluation(
                    expectation_id=expectation.id,
                    matched=False,
                    reason="No issue matched the expected holistic finding",
                    failed_checks=failed_checks,
                    best_candidate_issue_id=(best_issue["issue_id"] or None) if best_issue else None,
                    best_candidate_file_path=(best_issue["file_path"] or None) if best_issue else None,
                )
            )
            continue

        used_indices.add(matched_index)
        matched_issue = issues[matched_index]
        matched_count += 1
        expectation_results.append(
            ExpectationEvaluation(
                expectation_id=expectation.id,
                matched=True,
                matched_issue_id=matched_issue["issue_id"] or None,
                matched_file_path=matched_issue["file_path"] or None,
            )
        )

    total = max(1, len(fixture.expected_findings))
    score = matched_count / total
    return FixtureEvaluation(
        fixture_id=fixture.id,
        title=fixture.title,
        report_path=str(report_path) if report_path else None,
        passed=score >= fixture.minimum_score,
        score=score,
        minimum_score=fixture.minimum_score,
        matched_expectations=matched_count,
        total_expectations=len(fixture.expected_findings),
        missing_report=False,
        benchmark_metadata=benchmark_metadata,
        expectation_results=expectation_results,
    )


def evaluate_fixture_file(fixture: BenchmarkFixture, report_path: Path) -> FixtureEvaluation:
    """Evaluate a report file against one fixture."""
    benchmark_metadata = collect_benchmark_metadata(fixture.review_types)
    try:
        report = load_report(report_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return FixtureEvaluation(
            fixture_id=fixture.id,
            title=fixture.title,
            report_path=str(report_path),
            passed=False,
            score=0.0,
            minimum_score=fixture.minimum_score,
            matched_expectations=0,
            total_expectations=len(fixture.expected_findings),
            missing_report=False,
            benchmark_metadata=benchmark_metadata,
            expectation_results=[
                ExpectationEvaluation(
                    expectation_id=expectation.id,
                    matched=False,
                    reason=f"Invalid report payload: {exc}",
                )
                for expectation in fixture.expected_findings
            ],
        )
    return evaluate_fixture(fixture, report, report_path=report_path)


def evaluate_fixture_directory(fixtures: Sequence[BenchmarkFixture], reports_dir: Path) -> list[FixtureEvaluation]:
    """Evaluate a directory of reports named by fixture id."""
    results: list[FixtureEvaluation] = []
    for fixture in fixtures:
        report_path = reports_dir / f"{fixture.id}.json"
        benchmark_metadata = collect_benchmark_metadata(fixture.review_types)
        if not report_path.exists():
            results.append(
                FixtureEvaluation(
                    fixture_id=fixture.id,
                    title=fixture.title,
                    report_path=str(report_path),
                    passed=False,
                    score=0.0,
                    minimum_score=fixture.minimum_score,
                    matched_expectations=0,
                    total_expectations=len(fixture.expected_findings),
                    missing_report=True,
                    benchmark_metadata=benchmark_metadata,
                    expectation_results=[
                        ExpectationEvaluation(
                            expectation_id=expectation.id,
                            matched=False,
                            reason="Missing report file",
                        )
                        for expectation in fixture.expected_findings
                    ],
                )
            )
            continue
        results.append(evaluate_fixture_file(fixture, report_path))
    return results


def summarize_results(results: Sequence[FixtureEvaluation]) -> dict[str, Any]:
    """Build a machine-readable summary for a benchmark run."""
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    overall_score = (
        sum(result.score for result in results) / total if total else 0.0
    )
    summary = {
        "fixtures_evaluated": total,
        "fixtures_passed": passed,
        "fixtures_failed": total - passed,
        "overall_score": round(overall_score, 4),
        "results": [result.to_dict() for result in results],
    }
    benchmark_metadata = _summarize_benchmark_metadata(results)
    if benchmark_metadata:
        summary["benchmark_metadata"] = benchmark_metadata
    return summary


def describe_fixture_invocation(fixture: BenchmarkFixture) -> dict[str, Any]:
    """Return the review invocation shape needed to execute a fixture."""
    payload: dict[str, Any] = {
        "fixture_id": fixture.id,
        "scope": fixture.scope,
        "review_types": list(fixture.review_types),
    }
    benchmark_metadata = collect_benchmark_metadata(fixture.review_types)
    if benchmark_metadata:
        payload["benchmark_metadata"] = benchmark_metadata
    if fixture.project_dir is not None:
        payload["path"] = str(fixture.project_dir)
    if fixture.diff_file is not None:
        payload["diff_file"] = str(fixture.diff_file)
    if fixture.spec_file is not None:
        payload["spec_file"] = str(fixture.spec_file)
    return payload


def describe_fixture_catalog_entry(fixture: BenchmarkFixture) -> dict[str, Any]:
    """Return fixture metadata for selection or comparison UIs."""
    payload = {
        "id": fixture.id,
        "title": fixture.title,
        "scope": fixture.scope,
        "review_types": list(fixture.review_types),
    }
    benchmark_metadata = collect_benchmark_metadata(fixture.review_types)
    if benchmark_metadata:
        payload["benchmark_metadata"] = benchmark_metadata
    return payload


def _default_fixtures_root() -> Path:
    return Path(__file__).resolve().parents[2] / "benchmarks" / "holistic_review" / "fixtures"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate AICodeReviewer output against holistic review benchmark fixtures",
    )
    parser.add_argument(
        "--fixtures-root",
        default=str(_default_fixtures_root()),
        help="Directory containing benchmark fixture manifests",
    )
    parser.add_argument(
        "--report-dir",
        help="Directory containing report JSON files named <fixture-id>.json",
    )
    parser.add_argument(
        "--fixture",
        help="Evaluate a single fixture id (requires --report-file)",
    )
    parser.add_argument(
        "--report-file",
        help="Single review report or tool-mode review envelope to evaluate",
    )
    parser.add_argument(
        "--json-out",
        help="Optional path to also write the JSON summary",
    )
    parser.add_argument(
        "--list-fixtures",
        action="store_true",
        help="List available fixture ids and exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the holistic benchmark evaluator."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    fixtures = discover_fixtures(Path(args.fixtures_root))
    if args.list_fixtures:
        payload = {
            "fixtures": [
                describe_fixture_catalog_entry(fixture)
                for fixture in fixtures
            ]
        }
        rendered = json.dumps(payload, indent=2)
        print(rendered)
        return 0

    if bool(args.report_dir) == bool(args.report_file):
        parser.error("Provide exactly one of --report-dir or --report-file")
    if args.report_file and not args.fixture:
        parser.error("--fixture is required with --report-file")
    if args.fixture and not args.report_file:
        parser.error("--report-file is required with --fixture")

    if args.report_dir:
        results = evaluate_fixture_directory(fixtures, Path(args.report_dir))
    else:
        fixture = next((entry for entry in fixtures if entry.id == args.fixture), None)
        if fixture is None:
            parser.error(f"Unknown fixture id: {args.fixture}")
        results = [evaluate_fixture_file(fixture, Path(args.report_file))]

    summary = summarize_results(results)
    rendered = json.dumps(summary, indent=2)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())