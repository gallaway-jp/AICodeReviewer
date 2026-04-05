from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Sequence

from aicodereviewer.addons import discover_addon_review_pack_paths
from aicodereviewer.config import config
from aicodereviewer.registries import ReviewDefinition, ReviewRegistry, set_review_registry
from aicodereviewer.review_presets import ReviewPresetDefinition, compose_review_presets, install_review_presets


_BUILTIN_REVIEW_PROMPTS = {
    "security": (
        "You are a Senior Security Auditor with deep expertise in OWASP, CWE, and CVE databases. "
        "Focus on critical vulnerabilities: injection attacks (SQL, OS command, LDAP), XSS, CSRF, "
        "authentication/authorization flaws, insecure deserialization, sensitive data exposure, "
        "insecure configurations, and cryptographic weaknesses. "
        "Treat missing authorization on privileged or admin-only paths as at least high severity when sensitive operations or data become reachable to broader users. "
        "Provide specific remediation steps with severity levels (critical/high/medium/low)."
    ),
    "performance": (
        "You are a Performance Engineer specializing in profiling, algorithmic efficiency, "
        "and resource optimization. Identify: O(n²+) algorithms that can be improved, "
        "unnecessary memory allocations, N+1 query patterns, missing caching opportunities, "
        "blocking I/O in hot paths, and inefficient data structures. "
        "Provide actionable optimizations with estimated impact."
    ),
    "best_practices": (
        "You are a Lead Developer and Clean Code advocate. Review for SOLID principles, "
        "DRY violations, proper encapsulation, appropriate design patterns, consistent "
        "naming conventions, idiomatic language usage, and code organization. "
        "Reference specific principles or patterns when identifying issues."
    ),
    "maintainability": (
        "You are a Code Maintenance Expert. Analyze readability, cognitive complexity, "
        "coupling and cohesion, dead code, duplicated logic, overly long functions, "
        "and technical debt. Suggest refactoring opportunities that improve long-term "
        "maintenance without changing behavior."
    ),
    "dead_code": (
        "You are a Dead Code Detection Specialist. Review for unused functions, classes, modules, "
        "imports, feature flags, branches, parameters, return values, compatibility shims, and dormant "
        "UI paths or handlers that appear unreachable or no longer referenced. Focus on evidence-backed "
        "findings only: prefer concrete references, call sites, route wiring, exports, or configuration "
        "usage before declaring code dead. Distinguish truly unused code from public extension points, "
        "framework hooks, interface implementations, and intentionally reserved compatibility surfaces."
    ),
    "documentation": (
        "You are a Technical Writer and Documentation Specialist. Review inline comments, "
        "docstrings/JSDoc/Javadoc, README accuracy, API documentation completeness, "
        "misleading or outdated comments, and missing documentation for public interfaces. "
        "Rate documentation coverage and suggest improvements."
    ),
    "testing": (
        "You are a QA Engineer and Test Architect. Analyze testability, missing test "
        "coverage, inadequate assertions, brittle tests, missing edge cases, untested "
        "error paths, and suggest testing strategies (unit, integration, property-based). "
        "Identify code that is hard to test and suggest refactoring for testability."
    ),
    "accessibility": (
        "You are an Accessibility Specialist certified in WCAG 2.1 AA. Review for "
        "missing ARIA labels, insufficient color contrast, keyboard navigation issues, "
        "screen reader compatibility, focus management, and semantic HTML usage. "
        "Reference specific WCAG success criteria."
    ),
    "scalability": (
        "You are a System Architect specializing in distributed systems. Analyze "
        "scalability bottlenecks, stateful components that hinder horizontal scaling, "
        "missing connection pooling, unbounded queues, lack of circuit breakers, "
        "and missing rate limiting. Suggest architectural improvements."
    ),
    "compatibility": (
        "You are a Platform Engineer. Review cross-platform compatibility, deprecated "
        "API usage, browser compatibility issues, Python 2/3 or Node version concerns, "
        "OS-specific code paths, and dependency version conflicts. "
        "Flag potential breakage across environments."
    ),
    "error_handling": (
        "You are a Reliability Engineer. Analyze error handling completeness, bare "
        "except clauses, swallowed exceptions, missing finally blocks, insufficient "
        "error context, missing input validation at boundaries, and missing retry "
        "logic for transient failures. Suggest resilience improvements."
    ),
    "complexity": (
        "You are a Code Analyst specializing in complexity metrics. Evaluate cyclomatic "
        "complexity, cognitive complexity, nesting depth, method/class size, parameter "
        "counts, and coupling metrics. Suggest concrete simplifications and decompositions."
    ),
    "architecture": (
        "You are a Software Architect. Review code structure, layer separation, "
        "dependency direction, module boundaries, interface design, and adherence to "
        "architectural patterns (MVC, hexagonal, event-driven, etc.). "
        "Identify architectural smells and propose improvements."
    ),
    "license": (
        "You are a License Compliance Specialist. Review third-party library usage, "
        "license compatibility (GPL, MIT, Apache, etc.), attribution requirements, "
        "copyleft obligations, and potential compliance risks. "
        "Flag any license conflicts or missing notices."
    ),
    "localization": (
        "You are an Internationalization Specialist. Review for hardcoded strings, "
        "missing translation keys, date/time/number/currency formatting issues, "
        "RTL layout support, locale-sensitive comparisons, and cultural compliance. "
        "Identify i18n anti-patterns and suggest proper externalization."
    ),
    "specification": (
        "You are a Requirements Analyst. Compare the code against the provided "
        "specification document. Identify deviations, missing implementations, "
        "incorrect interpretations, unhandled edge cases from the spec, and any "
        "functionality that exceeds or contradicts the requirements."
    ),
    "dependency": (
        "You are a Dependency Management Expert. Analyze imported libraries and "
        "packages for: known vulnerabilities, outdated versions, unnecessary "
        "dependencies, license risks, heavy transitive dependency trees, and "
        "missing lockfile discipline. Recommend safer or lighter alternatives."
    ),
    "concurrency": (
        "You are a Concurrency and Parallelism Expert. Analyze thread safety, "
        "race conditions, deadlock potential, improper synchronization, shared "
        "mutable state, missing locks, async/await anti-patterns, and resource "
        "contention. Suggest correct synchronization strategies."
    ),
    "api_design": (
        "You are an API Design Specialist. Review REST/GraphQL endpoint design, "
        "resource naming, HTTP method usage, status code correctness, pagination, "
        "versioning strategy, request/response schema design, and backward "
        "compatibility. Reference relevant API design guidelines."
    ),
    "data_validation": (
        "You are a Data Validation Expert. Analyze input validation completeness, "
        "missing sanitization, type coercion risks, boundary checks, SQL/NoSQL "
        "injection vectors through unvalidated input, and schema validation gaps. "
        "Suggest validation strategies and libraries."
    ),
    "regression": (
        "You are a Regression Testing Specialist and Quality Assurance Expert. "
        "Analyze code changes for: unintended side effects, breaking changes that "
        "impact pre-existing features, degradation in performance (slower execution, "
        "higher memory usage, increased latency), breaks in backward compatibility, "
        "disabled features, and behavioral changes that contradict original intent. "
        "Focus on identifying what could break for existing users and suggest "
        "preventative measures like additional tests or gradual migration strategies."
    ),
    "ui_ux": (
        "You are a Senior UI/UX Reviewer with expertise in product usability, interaction design, "
        "content hierarchy, and frontend implementation quality. Review for confusing workflows, "
        "weak affordances, unclear calls to action, inconsistent states, poor visual hierarchy, "
        "overly dense layouts, missing empty/loading/error states, fragile form interactions, and "
        "responsive behavior risks. Focus on issues visible in the implemented interface or UI code. "
        "When accessibility is relevant you may note it, but prioritise broader usability and task-flow issues over strict WCAG-only findings."
    ),
    "fix": (
        "You are an expert code fixer. Fix the code issues identified. "
        "Return ONLY the complete corrected code, no explanations or markdown."
    ),
    "interaction_analysis": (
        "You are a Senior Code Review Analyst specialising in cross-issue "
        "dependency and conflict detection.  Given a list of code review "
        "findings, identify interactions between them: conflicts if both "
        "fixes are applied, cascading effects, issues that should be "
        "prioritised together, and duplicate / overlapping findings.\n\n"
        "Respond with valid JSON matching this schema:\n"
        '{\n'
        '  "interactions": [\n'
        '    {\n'
        '      "issue_indices": [<int>, <int>],\n'
        '      "relationship": "conflict|cascade|group|duplicate",\n'
        '      "summary": "<brief explanation>"\n'
        '    }\n'
        '  ],\n'
        '  "priority_order": [<int>, ...],\n'
        '  "overall_summary": "<1-2 sentence overview>"\n'
        '}\n\n'
        "Rules:\n"
        "- issue_indices are 0-based positions from the provided list.\n"
        "- relationship MUST be one of: conflict, cascade, group, duplicate.\n"
        "- priority_order lists issue indices in recommended fix order.\n"
        "- Return ONLY the JSON object. No markdown, no fences, no extra text.\n"
        "- If there are no meaningful interactions respond with an empty "
        "interactions array."
    ),
    "architectural_review": (
        "You are a Software Architect performing a project-level structural "
        "analysis.  You are given (1) a project directory overview, "
        "(2) a summary of per-file review findings, and optionally "
        "(3) an import / dependency graph.\n\n"
        "Identify cross-cutting architectural issues that are NOT visible "
        "when reviewing individual files in isolation:\n"
        "- Circular dependencies between modules\n"
        "- Layering violations (e.g. UI importing DB layer directly)\n"
        "- God classes or modules (excessive responsibility)\n"
        "- Inappropriate or hidden coupling\n"
        "- Missing abstractions or interfaces\n"
        "- Single points of failure\n"
        "- Incoherent module organization\n"
        "- Duplicated responsibility across modules\n\n"
        "Return your findings as valid JSON matching the standard review "
        "schema (see your instructions).  Use file_path='PROJECT' for "
        "project-level findings and the actual path for file-specific ones."
    ),
}

_BUILTIN_REVIEW_TYPE_META = {
    "security": {"label": "Security Audit", "group": "Quality", "summary_key": "review_type_desc.security"},
    "performance": {"label": "Performance", "group": "Quality", "summary_key": "review_type_desc.performance"},
    "best_practices": {"label": "Best Practices", "group": "Quality", "summary_key": "review_type_desc.best_practices"},
    "maintainability": {"label": "Maintainability", "group": "Quality", "summary_key": "review_type_desc.maintainability"},
    "dead_code": {"label": "Dead Code", "group": "Quality", "summary_key": "review_type_desc.dead_code"},
    "documentation": {"label": "Documentation", "group": "Quality", "summary_key": "review_type_desc.documentation"},
    "testing": {"label": "Testing", "group": "Quality", "summary_key": "review_type_desc.testing"},
    "error_handling": {"label": "Error Handling", "group": "Quality", "summary_key": "review_type_desc.error_handling"},
    "complexity": {"label": "Complexity Analysis", "group": "Quality", "summary_key": "review_type_desc.complexity"},
    "accessibility": {"label": "Accessibility", "group": "Compliance", "summary_key": "review_type_desc.accessibility"},
    "scalability": {"label": "Scalability", "group": "Architecture", "summary_key": "review_type_desc.scalability"},
    "compatibility": {"label": "Compatibility", "group": "Architecture", "summary_key": "review_type_desc.compatibility"},
    "architecture": {"label": "Architecture", "group": "Architecture", "summary_key": "review_type_desc.architecture"},
    "license": {"label": "License Compliance", "group": "Compliance", "summary_key": "review_type_desc.license"},
    "localization": {"label": "Localization / i18n", "group": "Compliance", "summary_key": "review_type_desc.localization"},
    "specification": {"label": "Specification Match", "group": "Compliance", "summary_key": "review_type_desc.specification"},
    "dependency": {"label": "Dependency Analysis", "group": "Architecture", "summary_key": "review_type_desc.dependency"},
    "concurrency": {"label": "Concurrency Safety", "group": "Quality", "summary_key": "review_type_desc.concurrency"},
    "api_design": {"label": "API Design", "group": "Architecture", "summary_key": "review_type_desc.api_design"},
    "data_validation": {"label": "Data Validation", "group": "Quality", "summary_key": "review_type_desc.data_validation"},
    "regression": {"label": "Regression Analysis", "group": "Quality", "summary_key": "review_type_desc.regression"},
    "ui_ux": {"label": "UI/UX Review", "group": "Quality", "summary_key": "review_type_desc.ui_ux"},
}

_INTERNAL_REVIEW_TYPES = frozenset({"fix", "interaction_analysis", "architectural_review"})

_BUILTIN_REVIEW_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "localization": ("i18n",),
    "specification": ("spec",),
}

_BUILTIN_REVIEW_TYPE_PARENTS: dict[str, str] = {
    "architectural_review": "architecture",
}

_BUILTIN_REVIEW_TYPE_SPEC_REQUIREMENTS = frozenset({"specification"})

REVIEW_PROMPTS: dict[str, str] = {}
REVIEW_TYPE_META: dict[str, dict[str, str]] = {}
REVIEW_TYPE_KEYS: list[str] = []
_ACTIVE_REVIEW_PACK_PATHS: tuple[Path, ...] = ()


def _config_base_dir() -> Path:
    config_path = getattr(config, "config_path", None)
    if config_path is not None:
        return Path(config_path).resolve().parent
    return Path.cwd()


def _parse_configured_pack_paths(raw_paths: str) -> list[str]:
    separators = ["\n", ",", os.pathsep]
    normalized = raw_paths
    for separator in separators:
        normalized = normalized.replace(separator, "\n")
    return [token.strip() for token in normalized.splitlines() if token.strip()]


def _expand_pack_path(path_spec: str, *, base_dir: Path) -> list[Path]:
    path = Path(path_spec)
    if not path.is_absolute():
        path = base_dir / path
    if any(glob_char in str(path) for glob_char in "*?["):
        return sorted(candidate.resolve() for candidate in path.parent.glob(path.name) if candidate.is_file())
    if path.is_dir():
        return sorted(candidate.resolve() for candidate in path.glob("*.json") if candidate.is_file())
    return [path.resolve()]


def discover_review_pack_paths() -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    default_dir = _config_base_dir() / "review_packs"
    if default_dir.is_dir():
        for candidate in sorted(default_dir.glob("*.json")):
            resolved = candidate.resolve()
            if resolved not in seen:
                discovered.append(resolved)
                seen.add(resolved)
    configured = str(config.get("review_packs", "paths", "") or "")
    for token in _parse_configured_pack_paths(configured):
        for candidate in _expand_pack_path(token, base_dir=_config_base_dir()):
            if candidate not in seen:
                discovered.append(candidate)
                seen.add(candidate)
    for candidate in discover_addon_review_pack_paths():
        if candidate not in seen:
            discovered.append(candidate)
            seen.add(candidate)
    return discovered


def merge_review_pack_paths(extra_pack_paths: Sequence[str | Path] | None = None) -> list[Path]:
    merged: list[Path] = []
    seen: set[Path] = set()
    for pack_path in discover_review_pack_paths():
        resolved = Path(pack_path).resolve()
        if resolved not in seen:
            merged.append(resolved)
            seen.add(resolved)
    for pack_path in extra_pack_paths or ():
        resolved = Path(pack_path).resolve()
        if resolved not in seen:
            merged.append(resolved)
            seen.add(resolved)
    return merged


def _coerce_string(value: Any, *, field_name: str, source: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{source}: field '{field_name}' must be a string")
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{source}: field '{field_name}' must not be empty")
    return normalized


def _coerce_aliases(value: Any, *, source: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(alias, str) for alias in value):
        raise ValueError(f"{source}: field 'aliases' must be a list of strings")
    return tuple(alias.strip().lower() for alias in value if alias.strip())


def _coerce_string_list(value: Any, *, field_name: str, source: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{source}: field '{field_name}' must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


def _coerce_mapping(value: Any, *, field_name: str, source: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{source}: field '{field_name}' must be an object with string keys")
    return dict(value)


def _merge_string_values(parent_values: tuple[str, ...], child_values: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in (*parent_values, *child_values):
        normalized = value.strip()
        if not normalized:
            continue
        dedupe_key = normalized.lower()
        if dedupe_key in seen:
            continue
        merged.append(normalized)
        seen.add(dedupe_key)
    return tuple(merged)


def _definition_meta_payload(definition: ReviewDefinition) -> dict[str, str]:
    return {
        "label": definition.label,
        "group": definition.group,
        "summary_key": definition.summary_key,
        "parent_key": definition.parent_key or "",
        "requires_spec_content": str(definition.requires_spec_content).lower(),
    }


def _register_definition_payload(
    registry: ReviewRegistry,
    payload: dict[str, Any],
    *,
    source: str,
) -> bool:
    key = _coerce_string(payload.get("key"), field_name="key", source=source).lower()
    parent_key_raw = payload.get("parent_key")
    parent_key = None
    parent_definition = None
    if parent_key_raw is not None:
        parent_key = _coerce_string(parent_key_raw, field_name="parent_key", source=source).lower()
        try:
            parent_definition = registry.resolve(parent_key)
        except KeyError:
            return False
        parent_key = parent_definition.key

    prompt_raw = payload.get("prompt")
    prompt_append_raw = payload.get("prompt_append")
    if prompt_raw is not None and not isinstance(prompt_raw, str):
        raise ValueError(f"{source}: field 'prompt' must be a string")
    if prompt_append_raw is not None and not isinstance(prompt_append_raw, str):
        raise ValueError(f"{source}: field 'prompt_append' must be a string")

    if prompt_raw is not None and prompt_raw.strip():
        prompt = prompt_raw.strip()
    elif parent_definition is not None:
        prompt = parent_definition.prompt
    else:
        raise ValueError(f"{source}: field 'prompt' is required for root review definitions")
    if prompt_append_raw and prompt_append_raw.strip():
        prompt = f"{prompt}\n\n{prompt_append_raw.strip()}"

    label = payload.get("label")
    if label is None:
        label_value = parent_definition.label if parent_definition is not None else key.replace("_", " ").title()
    else:
        label_value = _coerce_string(label, field_name="label", source=source)

    group = payload.get("group")
    if group is None:
        group_value = parent_definition.group if parent_definition is not None else "Custom"
    else:
        group_value = _coerce_string(group, field_name="group", source=source)

    summary_key = payload.get("summary_key")
    if summary_key is None:
        summary_value = parent_definition.summary_key if parent_definition is not None else ""
    else:
        summary_value = _coerce_string(summary_key, field_name="summary_key", source=source, allow_empty=True)

    selectable_raw = payload.get("selectable", True)
    if not isinstance(selectable_raw, bool):
        raise ValueError(f"{source}: field 'selectable' must be a boolean")

    requires_spec_raw = payload.get("requires_spec_content")
    if requires_spec_raw is None:
        requires_spec_content = parent_definition.requires_spec_content if parent_definition is not None else False
    else:
        if not isinstance(requires_spec_raw, bool):
            raise ValueError(f"{source}: field 'requires_spec_content' must be a boolean")
        requires_spec_content = requires_spec_raw

    if parent_definition is not None:
        inherited_category_aliases = parent_definition.category_aliases
        inherited_context_rules = parent_definition.context_augmentation_rules
        inherited_benchmark_metadata = dict(parent_definition.benchmark_metadata)
    else:
        inherited_category_aliases = ()
        inherited_context_rules = ()
        inherited_benchmark_metadata = {}

    category_aliases = _merge_string_values(
        inherited_category_aliases,
        _coerce_string_list(payload.get("category_aliases"), field_name="category_aliases", source=source),
    )
    context_augmentation_rules = _merge_string_values(
        inherited_context_rules,
        _coerce_string_list(
            payload.get("context_augmentation_rules"),
            field_name="context_augmentation_rules",
            source=source,
        ),
    )
    benchmark_metadata = inherited_benchmark_metadata
    benchmark_metadata.update(
        _coerce_mapping(payload.get("benchmark_metadata"), field_name="benchmark_metadata", source=source)
    )

    registry.register(
        ReviewDefinition(
            key=key,
            prompt=prompt,
            label=label_value,
            group=group_value,
            summary_key=summary_value,
            selectable=selectable_raw,
            parent_key=parent_key,
            aliases=_coerce_aliases(payload.get("aliases"), source=source),
            requires_spec_content=requires_spec_content,
            category_aliases=category_aliases,
            context_augmentation_rules=context_augmentation_rules,
            benchmark_metadata=benchmark_metadata,
        )
    )
    return True


def _load_pack_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Review pack '{path}' was not found") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Review pack '{path}' is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Review pack '{path}' must contain a JSON object")
    version = payload.get("version", 1)
    if version != 1:
        raise ValueError(f"Review pack '{path}' uses unsupported version '{version}'")
    return payload


def _load_pack_definition_payloads(path: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = manifest.get("review_definitions")
    if definitions is None:
        return []
    if not isinstance(definitions, list):
        raise ValueError(f"Review pack '{path}' must define a 'review_definitions' list")
    for index, definition_payload in enumerate(definitions):
        if not isinstance(definition_payload, dict):
            raise ValueError(
                f"Review pack '{path}' has invalid review definition at index {index}: expected object"
            )
    return definitions


def _load_pack_preset_payloads(path: Path, manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    presets = manifest.get("review_presets")
    if presets is None:
        return []
    if not isinstance(presets, list):
        raise ValueError(f"Review pack '{path}' must define a 'review_presets' list")
    payloads: list[tuple[str, dict[str, Any]]] = []
    for index, preset_payload in enumerate(presets):
        if not isinstance(preset_payload, dict):
            raise ValueError(
                f"Review pack '{path}' has invalid review preset at index {index}: expected object"
            )
        payloads.append((f"{path} preset #{index + 1}", preset_payload))
    return payloads


def _register_pack(registry: ReviewRegistry, path: Path, manifest: dict[str, Any]) -> None:
    pending = list(_load_pack_definition_payloads(path, manifest))
    while pending:
        remaining: list[dict[str, Any]] = []
        progress_made = False
        for index, payload in enumerate(pending):
            source = f"{path} definition #{index + 1}"
            try:
                registered = _register_definition_payload(registry, payload, source=source)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
            if registered:
                progress_made = True
            else:
                remaining.append(payload)
        if not progress_made:
            unresolved = []
            for payload in remaining:
                key = payload.get("key", "<unknown>")
                parent_key = payload.get("parent_key", "<missing>")
                unresolved.append(f"{key} -> parent {parent_key}")
            joined = ", ".join(unresolved)
            raise ValueError(f"Review pack '{path}' contains unknown or cyclic parent definitions: {joined}")
        pending = remaining


def _resolve_pack_paths(pack_paths: Sequence[str | Path] | None = None) -> list[Path]:
    return discover_review_pack_paths() if pack_paths is None else [Path(pack_path).resolve() for pack_path in pack_paths]


def get_active_review_pack_paths() -> tuple[Path, ...]:
    return _ACTIVE_REVIEW_PACK_PATHS


def compose_review_pack_state(
    pack_paths: Sequence[str | Path] | None = None,
) -> tuple[ReviewRegistry, list[ReviewPresetDefinition]]:
    resolved_pack_paths = _resolve_pack_paths(pack_paths)
    manifests = [(pack_path, _load_pack_manifest(pack_path)) for pack_path in resolved_pack_paths]

    registry = ReviewRegistry()
    for key, prompt in _BUILTIN_REVIEW_PROMPTS.items():
        meta = _BUILTIN_REVIEW_TYPE_META.get(
            key,
            {
                "label": key.replace("_", " ").title(),
                "group": "Internal",
                "summary_key": "",
            },
        )
        registry.register(
            ReviewDefinition(
                key=key,
                prompt=prompt,
                label=meta["label"],
                group=meta["group"],
                summary_key=meta["summary_key"],
                selectable=key not in _INTERNAL_REVIEW_TYPES,
                parent_key=_BUILTIN_REVIEW_TYPE_PARENTS.get(key),
                aliases=_BUILTIN_REVIEW_TYPE_ALIASES.get(key, ()),
                requires_spec_content=key in _BUILTIN_REVIEW_TYPE_SPEC_REQUIREMENTS,
            )
        )
    for pack_path, manifest in manifests:
        _register_pack(registry, pack_path, manifest)

    preset_payloads: list[tuple[str, dict[str, Any]]] = []
    for pack_path, manifest in manifests:
        preset_payloads.extend(_load_pack_preset_payloads(pack_path, manifest))
    preset_definitions = compose_review_presets(registry, preset_payloads)
    return registry, preset_definitions


def compose_review_registry(pack_paths: Sequence[str | Path] | None = None) -> ReviewRegistry:
    registry, _preset_definitions = compose_review_pack_state(pack_paths)
    return registry


def install_review_registry(pack_paths: Sequence[str | Path] | None = None) -> ReviewRegistry:
    global _ACTIVE_REVIEW_PACK_PATHS
    registry, preset_definitions = compose_review_pack_state(pack_paths)
    _ACTIVE_REVIEW_PACK_PATHS = tuple(_resolve_pack_paths(pack_paths))
    set_review_registry(registry)
    install_review_presets(preset_definitions, registry=registry)
    REVIEW_PROMPTS.clear()
    REVIEW_PROMPTS.update({definition.key: definition.prompt for definition in registry.list_all()})
    REVIEW_TYPE_META.clear()
    REVIEW_TYPE_META.update({definition.key: _definition_meta_payload(definition) for definition in registry.list_all()})
    REVIEW_TYPE_KEYS[:] = list(registry.visible_keys())
    return registry


install_review_registry()