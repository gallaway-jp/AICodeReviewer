from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ReviewDefinition:
    key: str
    prompt: str
    label: str
    group: str
    summary_key: str
    selectable: bool = True
    parent_key: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    requires_spec_content: bool = False
    category_aliases: tuple[str, ...] = field(default_factory=tuple)
    context_augmentation_rules: tuple[str, ...] = field(default_factory=tuple)
    benchmark_metadata: dict[str, Any] = field(default_factory=dict)


class ReviewRegistry:
    """Registry for built-in and future custom review definitions."""

    def __init__(self) -> None:
        self._definitions: dict[str, ReviewDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, definition: ReviewDefinition) -> None:
        if definition.parent_key is not None and definition.parent_key not in self._definitions:
            raise ValueError(
                f"Parent review type '{definition.parent_key}' must be registered before '{definition.key}'"
            )
        if definition.key in self._definitions:
            raise ValueError(f"Review type '{definition.key}' is already registered")
        if definition.key in self._aliases:
            raise ValueError(f"Review type '{definition.key}' is already registered as an alias")
        normalized_aliases = tuple(alias.strip().lower() for alias in definition.aliases if alias.strip())
        for alias in normalized_aliases:
            if alias == definition.key:
                continue
            if alias in self._definitions or alias in self._aliases:
                raise ValueError(f"Review type alias '{alias}' is already registered")
        self._definitions[definition.key] = definition
        for alias in normalized_aliases:
            if alias != definition.key:
                self._aliases[alias] = definition.key

    def get(self, key: str) -> ReviewDefinition:
        return self._definitions[key]

    def resolve_key(self, key: str) -> str:
        normalized = key.strip().lower()
        if normalized in self._definitions:
            return normalized
        if normalized in self._aliases:
            return self._aliases[normalized]
        raise KeyError(normalized)

    def resolve(self, key: str) -> ReviewDefinition:
        return self.get(self.resolve_key(key))

    def list_all(self) -> list[ReviewDefinition]:
        return list(self._definitions.values())

    def list_visible(self) -> list[ReviewDefinition]:
        return [definition for definition in self._definitions.values() if definition.selectable]

    def list_children(self, parent_key: str, *, visible_only: bool = False) -> list[ReviewDefinition]:
        definitions = self.list_visible() if visible_only else self.list_all()
        return [definition for definition in definitions if definition.parent_key == parent_key]

    def lineage_keys(self, key: str) -> tuple[str, ...]:
        definition = self.resolve(key)
        lineage: list[str] = []
        current: ReviewDefinition | None = definition
        seen: set[str] = set()
        while current is not None and current.key not in seen:
            lineage.append(current.key)
            seen.add(current.key)
            if current.parent_key is None:
                break
            current = self._definitions.get(current.parent_key)
        return tuple(lineage)

    def iter_hierarchy(self, *, visible_only: bool = False) -> list[tuple[ReviewDefinition, int]]:
        definitions = self.list_visible() if visible_only else self.list_all()
        included_keys = {definition.key for definition in definitions}
        children_by_parent: dict[str | None, list[ReviewDefinition]] = {}
        for definition in definitions:
            parent_key = definition.parent_key if definition.parent_key in included_keys else None
            children_by_parent.setdefault(parent_key, []).append(definition)

        ordered: list[tuple[ReviewDefinition, int]] = []
        emitted: set[str] = set()

        def _walk(definition: ReviewDefinition, depth: int) -> None:
            if definition.key in emitted:
                return
            ordered.append((definition, depth))
            emitted.add(definition.key)
            for child in children_by_parent.get(definition.key, []):
                _walk(child, depth + 1)

        for definition in children_by_parent.get(None, []):
            _walk(definition, 0)
        for definition in definitions:
            _walk(definition, 0)
        return ordered

    def visible_keys(self) -> list[str]:
        return sorted(definition.key for definition in self.list_visible())


_DEFAULT_REVIEW_REGISTRY: Optional[ReviewRegistry] = None


def set_review_registry(registry: ReviewRegistry) -> None:
    global _DEFAULT_REVIEW_REGISTRY
    _DEFAULT_REVIEW_REGISTRY = registry


def get_review_registry() -> ReviewRegistry:
    if _DEFAULT_REVIEW_REGISTRY is None:
        raise RuntimeError("Review registry has not been initialized")
    return _DEFAULT_REVIEW_REGISTRY