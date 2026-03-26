# src/aicodereviewer/backends/__init__.py
"""
AI backend implementations for AICodeReviewer.

Provides a unified factory for creating AI clients backed by different
services: AWS Bedrock, Kiro CLI (via WSL), GitHub Copilot CLI, and
local LLM servers (OpenAI / Anthropic compatible).

Functions:
    create_backend: Factory that returns an AIBackend based on configuration.

Performance Note:
    Backend classes are imported lazily to avoid loading heavy dependencies
    (e.g. boto3 for Bedrock) until actually needed.
"""
from typing import Any, Dict, Optional, Type, TYPE_CHECKING

from .base import AIBackend

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
    "create_backend",
    "resolve_backend_type",
]

# Lazy-loaded backend class cache
_backend_classes: Dict[str, Type[AIBackend]] = {}

_BACKEND_ALIASES: Dict[str, str] = {
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

_LOCAL_PROVIDER_ALIASES = {"lmstudio", "ollama", "openai", "anthropic"}


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
    resolved_type: str
    if backend_type is None:
        from aicodereviewer.config import config as app_config
        resolved_type = app_config.get("backend", "type", "bedrock")
    else:
        resolved_type = backend_type

    normalized = str(resolved_type or "bedrock").strip().lower()
    if not normalized:
        normalized = "bedrock"

    alias_key = normalized.replace("_", "-").replace(" ", "-")
    if alias_key in _LOCAL_PROVIDER_ALIASES:
        return "local", {"api_type": alias_key}

    canonical = _BACKEND_ALIASES.get(alias_key, alias_key)
    return canonical, {}


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
    _type, backend_kwargs = resolve_backend_type(backend_type)
    backend_kwargs.update(kwargs)

    if _type == "bedrock":
        from .bedrock import BedrockBackend
        return BedrockBackend(**backend_kwargs)
    elif _type == "kiro":
        from .kiro import KiroBackend
        return KiroBackend(**backend_kwargs)
    elif _type == "copilot":
        from .copilot import CopilotBackend
        return CopilotBackend(**backend_kwargs)
    elif _type == "local":
        from .local_llm import LocalLLMBackend
        return LocalLLMBackend(**backend_kwargs)
    else:
        raise ValueError(
            f"Unknown backend type '{_type}'. "
            "Supported backends: bedrock, kiro, copilot, local"
        )
