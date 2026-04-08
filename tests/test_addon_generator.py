from __future__ import annotations

import json
from pathlib import Path

from aicodereviewer.addon_generator import analyze_repository, generate_addon_preview
from aicodereviewer.addons import load_addon_manifest
from aicodereviewer.review_definitions import compose_review_pack_state


def test_analyze_repository_detects_frameworks_and_recommendations(tmp_path: Path) -> None:
    project_root = tmp_path / "service_repo"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        "[project]\nname = 'service-repo'\nversion = '0.1.0'\n\n[tool.pytest.ini_options]\naddopts = '-q'\n",
        encoding="utf-8",
    )
    (project_root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "api.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
        encoding="utf-8",
    )

    profile = analyze_repository(project_root)

    assert profile.repo_name == "service_repo"
    assert "Python" in profile.languages
    assert "fastapi" in profile.frameworks
    assert "pytest" in profile.test_harnesses
    assert "pyproject.toml" in profile.manifests
    assert "best_practices" in profile.recommended_review_types
    assert "api_design" in profile.recommended_review_types
    assert "testing" in profile.recommended_review_types


def test_generate_addon_preview_writes_valid_manifest_and_review_pack(tmp_path: Path) -> None:
    project_root = tmp_path / "frontend_repo"
    project_root.mkdir()
    (project_root / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"react": "18.0.0"},
                "devDependencies": {"vitest": "1.0.0", "eslint": "9.0.0"},
                "scripts": {"test": "vitest run"},
            }
        ),
        encoding="utf-8",
    )
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "App.tsx").write_text(
        "import React from 'react';\nexport function App() { return <button>Save</button>; }\n",
        encoding="utf-8",
    )

    preview = generate_addon_preview(
        project_root,
        tmp_path / "generated",
        addon_id="frontend-preview-addon",
        addon_name="Frontend Preview Addon",
    )

    manifest = load_addon_manifest(preview.manifest_path)
    registry, presets = compose_review_pack_state([preview.review_pack_path])

    assert manifest.addon_id == "frontend-preview-addon"
    assert preview.capability_profile_path.is_file()
    assert preview.summary_path.is_file()
    assert preview.review_key in {definition.key for definition in registry.list_all()}
    assert any(preset.key == preview.preset_key for preset in presets)
    assert preview.review_pack["review_presets"][0]["review_types"][0] == preview.review_key


def test_analyze_repository_ignores_nested_fixture_and_example_projects(tmp_path: Path) -> None:
    project_root = tmp_path / "primary_repo"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        "[project]\nname = 'primary-repo'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "api.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
        encoding="utf-8",
    )

    example_dir = project_root / "examples" / "react_demo" / "src"
    example_dir.mkdir(parents=True)
    (project_root / "examples" / "react_demo" / "package.json").write_text(
        json.dumps({"dependencies": {"react": "18.0.0"}}),
        encoding="utf-8",
    )
    (example_dir / "App.tsx").write_text(
        "import React from 'react';\nexport function App() { return <div />; }\n",
        encoding="utf-8",
    )

    fixture_dir = project_root / "benchmarks" / "fixtures" / "demo_service" / "project"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "manage.py").write_text("import django\n", encoding="utf-8")

    tests_dir = project_root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_prompts.py").write_text(
        "EXAMPLE = \"from flask import Flask\\nimport react\\n\"\n",
        encoding="utf-8",
    )

    profile = analyze_repository(project_root)

    assert profile.frameworks == ("fastapi",)
    assert profile.manifests == ("pyproject.toml",)
    assert profile.source_file_count == 2
    assert profile.total_files == 3