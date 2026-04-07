from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Optional

if TYPE_CHECKING:
    from aicodereviewer.backends.base import AIBackend

BackendFactory = Callable[..., "AIBackend"]


DEFAULT_BACKEND_ALIASES: Dict[str, str] = {
    "aws": "bedrock",
    "aws-bedrock": "bedrock",
    "bedrock-runtime": "bedrock",
    "kiro-cli": "kiro",
    "github-copilot": "copilot",
    "copilot-cli": "copilot",
    "local-llm": "local",
    "local-llm-server": "local",
    "local-llm-backend": "local",
    "local-llm-api": "local",
}

LOCAL_PROVIDER_ALIASES = frozenset({"lmstudio", "ollama", "openai", "anthropic"})


@dataclass(frozen=True)
class BackendDescriptor:
    key: str
    factory: BackendFactory
    display_name: str
    aliases: tuple[str, ...] = ()
    capabilities: frozenset[str] = field(default_factory=frozenset)


class BackendRegistry:
    """Registry of available backend providers and their aliases."""

    def __init__(self) -> None:
        self._descriptors: dict[str, BackendDescriptor] = {}
        self._alias_map: dict[str, str] = {}

    def register(self, descriptor: BackendDescriptor) -> None:
        key = self._normalize(descriptor.key)
        if key in self._descriptors:
            raise ValueError(f"Backend '{descriptor.key}' is already registered")
        self._descriptors[key] = descriptor
        self._alias_map[key] = key
        for alias in descriptor.aliases:
            normalized_alias = self._normalize(alias)
            existing = self._alias_map.get(normalized_alias)
            if existing is not None and existing != key:
                raise ValueError(
                    f"Backend alias '{alias}' is already registered for '{existing}'"
                )
            self._alias_map[normalized_alias] = key

    def list_descriptors(self) -> list[BackendDescriptor]:
        return list(self._descriptors.values())

    def resolve_descriptor(self, backend_type: Optional[str] = None) -> tuple[BackendDescriptor, Dict[str, Any]]:
        canonical, overrides = self.resolve(backend_type)
        descriptor = self._descriptors.get(canonical)
        if descriptor is None:
            supported = ", ".join(sorted(self._descriptors))
            raise ValueError(
                f"Unknown backend type '{canonical}'. Supported backends: {supported}"
            )
        return descriptor, overrides

    @property
    def backend_choices(self) -> tuple[str, ...]:
        canonical = sorted(self._descriptors)
        aliases = sorted(
            alias for alias, key in self._alias_map.items() if alias != key
        )
        return tuple([*canonical, *aliases, *sorted(LOCAL_PROVIDER_ALIASES)])

    def resolve(
        self,
        backend_type: Optional[str] = None,
    ) -> tuple[str, Dict[str, Any]]:
        resolved_type: str
        if backend_type is None:
            from aicodereviewer.config import config as app_config

            resolved_type = app_config.get("backend", "type", "bedrock")
        else:
            resolved_type = backend_type

        normalized = self._normalize(resolved_type or "bedrock")
        if not normalized:
            normalized = "bedrock"

        if normalized in LOCAL_PROVIDER_ALIASES:
            return "local", {"api_type": normalized}

        canonical = self._alias_map.get(normalized, normalized)
        return canonical, {}

    def create(self, backend_type: Optional[str] = None, **kwargs: Any) -> AIBackend:
        descriptor, backend_kwargs = self.resolve_descriptor(backend_type)
        backend_kwargs.update(kwargs)
        return descriptor.factory(**backend_kwargs)

    @staticmethod
    def _normalize(value: str) -> str:
        return str(value).strip().lower().replace("_", "-").replace(" ", "-")


def _create_bedrock_backend(**kwargs: Any) -> AIBackend:
    from aicodereviewer.backends.bedrock import BedrockBackend

    return BedrockBackend(**kwargs)


def _create_kiro_backend(**kwargs: Any) -> AIBackend:
    from aicodereviewer.backends.kiro import KiroBackend

    return KiroBackend(**kwargs)


def _create_copilot_backend(**kwargs: Any) -> AIBackend:
    from aicodereviewer.backends.copilot import CopilotBackend

    return CopilotBackend(**kwargs)


def _create_local_backend(**kwargs: Any) -> AIBackend:
    from aicodereviewer.backends.local_llm import LocalLLMBackend

    return LocalLLMBackend(**kwargs)


def _build_default_backend_registry() -> BackendRegistry:
    registry = BackendRegistry()
    registry.register(
        BackendDescriptor(
            key="bedrock",
            display_name="AWS Bedrock",
            factory=_create_bedrock_backend,
            aliases=("aws", "aws-bedrock", "bedrock-runtime"),
        )
    )
    registry.register(
        BackendDescriptor(
            key="kiro",
            display_name="Kiro CLI",
            factory=_create_kiro_backend,
            aliases=("kiro-cli",),
        )
    )
    registry.register(
        BackendDescriptor(
            key="copilot",
            display_name="GitHub Copilot CLI",
            factory=_create_copilot_backend,
            aliases=("github-copilot", "copilot-cli"),
            capabilities=frozenset({"tool_file_access"}),
        )
    )
    registry.register(
        BackendDescriptor(
            key="local",
            display_name="Local LLM",
            factory=_create_local_backend,
            aliases=("local-llm", "local-llm-server", "local-llm-backend", "local-llm-api"),
        )
    )
    return registry


_DEFAULT_BACKEND_REGISTRY: BackendRegistry | None = None


def set_backend_registry(registry: BackendRegistry) -> None:
    global _DEFAULT_BACKEND_REGISTRY
    _DEFAULT_BACKEND_REGISTRY = registry


def compose_backend_registry(
    descriptors: Iterable[BackendDescriptor] | None = None,
) -> BackendRegistry:
    registry = _build_default_backend_registry()
    for descriptor in descriptors or ():
        registry.register(descriptor)
    return registry


def install_backend_registry(
    descriptors: Iterable[BackendDescriptor] | None = None,
) -> BackendRegistry:
    registry = compose_backend_registry(descriptors)
    set_backend_registry(registry)
    return registry


def get_backend_registry() -> BackendRegistry:
    global _DEFAULT_BACKEND_REGISTRY
    if _DEFAULT_BACKEND_REGISTRY is None:
        _DEFAULT_BACKEND_REGISTRY = _build_default_backend_registry()
    return _DEFAULT_BACKEND_REGISTRY