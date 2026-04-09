from __future__ import annotations

import json
from dataclasses import dataclass

from aicodereviewer.addon_approval import APPROVAL_DECISION_FILENAME
from aicodereviewer.addon_review_surface import AddonReviewSurface


@dataclass(frozen=True)
class AddonReviewDiffViewModel:
    label: str
    diff_text: str


@dataclass(frozen=True)
class AddonReviewViewModel:
    status_text: str
    metadata_text: str
    checklist_text: str
    diffs: tuple[AddonReviewDiffViewModel, ...]


class AddonReviewRenderer:
    def build_view_model(self, surface: AddonReviewSurface) -> AddonReviewViewModel:
        return AddonReviewViewModel(
            status_text=self._build_status_text(surface),
            metadata_text=self._build_metadata_text(surface),
            checklist_text=surface.review_checklist_path.read_text(encoding="utf-8").strip(),
            diffs=tuple(
                AddonReviewDiffViewModel(
                    label=diff.label,
                    diff_text=diff.diff_text or "(no diff)",
                )
                for diff in surface.diffs
            ),
        )

    @staticmethod
    def _build_status_text(surface: AddonReviewSurface) -> str:
        decision_path = surface.preview_dir / APPROVAL_DECISION_FILENAME
        lines = []
        if decision_path.is_file():
            payload = json.loads(decision_path.read_text(encoding="utf-8"))
            lines.append(
                "Decision recorded: "
                f"{payload.get('decision', 'unknown')} by {payload.get('reviewer', 'unknown')}"
            )
            decided_at = str(payload.get("decided_at") or "").strip()
            if decided_at:
                lines.append(f"Decided at: {decided_at}")
            install_path = str(payload.get("install_path") or "").strip()
            if install_path:
                lines.append(f"Installed to: {install_path}")
        else:
            lines.append("No decision recorded yet.")

        if surface.installed_addon_path is not None:
            lines.append(f"Existing installed addon detected: {surface.installed_addon_path}")
        else:
            lines.append("No installed addon with this id was found.")
        return "\n".join(lines)

    @staticmethod
    def _build_metadata_text(surface: AddonReviewSurface) -> str:
        lines = [
            f"Addon id: {surface.addon_id}",
            f"Addon name: {surface.addon_name}",
            f"Repository: {surface.repo_name}",
            f"Repository path: {surface.repo_path}",
            f"Preview directory: {surface.preview_dir}",
            f"Approval request: {surface.approval_request_path}",
            f"Review checklist: {surface.review_checklist_path}",
            f"Generated review types: {', '.join(surface.generated_review_types) or 'none'}",
            f"Added vs default bundle: {', '.join(surface.added_review_types) or 'none'}",
            f"Removed vs default bundle: {', '.join(surface.removed_review_types) or 'none'}",
        ]
        return "\n".join(lines)