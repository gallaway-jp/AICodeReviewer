from pathlib import Path

from aicodereviewer.addons import AddonDiagnostic, AddonManifest, AddonRuntime, AddonUIContributorSpec
from aicodereviewer.gui.settings_addons import SettingsAddonDiagnosticsRenderer


def test_settings_addon_renderer_builds_summary_diagnostics_and_contributions() -> None:
    runtime = AddonRuntime(
        manifests=(
            AddonManifest(
                addon_id="demo-addon",
                addon_version="1.2.3",
                name="Demo Addon",
                manifest_path=Path(__file__).resolve(),
                root_dir=Path(__file__).resolve().parent,
                ui_contributor_specs=(
                    AddonUIContributorSpec(
                        addon_id="demo-addon",
                        surface="settings_section",
                        title="Demo Settings Surface",
                        description="Rendered in the Settings tab.",
                        lines=("Backend key: demo-addon",),
                    ),
                ),
            ),
        ),
        diagnostics=(
            AddonDiagnostic(
                severity="error",
                message="Demo addon failed validation",
            ),
        ),
    )

    view_model = SettingsAddonDiagnosticsRenderer(runtime).build_view_model()

    assert "Demo Addon [demo-addon] v1.2.3" in view_model.summary_text
    assert "settings_section: Demo Settings Surface" in view_model.summary_text
    assert "Demo addon failed validation" in view_model.diagnostics_text
    assert len(view_model.contributions) == 1
    contribution = view_model.contributions[0]
    assert contribution.title == "Demo Settings Surface"
    assert contribution.description == "Rendered in the Settings tab."
    assert contribution.lines == ("Backend key: demo-addon",)
    assert "Demo Addon [demo-addon]" in contribution.source_text


def test_settings_addon_renderer_ignores_non_settings_contributions() -> None:
    runtime = AddonRuntime(
        manifests=(
            AddonManifest(
                addon_id="demo-addon",
                addon_version="1.2.3",
                name="Demo Addon",
                manifest_path=Path(__file__).resolve(),
                root_dir=Path(__file__).resolve().parent,
                ui_contributor_specs=(
                    AddonUIContributorSpec(
                        addon_id="demo-addon",
                        surface="settings_section",
                        title="Settings Surface",
                    ),
                    AddonUIContributorSpec(
                        addon_id="demo-addon",
                        surface="menu",
                        title="Unsupported Surface",
                    ),
                ),
            ),
        ),
    )

    view_model = SettingsAddonDiagnosticsRenderer(runtime).build_view_model()

    assert len(view_model.contributions) == 1
    assert view_model.contributions[0].title == "Settings Surface"