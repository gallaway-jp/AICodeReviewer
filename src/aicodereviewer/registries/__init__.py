"""Lazy registry exports to avoid cross-module import cycles."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	from .backend_registry import BackendDescriptor, BackendRegistry, compose_backend_registry, get_backend_registry, install_backend_registry, set_backend_registry
	from .review_registry import ReviewDefinition, ReviewRegistry, get_review_registry, set_review_registry

__all__ = [
	"BackendDescriptor",
	"BackendRegistry",
	"compose_backend_registry",
	"ReviewDefinition",
	"ReviewRegistry",
	"get_backend_registry",
	"install_backend_registry",
	"get_review_registry",
	"set_backend_registry",
	"set_review_registry",
]


def __getattr__(name: str) -> Any:
	if name in {"BackendDescriptor", "BackendRegistry", "compose_backend_registry", "get_backend_registry", "install_backend_registry", "set_backend_registry"}:
		from .backend_registry import BackendDescriptor, BackendRegistry, compose_backend_registry, get_backend_registry, install_backend_registry, set_backend_registry

		return {
			"BackendDescriptor": BackendDescriptor,
			"BackendRegistry": BackendRegistry,
			"compose_backend_registry": compose_backend_registry,
			"get_backend_registry": get_backend_registry,
			"install_backend_registry": install_backend_registry,
			"set_backend_registry": set_backend_registry,
		}[name]
	if name in {"ReviewDefinition", "ReviewRegistry", "get_review_registry", "set_review_registry"}:
		from .review_registry import (
			ReviewDefinition,
			ReviewRegistry,
			get_review_registry,
			set_review_registry,
		)

		return {
			"ReviewDefinition": ReviewDefinition,
			"ReviewRegistry": ReviewRegistry,
			"get_review_registry": get_review_registry,
			"set_review_registry": set_review_registry,
		}[name]
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")