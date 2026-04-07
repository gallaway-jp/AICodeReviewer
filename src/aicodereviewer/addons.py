from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from aicodereviewer import __version__
from aicodereviewer.config import config
from aicodereviewer.registries import BackendDescriptor, compose_backend_registry, set_backend_registry

if TYPE_CHECKING:
    from aicodereviewer.backends.base import AIBackend

logger = logging.getLogger(__name__)

ADDON_MANIFEST_FILENAME = "addon.json"
ADDON_MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AddonCompatibility:
    min_app_version: str | None = None
    max_app_version: str | None = None


@dataclass(frozen=True)
class AddonManifest:
    addon_id: str
    addon_version: str
    name: str
    manifest_path: Path
    root_dir: Path
    permissions: tuple[str, ...] = ()
    compatibility: AddonCompatibility = field(default_factory=AddonCompatibility)
    entry_points: dict[str, Any] = field(default_factory=dict)
    review_pack_paths: tuple[Path, ...] = ()
    backend_provider_specs: tuple["AddonBackendProviderSpec", ...] = ()
    ui_contributor_specs: tuple["AddonUIContributorSpec", ...] = ()
    editor_hook_specs: tuple["AddonEditorHookSpec", ...] = ()


@dataclass(frozen=True)
class AddonBackendProviderSpec:
    addon_id: str
    key: str
    display_name: str
    module_path: Path
    factory_name: str
    aliases: tuple[str, ...] = ()
    capabilities: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AddonUIContributorSpec:
    addon_id: str
    surface: str
    title: str
    description: str | None = None
    lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class AddonEditorHookSpec:
    addon_id: str
    module_path: Path
    factory_name: str


@dataclass(frozen=True)
class AddonEditorHook:
    addon_id: str
    manifest_path: Path
    handler: Any


@dataclass(frozen=True)
class AddonEditorDiagnostic:
    addon_id: str
    message: str
    severity: str = "info"


@dataclass(frozen=True)
class AddonDiagnostic:
    severity: str
    message: str
    manifest_path: Path | None = None
    addon_id: str | None = None


@dataclass(frozen=True)
class AddonRuntime:
    manifests: tuple[AddonManifest, ...] = ()
    backend_descriptors: tuple[BackendDescriptor, ...] = ()
    editor_hooks: tuple[AddonEditorHook, ...] = ()
    diagnostics: tuple[AddonDiagnostic, ...] = ()


_ACTIVE_ADDON_RUNTIME = AddonRuntime()


def _config_base_dir() -> Path:
    config_path = getattr(config, "config_path", None)
    if config_path is not None:
        return Path(config_path).resolve().parent
    return Path.cwd()


def _parse_configured_paths(raw_paths: str) -> list[str]:
    separators = ["\n", ",", os.pathsep]
    normalized = raw_paths
    for separator in separators:
        normalized = normalized.replace(separator, "\n")
    return [token.strip() for token in normalized.splitlines() if token.strip()]


def _resolve_addon_entry_path(root_dir: Path, raw_path: str, *, source: str, field_name: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    resolved = candidate.resolve()
    resolved_root = root_dir.resolve()
    if not (resolved == resolved_root or resolved.is_relative_to(resolved_root)):
        raise ValueError(
            f"{source}: {field_name} '{raw_path}' must stay within the addon root"
        )
    return resolved


def _coerce_string(value: Any, *, field_name: str, source: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{source}: field '{field_name}' must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{source}: field '{field_name}' must not be empty")
    return normalized


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


def _coerce_mapping_list(value: Any, *, field_name: str, source: str) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{source}: field '{field_name}' must be a list of objects")
    return tuple(dict(item) for item in value)


def _parse_version(value: str, *, field_name: str, source: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in value.split("."):
        match = re.match(r"(\d+)", token.strip())
        if match is None:
            break
        parts.append(int(match.group(1)))
    if not parts:
        raise ValueError(f"{source}: field '{field_name}' must start with a numeric version segment")
    return tuple(parts)


def _is_version_less_than(current: tuple[int, ...], required: tuple[int, ...]) -> bool:
    width = max(len(current), len(required))
    return current + (0,) * (width - len(current)) < required + (0,) * (width - len(required))


def _is_version_greater_than(current: tuple[int, ...], maximum: tuple[int, ...]) -> bool:
    width = max(len(current), len(maximum))
    return current + (0,) * (width - len(current)) > maximum + (0,) * (width - len(maximum))


def _expand_addon_path(path_spec: str, *, base_dir: Path) -> list[Path]:
    path = Path(path_spec)
    if not path.is_absolute():
        path = base_dir / path
    if any(glob_char in str(path) for glob_char in "*?["):
        resolved_paths: list[Path] = []
        for candidate in sorted(path.parent.glob(path.name)):
            if candidate.is_dir() and (candidate / ADDON_MANIFEST_FILENAME).is_file():
                resolved_paths.append((candidate / ADDON_MANIFEST_FILENAME).resolve())
            elif candidate.is_file() and candidate.name == ADDON_MANIFEST_FILENAME:
                resolved_paths.append(candidate.resolve())
        return resolved_paths
    if path.is_dir():
        direct_manifest = path / ADDON_MANIFEST_FILENAME
        if direct_manifest.is_file():
            return [direct_manifest.resolve()]
        return sorted(
            (candidate / ADDON_MANIFEST_FILENAME).resolve()
            for candidate in path.iterdir()
            if candidate.is_dir() and (candidate / ADDON_MANIFEST_FILENAME).is_file()
        )
    return [path.resolve()]


def discover_addon_manifest_paths() -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    default_dir = _config_base_dir() / "addons"
    if default_dir.is_dir():
        direct_manifest = default_dir / ADDON_MANIFEST_FILENAME
        if direct_manifest.is_file():
            resolved = direct_manifest.resolve()
            discovered.append(resolved)
            seen.add(resolved)
        for candidate in sorted(default_dir.iterdir()):
            manifest_path = candidate / ADDON_MANIFEST_FILENAME
            if candidate.is_dir() and manifest_path.is_file():
                resolved = manifest_path.resolve()
                if resolved not in seen:
                    discovered.append(resolved)
                    seen.add(resolved)

    configured = str(config.get("addons", "paths", "") or "")
    for token in _parse_configured_paths(configured):
        for candidate in _expand_addon_path(token, base_dir=_config_base_dir()):
            if candidate not in seen:
                discovered.append(candidate)
                seen.add(candidate)
    return discovered


def _validate_addon_compatibility(
    compatibility: AddonCompatibility,
    *,
    addon_id: str,
    source: str,
) -> None:
    current_version = _parse_version(__version__, field_name="__version__", source="application")
    if compatibility.min_app_version is not None:
        minimum = _parse_version(compatibility.min_app_version, field_name="compatibility.min_app_version", source=source)
        if _is_version_less_than(current_version, minimum):
            raise ValueError(
                f"{source}: addon '{addon_id}' requires AICodeReviewer >= {compatibility.min_app_version}"
            )
    if compatibility.max_app_version is not None:
        maximum = _parse_version(compatibility.max_app_version, field_name="compatibility.max_app_version", source=source)
        if _is_version_greater_than(current_version, maximum):
            raise ValueError(
                f"{source}: addon '{addon_id}' supports AICodeReviewer <= {compatibility.max_app_version}"
            )


def load_addon_manifest(manifest_path: str | Path) -> AddonManifest:
    path = Path(manifest_path).resolve()
    source = f"Addon manifest '{path}'"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{source} was not found") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{source} must contain a JSON object")

    manifest_version = payload.get("manifest_version", ADDON_MANIFEST_SCHEMA_VERSION)
    if manifest_version != ADDON_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"{source} uses unsupported manifest_version '{manifest_version}'")

    addon_id = _coerce_string(payload.get("id"), field_name="id", source=source).lower()
    addon_version = _coerce_string(payload.get("version"), field_name="version", source=source)
    name = str(payload.get("name") or addon_id).strip() or addon_id
    permissions = _coerce_string_list(payload.get("permissions"), field_name="permissions", source=source)
    compatibility_payload = _coerce_mapping(payload.get("compatibility"), field_name="compatibility", source=source)
    compatibility = AddonCompatibility(
        min_app_version=(
            _coerce_string(compatibility_payload["min_app_version"], field_name="compatibility.min_app_version", source=source)
            if "min_app_version" in compatibility_payload
            else None
        ),
        max_app_version=(
            _coerce_string(compatibility_payload["max_app_version"], field_name="compatibility.max_app_version", source=source)
            if "max_app_version" in compatibility_payload
            else None
        ),
    )
    _validate_addon_compatibility(compatibility, addon_id=addon_id, source=source)

    entry_points = _coerce_mapping(payload.get("entry_points"), field_name="entry_points", source=source)
    raw_review_pack_paths = _coerce_string_list(
        entry_points.get("review_packs"),
        field_name="entry_points.review_packs",
        source=source,
    )
    raw_backend_providers = _coerce_mapping_list(
        entry_points.get("backend_providers"),
        field_name="entry_points.backend_providers",
        source=source,
    )
    raw_ui_contributors = _coerce_mapping_list(
        entry_points.get("ui_contributors"),
        field_name="entry_points.ui_contributors",
        source=source,
    )
    raw_editor_hooks = _coerce_mapping_list(
        entry_points.get("editor_hooks"),
        field_name="entry_points.editor_hooks",
        source=source,
    )
    root_dir = path.parent
    review_pack_paths: list[Path] = []
    for raw_pack_path in raw_review_pack_paths:
        pack_path = _resolve_addon_entry_path(
            root_dir,
            raw_pack_path,
            source=source,
            field_name="entry_points.review_packs",
        )
        if not pack_path.is_file():
            raise ValueError(
                f"{source}: review pack entry '{raw_pack_path}' does not resolve to a file"
            )
        review_pack_paths.append(pack_path)

    backend_provider_specs: list[AddonBackendProviderSpec] = []
    for index, provider_payload in enumerate(raw_backend_providers, start=1):
        provider_source = f"{source} backend provider #{index}"
        key = _coerce_string(provider_payload.get("key"), field_name="key", source=provider_source).lower()
        display_name = str(provider_payload.get("display_name") or key).strip() or key
        module_relative_path = _coerce_string(provider_payload.get("module"), field_name="module", source=provider_source)
        factory_name = _coerce_string(provider_payload.get("factory"), field_name="factory", source=provider_source)
        module_path = _resolve_addon_entry_path(
            root_dir,
            module_relative_path,
            source=provider_source,
            field_name="module",
        )
        if not module_path.is_file():
            raise ValueError(
                f"{provider_source}: module '{module_relative_path}' does not resolve to a file"
            )
        backend_provider_specs.append(
            AddonBackendProviderSpec(
                addon_id=addon_id,
                key=key,
                display_name=display_name,
                module_path=module_path,
                factory_name=factory_name,
                aliases=_coerce_string_list(provider_payload.get("aliases"), field_name="aliases", source=provider_source),
                capabilities=frozenset(
                    _coerce_string_list(provider_payload.get("capabilities"), field_name="capabilities", source=provider_source)
                ),
            )
        )

    ui_contributor_specs: list[AddonUIContributorSpec] = []
    for index, contributor_payload in enumerate(raw_ui_contributors, start=1):
        contributor_source = f"{source} ui contributor #{index}"
        surface = _coerce_string(contributor_payload.get("surface"), field_name="surface", source=contributor_source)
        if surface != "settings_section":
            raise ValueError(f"{contributor_source}: unsupported surface '{surface}'")
        description_value = contributor_payload.get("description")
        ui_contributor_specs.append(
            AddonUIContributorSpec(
                addon_id=addon_id,
                surface=surface,
                title=_coerce_string(contributor_payload.get("title"), field_name="title", source=contributor_source),
                description=(
                    _coerce_string(description_value, field_name="description", source=contributor_source)
                    if description_value is not None
                    else None
                ),
                lines=_coerce_string_list(contributor_payload.get("lines"), field_name="lines", source=contributor_source),
            )
        )

    editor_hook_specs: list[AddonEditorHookSpec] = []
    for index, hook_payload in enumerate(raw_editor_hooks, start=1):
        hook_source = f"{source} editor hook #{index}"
        module_relative_path = _coerce_string(hook_payload.get("module"), field_name="module", source=hook_source)
        factory_name = _coerce_string(hook_payload.get("factory"), field_name="factory", source=hook_source)
        module_path = _resolve_addon_entry_path(
            root_dir,
            module_relative_path,
            source=hook_source,
            field_name="module",
        )
        if not module_path.is_file():
            raise ValueError(
                f"{hook_source}: module '{module_relative_path}' does not resolve to a file"
            )
        editor_hook_specs.append(
            AddonEditorHookSpec(
                addon_id=addon_id,
                module_path=module_path,
                factory_name=factory_name,
            )
        )

    normalized_entry_points = dict(entry_points)
    normalized_entry_points["review_packs"] = tuple(str(path_value) for path_value in review_pack_paths)
    normalized_entry_points["backend_providers"] = tuple(spec.key for spec in backend_provider_specs)
    normalized_entry_points["ui_contributors"] = tuple(spec.title for spec in ui_contributor_specs)
    normalized_entry_points["editor_hooks"] = tuple(spec.factory_name for spec in editor_hook_specs)
    return AddonManifest(
        addon_id=addon_id,
        addon_version=addon_version,
        name=name,
        manifest_path=path,
        root_dir=root_dir,
        permissions=permissions,
        compatibility=compatibility,
        entry_points=normalized_entry_points,
        review_pack_paths=tuple(review_pack_paths),
        backend_provider_specs=tuple(backend_provider_specs),
        ui_contributor_specs=tuple(ui_contributor_specs),
        editor_hook_specs=tuple(editor_hook_specs),
    )


def load_addon_manifests(manifest_paths: Sequence[str | Path] | None = None) -> list[AddonManifest]:
    resolved_paths = discover_addon_manifest_paths() if manifest_paths is None else [Path(path).resolve() for path in manifest_paths]
    manifests: list[AddonManifest] = []
    seen_ids: set[str] = set()
    for manifest_path in resolved_paths:
        manifest = load_addon_manifest(manifest_path)
        if manifest.addon_id in seen_ids:
            raise ValueError(f"Duplicate addon id '{manifest.addon_id}' discovered at '{manifest.manifest_path}'")
        manifests.append(manifest)
        seen_ids.add(manifest.addon_id)
    return manifests


def discover_addon_review_pack_paths() -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    for manifest in compose_addon_runtime().manifests:
        for review_pack_path in manifest.review_pack_paths:
            if review_pack_path not in seen:
                discovered.append(review_pack_path)
                seen.add(review_pack_path)
    return discovered


def _load_backend_factory(spec: AddonBackendProviderSpec):
    module_name = f"aicodereviewer_addon_{spec.addon_id}_{spec.key}".replace("-", "_")
    module_spec = importlib.util.spec_from_file_location(module_name, spec.module_path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"Failed to load backend provider module '{spec.module_path}'")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    factory = getattr(module, spec.factory_name, None)
    if factory is None or not callable(factory):
        raise ValueError(
            f"Addon backend provider '{spec.key}' does not export callable '{spec.factory_name}'"
        )

    def _factory(**kwargs: Any) -> AIBackend:
        from aicodereviewer.backends.base import AIBackend

        instance = factory(**kwargs)
        if not isinstance(instance, AIBackend):
            raise TypeError(
                f"Addon backend provider '{spec.key}' factory '{spec.factory_name}' did not return an AIBackend"
            )
        return instance

    return _factory


def _load_editor_hook(spec: AddonEditorHookSpec) -> Any:
    module_name = f"aicodereviewer_addon_{spec.addon_id}_editor_hooks".replace("-", "_")
    module_spec = importlib.util.spec_from_file_location(module_name, spec.module_path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"Failed to load editor hook module '{spec.module_path}'")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    factory = getattr(module, spec.factory_name, None)
    if factory is None or not callable(factory):
        raise ValueError(
            f"Addon editor hook factory '{spec.factory_name}' is not callable in '{spec.module_path}'"
        )
    handler = factory()
    if handler is None:
        raise ValueError(
            f"Addon editor hook factory '{spec.factory_name}' returned no hook handler"
        )
    if not any(
        callable(getattr(handler, method_name, None))
        for method_name in (
            "on_editor_event",
            "on_buffer_event",
            "on_buffer_opened",
            "on_buffer_switched",
            "on_buffer_saved",
            "on_buffer_closed",
            "on_staged_preview_opened",
            "on_change_navigation",
            "on_preview_staged",
            "collect_diagnostics",
            "get_diagnostics",
            "on_patch_applied",
        )
    ):
        raise ValueError(
            f"Addon editor hook factory '{spec.factory_name}' did not return a supported hook handler"
        )
    return handler


def _call_editor_hook(handler: Any, method_name: str, payload: dict[str, Any]) -> Any:
    method = getattr(handler, method_name, None)
    if callable(method):
        return method(dict(payload))
    return None


def emit_addon_editor_event(
    event_name: str,
    payload: dict[str, Any],
    *,
    runtime: AddonRuntime | None = None,
) -> None:
    runtime = runtime or get_active_addon_runtime()
    event_payload = dict(payload)
    event_payload["event"] = event_name
    for hook in runtime.editor_hooks:
        try:
            if _call_editor_hook(hook.handler, f"on_{event_name}", event_payload) is not None:
                continue
            if _call_editor_hook(hook.handler, "on_editor_event", event_payload) is not None:
                continue
            if event_name.startswith("buffer_"):
                _call_editor_hook(hook.handler, "on_buffer_event", event_payload)
        except Exception as exc:
            logger.warning("Addon editor hook '%s' failed during %s: %s", hook.addon_id, event_name, exc)


def _normalize_editor_diagnostics(result: Any, *, addon_id: str) -> tuple[AddonEditorDiagnostic, ...]:
    if result is None:
        return ()
    items = result if isinstance(result, (list, tuple, set)) else (result,)
    normalized: list[AddonEditorDiagnostic] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, AddonEditorDiagnostic):
            normalized.append(item)
            continue
        if isinstance(item, str):
            normalized.append(AddonEditorDiagnostic(addon_id=addon_id, message=item))
            continue
        if isinstance(item, dict):
            message = str(item.get("message") or "").strip()
            if not message:
                continue
            severity = str(item.get("severity") or "info").strip() or "info"
            normalized.append(
                AddonEditorDiagnostic(
                    addon_id=str(item.get("addon_id") or addon_id),
                    message=message,
                    severity=severity,
                )
            )
    return tuple(normalized)


def emit_addon_editor_buffer_event(
    event_name: str,
    payload: dict[str, Any],
    *,
    runtime: AddonRuntime | None = None,
) -> None:
    emit_addon_editor_event(event_name, payload, runtime=runtime)


def collect_addon_editor_diagnostics(
    payload: dict[str, Any],
    *,
    runtime: AddonRuntime | None = None,
) -> tuple[AddonEditorDiagnostic, ...]:
    runtime = runtime or get_active_addon_runtime()
    collected: list[AddonEditorDiagnostic] = []
    for hook in runtime.editor_hooks:
        try:
            result = _call_editor_hook(hook.handler, "collect_diagnostics", payload)
            if result is None:
                result = _call_editor_hook(hook.handler, "get_diagnostics", payload)
            collected.extend(_normalize_editor_diagnostics(result, addon_id=hook.addon_id))
        except Exception as exc:
            logger.warning("Addon editor hook '%s' failed during diagnostic collection: %s", hook.addon_id, exc)
    return tuple(collected)


def emit_addon_patch_applied_event(
    payload: dict[str, Any],
    *,
    runtime: AddonRuntime | None = None,
) -> None:
    runtime = runtime or get_active_addon_runtime()
    for hook in runtime.editor_hooks:
        try:
            _call_editor_hook(hook.handler, "on_patch_applied", payload)
        except Exception as exc:
            logger.warning("Addon editor hook '%s' failed during patch-applied handling: %s", hook.addon_id, exc)


def compose_addon_runtime(manifest_paths: Sequence[str | Path] | None = None) -> AddonRuntime:
    resolved_paths = discover_addon_manifest_paths() if manifest_paths is None else [Path(path).resolve() for path in manifest_paths]
    manifests: list[AddonManifest] = []
    backend_descriptors: list[BackendDescriptor] = []
    editor_hooks: list[AddonEditorHook] = []
    diagnostics: list[AddonDiagnostic] = []
    seen_addon_ids: set[str] = set()

    for manifest_path in resolved_paths:
        try:
            manifest = load_addon_manifest(manifest_path)
        except ValueError as exc:
            diagnostics.append(
                AddonDiagnostic(
                    severity="error",
                    message=str(exc),
                    manifest_path=Path(manifest_path).resolve(),
                )
            )
            continue
        if manifest.addon_id in seen_addon_ids:
            diagnostics.append(
                AddonDiagnostic(
                    severity="error",
                    message=f"Duplicate addon id '{manifest.addon_id}' discovered at '{manifest.manifest_path}'",
                    manifest_path=manifest.manifest_path,
                    addon_id=manifest.addon_id,
                )
            )
            continue
        seen_addon_ids.add(manifest.addon_id)
        manifests.append(manifest)
        for spec in manifest.backend_provider_specs:
            try:
                backend_factory = _load_backend_factory(spec)
                # Validate addon providers during composition so broken factories
                # are reported immediately instead of surfacing only on first use.
                probe_backend = backend_factory()
                probe_backend.close()
                backend_descriptors.append(
                    BackendDescriptor(
                        key=spec.key,
                        display_name=spec.display_name,
                        factory=backend_factory,
                        aliases=spec.aliases,
                        capabilities=spec.capabilities,
                    )
                )
            except Exception as exc:
                diagnostics.append(
                    AddonDiagnostic(
                        severity="error",
                        message=f"Addon manifest '{manifest.manifest_path}': failed to register backend provider '{spec.key}': {exc}",
                        manifest_path=manifest.manifest_path,
                        addon_id=manifest.addon_id,
                    )
                )
        for spec in manifest.editor_hook_specs:
            try:
                editor_hooks.append(
                    AddonEditorHook(
                        addon_id=manifest.addon_id,
                        manifest_path=manifest.manifest_path,
                        handler=_load_editor_hook(spec),
                    )
                )
            except Exception as exc:
                diagnostics.append(
                    AddonDiagnostic(
                        severity="error",
                        message=f"Addon manifest '{manifest.manifest_path}': failed to register editor hooks: {exc}",
                        manifest_path=manifest.manifest_path,
                        addon_id=manifest.addon_id,
                    )
                )

    active_backend_descriptors: list[BackendDescriptor] = []
    registry = compose_backend_registry()
    for descriptor in backend_descriptors:
        try:
            registry.register(descriptor)
            active_backend_descriptors.append(descriptor)
        except ValueError as exc:
            diagnostics.append(
                AddonDiagnostic(
                    severity="error",
                    message=str(exc),
                )
            )
    return AddonRuntime(
        manifests=tuple(manifests),
        backend_descriptors=tuple(active_backend_descriptors),
        editor_hooks=tuple(editor_hooks),
        diagnostics=tuple(diagnostics),
    )


def install_addon_runtime(manifest_paths: Sequence[str | Path] | None = None) -> AddonRuntime:
    global _ACTIVE_ADDON_RUNTIME
    _ACTIVE_ADDON_RUNTIME = compose_addon_runtime(manifest_paths)
    set_backend_registry(compose_backend_registry(_ACTIVE_ADDON_RUNTIME.backend_descriptors))
    return _ACTIVE_ADDON_RUNTIME


def get_active_addon_runtime() -> AddonRuntime:
    return _ACTIVE_ADDON_RUNTIME