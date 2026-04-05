from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

from aicodereviewer.i18n import t
from aicodereviewer.registries import get_review_registry

if TYPE_CHECKING:
    from aicodereviewer.registries import ReviewRegistry


@dataclass(frozen=True)
class ReviewPresetDefinition:
    key: str
    review_types: tuple[str, ...]
    label: str = ""
    summary: str = ""
    group: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


_BUILTIN_REVIEW_PRESET_DEFINITIONS: tuple[ReviewPresetDefinition, ...] = (
    ReviewPresetDefinition(
        key="runtime_safety",
        group="risk_resilience",
        review_types=("security", "error_handling", "data_validation", "dependency"),
    ),
    ReviewPresetDefinition(
        key="code_health",
        group="code_quality",
        review_types=("best_practices", "maintainability", "dead_code", "complexity", "regression"),
    ),
    ReviewPresetDefinition(
        key="interface_platform",
        group="surface_coverage",
        review_types=("api_design", "compatibility", "architecture", "scalability"),
    ),
    ReviewPresetDefinition(
        key="product_surface",
        group="surface_coverage",
        review_types=("ui_ux", "accessibility", "localization", "documentation"),
    ),
    ReviewPresetDefinition(
        key="release_safety",
        group="risk_resilience",
        review_types=("testing", "regression", "error_handling", "compatibility"),
    ),
)


REVIEW_TYPE_PRESETS: dict[str, list[str]] = {}
_REVIEW_PRESET_DEFINITIONS: dict[str, ReviewPresetDefinition] = {}
_REVIEW_PRESET_ALIASES: dict[str, str] = {}
_REVIEW_PRESET_ORDER: list[str] = []


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


def _coerce_review_types(value: Any, *, registry: ReviewRegistry, source: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(review_type, str) for review_type in value):
        raise ValueError(f"{source}: field 'review_types' must be a list of strings")
    if not value:
        raise ValueError(f"{source}: field 'review_types' must not be empty")

    result: list[str] = []
    seen: set[str] = set()
    for raw_review_type in value:
        try:
            canonical_key = registry.resolve_key(raw_review_type)
        except KeyError as exc:
            raise ValueError(
                f"{source}: field 'review_types' references unknown review type '{raw_review_type}'"
            ) from exc
        if not registry.get(canonical_key).selectable:
            raise ValueError(
                f"{source}: field 'review_types' references non-selectable review type '{raw_review_type}'"
            )
        if canonical_key not in seen:
            result.append(canonical_key)
            seen.add(canonical_key)
    return tuple(result)


def _coerce_preset_definition(
    payload: dict[str, Any],
    *,
    registry: ReviewRegistry,
    source: str,
) -> ReviewPresetDefinition:
    key = _coerce_string(payload.get("key"), field_name="key", source=source).lower()
    label = payload.get("label", "")
    summary = payload.get("summary", "")
    if label is None:
        label = ""
    if summary is None:
        summary = ""
    if not isinstance(label, str):
        raise ValueError(f"{source}: field 'label' must be a string")
    if not isinstance(summary, str):
        raise ValueError(f"{source}: field 'summary' must be a string")
    group = payload.get("group", "")
    if group is None:
        group = ""
    if not isinstance(group, str):
        raise ValueError(f"{source}: field 'group' must be a string")

    return ReviewPresetDefinition(
        key=key,
        label=label.strip(),
        summary=summary.strip(),
        group=group.strip(),
        aliases=_coerce_aliases(payload.get("aliases"), source=source),
        review_types=_coerce_review_types(payload.get("review_types"), registry=registry, source=source),
    )


def compose_review_presets(
    registry: ReviewRegistry,
    preset_payloads: Sequence[tuple[str, dict[str, Any]]] | None = None,
) -> list[ReviewPresetDefinition]:
    definitions = list(_BUILTIN_REVIEW_PRESET_DEFINITIONS)
    seen_keys = {definition.key for definition in definitions}
    seen_aliases: set[str] = set()
    for definition in definitions:
        seen_aliases.update(alias for alias in definition.aliases if alias != definition.key)

    if preset_payloads:
        for source, payload in preset_payloads:
            definition = _coerce_preset_definition(payload, registry=registry, source=source)
            if definition.key in seen_keys or definition.key in seen_aliases:
                raise ValueError(f"{source}: review preset '{definition.key}' is already registered")
            for alias in definition.aliases:
                if alias == definition.key:
                    continue
                if alias in seen_keys or alias in seen_aliases:
                    raise ValueError(f"{source}: review preset alias '{alias}' is already registered")
            definitions.append(definition)
            seen_keys.add(definition.key)
            seen_aliases.update(alias for alias in definition.aliases if alias != definition.key)

    return definitions


def install_review_presets(
    preset_definitions: Sequence[ReviewPresetDefinition] | None = None,
    *,
    registry: ReviewRegistry | None = None,
) -> None:
    if preset_definitions is None:
        preset_definitions = compose_review_presets(registry or get_review_registry())

    REVIEW_TYPE_PRESETS.clear()
    _REVIEW_PRESET_DEFINITIONS.clear()
    _REVIEW_PRESET_ALIASES.clear()
    _REVIEW_PRESET_ORDER[:] = []

    for definition in preset_definitions:
        _REVIEW_PRESET_DEFINITIONS[definition.key] = definition
        REVIEW_TYPE_PRESETS[definition.key] = list(definition.review_types)
        _REVIEW_PRESET_ORDER.append(definition.key)
        for alias in definition.aliases:
            if alias != definition.key:
                _REVIEW_PRESET_ALIASES[alias] = definition.key


def list_review_presets() -> list[ReviewPresetDefinition]:
    return [_REVIEW_PRESET_DEFINITIONS[key] for key in _REVIEW_PRESET_ORDER]


def resolve_review_preset_key(preset_key: str) -> str:
    normalized = preset_key.strip().lower()
    if normalized in _REVIEW_PRESET_DEFINITIONS:
        return normalized
    if normalized in _REVIEW_PRESET_ALIASES:
        return _REVIEW_PRESET_ALIASES[normalized]
    raise KeyError(normalized)


def get_review_type_label(review_type: str) -> str:
    label = t(f"review_type.{review_type}")
    if label != f"review_type.{review_type}":
        return label
    try:
        return get_review_registry().get(review_type).label
    except KeyError:
        return review_type


def get_review_preset_label(preset_key: str) -> str:
    canonical_key = resolve_review_preset_key(preset_key)
    definition = _REVIEW_PRESET_DEFINITIONS[canonical_key]
    if definition.label:
        return definition.label
    label = t(f"review_preset.{canonical_key}.label")
    if label != f"review_preset.{canonical_key}.label":
        return label
    return canonical_key.replace("_", " ").title()


def get_review_preset_group_label(preset_key: str) -> str:
    canonical_key = resolve_review_preset_key(preset_key)
    definition = _REVIEW_PRESET_DEFINITIONS[canonical_key]
    if not definition.group:
        return ""
    label = t(f"review_preset_group.{definition.group}")
    if label != f"review_preset_group.{definition.group}":
        return label
    return definition.group


def format_review_preset_picker_label(preset_key: str) -> str:
    group_label = get_review_preset_group_label(preset_key)
    preset_label = get_review_preset_label(preset_key)
    if group_label:
        return f"{group_label} / {preset_label} [{preset_key}]"
    return f"{preset_label} [{preset_key}]"


def get_review_preset_summary(preset_key: str) -> str:
    canonical_key = resolve_review_preset_key(preset_key)
    definition = _REVIEW_PRESET_DEFINITIONS[canonical_key]
    if definition.summary:
        return definition.summary
    summary = t(f"review_preset.{canonical_key}.summary")
    if summary != f"review_preset.{canonical_key}.summary":
        return summary
    return ", ".join(get_review_type_label(review_type) for review_type in REVIEW_TYPE_PRESETS[canonical_key])


def infer_review_type_preset(selected_types: Sequence[str]) -> str | None:
    selected_set = {review_type for review_type in selected_types if review_type}
    if not selected_set:
        return None
    for definition in list_review_presets():
        if selected_set == set(definition.review_types):
            return definition.key
    return None


def format_review_type_preset_lines() -> list[str]:
    lines: list[str] = []
    for definition in list_review_presets():
        preset_key = definition.key
        review_types = REVIEW_TYPE_PRESETS[preset_key]
        group_label = get_review_preset_group_label(preset_key)
        heading = get_review_preset_label(preset_key)
        if group_label:
            heading = f"{heading}  [{group_label}]"
        lines.append(f"  {preset_key:20s}  {heading}")
        summary = get_review_preset_summary(preset_key)
        if summary:
            lines.append(f"{'':24s}{summary}")
        lines.append(f"{'':24s}{t('cli.preset_includes', types=', '.join(review_types))}")
    return lines


try:
    install_review_presets()
except RuntimeError:
    pass