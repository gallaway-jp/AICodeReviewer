# src/aicodereviewer/bedrock.py
"""
Backward-compatibility shim.

The implementation has moved to :mod:`aicodereviewer.backends.bedrock`.
This module re-exports :class:`BedrockClient` so that existing imports
and tests continue to work.
"""
from aicodereviewer.backends.bedrock import BedrockBackend as BedrockClient  # noqa: F401

__all__ = ["BedrockClient"]
