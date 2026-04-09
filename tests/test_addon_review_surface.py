from __future__ import annotations

from pathlib import Path

import aicodereviewer.main as cli
from aicodereviewer.addon_generator import generate_addon_preview
from aicodereviewer.addon_review_surface import build_addon_review_surface, render_addon_review_surface


def test_build_addon_review_surface_includes_bundle_diff(tmp_path: Path) -> None:
    project_root = tmp_path / "service_repo"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        "[project]\nname = 'service-repo'\nversion = '0.1.0'\n\n[tool.pytest.ini_options]\naddopts = '-q'\n",
        encoding="utf-8",
    )
    (project_root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "api.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

    preview = generate_addon_preview(project_root, tmp_path / "preview", addon_id="surface-preview")

    surface = build_addon_review_surface(preview.output_dir)
    rendered = render_addon_review_surface(surface)

    assert surface.added_review_types
    assert "Generated Bundle vs Default Bundle" in rendered
    assert "api_design" in rendered


def test_cli_review_addon_preview_can_approve_without_prompt(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "service_repo"
    project_root.mkdir()
    (project_root / "package.json").write_text(
        '{"dependencies": {"react": "18.0.0"}, "devDependencies": {"vitest": "1.0.0"}}',
        encoding="utf-8",
    )
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "App.tsx").write_text("export function App() { return <button>Save</button>; }\n", encoding="utf-8")

    preview = generate_addon_preview(project_root, tmp_path / "generated", addon_id="interactive-preview")
    install_dir = tmp_path / "installed-addons"

    exit_code = cli.main([
        "review-addon-preview",
        str(preview.output_dir),
        "--decision",
        "approve",
        "--reviewer",
        "Colin",
        "--install-dir",
        str(install_dir),
    ])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Decision recorded: approve by Colin" in output
    assert (install_dir / "interactive-preview" / "addon.json").is_file()
