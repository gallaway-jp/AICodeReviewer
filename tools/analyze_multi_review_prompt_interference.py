"""Analyze prompt growth and cross-type interference risk for multi-review sessions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aicodereviewer.backends.base import AIBackend, REVIEW_TYPE_KEYS, REVIEW_TYPE_META


DUMMY_CODE = "def demo() -> None:\n    return None\n"
DUMMY_SPEC = "The implementation must preserve documented behavior exactly."
REFERENCE_ORDER = [
    "accessibility",
    "api_design",
    "architecture",
    "best_practices",
    "compatibility",
    "complexity",
    "concurrency",
    "data_validation",
    "dead_code",
    "dependency",
    "documentation",
    "error_handling",
    "license",
    "localization",
    "maintainability",
    "performance",
    "regression",
    "scalability",
    "security",
    "specification",
    "testing",
    "ui_ux",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze offline prompt growth and category-interference risk for multi-review sessions.",
    )
    parser.add_argument("--artifact", default="artifacts/review-type-degradation-copilot-fast2-summary.json")
    parser.add_argument("--json-out")
    return parser


def _generic_user_message() -> str:
    return AIBackend._build_user_message(DUMMY_CODE, "", None)


def _single_focus_text(review_type: str) -> str:
    if review_type == "specification":
        combined = AIBackend._build_user_message(DUMMY_CODE, "accessibility+specification", DUMMY_SPEC)
        baseline = AIBackend._build_user_message(DUMMY_CODE, "accessibility", None)
        return combined.replace(baseline, "", 1)
    prompt = AIBackend._build_user_message(DUMMY_CODE, review_type, None)
    return prompt.replace(_generic_user_message(), "", 1)


def _review_type_group(review_type: str) -> str:
    return str(REVIEW_TYPE_META.get(review_type, {}).get("group", "unknown"))


def _cross_type_mentions(focus_text: str, review_type: str) -> list[str]:
    mentions: list[str] = []
    lowered = focus_text.lower()
    for candidate in REVIEW_TYPE_KEYS:
        if candidate == review_type:
            continue
        token = re.escape(candidate.lower())
        if re.search(rf"\b{token}\b", lowered):
            mentions.append(candidate)
    return mentions


def _classification_pressure(focus_text: str) -> dict[str, Any]:
    lowered = focus_text.lower()
    return {
        "instead_of_count": lowered.count("instead of"),
        "classify_as_count": lowered.count("classify"),
        "category_exact_count": lowered.count("category exactly"),
        "do_not_leave_evidence_basis_empty_count": lowered.count("do not leave evidence_basis empty"),
    }


def _type_focus_summary(review_type: str) -> dict[str, Any]:
    focus_text = _single_focus_text(review_type)
    return {
        "review_type": review_type,
        "group": _review_type_group(review_type),
        "focus_chars": len(focus_text),
        "focus_lines": focus_text.count("\n") + 1 if focus_text else 0,
        "cross_type_mentions": _cross_type_mentions(focus_text, review_type),
        "classification_pressure": _classification_pressure(focus_text),
    }


def _bundle_prompt_summary(selected_types: list[str]) -> dict[str, Any]:
    review_type = "+".join(selected_types)
    user_message = AIBackend._build_user_message(DUMMY_CODE, review_type, DUMMY_SPEC)
    system_prompt = AIBackend._build_system_prompt(review_type, "en")
    return {
        "selected_review_types": selected_types,
        "type_count": len(selected_types),
        "system_prompt_chars": len(system_prompt),
        "user_prompt_chars": len(user_message),
        "total_prompt_chars": len(system_prompt) + len(user_message),
    }


def _load_empirical_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _empirical_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    level_summaries = payload.get("level_summaries", [])
    trusted_levels = []
    for row in level_summaries:
        trusted_levels.append(
            {
                "type_count": row.get("type_count"),
                "strict_pass_rate": row.get("pass_rate"),
                "failed_fixture_ids": row.get("failed_fixture_ids", []),
            }
        )

    drift_examples = []
    for fixture in payload.get("fixture_trends", []):
        levels = fixture.get("levels", [])
        baseline = next((row for row in levels if row.get("type_count") == 1), None)
        eight = next((row for row in levels if row.get("type_count") == 8), None)
        twenty_two = next((row for row in levels if row.get("type_count") == 22), None)
        if eight and baseline and not eight.get("matched_target"):
            best_candidate = None
            for expectation in eight.get("expectation_results", []):
                if expectation.get("best_candidate_issue_id") or expectation.get("best_candidate_file_path"):
                    best_candidate = expectation
                    break
            drift_examples.append(
                {
                    "fixture_id": fixture.get("fixture_id"),
                    "target_review_type": fixture.get("target_review_type"),
                    "baseline_matched": baseline.get("matched_target"),
                    "eight_type_matched": eight.get("matched_target"),
                    "eight_type_best_candidate_file_path": best_candidate.get("best_candidate_file_path") if best_candidate else None,
                    "eight_type_failed_checks": best_candidate.get("failed_checks") if best_candidate else None,
                    "twenty_two_type_exit_code": twenty_two.get("exit_code") if twenty_two else None,
                    "twenty_two_type_report_exists": twenty_two.get("report_exists") if twenty_two else None,
                }
            )

    return {
        "level_summaries": trusted_levels,
        "drift_examples": drift_examples,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    focus_summaries = [_type_focus_summary(review_type) for review_type in REVIEW_TYPE_KEYS]
    ranked_focus = sorted(
        focus_summaries,
        key=lambda row: (
            row["focus_chars"],
            len(row["cross_type_mentions"]),
            row["classification_pressure"]["instead_of_count"],
        ),
        reverse=True,
    )

    bundle_summaries = [
        _bundle_prompt_summary([REFERENCE_ORDER[0]]),
        _bundle_prompt_summary(REFERENCE_ORDER[:8]),
        _bundle_prompt_summary(REFERENCE_ORDER),
    ]

    empirical = _empirical_summary(_load_empirical_artifact(Path(args.artifact)))

    payload = {
        "reference_order": REFERENCE_ORDER,
        "largest_focus_blocks": ranked_focus[:8],
        "bundle_prompt_summaries": bundle_summaries,
        "empirical_artifact_summary": empirical,
    }
    rendered = json.dumps(payload, indent=2)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())