from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from aicodereviewer.context_collector import collect_project_context
from aicodereviewer.registries import get_review_registry
from aicodereviewer.review_presets import REVIEW_TYPE_PRESETS, infer_review_type_preset, resolve_review_preset_key
from aicodereviewer.scanner import scan_project_with_scope

logger = logging.getLogger(__name__)


CancelCheck = Callable[[], bool]


class ReviewRecommendationCancelledError(RuntimeError):
    """Raised when recommendation generation is cancelled before completion."""


@dataclass(frozen=True)
class ReviewTypeRecommendation:
    review_type: str
    reason: str


@dataclass(frozen=True)
class ReviewRecommendationResult:
    review_types: list[str]
    rationale: list[ReviewTypeRecommendation]
    project_signals: list[str]
    recommended_preset: str | None = None
    source: str = "heuristic"


@dataclass(frozen=True)
class _RecommendationContext:
    scope: str
    project_signals: list[str]
    available_review_types: list[str]
    available_presets: dict[str, list[str]]
    scores: dict[str, int]
    dependency_summary: list[str]
    diff_summary: list[str]


def recommend_review_types(
    *,
    path: str | None,
    scope: str,
    diff_file: str | None = None,
    commits: str | None = None,
    target_lang: str = "en",
    client: Any | None = None,
    selected_files: Sequence[str] | None = None,
    diff_filter_file: str | None = None,
    diff_filter_commits: str | None = None,
    cancel_check: CancelCheck | None = None,
) -> ReviewRecommendationResult:
    _raise_if_cancelled(cancel_check)
    context = _build_recommendation_context(
        path=path,
        scope=scope,
        diff_file=diff_file,
        commits=commits,
        selected_files=selected_files,
        diff_filter_file=diff_filter_file,
        diff_filter_commits=diff_filter_commits,
        cancel_check=cancel_check,
    )
    _raise_if_cancelled(cancel_check)

    if client is not None and hasattr(client, "get_review_recommendations"):
        try:
            response = client.get_review_recommendations(
                _build_recommendation_prompt(context),
                lang=target_lang,
            )
            _raise_if_cancelled(cancel_check)
            parsed = _parse_recommendation_response(response, context)
            if parsed is not None:
                return parsed
        except NotImplementedError:
            logger.info("Backend does not implement review recommendations; using heuristic fallback")
        except Exception as exc:
            logger.warning("Backend recommendation request failed; using heuristic fallback: %s", exc)

    _raise_if_cancelled(cancel_check)
    return _build_fallback_recommendation(context)


def format_review_recommendation_reasons(result: ReviewRecommendationResult) -> str:
    lines = [f"- {item.review_type}: {item.reason}" for item in result.rationale]
    return "\n".join(lines)


def _build_recommendation_context(
    *,
    path: str | None,
    scope: str,
    diff_file: str | None,
    commits: str | None,
    selected_files: Sequence[str] | None,
    diff_filter_file: str | None,
    diff_filter_commits: str | None,
    cancel_check: CancelCheck | None = None,
) -> _RecommendationContext:
    _raise_if_cancelled(cancel_check)
    review_registry = get_review_registry()
    available_review_types = [
        definition.key
        for definition in review_registry.list_all()
        if definition.selectable
    ]

    selected_relative_files = {
        str(Path(item)).replace("\\", "/")
        for item in (selected_files or [])
        if str(item).strip()
    }

    project_root = Path(path).resolve() if path else None
    scanned_project_files: list[str] = []
    changed_files: list[str] = []

    if scope == "project" and path:
        project_entries = scan_project_with_scope(path, "project")
        _raise_if_cancelled(cancel_check)
        for entry in project_entries:
            resolved = str(Path(entry).resolve())
            if selected_relative_files and project_root is not None:
                try:
                    relative = Path(resolved).resolve().relative_to(project_root).as_posix()
                except ValueError:
                    relative = Path(resolved).name
                if relative not in selected_relative_files:
                    continue
            scanned_project_files.append(resolved)

        focus_diff_file = diff_filter_file
        focus_diff_commits = diff_filter_commits
    else:
        focus_diff_file = diff_file
        focus_diff_commits = commits

    if focus_diff_file or focus_diff_commits:
        diff_entries = scan_project_with_scope(path, "diff", focus_diff_file, focus_diff_commits)
        _raise_if_cancelled(cancel_check)
        for entry in diff_entries:
            filename = entry.get("filename") or Path(entry.get("path", "")).name
            normalized = str(filename).replace("\\", "/")
            if normalized:
                changed_files.append(normalized)
            entry_path = entry.get("path")
            if entry_path:
                try:
                    scanned_project_files.append(str(Path(entry_path).resolve()))
                except Exception:
                    pass

    manifests = _detect_dependency_manifests(project_root)
    dependency_summary = _summarize_dependency_manifests(project_root, manifests)
    language_signals = _detect_languages(scanned_project_files)
    frontend_focus = _contains_frontend_files(changed_files or scanned_project_files)
    diff_summary = _summarize_diff_entries(diff_entries if focus_diff_file or focus_diff_commits else [])

    frameworks: list[str] = []
    tools: list[str] = []
    total_files = len(scanned_project_files)
    if project_root is not None and project_root.is_dir():
        project_context = collect_project_context(project_root.as_posix(), scanned_project_files or None)
        _raise_if_cancelled(cancel_check)
        frameworks = list(project_context.frameworks)
        tools = list(project_context.tools)
        total_files = project_context.total_files or total_files

    project_signals: list[str] = []
    if language_signals:
        project_signals.append(f"Languages: {', '.join(language_signals)}")
    if frameworks:
        project_signals.append(f"Frameworks: {', '.join(frameworks)}")
    if tools:
        project_signals.append(f"Tools: {', '.join(tools)}")
    if manifests:
        project_signals.append(f"Dependency manifests: {', '.join(manifests)}")
    for summary in dependency_summary:
        project_signals.append(summary)
    if selected_relative_files:
        project_signals.append(
            "Selected files: "
            + ", ".join(sorted(selected_relative_files)[:5])
            + (" ..." if len(selected_relative_files) > 5 else "")
        )
    if changed_files:
        project_signals.append(
            "Changed files: "
            + ", ".join(changed_files[:5])
            + (" ..." if len(changed_files) > 5 else "")
        )
    for summary in diff_summary:
        project_signals.append(summary)
    if total_files:
        project_signals.append(f"Approximate project size: {total_files} files")
    if frontend_focus and "Frontend surface present" not in project_signals:
        project_signals.append("Frontend surface present in the current target")
    if scope == "diff":
        project_signals.append("Diff scope narrows attention to recent changes")

    scores = {review_type: 0 for review_type in available_review_types}
    _increment_score(scores, "best_practices", 2)
    if manifests:
        _increment_score(scores, "dependency", 2)
        _increment_score(scores, "license", 1)
    if scope == "diff" or changed_files:
        _increment_score(scores, "regression", 3)
        _increment_score(scores, "compatibility", 1)
        _increment_score(scores, "testing", 1)
    if (project_root is not None and (project_root / "tests").exists()) or "pytest" in frameworks:
        _increment_score(scores, "testing", 2)

    server_frameworks = {"django", "flask", "fastapi", "express", "rails", "spring_boot"}
    api_frameworks = {"fastapi", "express", "django", "flask", "rails", "spring_boot"}
    frontend_frameworks = {"react", "next.js", "vue", "angular", "django", "flask"}

    if set(frameworks) & server_frameworks:
        _increment_score(scores, "security", 3)
        _increment_score(scores, "error_handling", 2)
        _increment_score(scores, "data_validation", 2)
    if set(frameworks) & api_frameworks:
        _increment_score(scores, "api_design", 3)
    if frontend_focus or set(frameworks) & frontend_frameworks:
        _increment_score(scores, "ui_ux", 3)
        _increment_score(scores, "accessibility", 2)
        _increment_score(scores, "localization", 1)
    if total_files >= 80:
        _increment_score(scores, "maintainability", 2)
        _increment_score(scores, "architecture", 2)
    if any("Dependencies:" in summary for summary in dependency_summary):
        _increment_score(scores, "dependency", 1)
    if any("Hunks:" in summary or "Commit messages:" in summary for summary in diff_summary):
        _increment_score(scores, "regression", 1)

    return _RecommendationContext(
        scope=scope,
        project_signals=project_signals,
        available_review_types=available_review_types,
        available_presets={key: list(value) for key, value in REVIEW_TYPE_PRESETS.items()},
        scores=scores,
        dependency_summary=dependency_summary,
        diff_summary=diff_summary,
    )


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise ReviewRecommendationCancelledError("Recommendation cancelled")


def _build_recommendation_prompt(context: _RecommendationContext) -> str:
    type_lines = "\n".join(f"- {review_type}" for review_type in context.available_review_types)
    preset_lines = "\n".join(
        f"- {preset_key}: {', '.join(review_types)}"
        for preset_key, review_types in context.available_presets.items()
    )
    signal_lines = "\n".join(f"- {signal}" for signal in context.project_signals)
    dependency_lines = "\n".join(f"- {line}" for line in context.dependency_summary) or "- none detected"
    diff_lines = "\n".join(f"- {line}" for line in context.diff_summary) or "- none detected"
    return (
        f"TARGET SCOPE: {context.scope}\n"
        f"OBSERVED PROJECT SIGNALS:\n{signal_lines}\n\n"
        f"DEPENDENCY SUMMARY:\n{dependency_lines}\n\n"
        f"DIFF SUMMARY:\n{diff_lines}\n\n"
        f"AVAILABLE REVIEW TYPES:\n{type_lines}\n\n"
        f"AVAILABLE REVIEW PRESETS:\n{preset_lines}\n"
    )


def _parse_recommendation_response(
    response: Any,
    context: _RecommendationContext,
) -> ReviewRecommendationResult | None:
    if not isinstance(response, str) or not response.strip():
        return None

    payload = _extract_json_payload(response)
    if not isinstance(payload, dict):
        return None

    review_registry = get_review_registry()
    review_types: list[str] = []
    for raw_review_type in payload.get("recommended_review_types", []) or payload.get("review_types", []):
        if not isinstance(raw_review_type, str):
            continue
        try:
            canonical = review_registry.resolve_key(raw_review_type)
        except KeyError:
            continue
        if canonical in context.available_review_types and canonical not in review_types:
            review_types.append(canonical)
    if not review_types:
        return None

    reasons_by_type: dict[str, str] = {}
    for entry in payload.get("rationale", []):
        if not isinstance(entry, dict):
            continue
        raw_type = entry.get("review_type")
        reason = str(entry.get("reason") or "").strip()
        if not isinstance(raw_type, str) or not reason:
            continue
        try:
            canonical = review_registry.resolve_key(raw_type)
        except KeyError:
            continue
        reasons_by_type[canonical] = reason

    project_signals = [
        str(item).strip()
        for item in payload.get("project_signals", [])
        if str(item).strip()
    ] or list(context.project_signals)

    preset_key = payload.get("recommended_preset")
    recommended_preset: str | None = None
    if isinstance(preset_key, str) and preset_key.strip():
        try:
            recommended_preset = resolve_review_preset_key(preset_key)
        except KeyError:
            recommended_preset = None
    if recommended_preset is None:
        recommended_preset = infer_review_type_preset(review_types)

    rationale = [
        ReviewTypeRecommendation(
            review_type=review_type,
            reason=reasons_by_type.get(review_type) or _default_reason(review_type, project_signals),
        )
        for review_type in review_types
    ]
    return ReviewRecommendationResult(
        review_types=review_types,
        rationale=rationale,
        project_signals=project_signals,
        recommended_preset=recommended_preset,
        source="ai",
    )


def _build_fallback_recommendation(context: _RecommendationContext) -> ReviewRecommendationResult:
    best_preset = _best_matching_preset(context)
    if best_preset is not None:
        review_types = list(context.available_presets[best_preset])
        recommended_preset = best_preset
    else:
        ranked = sorted(
            context.scores.items(),
            key=lambda item: (-item[1], item[0]),
        )
        review_types = [review_type for review_type, score in ranked if score > 0][:4]
        if not review_types:
            review_types = ["best_practices"]
        recommended_preset = infer_review_type_preset(review_types)

    rationale = [
        ReviewTypeRecommendation(
            review_type=review_type,
            reason=_default_reason(review_type, context.project_signals),
        )
        for review_type in review_types
    ]
    return ReviewRecommendationResult(
        review_types=review_types,
        rationale=rationale,
        project_signals=list(context.project_signals),
        recommended_preset=recommended_preset,
        source="heuristic",
    )


def _best_matching_preset(context: _RecommendationContext) -> str | None:
    best_key: str | None = None
    best_score = 0
    for preset_key, review_types in context.available_presets.items():
        score = sum(context.scores.get(review_type, 0) for review_type in review_types)
        if score > best_score:
            best_key = preset_key
            best_score = score
    if best_key is None or best_score < 5:
        return None
    return best_key


def _default_reason(review_type: str, project_signals: Sequence[str]) -> str:
    lower_signals = " ".join(project_signals).lower()
    if review_type == "security":
        return "The current target includes service or API signals where boundary checks and auth flaws are common."
    if review_type == "error_handling":
        return "The current target includes request or workflow boundaries where failure propagation matters."
    if review_type == "data_validation":
        return "The current target exposes input-heavy paths where validation drift is likely to matter."
    if review_type == "dependency":
        return "Dependency manifests are present, so package and runtime contract checks are high leverage."
    if review_type == "api_design":
        return "The current target includes API-oriented signals that benefit from contract and endpoint review."
    if review_type == "ui_ux":
        return "The current target includes user-facing files or frameworks where workflow clarity matters."
    if review_type == "accessibility":
        return "The current target includes user-facing surface area that should be checked for interaction barriers."
    if review_type == "localization":
        return "The current target includes interface surface where untranslated strings and locale assumptions are visible."
    if review_type == "testing":
        return "The project includes test signals, so reviewing coverage gaps and regression pinning is useful."
    if review_type == "regression":
        return "Recent changes are in scope, so focusing on existing workflow breakage is a good first pass."
    if review_type == "maintainability":
        return "The current target is large enough that structural drift and duplicated maintenance cost are worth checking."
    if review_type == "architecture":
        return "The current target includes enough surface area to justify a dependency and boundary check."
    if review_type == "compatibility":
        return "Recent changes or mixed tooling increase the chance of platform or environment-specific breakage."
    if review_type == "best_practices":
        return "A baseline quality pass is useful before expanding into narrower review lenses."
    if "frontend surface" in lower_signals:
        return "The current target includes user-facing code, so this lens is likely to produce actionable findings."
    if "diff scope" in lower_signals:
        return "The recommendation is biased toward recent changes in the current diff scope."
    return "This lens aligns with the observable project signals in the current target."


def _extract_json_payload(response: str) -> dict[str, Any] | None:
    raw = response.strip()
    candidates = [raw]
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _detect_dependency_manifests(project_root: Path | None) -> list[str]:
    if project_root is None:
        return []
    manifest_names = [
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "Gemfile",
    ]
    return [name for name in manifest_names if (project_root / name).exists()]


def _summarize_dependency_manifests(project_root: Path | None, manifests: Sequence[str]) -> list[str]:
    if project_root is None:
        return []

    summaries: list[str] = []
    pyproject_path = project_root / "pyproject.toml"
    if "pyproject.toml" in manifests and pyproject_path.exists():
        try:
            text = pyproject_path.read_text(encoding="utf-8", errors="ignore")
            dependency_lines = [line for line in text.splitlines() if "dependencies" in line.lower()]
            tool_sections = [line.strip() for line in text.splitlines() if line.strip().startswith("[tool.")]
            if dependency_lines:
                summaries.append(f"Dependencies: pyproject.toml defines dependency metadata ({len(dependency_lines)} matching lines)")
            if tool_sections:
                summaries.append(
                    "Tooling: pyproject.toml sections include "
                    + ", ".join(tool_sections[:4])
                    + (" ..." if len(tool_sections) > 4 else "")
                )
        except OSError:
            pass

    requirements_path = project_root / "requirements.txt"
    if "requirements.txt" in manifests and requirements_path.exists():
        try:
            packages = [
                line.strip() for line in requirements_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            if packages:
                summaries.append(
                    "Dependencies: requirements.txt lists "
                    + ", ".join(packages[:5])
                    + (" ..." if len(packages) > 5 else "")
                )
        except OSError:
            pass

    package_json_path = project_root / "package.json"
    if "package.json" in manifests and package_json_path.exists():
        try:
            payload = json.loads(package_json_path.read_text(encoding="utf-8", errors="ignore"))
            dependencies = sorted((payload.get("dependencies") or {}).keys())
            dev_dependencies = sorted((payload.get("devDependencies") or {}).keys())
            if dependencies:
                summaries.append(
                    "Dependencies: package.json runtime deps include "
                    + ", ".join(dependencies[:5])
                    + (" ..." if len(dependencies) > 5 else "")
                )
            if dev_dependencies:
                summaries.append(
                    "Tooling: package.json dev deps include "
                    + ", ".join(dev_dependencies[:5])
                    + (" ..." if len(dev_dependencies) > 5 else "")
                )
        except (OSError, json.JSONDecodeError):
            pass

    return summaries


def _summarize_diff_entries(diff_entries: Sequence[dict[str, Any]]) -> list[str]:
    if not diff_entries:
        return []

    file_names: list[str] = []
    total_hunks = 0
    extensions: dict[str, int] = {}
    commit_messages: list[str] = []
    for entry in diff_entries:
        filename = str(entry.get("filename") or entry.get("path") or "").replace("\\", "/")
        if filename:
            file_names.append(filename)
            suffix = Path(filename).suffix.lower() or "<none>"
            extensions[suffix] = extensions.get(suffix, 0) + 1
        hunks = entry.get("hunks") or []
        total_hunks += len(hunks)
        commit_message = str(entry.get("commit_messages") or "").strip()
        if commit_message:
            first_line = commit_message.splitlines()[0].strip()
            if first_line and first_line not in commit_messages:
                commit_messages.append(first_line)

    summaries = [
        "Diff files: " + ", ".join(file_names[:5]) + (" ..." if len(file_names) > 5 else ""),
        f"Hunks: {total_hunks} across {len(file_names)} file(s)",
    ]
    if extensions:
        ranked = sorted(extensions.items(), key=lambda item: (-item[1], item[0]))
        summaries.append(
            "Changed file types: "
            + ", ".join(f"{suffix} x{count}" for suffix, count in ranked[:5])
        )
    if commit_messages:
        summaries.append(
            "Commit messages: "
            + " | ".join(commit_messages[:3])
            + (" ..." if len(commit_messages) > 3 else "")
        )
    return summaries


def _detect_languages(paths: Sequence[str]) -> list[str]:
    suffix_map = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".vue": "Vue",
        ".java": "Java",
        ".rb": "Ruby",
        ".go": "Go",
        ".rs": "Rust",
        ".cs": "C#",
        ".php": "PHP",
    }
    detected: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        suffix = Path(raw_path).suffix.lower()
        language = suffix_map.get(suffix)
        if language and language not in seen:
            detected.append(language)
            seen.add(language)
    return detected


def _contains_frontend_files(paths: Sequence[str]) -> bool:
    frontend_suffixes = {".js", ".jsx", ".ts", ".tsx", ".vue", ".html", ".css", ".scss"}
    return any(Path(raw_path).suffix.lower() in frontend_suffixes for raw_path in paths)


def _increment_score(scores: dict[str, int], review_type: str, amount: int) -> None:
    if review_type in scores:
        scores[review_type] += amount
