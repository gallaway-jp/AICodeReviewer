from __future__ import annotations

import json
import re
import tomllib
from datetime import datetime, timezone
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from aicodereviewer import __version__
from aicodereviewer.addons import load_addon_manifest
from aicodereviewer.context_collector import collect_project_context


_SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".cs",
    ".rb",
    ".php",
    ".swift",
}

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
}

_NON_PRIMARY_DIR_NAMES = {
    "artifact",
    "artifacts",
    "benchmark",
    "benchmarks",
    "demo",
    "demos",
    "example",
    "examples",
    "fixture",
    "fixtures",
    "sample",
    "samples",
    "testdata",
}

_MANIFEST_PATTERNS = (
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Gemfile",
    "composer.json",
    "Package.swift",
    "*.csproj",
    "*.sln",
)

_FRONTEND_FRAMEWORKS = frozenset({"react", "next.js", "vue", "angular"})
_SERVICE_FRAMEWORKS = frozenset({"fastapi", "flask", "django", "express", "spring_boot", "rails"})
_STYLE_TOOLS = frozenset({"ruff", "black", "mypy", "eslint", "prettier", "flake8"})
_DEFAULT_BUNDLE_REVIEW_TYPES = ("best_practices", "maintainability", "testing")

_FRAMEWORK_GUIDANCE: dict[str, dict[str, tuple[str, ...] | str]] = {
    "react": {
        "prompt": "Check component state boundaries, hook lifecycles, stale closures, and missing loading or error states in interactive flows.",
        "rules": (
            "Inspect component props, local state, and effect dependencies before recommending React changes.",
            "Prefer findings tied to concrete user flows such as forms, navigation, loading, and empty states.",
        ),
    },
    "next.js": {
        "prompt": "Check server and client component boundaries, routing assumptions, and data-fetching behavior across page transitions.",
        "rules": (
            "Inspect app or pages routing structure before flagging navigation or rendering behavior.",
        ),
    },
    "fastapi": {
        "prompt": "Check request and response models, dependency injection seams, status code semantics, and validation at API boundaries.",
        "rules": (
            "Inspect route decorators, response contracts, and validation models before flagging API behavior.",
        ),
    },
    "django": {
        "prompt": "Check ORM query behavior, model and serializer boundaries, settings defaults, and view-to-template or API seams.",
        "rules": (
            "Inspect models, views, settings, and migration-facing code before assuming behavior is isolated to one file.",
        ),
    },
    "flask": {
        "prompt": "Check app-factory or blueprint structure, request validation, configuration separation, and error handling around route handlers.",
        "rules": (
            "Inspect application bootstrap and blueprint wiring before flagging Flask route behavior.",
        ),
    },
    "express": {
        "prompt": "Check middleware ordering, request validation, async error propagation, and route contract consistency.",
        "rules": (
            "Inspect router and middleware composition before flagging request lifecycle issues.",
        ),
    },
    "pytest": {
        "prompt": "Check fixture scope, parametrization, and whether failure paths and contract boundaries are actually exercised in tests.",
        "rules": (
            "Inspect pytest fixtures, conftest wiring, and parametrized coverage before calling tests insufficient.",
        ),
    },
}


@dataclass(frozen=True)
class RepositoryCapabilityProfile:
    project_path: str
    repo_name: str
    languages: tuple[str, ...]
    frameworks: tuple[str, ...]
    tools: tuple[str, ...]
    test_harnesses: tuple[str, ...]
    manifests: tuple[str, ...]
    style_signals: tuple[str, ...]
    naming_convention: str
    total_files: int
    file_counts: dict[str, int]
    source_file_count: int
    recommended_review_types: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "repo_name": self.repo_name,
            "languages": list(self.languages),
            "frameworks": list(self.frameworks),
            "tools": list(self.tools),
            "test_harnesses": list(self.test_harnesses),
            "manifests": list(self.manifests),
            "style_signals": list(self.style_signals),
            "naming_convention": self.naming_convention,
            "total_files": self.total_files,
            "file_counts": dict(self.file_counts),
            "source_file_count": self.source_file_count,
            "recommended_review_types": list(self.recommended_review_types),
        }


@dataclass(frozen=True)
class GeneratedAddonPreview:
    profile: RepositoryCapabilityProfile
    addon_id: str
    addon_name: str
    output_dir: Path
    addon_root: Path
    capability_profile_path: Path
    summary_path: Path
    approval_request_path: Path
    review_checklist_path: Path
    manifest_path: Path
    review_pack_path: Path
    review_key: str
    preset_key: str
    addon_manifest: dict[str, Any]
    review_pack: dict[str, Any]
    approval_request: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "addon_id": self.addon_id,
            "addon_name": self.addon_name,
            "output_dir": str(self.output_dir),
            "addon_root": str(self.addon_root),
            "capability_profile_path": str(self.capability_profile_path),
            "summary_path": str(self.summary_path),
            "approval_request_path": str(self.approval_request_path),
            "review_checklist_path": str(self.review_checklist_path),
            "manifest_path": str(self.manifest_path),
            "review_pack_path": str(self.review_pack_path),
            "review_key": self.review_key,
            "preset_key": self.preset_key,
            "profile": self.profile.to_dict(),
        }


def analyze_repository(project_path: str | Path) -> RepositoryCapabilityProfile:
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise ValueError(f"Project path is not a directory: {root}")

    source_files = _discover_source_files(root)
    context = collect_project_context(str(root), source_files)
    manifests = _detect_manifests(root)
    test_harnesses = _detect_test_harnesses(root)
    style_signals = _detect_style_signals(root, context.naming_convention, context.tools)
    recommended_review_types = _recommend_review_types(context.frameworks, context.tools, manifests)
    file_counts, total_files = _count_primary_files(root)

    return RepositoryCapabilityProfile(
        project_path=str(root),
        repo_name=root.name,
        languages=tuple(context.languages),
        frameworks=tuple(context.frameworks),
        tools=tuple(context.tools),
        test_harnesses=tuple(test_harnesses),
        manifests=tuple(manifests),
        style_signals=tuple(style_signals),
        naming_convention=context.naming_convention,
        total_files=total_files,
        file_counts=file_counts,
        source_file_count=len(source_files),
        recommended_review_types=tuple(recommended_review_types),
    )


def generate_addon_preview(
    project_path: str | Path,
    output_dir: str | Path,
    *,
    addon_id: str | None = None,
    addon_name: str | None = None,
) -> GeneratedAddonPreview:
    profile = analyze_repository(project_path)
    resolved_output_dir = Path(output_dir).resolve()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    normalized_addon_id = _normalize_addon_id(addon_id or f"{profile.repo_name}-adaptive-review")
    resolved_addon_name = addon_name or f"{profile.repo_name} Adaptive Review Addon"
    review_key = f"{normalized_addon_id.replace('-', '_')}_project_profile"
    preset_key = f"{normalized_addon_id.replace('-', '_')}_generated_bundle"
    addon_root = resolved_output_dir / normalized_addon_id
    addon_root.mkdir(parents=True, exist_ok=True)

    capability_profile_path = resolved_output_dir / "capability-profile.json"
    capability_profile_path.write_text(
        json.dumps(profile.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary_path = resolved_output_dir / "summary.txt"
    summary_path.write_text(_render_summary(profile, normalized_addon_id, review_key, preset_key), encoding="utf-8")

    review_pack = _build_review_pack(profile, review_key, preset_key, resolved_addon_name)
    review_pack_path = addon_root / "review-pack.json"
    review_pack_path.write_text(json.dumps(review_pack, indent=2, ensure_ascii=False), encoding="utf-8")

    addon_manifest = {
        "manifest_version": 1,
        "id": normalized_addon_id,
        "version": "0.1.0",
        "name": resolved_addon_name,
        "compatibility": {"min_app_version": __version__},
        "permissions": ["review_definitions"],
        "entry_points": {"review_packs": ["review-pack.json"]},
    }
    manifest_path = addon_root / "addon.json"
    manifest_path.write_text(json.dumps(addon_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    load_addon_manifest(manifest_path)

    approval_request = _build_approval_request(
        profile,
        resolved_output_dir,
        addon_root,
        normalized_addon_id,
        resolved_addon_name,
        capability_profile_path,
        summary_path,
        manifest_path,
        review_pack_path,
        review_key,
        preset_key,
    )
    approval_request_path = resolved_output_dir / "approval-request.json"
    approval_request_path.write_text(
        json.dumps(approval_request, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    review_checklist_path = resolved_output_dir / "review-checklist.md"
    review_checklist_path.write_text(
        _render_review_checklist(approval_request),
        encoding="utf-8",
    )

    return GeneratedAddonPreview(
        profile=profile,
        addon_id=normalized_addon_id,
        addon_name=resolved_addon_name,
        output_dir=resolved_output_dir,
        addon_root=addon_root,
        capability_profile_path=capability_profile_path,
        summary_path=summary_path,
        approval_request_path=approval_request_path,
        review_checklist_path=review_checklist_path,
        manifest_path=manifest_path,
        review_pack_path=review_pack_path,
        review_key=review_key,
        preset_key=preset_key,
        addon_manifest=addon_manifest,
        review_pack=review_pack,
        approval_request=approval_request,
    )


def _discover_source_files(root: Path) -> list[str]:
    source_files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _should_exclude_path(root, path):
            continue
        if path.suffix.lower() in _SOURCE_SUFFIXES:
            source_files.append(str(path))
    return source_files


def _detect_manifests(root: Path) -> list[str]:
    manifests: list[str] = []
    seen: set[str] = set()
    for pattern in _MANIFEST_PATTERNS:
        for path in sorted(root.rglob(pattern)):
            if not path.is_file():
                continue
            if _should_exclude_path(root, path):
                continue
            relative = path.relative_to(root).as_posix()
            if relative not in seen:
                manifests.append(relative)
                seen.add(relative)
    return manifests


def _detect_test_harnesses(root: Path) -> list[str]:
    harnesses: list[str] = []
    if (root / "pytest.ini").exists() or (root / "conftest.py").exists() or _pyproject_has_section(root, "tool.pytest"):
        harnesses.append("pytest")

    package_json = root / "package.json"
    if package_json.exists():
        payload = _load_json(package_json)
        tokens = _collect_package_json_tokens(payload)
        for harness in ("jest", "vitest", "playwright", "cypress", "mocha"):
            if harness in tokens:
                harnesses.append(harness)

    pom_xml = root / "pom.xml"
    if pom_xml.exists() and "junit" in pom_xml.read_text(encoding="utf-8", errors="ignore").lower():
        harnesses.append("junit")

    return _dedupe(harnesses)


def _count_primary_files(root: Path) -> tuple[dict[str, int], int]:
    file_counts: dict[str, int] = {}
    total_files = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _should_exclude_path(root, path):
            continue
        suffix = path.suffix or "(no ext)"
        file_counts[suffix] = file_counts.get(suffix, 0) + 1
        total_files += 1
    return file_counts, total_files


def _detect_style_signals(root: Path, naming_convention: str, tools: list[str]) -> list[str]:
    signals: list[str] = []
    if (root / ".editorconfig").exists():
        signals.append("editorconfig")
    if naming_convention and naming_convention != "unknown":
        signals.append(f"naming:{naming_convention}")
    for tool in tools:
        if tool in _STYLE_TOOLS:
            signals.append(tool)
    return _dedupe(signals)


def _recommend_review_types(frameworks: list[str], tools: list[str], manifests: list[str]) -> list[str]:
    recommended = ["best_practices", "maintainability", "testing"]
    framework_set = set(frameworks)
    if framework_set & _FRONTEND_FRAMEWORKS:
        recommended.extend(["ui_ux", "accessibility"])
    if framework_set & _SERVICE_FRAMEWORKS:
        recommended.extend(["api_design", "data_validation", "error_handling"])
    if "docker" in tools or any(path.endswith(("Dockerfile", "docker-compose.yml", "docker-compose.yaml")) for path in manifests):
        recommended.append("compatibility")
    if len(manifests) > 3:
        recommended.append("dependency")
    return _dedupe(recommended)


def _build_review_pack(
    profile: RepositoryCapabilityProfile,
    review_key: str,
    preset_key: str,
    addon_name: str,
) -> dict[str, Any]:
    prompt_append = _build_prompt_append(profile)
    context_rules = _build_context_rules(profile)
    preset_types = [review_key]
    preset_types.extend(review_type for review_type in profile.recommended_review_types if review_type != "best_practices")

    return {
        "version": 1,
        "review_definitions": [
            {
                "key": review_key,
                "parent_key": "best_practices",
                "label": f"{addon_name} Project Profile",
                "summary_key": "",
                "aliases": [review_key.replace("_", "-")],
                "prompt_append": prompt_append,
                "context_augmentation_rules": context_rules,
                "benchmark_metadata": {
                    "generated": True,
                    "repo_name": profile.repo_name,
                    "frameworks": list(profile.frameworks),
                },
            }
        ],
        "review_presets": [
            {
                "key": preset_key,
                "group": "Generated Addons",
                "aliases": [preset_key.replace("_", "-")],
                "label": f"{profile.repo_name} Generated Bundle",
                "summary": "Project-tuned review bundle generated from repository heuristics.",
                "review_types": preset_types,
            }
        ],
    }


def _build_approval_request(
    profile: RepositoryCapabilityProfile,
    output_dir: Path,
    addon_root: Path,
    addon_id: str,
    addon_name: str,
    capability_profile_path: Path,
    summary_path: Path,
    manifest_path: Path,
    review_pack_path: Path,
    review_key: str,
    preset_key: str,
) -> dict[str, Any]:
    bundle_comparison = _build_bundle_comparison(profile)
    reviewed_files = {
        "capability_profile": _sha256_path(capability_profile_path),
        "summary": _sha256_path(summary_path),
        "manifest": _sha256_path(manifest_path),
        "review_pack": _sha256_path(review_pack_path),
    }
    return {
        "schema_version": 1,
        "status": "pending_review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preview_only": True,
        "addon_id": addon_id,
        "addon_name": addon_name,
        "output_dir": str(output_dir),
        "addon_root": str(addon_root),
        "capability_profile_path": str(capability_profile_path),
        "summary_path": str(summary_path),
        "manifest_path": str(manifest_path),
        "review_pack_path": str(review_pack_path),
        "generated_review_key": review_key,
        "generated_preset_key": preset_key,
        "bundle_comparison": bundle_comparison,
        "profile": profile.to_dict(),
        "reviewed_files": reviewed_files,
        "review_checklist": [
            f"Inspect {summary_path.name} for the detected language, framework, and review-type summary.",
            f"Inspect {capability_profile_path.name} for false positives or missing repository signals.",
            f"Review {manifest_path.relative_to(output_dir).as_posix()} for addon metadata and compatibility.",
            f"Review {review_pack_path.relative_to(output_dir).as_posix()} for prompt append text, context rules, and preset review types.",
            "Edit the generated files if the repository needs narrower prompts or a different review bundle.",
            "Approve the preview only after the generated bundle matches the maintainer's intent.",
        ],
    }


def _build_bundle_comparison(profile: RepositoryCapabilityProfile) -> dict[str, list[str]]:
    baseline = list(_DEFAULT_BUNDLE_REVIEW_TYPES)
    generated = ["best_practices"]
    generated.extend(review_type for review_type in profile.recommended_review_types if review_type != "best_practices")
    generated = _dedupe(generated)
    return {
        "default_review_types": baseline,
        "generated_review_types": generated,
        "added_review_types": [review_type for review_type in generated if review_type not in baseline],
        "removed_review_types": [review_type for review_type in baseline if review_type not in generated],
    }


def _build_prompt_append(profile: RepositoryCapabilityProfile) -> str:
    parts = [
        "Repository capability profile:",
        f"languages={', '.join(profile.languages) or 'unknown'};",
        f"frameworks={', '.join(profile.frameworks) or 'none detected'};",
        f"tools={', '.join(profile.tools) or 'none detected'};",
        f"test_harnesses={', '.join(profile.test_harnesses) or 'none detected'}.",
        "Tailor feedback to the conventions visible in this repository and prefer framework-aware findings over generic advice.",
    ]

    for framework in profile.frameworks:
        guidance = _FRAMEWORK_GUIDANCE.get(framework)
        if guidance is not None:
            parts.append(str(guidance["prompt"]))

    if profile.style_signals:
        parts.append(f"Style signals: {', '.join(profile.style_signals)}.")

    return " ".join(parts)


def _build_context_rules(profile: RepositoryCapabilityProfile) -> list[str]:
    rules = [
        "Inspect the repository manifests and detected toolchain before recommending new framework conventions or dependencies.",
        "Use the generated capability profile as context only; do not suppress core findings solely because a pattern is common in the repository.",
    ]
    if profile.test_harnesses:
        rules.append(
            f"When discussing test gaps, anchor suggestions to the detected harnesses: {', '.join(profile.test_harnesses)}."
        )
    for framework in profile.frameworks:
        guidance = _FRAMEWORK_GUIDANCE.get(framework)
        if guidance is not None:
            rules.extend(str(rule) for rule in guidance["rules"])
    return _dedupe(rules)


def _render_summary(
    profile: RepositoryCapabilityProfile,
    addon_id: str,
    review_key: str,
    preset_key: str,
) -> str:
    lines = [
        f"Repository: {profile.repo_name}",
        f"Path: {profile.project_path}",
        f"Addon id: {addon_id}",
        f"Generated review key: {review_key}",
        f"Generated preset key: {preset_key}",
        "",
        f"Languages: {', '.join(profile.languages) or 'unknown'}",
        f"Frameworks: {', '.join(profile.frameworks) or 'none detected'}",
        f"Tools: {', '.join(profile.tools) or 'none detected'}",
        f"Test harnesses: {', '.join(profile.test_harnesses) or 'none detected'}",
        f"Style signals: {', '.join(profile.style_signals) or 'none detected'}",
        f"Recommended review types: {', '.join(profile.recommended_review_types)}",
        "",
        "Manifest files:",
    ]
    lines.extend(f"- {manifest}" for manifest in profile.manifests)
    return "\n".join(lines) + "\n"


def _render_review_checklist(approval_request: dict[str, Any]) -> str:
    bundle_comparison = approval_request.get("bundle_comparison", {})
    generated_review_types = ", ".join(bundle_comparison.get("generated_review_types", [])) or "none"
    added_review_types = ", ".join(bundle_comparison.get("added_review_types", [])) or "none"
    lines = [
        "# Generated Addon Review Checklist",
        "",
        f"Addon id: {approval_request.get('addon_id', '')}",
        f"Addon name: {approval_request.get('addon_name', '')}",
        f"Generated review types: {generated_review_types}",
        f"Additional focus beyond the default bundle: {added_review_types}",
        "",
        "## Review Steps",
    ]
    for item in approval_request.get("review_checklist", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Approval Command",
            "",
            f"aicodereviewer approve-addon-preview \"{approval_request.get('output_dir', '')}\" --reviewer <name> --decision approve",
            "",
        ]
    )
    return "\n".join(lines)


def _normalize_addon_id(raw_addon_id: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", raw_addon_id.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Addon id must contain at least one alphanumeric character")
    return normalized


def _pyproject_has_section(root: Path, section: str) -> bool:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return False
    payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    current: Any = payload
    for token in section.split("."):
        if not isinstance(current, dict) or token not in current:
            return False
        current = current[token]
    return True


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_exclude_path(root: Path, path: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts[:-1]
    except ValueError:
        relative_parts = path.parts[:-1]

    for part in relative_parts:
        lowered = part.lower()
        if lowered in _SKIP_DIRS or lowered in _NON_PRIMARY_DIR_NAMES:
            return True
    return False


def _collect_package_json_tokens(payload: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        mapping = payload.get(section)
        if isinstance(mapping, dict):
            tokens.update(str(key).lower() for key in mapping.keys())
    scripts = payload.get("scripts")
    if isinstance(scripts, dict):
        for name, command in scripts.items():
            tokens.add(str(name).lower())
            tokens.update(re.findall(r"[a-z0-9_.-]+", str(command).lower()))
    return tokens


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered