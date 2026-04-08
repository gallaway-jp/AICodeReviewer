from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from aicodereviewer.addons import load_addon_manifest
from aicodereviewer.config import config
from aicodereviewer.review_definitions import compose_review_pack_state


APPROVAL_REQUEST_FILENAME = "approval-request.json"
APPROVAL_DECISION_FILENAME = "approval-decision.json"
REVIEW_CHECKLIST_FILENAME = "review-checklist.md"


@dataclass(frozen=True)
class GeneratedAddonCandidate:
    output_dir: Path
    addon_root: Path
    addon_id: str
    addon_name: str
    manifest_path: Path
    review_pack_path: Path
    capability_profile_path: Path
    summary_path: Path
    approval_request_path: Path
    review_checklist_path: Path
    manifest: dict[str, Any]
    review_pack: dict[str, Any]
    approval_request: dict[str, Any]
    profile: dict[str, Any]


@dataclass(frozen=True)
class AddonApprovalResult:
    candidate: GeneratedAddonCandidate
    decision: str
    reviewer: str
    notes: str
    decided_at: str
    approval_decision_path: Path
    install_path: Path | None
    activation_hint: str
    approved: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reviewer": self.reviewer,
            "notes": self.notes,
            "decided_at": self.decided_at,
            "approval_decision_path": str(self.approval_decision_path),
            "install_path": str(self.install_path) if self.install_path is not None else None,
            "activation_hint": self.activation_hint,
            "approved": self.approved,
            "addon_id": self.candidate.addon_id,
            "addon_name": self.candidate.addon_name,
            "manifest_path": str(self.candidate.manifest_path),
            "review_pack_path": str(self.candidate.review_pack_path),
            "approval_request_path": str(self.candidate.approval_request_path),
            "review_checklist_path": str(self.candidate.review_checklist_path),
        }


def load_generated_addon_candidate(preview_dir: str | Path) -> GeneratedAddonCandidate:
    output_dir = Path(preview_dir).resolve()
    if not output_dir.is_dir():
        raise ValueError(f"Generated addon preview directory was not found: {output_dir}")

    approval_request_path = output_dir / APPROVAL_REQUEST_FILENAME
    if not approval_request_path.is_file():
        raise ValueError(f"Missing approval request file: {approval_request_path}")
    approval_request = _load_json(approval_request_path)

    addon_root = Path(str(approval_request.get("addon_root") or "")).resolve()
    if not addon_root.is_dir():
        addon_root = _infer_addon_root(output_dir)

    manifest_path = Path(str(approval_request.get("manifest_path") or addon_root / "addon.json")).resolve()
    review_pack_path = Path(str(approval_request.get("review_pack_path") or addon_root / "review-pack.json")).resolve()
    capability_profile_path = Path(str(approval_request.get("capability_profile_path") or output_dir / "capability-profile.json")).resolve()
    summary_path = Path(str(approval_request.get("summary_path") or output_dir / "summary.txt")).resolve()
    review_checklist_path = output_dir / REVIEW_CHECKLIST_FILENAME

    if not manifest_path.is_file():
        raise ValueError(f"Missing generated addon manifest: {manifest_path}")
    if not review_pack_path.is_file():
        raise ValueError(f"Missing generated review pack: {review_pack_path}")
    if not capability_profile_path.is_file():
        raise ValueError(f"Missing generated capability profile: {capability_profile_path}")
    if not summary_path.is_file():
        raise ValueError(f"Missing generated summary file: {summary_path}")
    if not review_checklist_path.is_file():
        raise ValueError(f"Missing review checklist file: {review_checklist_path}")

    manifest = _load_json(manifest_path)
    review_pack = _load_json(review_pack_path)
    profile = _load_json(capability_profile_path)

    loaded_manifest = load_addon_manifest(manifest_path)
    compose_review_pack_state([review_pack_path])

    return GeneratedAddonCandidate(
        output_dir=output_dir,
        addon_root=addon_root,
        addon_id=loaded_manifest.addon_id,
        addon_name=loaded_manifest.name,
        manifest_path=manifest_path,
        review_pack_path=review_pack_path,
        capability_profile_path=capability_profile_path,
        summary_path=summary_path,
        approval_request_path=approval_request_path,
        review_checklist_path=review_checklist_path,
        manifest=manifest,
        review_pack=review_pack,
        approval_request=approval_request,
        profile=profile,
    )


def approve_generated_addon(
    preview_dir: str | Path,
    *,
    reviewer: str,
    decision: str = "approve",
    notes: str = "",
    install_dir: str | Path | None = None,
    force: bool = False,
) -> AddonApprovalResult:
    candidate = load_generated_addon_candidate(preview_dir)
    normalized_reviewer = reviewer.strip()
    if not normalized_reviewer:
        raise ValueError("Reviewer name must not be empty")

    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"approve", "reject"}:
        raise ValueError("Decision must be either 'approve' or 'reject'")

    approved = normalized_decision == "approve"
    decided_at = datetime.now(timezone.utc).isoformat()
    install_path: Path | None = None
    activation_hint = "Preview remains inactive."

    if approved:
        target_install_dir = Path(install_dir).resolve() if install_dir else _default_addons_dir()
        target_install_dir.mkdir(parents=True, exist_ok=True)
        install_path = target_install_dir / candidate.addon_id
        if install_path.exists():
            if not force:
                raise ValueError(f"Install path already exists: {install_path}")
            shutil.rmtree(install_path)
        shutil.copytree(candidate.addon_root, install_path)
        activation_hint = (
            "Installed into the default addons directory and will be discovered automatically."
            if target_install_dir == _default_addons_dir()
            else "Installed outside the default addons directory; add the path to [addons] paths or move it under the default addons directory to activate it."
        )
    else:
        activation_hint = "Preview was rejected and was not installed."

    decision_payload = {
        "schema_version": 1,
        "status": "approved" if approved else "rejected",
        "decision": normalized_decision,
        "reviewer": normalized_reviewer,
        "notes": notes,
        "decided_at": decided_at,
        "addon_id": candidate.addon_id,
        "addon_name": candidate.addon_name,
        "output_dir": str(candidate.output_dir),
        "manifest_path": str(candidate.manifest_path),
        "review_pack_path": str(candidate.review_pack_path),
        "approval_request_path": str(candidate.approval_request_path),
        "review_checklist_path": str(candidate.review_checklist_path),
        "reviewed_files": {
            "manifest": _sha256_path(candidate.manifest_path),
            "review_pack": _sha256_path(candidate.review_pack_path),
            "capability_profile": _sha256_path(candidate.capability_profile_path),
            "summary": _sha256_path(candidate.summary_path),
        },
        "install_path": str(install_path) if install_path is not None else None,
        "activation_hint": activation_hint,
    }
    approval_decision_path = candidate.output_dir / APPROVAL_DECISION_FILENAME
    approval_decision_path.write_text(json.dumps(decision_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if install_path is not None:
        (install_path / APPROVAL_DECISION_FILENAME).write_text(
            json.dumps(decision_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return AddonApprovalResult(
        candidate=candidate,
        decision=normalized_decision,
        reviewer=normalized_reviewer,
        notes=notes,
        decided_at=decided_at,
        approval_decision_path=approval_decision_path,
        install_path=install_path,
        activation_hint=activation_hint,
        approved=approved,
    )


def _infer_addon_root(output_dir: Path) -> Path:
    candidates = [candidate for candidate in output_dir.iterdir() if candidate.is_dir() and (candidate / "addon.json").is_file()]
    if len(candidates) != 1:
        raise ValueError(f"Could not uniquely resolve generated addon root under: {output_dir}")
    return candidates[0].resolve()


def _default_addons_dir() -> Path:
    config_path = getattr(config, "config_path", None)
    base_dir = Path(config_path).resolve().parent if config_path is not None else Path.cwd()
    return base_dir / "addons"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()