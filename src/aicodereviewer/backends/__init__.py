# src/aicodereviewer/backends/__init__.py
"""
AI backend implementations for AICodeReviewer.

Provides a unified factory for creating AI clients backed by different
services: AWS Bedrock, Kiro CLI (via WSL), GitHub Copilot CLI, and
local LLM servers (OpenAI / Anthropic compatible).

Functions:
    create_backend: Factory that returns an AIBackend based on configuration.
"""
from typing import Optional

from .base import AIBackend
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
]


def create_backend(backend_type: Optional[str] = None, **kwargs) -> AIBackend:
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
    if backend_type is None:
        from aicodereviewer.config import config as app_config
        backend_type = app_config.get("backend", "type", "bedrock")

    backend_type = backend_type.strip().lower()

    if backend_type == "bedrock":
        return BedrockBackend(**kwargs)
    elif backend_type == "kiro":
        return KiroBackend(**kwargs)
    elif backend_type == "copilot":
        return CopilotBackend(**kwargs)
    elif backend_type == "local":
        return LocalLLMBackend(**kwargs)
    else:
        raise ValueError(
            f"Unknown backend type '{backend_type}'. "
            "Supported backends: bedrock, kiro, copilot, local"
        )
