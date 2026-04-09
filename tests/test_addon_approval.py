from __future__ import annotations

import json
from pathlib import Path

from aicodereviewer.addon_approval import approve_generated_addon, load_generated_addon_candidate
from aicodereviewer.addon_generator import generate_addon_preview
from aicodereviewer.addons import load_addon_manifest
from aicodereviewer.review_definitions import compose_review_pack_state


def test_approve_generated_addon_installs_reviewed_preview(tmp_path: Path) -> None:
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

    preview = generate_addon_preview(project_root, tmp_path / "preview", addon_id="service-preview")

    loaded = load_generated_addon_candidate(preview.output_dir)
    assert loaded.addon_id == "service-preview"

    result = approve_generated_addon(
        preview.output_dir,
        reviewer="Colin",
        install_dir=tmp_path / "installed-addons",
    )

    assert result.approved is True
    assert result.install_path is not None
    assert (result.install_path / "addon.json").is_file()
    assert (result.install_path / "review-pack.json").is_file()
    assert result.approval_decision_path.is_file()

    manifest = load_addon_manifest(result.install_path / "addon.json")
    registry, presets = compose_review_pack_state([result.install_path / "review-pack.json"])
    assert manifest.addon_id == "service-preview"
    assert any(preset.key == preview.preset_key for preset in presets)
    assert preview.review_key in {definition.key for definition in registry.list_all()}


def test_reject_generated_addon_records_decision_without_install(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "package.json").write_text(json.dumps({"dependencies": {"react": "18.0.0"}}), encoding="utf-8")
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "App.tsx").write_text("import React from 'react';\n", encoding="utf-8")

    preview = generate_addon_preview(project_root, tmp_path / "generated", addon_id="reject-preview")
    result = approve_generated_addon(
        preview.output_dir,
        reviewer="Colin",
        decision="reject",
        notes="Too broad for this repository.",
    )

    assert result.approved is False
    assert result.install_path is None
    decision_payload = json.loads(result.approval_decision_path.read_text(encoding="utf-8"))
    assert decision_payload["status"] == "rejected"
