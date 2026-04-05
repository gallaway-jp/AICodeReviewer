from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.addons import AddonRuntime
from aicodereviewer.i18n import t

if TYPE_CHECKING:
    from aicodereviewer.addons import AddonManifest, AddonUIContributorSpec


@dataclass(frozen=True)
class SettingsAddonContributionViewModel:
    title: str
    source_text: str
    description: str | None
    lines: tuple[str, ...]


@dataclass(frozen=True)
class SettingsAddonDiagnosticsViewModel:
    summary_text: str
    diagnostics_text: str
    contributions: tuple[SettingsAddonContributionViewModel, ...]


class SettingsAddonDiagnosticsRenderer:
    def __init__(self, runtime: AddonRuntime) -> None:
        self._runtime = runtime

    def build_view_model(self) -> SettingsAddonDiagnosticsViewModel:
        contributions = tuple(self._build_contribution_view_models())
        return SettingsAddonDiagnosticsViewModel(
            summary_text=self._build_summary_text(),
            diagnostics_text=self._build_diagnostics_text(),
            contributions=contributions,
        )

    def populate_contributions(
        self,
        parent: Any,
        *,
        wraplength: int = 520,
    ) -> None:
        for child in parent.winfo_children():
            child.destroy()

        view_model = self.build_view_model()
        if not view_model.contributions:
            ctk.CTkLabel(
                parent,
                text=t("gui.settings.addons_contributions_none"),
                anchor="w",
                justify="left",
                text_color="gray50",
            ).grid(row=0, column=0, sticky="ew")
            return

        for index, contribution in enumerate(view_model.contributions):
            card = ctk.CTkFrame(parent)
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                card,
                text=contribution.title,
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))
            ctk.CTkLabel(
                card,
                text=contribution.source_text,
                anchor="w",
                text_color="gray50",
                font=ctk.CTkFont(size=11),
            ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))

            body_row = 2
            if contribution.description:
                ctk.CTkLabel(
                    card,
                    text=contribution.description,
                    anchor="w",
                    justify="left",
                    wraplength=wraplength,
                ).grid(row=body_row, column=0, sticky="ew", padx=10, pady=(0, 4))
                body_row += 1
            for line in contribution.lines:
                ctk.CTkLabel(
                    card,
                    text=f"- {line}",
                    anchor="w",
                    justify="left",
                    wraplength=wraplength,
                ).grid(row=body_row, column=0, sticky="ew", padx=10, pady=(0, 2))
                body_row += 1

    def _build_summary_text(self) -> str:
        if not self._runtime.manifests:
            return t("gui.settings.addons_none")

        lines: list[str] = []
        for manifest in self._runtime.manifests:
            lines.append(self._manifest_line(manifest))
            if manifest.review_pack_paths:
                lines.append(t("gui.settings.addons_review_pack_count", count=len(manifest.review_pack_paths)))
            if manifest.backend_provider_specs:
                lines.append(t("gui.settings.addons_backend_count", count=len(manifest.backend_provider_specs)))
                for provider in manifest.backend_provider_specs:
                    lines.append(
                        t(
                            "gui.settings.addons_backend_line",
                            backend_key=provider.key,
                            display_name=provider.display_name,
                        )
                    )
            if manifest.ui_contributor_specs:
                lines.append(t("gui.settings.addons_ui_count", count=len(manifest.ui_contributor_specs)))
                for contributor in manifest.ui_contributor_specs:
                    lines.append(
                        t(
                            "gui.settings.addons_ui_line",
                            surface=contributor.surface,
                            title=contributor.title,
                        )
                    )
            lines.append("")
        return "\n".join(lines).strip()

    def _build_diagnostics_text(self) -> str:
        if not self._runtime.diagnostics:
            return t("gui.settings.addons_diagnostics_none")
        return "\n".join(f"- {diagnostic.message}" for diagnostic in self._runtime.diagnostics)

    def _build_contribution_view_models(self) -> list[SettingsAddonContributionViewModel]:
        models: list[SettingsAddonContributionViewModel] = []
        for manifest in self._runtime.manifests:
            for contributor in manifest.ui_contributor_specs:
                if contributor.surface != "settings_section":
                    continue
                models.append(self._contribution_view_model(manifest, contributor))
        return models

    @staticmethod
    def _manifest_line(manifest: AddonManifest) -> str:
        return t(
            "gui.settings.addons_manifest_line",
            addon_id=manifest.addon_id,
            version=manifest.addon_version,
            name=manifest.name,
        )

    @staticmethod
    def _contribution_view_model(
        manifest: AddonManifest,
        contributor: AddonUIContributorSpec,
    ) -> SettingsAddonContributionViewModel:
        return SettingsAddonContributionViewModel(
            title=contributor.title,
            source_text=t(
                "gui.settings.addons_contributor_source",
                name=manifest.name,
                addon_id=manifest.addon_id,
            ),
            description=contributor.description,
            lines=contributor.lines,
        )