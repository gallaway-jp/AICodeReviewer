# src/aicodereviewer/backends/__init__.py
"""Public backend factory and lazy class exports."""
from typing import Any, Dict, Optional, Type, TYPE_CHECKING

from .base import AIBackend
from aicodereviewer.registries import get_backend_registry

# Type-checking imports (not executed at runtime)
if TYPE_CHECKING:
    from .bedrock import BedrockBackend
    from .kiro import KiroBackend
    from .copilot import CopilotBackend
    from .local_llm import LocalLLMBackend

__all__ = [
    "AIBackend",
    "BedrockBackend",
    "KiroBackend",
    "CopilotBackend",
    "LocalLLMBackend",
    "BACKEND_CHOICES",
    "get_backend_choices",
    "get_backend_registry",
    "create_backend",
    "resolve_backend_type",
]

# Lazy-loaded backend class cache
_backend_classes: Dict[str, Type[AIBackend]] = {}

BACKEND_CHOICES = get_backend_registry().backend_choices


def get_backend_choices() -> tuple[str, ...]:
    """Return the current backend choices from the active registry."""
    return get_backend_registry().backend_choices


def __getattr__(name: str) -> Type[AIBackend]:
    """Lazy import backend classes on first access."""
    if name == "BedrockBackend":
        if "BedrockBackend" not in _backend_classes:
            from .bedrock import BedrockBackend
            _backend_classes["BedrockBackend"] = BedrockBackend
        return _backend_classes["BedrockBackend"]
    elif name == "KiroBackend":
        if "KiroBackend" not in _backend_classes:
            from .kiro import KiroBackend
            _backend_classes["KiroBackend"] = KiroBackend
        return _backend_classes["KiroBackend"]
    elif name == "CopilotBackend":
        if "CopilotBackend" not in _backend_classes:
            from .copilot import CopilotBackend
            _backend_classes["CopilotBackend"] = CopilotBackend
        return _backend_classes["CopilotBackend"]
    elif name == "LocalLLMBackend":
        if "LocalLLMBackend" not in _backend_classes:
            from .local_llm import LocalLLMBackend
            _backend_classes["LocalLLMBackend"] = LocalLLMBackend
        return _backend_classes["LocalLLMBackend"]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def resolve_backend_type(backend_type: Optional[str] = None) -> tuple[str, Dict[str, Any]]:
    """Resolve backend aliases to a canonical backend type plus constructor overrides."""
    return get_backend_registry().resolve(backend_type)


def create_backend(backend_type: Optional[str] = None, **kwargs: Any) -> AIBackend:
    """
    Factory that instantiates the requested AI backend.

    Args:
        backend_type: One of ``'bedrock'``, ``'kiro'``, ``'copilot'``, ``'local'``.
                      If *None*, reads from ``config.ini [backend] type``.
        **kwargs: Forwarded to the backend constructor.

    Returns:
        An initialised :class:`AIBackend` instance.

    Raises:
        ValueError: If *backend_type* is unrecognised.
    """
    return get_backend_registry().create(backend_type, **kwargs)
