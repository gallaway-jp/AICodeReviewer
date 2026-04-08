from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aicodereviewer.addon_approval import approve_generated_addon, load_generated_addon_candidate


_DEFAULT_BUNDLE_REVIEW_TYPES = ("best_practices", "maintainability", "testing")


@dataclass(frozen=True)
class AddonReviewDiff:
    label: str
    source_label: str
    target_label: str
    diff_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "source_label": self.source_label,
            "target_label": self.target_label,
            "diff_text": self.diff_text,
        }


@dataclass(frozen=True)
class AddonReviewSurface:
    addon_id: str
    addon_name: str
    repo_name: str
    repo_path: str
    preview_dir: Path
    manifest_path: Path
    review_pack_path: Path
    approval_request_path: Path
    review_checklist_path: Path
    installed_addon_path: Path | None
    generated_review_types: tuple[str, ...]
    added_review_types: tuple[str, ...]
    removed_review_types: tuple[str, ...]
    diffs: tuple[AddonReviewDiff, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "addon_id": self.addon_id,
            "addon_name": self.addon_name,
            "repo_name": self.repo_name,
            "repo_path": self.repo_path,
            "preview_dir": str(self.preview_dir),
            "manifest_path": str(self.manifest_path),
            "review_pack_path": str(self.review_pack_path),
            "approval_request_path": str(self.approval_request_path),
            "review_checklist_path": str(self.review_checklist_path),
            "installed_addon_path": str(self.installed_addon_path) if self.installed_addon_path is not None else None,
            "generated_review_types": list(self.generated_review_types),
            "added_review_types": list(self.added_review_types),
            "removed_review_types": list(self.removed_review_types),
            "diffs": [diff.to_dict() for diff in self.diffs],
        }


def build_addon_review_surface(
    preview_dir: str | Path,
    *,
    install_dir: str | Path | None = None,
) -> AddonReviewSurface:
    candidate = load_generated_addon_candidate(preview_dir)
    bundle_comparison = candidate.approval_request.get("bundle_comparison", {})
    generated_review_types = tuple(_coerce_string_list(bundle_comparison.get("generated_review_types")))
    added_review_types = tuple(_coerce_string_list(bundle_comparison.get("added_review_types")))
    removed_review_types = tuple(_coerce_string_list(bundle_comparison.get("removed_review_types")))

    installed_addon_path = _installed_addon_path(candidate.addon_id, install_dir=install_dir)
    diffs: list[AddonReviewDiff] = [
        AddonReviewDiff(
            label="Generated Bundle vs Default Bundle",
            source_label="default-bundle",
            target_label="generated-bundle",
            diff_text=_unified_json_diff(
                _default_bundle_summary(candidate),
                _generated_bundle_summary(candidate),
                fromfile="default-bundle.json",
                tofile="generated-bundle.json",
            ),
        )
    ]

    if installed_addon_path is not None and (installed_addon_path / "addon.json").is_file():
        installed_manifest = json.loads((installed_addon_path / "addon.json").read_text(encoding="utf-8"))
        diffs.append(
            AddonReviewDiff(
                label="Installed Manifest vs Generated Manifest",
                source_label="installed-addon.json",
                target_label="generated-addon.json",
                diff_text=_unified_json_diff(
                    installed_manifest,
                    candidate.manifest,
                    fromfile="installed-addon.json",
                    tofile="generated-addon.json",
                ),
            )
        )
    if installed_addon_path is not None and (installed_addon_path / "review-pack.json").is_file():
        installed_review_pack = json.loads((installed_addon_path / "review-pack.json").read_text(encoding="utf-8"))
        diffs.append(
            AddonReviewDiff(
                label="Installed Review Pack vs Generated Review Pack",
                source_label="installed-review-pack.json",
                target_label="generated-review-pack.json",
                diff_text=_unified_json_diff(
                    installed_review_pack,
                    candidate.review_pack,
                    fromfile="installed-review-pack.json",
                    tofile="generated-review-pack.json",
                ),
            )
        )

    profile = candidate.profile if isinstance(candidate.profile, dict) else {}
    return AddonReviewSurface(
        addon_id=candidate.addon_id,
        addon_name=candidate.addon_name,
        repo_name=str(profile.get("repo_name") or candidate.addon_id),
        repo_path=str(profile.get("project_path") or ""),
        preview_dir=candidate.output_dir,
        manifest_path=candidate.manifest_path,
        review_pack_path=candidate.review_pack_path,
        approval_request_path=candidate.approval_request_path,
        review_checklist_path=candidate.review_checklist_path,
        installed_addon_path=installed_addon_path,
        generated_review_types=generated_review_types,
        added_review_types=added_review_types,
        removed_review_types=removed_review_types,
        diffs=tuple(diffs),
    )


def render_addon_review_surface(surface: AddonReviewSurface) -> str:
    lines = [
        "Generated Addon Review Surface",
        "==============================",
        f"Addon id: {surface.addon_id}",
        f"Addon name: {surface.addon_name}",
        f"Repository: {surface.repo_name}",
        f"Repository path: {surface.repo_path}",
        f"Preview directory: {surface.preview_dir}",
        f"Approval request: {surface.approval_request_path}",
        f"Review checklist: {surface.review_checklist_path}",
        f"Installed addon path: {surface.installed_addon_path if surface.installed_addon_path is not None else 'none'}",
        "",
        f"Generated review types: {', '.join(surface.generated_review_types) or 'none'}",
        f"Added vs default bundle: {', '.join(surface.added_review_types) or 'none'}",
        f"Removed vs default bundle: {', '.join(surface.removed_review_types) or 'none'}",
    ]

    for diff in surface.diffs:
        lines.extend(
            [
                "",
                diff.label,
                "-" * len(diff.label),
                diff.diff_text or "(no diff)",
            ]
        )
    return "\n".join(lines) + "\n"


def review_generated_addon_preview(
    preview_dir: str | Path,
    *,
    reviewer: str,
    decision: str,
    notes: str = "",
    install_dir: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    result = approve_generated_addon(
        preview_dir,
        reviewer=reviewer,
        decision=decision,
        notes=notes,
        install_dir=install_dir,
        force=force,
    )
    return result.to_dict()


def _default_bundle_summary(candidate: Any) -> dict[str, Any]:
    return {
        "review_types": list(candidate.approval_request.get("bundle_comparison", {}).get("default_review_types", _DEFAULT_BUNDLE_REVIEW_TYPES)),
        "prompt_append": "",
        "context_augmentation_rules": [],
    }


def _generated_bundle_summary(candidate: Any) -> dict[str, Any]:
    definitions = candidate.review_pack.get("review_definitions", [])
    generated_definition = definitions[0] if isinstance(definitions, list) and definitions else {}
    return {
        "review_types": list(candidate.approval_request.get("bundle_comparison", {}).get("generated_review_types", [])),
        "prompt_append": generated_definition.get("prompt_append", ""),
        "context_augmentation_rules": list(generated_definition.get("context_augmentation_rules", [])),
    }


def _installed_addon_path(addon_id: str, *, install_dir: str | Path | None = None) -> Path | None:
    if install_dir is not None:
        path = Path(install_dir).resolve() / addon_id
        return path if path.exists() else None
    from aicodereviewer.addon_approval import _default_addons_dir  # local import to avoid circularity at module load

    path = _default_addons_dir() / addon_id
    return path if path.exists() else None


def _unified_json_diff(source: Any, target: Any, *, fromfile: str, tofile: str) -> str:
    source_lines = json.dumps(source, indent=2, ensure_ascii=False, sort_keys=True).splitlines()
    target_lines = json.dumps(target, indent=2, ensure_ascii=False, sort_keys=True).splitlines()
    return "\n".join(
        difflib.unified_diff(source_lines, target_lines, fromfile=fromfile, tofile=tofile, lineterm="")
    )


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]