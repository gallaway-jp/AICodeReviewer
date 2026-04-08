from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from aicodereviewer.addon_generator import GeneratedAddonPreview, generate_addon_preview


_DEFAULT_REVIEW_TYPES = ("best_practices", "maintainability", "testing")
_EXPECTED_FIELDS = (
    "languages",
    "frameworks",
    "tools",
    "test_harnesses",
    "manifests",
    "relevant_review_types",
)

_DEFAULT_THRESHOLD_RULES: tuple[dict[str, Any], ...] = (
    {
        "key": "languages_recall",
        "label": "Language recall",
        "metric_path": ("heuristic_summary", "languages", "average_recall"),
        "minimum": 0.95,
        "severity": "failure",
    },
    {
        "key": "frameworks_f1",
        "label": "Framework F1",
        "metric_path": ("heuristic_summary", "frameworks", "average_f1"),
        "minimum": 0.65,
        "severity": "failure",
    },
    {
        "key": "manifests_recall",
        "label": "Manifest recall",
        "metric_path": ("heuristic_summary", "manifests", "average_recall"),
        "minimum": 0.85,
        "severity": "failure",
    },
    {
        "key": "tools_f1",
        "label": "Tooling F1",
        "metric_path": ("heuristic_summary", "tools", "average_f1"),
        "minimum": 0.60,
        "severity": "warning",
    },
    {
        "key": "test_harness_recall",
        "label": "Test harness recall",
        "metric_path": ("heuristic_summary", "test_harnesses", "average_recall"),
        "minimum": 0.60,
        "severity": "warning",
    },
    {
        "key": "bundle_f1_delta",
        "label": "Bundle relevance F1 delta",
        "metric_path": ("bundle_relevance_summary", "average_f1_delta"),
        "minimum": 0.0,
        "severity": "failure",
    },
    {
        "key": "bundle_recall_delta",
        "label": "Bundle relevance recall delta",
        "metric_path": ("bundle_relevance_summary", "average_recall_delta"),
        "minimum": 0.0,
        "severity": "warning",
    },
)


@dataclass(frozen=True)
class ExternalRepositoryTarget:
    repo_id: str
    repo_url: str
    checkout_dir: str
    ref: str | None = None
    languages: tuple[str, ...] = ()
    frameworks: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    test_harnesses: tuple[str, ...] = ()
    manifests: tuple[str, ...] = ()
    relevant_review_types: tuple[str, ...] = ()


def load_external_repository_catalog(catalog_path: str | Path) -> list[ExternalRepositoryTarget]:
    path = Path(catalog_path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"External repository catalog must contain an object: {path}")
    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        raise ValueError(f"External repository catalog must contain a 'repositories' list: {path}")

    targets: list[ExternalRepositoryTarget] = []
    for entry in repositories:
        if not isinstance(entry, dict):
            raise ValueError(f"Catalog entry must be an object: {path}")
        expected = entry.get("expected")
        if not isinstance(expected, dict):
            raise ValueError(f"Catalog entry is missing an 'expected' object: {entry}")
        targets.append(
            ExternalRepositoryTarget(
                repo_id=_coerce_non_empty_string(entry.get("id"), "id"),
                repo_url=_coerce_non_empty_string(entry.get("repo_url"), "repo_url"),
                checkout_dir=_coerce_non_empty_string(entry.get("checkout_dir"), "checkout_dir"),
                ref=_coerce_optional_string(entry.get("ref")),
                languages=tuple(_coerce_string_list(expected.get("languages"))),
                frameworks=tuple(_coerce_string_list(expected.get("frameworks"))),
                tools=tuple(_coerce_string_list(expected.get("tools"))),
                test_harnesses=tuple(_coerce_string_list(expected.get("test_harnesses"))),
                manifests=tuple(_coerce_string_list(expected.get("manifests"))),
                relevant_review_types=tuple(_coerce_string_list(expected.get("relevant_review_types"))),
            )
        )
    return targets


def ensure_repository_checkout(
    target: ExternalRepositoryTarget,
    repos_root: str | Path,
    *,
    refresh: bool = False,
    skip_clone: bool = False,
) -> Path:
    root = Path(repos_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    checkout_path = root / target.checkout_dir
    if checkout_path.is_dir():
        if refresh:
            _run_git(["git", "-C", str(checkout_path), "pull", "--ff-only"])
        return checkout_path

    if skip_clone:
        raise ValueError(f"Repository checkout is missing and cloning is disabled: {checkout_path}")

    clone_command = ["git", "clone", "--depth", "1"]
    if target.ref:
        clone_command.extend(["--branch", target.ref])
    clone_command.extend([target.repo_url, str(checkout_path)])
    _run_git(clone_command)
    return checkout_path


def evaluate_external_repository(
    target: ExternalRepositoryTarget,
    repo_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    context_logger = logging.getLogger("aicodereviewer.context_collector")
    previous_context_level = context_logger.level
    try:
        context_logger.setLevel(logging.WARNING)
        preview = generate_addon_preview(
            repo_path,
            Path(output_dir).resolve() / target.repo_id,
            addon_id=f"{target.repo_id}-adaptive-review",
            addon_name=f"{target.repo_id} Adaptive Review Addon",
        )
    finally:
        context_logger.setLevel(previous_context_level)
    profile = preview.profile.to_dict()
    heuristic_scores = {
        "languages": _score_signal_set(target.languages, profile.get("languages", [])),
        "frameworks": _score_signal_set(target.frameworks, profile.get("frameworks", [])),
        "tools": _score_signal_set(target.tools, profile.get("tools", [])),
        "test_harnesses": _score_signal_set(target.test_harnesses, profile.get("test_harnesses", [])),
        "manifests": _score_signal_set(target.manifests, profile.get("manifests", [])),
    }

    generated_bundle = _normalize_generated_bundle(preview)
    default_bundle = list(_DEFAULT_REVIEW_TYPES)
    expected_focus = list(target.relevant_review_types)
    generated_relevance = _score_signal_set(expected_focus, generated_bundle)
    default_relevance = _score_signal_set(expected_focus, default_bundle)

    return {
        "repo_id": target.repo_id,
        "repo_url": target.repo_url,
        "repo_path": str(Path(repo_path).resolve()),
        "preview_dir": str((Path(output_dir).resolve() / target.repo_id)),
        "profile": profile,
        "heuristic_scores": heuristic_scores,
        "bundle_relevance": {
            "expected_review_types": expected_focus,
            "generated_bundle": generated_bundle,
            "default_bundle": default_bundle,
            "generated": generated_relevance,
            "default": default_relevance,
            "f1_delta": round(generated_relevance["f1"] - default_relevance["f1"], 4),
            "recall_delta": round(generated_relevance["recall"] - default_relevance["recall"], 4),
            "precision_delta": round(generated_relevance["precision"] - default_relevance["precision"], 4),
        },
    }


def summarize_external_repository_results(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    repositories = list(results)
    summary: dict[str, Any] = {
        "repositories_evaluated": len(repositories),
        "repositories": repositories,
    }
    if not repositories:
        return summary

    heuristic_summary: dict[str, Any] = {}
    for field_name in ("languages", "frameworks", "tools", "test_harnesses", "manifests"):
        scores = [repo["heuristic_scores"][field_name] for repo in repositories]
        heuristic_summary[field_name] = {
            "average_precision": round(mean(score["precision"] for score in scores), 4),
            "average_recall": round(mean(score["recall"] for score in scores), 4),
            "average_f1": round(mean(score["f1"] for score in scores), 4),
        }
    summary["heuristic_summary"] = heuristic_summary

    relevance_rows = [repo["bundle_relevance"] for repo in repositories]
    summary["bundle_relevance_summary"] = {
        "generated_average_f1": round(mean(row["generated"]["f1"] for row in relevance_rows), 4),
        "default_average_f1": round(mean(row["default"]["f1"] for row in relevance_rows), 4),
        "generated_average_recall": round(mean(row["generated"]["recall"] for row in relevance_rows), 4),
        "default_average_recall": round(mean(row["default"]["recall"] for row in relevance_rows), 4),
        "average_f1_delta": round(mean(row["f1_delta"] for row in relevance_rows), 4),
        "average_recall_delta": round(mean(row["recall_delta"] for row in relevance_rows), 4),
        "repositories_generated_better": sum(1 for row in relevance_rows if row["f1_delta"] > 0),
        "repositories_tied": sum(1 for row in relevance_rows if row["f1_delta"] == 0),
        "repositories_default_better": sum(1 for row in relevance_rows if row["f1_delta"] < 0),
    }
    return summary


def evaluate_external_repository_thresholds(summary: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for rule in _DEFAULT_THRESHOLD_RULES:
        actual = _resolve_summary_metric(summary, rule["metric_path"])
        if not isinstance(actual, (int, float)):
            target = failures if rule["severity"] == "failure" else warnings
            target.append(
                {
                    "key": rule["key"],
                    "label": rule["label"],
                    "severity": rule["severity"],
                    "message": f"Metric {'.'.join(rule['metric_path'])} was unavailable.",
                }
            )
            continue
        if float(actual) >= float(rule["minimum"]):
            continue
        target = failures if rule["severity"] == "failure" else warnings
        target.append(
            {
                "key": rule["key"],
                "label": rule["label"],
                "severity": rule["severity"],
                "actual": round(float(actual), 4),
                "minimum": round(float(rule["minimum"]), 4),
                "message": f"{rule['label']} dropped to {float(actual):.4f} (minimum {float(rule['minimum']):.4f}).",
            }
        )

    generated_better = int(summary.get("bundle_relevance_summary", {}).get("repositories_generated_better", 0) or 0)
    default_better = int(summary.get("bundle_relevance_summary", {}).get("repositories_default_better", 0) or 0)
    if generated_better < default_better:
        failures.append(
            {
                "key": "bundle_win_balance",
                "label": "Bundle win balance",
                "severity": "failure",
                "actual": generated_better - default_better,
                "minimum": 0,
                "message": (
                    "Generated bundles underperformed the default bundle on more repositories than they improved. "
                    f"Generated-better: {generated_better}, default-better: {default_better}."
                ),
            }
        )

    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
    }


def render_external_repository_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Generated Addon External Validation",
        "",
        f"- Status: {summary.get('status', 'unknown')}",
        f"- Repositories evaluated: {summary.get('repositories_evaluated', 0)}",
    ]

    threshold_summary = summary.get("thresholds", {})
    if threshold_summary:
        lines.extend(
            [
                f"- Thresholds passed: {'yes' if threshold_summary.get('passed') else 'no'}",
                "",
            ]
        )

    heuristic_summary = summary.get("heuristic_summary", {})
    if heuristic_summary:
        lines.extend(
            [
                "## Heuristic Summary",
                "",
                "| Signal | Avg Precision | Avg Recall | Avg F1 |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for signal_name in ("languages", "frameworks", "tools", "test_harnesses", "manifests"):
            signal = heuristic_summary.get(signal_name, {})
            lines.append(
                f"| {signal_name} | {signal.get('average_precision', 0):.4f} | {signal.get('average_recall', 0):.4f} | {signal.get('average_f1', 0):.4f} |"
            )
        lines.append("")

    bundle_summary = summary.get("bundle_relevance_summary", {})
    if bundle_summary:
        lines.extend(
            [
                "## Bundle Relevance",
                "",
                f"- Generated average F1: {bundle_summary.get('generated_average_f1', 0):.4f}",
                f"- Default average F1: {bundle_summary.get('default_average_f1', 0):.4f}",
                f"- Average F1 delta: {bundle_summary.get('average_f1_delta', 0):+.4f}",
                f"- Average recall delta: {bundle_summary.get('average_recall_delta', 0):+.4f}",
                f"- Generated better / tied / default better: {bundle_summary.get('repositories_generated_better', 0)} / {bundle_summary.get('repositories_tied', 0)} / {bundle_summary.get('repositories_default_better', 0)}",
                "",
            ]
        )

    failures = list(threshold_summary.get("failures", []))
    warnings = list(threshold_summary.get("warnings", []))
    checkout_failures = list(summary.get("failures", []))

    if failures:
        lines.extend(["## Threshold Failures", ""])
        lines.extend(f"- {item['message']}" for item in failures)
        lines.append("")

    if warnings:
        lines.extend(["## Threshold Warnings", ""])
        lines.extend(f"- {item['message']}" for item in warnings)
        lines.append("")

    if checkout_failures:
        lines.extend(["## Repository Failures", ""])
        for failure in checkout_failures:
            lines.append(f"- {failure.get('repo_id', 'unknown')}: {failure.get('error', 'unknown error')}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _resolve_summary_metric(summary: dict[str, Any], metric_path: Sequence[str]) -> Any:
    current: Any = summary
    for key in metric_path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _normalize_generated_bundle(preview: GeneratedAddonPreview) -> list[str]:
    raw_review_types = preview.review_pack.get("review_presets", [{}])[0].get("review_types", [])
    if not isinstance(raw_review_types, list):
        return list(_DEFAULT_REVIEW_TYPES)
    normalized: list[str] = []
    for review_type in raw_review_types:
        if not isinstance(review_type, str):
            continue
        normalized.append("best_practices" if review_type == preview.review_key else review_type)
    return _dedupe_strings(normalized)


def _score_signal_set(expected: Sequence[str], observed: Sequence[str]) -> dict[str, Any]:
    expected_lookup = {item.lower(): item for item in expected if isinstance(item, str) and item.strip()}
    observed_lookup = {item.lower(): item for item in observed if isinstance(item, str) and item.strip()}
    expected_keys = set(expected_lookup)
    observed_keys = set(observed_lookup)
    matched_keys = expected_keys & observed_keys
    missing_keys = expected_keys - observed_keys
    unexpected_keys = observed_keys - expected_keys

    matched_count = len(matched_keys)
    precision = matched_count / len(observed_keys) if observed_keys else 0.0
    recall = matched_count / len(expected_keys) if expected_keys else 1.0
    f1 = 0.0 if precision == 0.0 and recall == 0.0 else (2 * precision * recall) / (precision + recall)
    return {
        "expected": [expected_lookup[key] for key in sorted(expected_keys)],
        "observed": [observed_lookup[key] for key in sorted(observed_keys)],
        "matched": [expected_lookup[key] for key in sorted(matched_keys)],
        "missing": [expected_lookup[key] for key in sorted(missing_keys)],
        "unexpected": [observed_lookup[key] for key in sorted(unexpected_keys)],
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _run_git(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ValueError(
            f"Git command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr.strip() or completed.stdout.strip()}"
        )


def _coerce_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Catalog field '{field_name}' must be a non-empty string")
    return value.strip()


def _coerce_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Optional catalog field must be a non-empty string when provided")
    return value.strip()


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("Catalog expected values must be lists of strings")
    return [item.strip() for item in value if item.strip()]


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered