from __future__ import annotations

import json

from aicodereviewer.recommendations import (
    _RecommendationContext,
    _build_fallback_recommendation,
    _build_recommendation_context,
    _build_recommendation_prompt,
    _parse_recommendation_response,
)
from aicodereviewer.review_definitions import install_review_registry


def test_build_recommendation_context_scores_diff_and_dependency_signals(tmp_path, monkeypatch) -> None:
    install_review_registry([])
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        """
[project]
name = "sample"
dependencies = ["fastapi", "httpx"]

[tool.pytest.ini_options]
addopts = "-q"
""".strip(),
        encoding="utf-8",
    )
    (project_root / "requirements.txt").write_text("fastapi==0.115.0\nhttpx==0.28.0\n", encoding="utf-8")
    (project_root / "tests").mkdir()

    def _fake_scan(path: str | None, scope: str, diff_file: str | None = None, commits: str | None = None):
        if scope == "project":
            return [project_root / "api.py", project_root / "ui.tsx"]
        return [
            {
                "filename": "src/api.py",
                "path": project_root / "api.py",
                "hunks": [object(), object()],
                "commit_messages": "Tighten API validation\n\nMore detail",
            },
            {
                "filename": "src/ui.tsx",
                "path": project_root / "ui.tsx",
                "hunks": [object()],
            },
        ]

    class _FakeProjectContext:
        frameworks = ["fastapi", "pytest", "react"]
        tools = ["ruff"]
        total_files = 120

    monkeypatch.setattr("aicodereviewer.recommendations.scan_project_with_scope", _fake_scan)
    monkeypatch.setattr(
        "aicodereviewer.recommendations.collect_project_context",
        lambda *_args, **_kwargs: _FakeProjectContext(),
    )

    context = _build_recommendation_context(
        path=str(project_root),
        scope="project",
        diff_file=None,
        commits=None,
        selected_files=None,
        diff_filter_file="changes.diff",
        diff_filter_commits=None,
    )

    assert "Dependency manifests: pyproject.toml, requirements.txt" in context.project_signals
    assert any(signal.startswith("Dependencies: pyproject.toml defines dependency metadata") for signal in context.project_signals)
    assert any(signal.startswith("Diff files: src/api.py, src/ui.tsx") for signal in context.project_signals)
    assert any(signal.startswith("Commit messages: Tighten API validation") for signal in context.project_signals)
    assert context.scores["dependency"] >= 3
    assert context.scores["regression"] >= 4
    assert context.scores["testing"] >= 3
    assert context.scores["security"] >= 3
    assert context.scores["ui_ux"] >= 3
    assert context.scores["architecture"] >= 2

    prompt = _build_recommendation_prompt(context)
    assert "DEPENDENCY SUMMARY:" in prompt
    assert "DIFF SUMMARY:" in prompt
    assert "Changed file types: .py x1, .tsx x1" in prompt


def test_parse_recommendation_response_normalizes_aliases_and_fills_missing_reasons() -> None:
    install_review_registry([])
    context = _RecommendationContext(
        scope="project",
        project_signals=["Frameworks: react", "Frontend surface present in the current target"],
        available_review_types=["ui_ux", "localization", "best_practices"],
        available_presets={"product_surface": ["ui_ux", "localization"]},
        scores={"ui_ux": 3, "localization": 2, "best_practices": 1},
        dependency_summary=[],
        diff_summary=[],
    )

    response = json.dumps(
        {
            "recommended_review_types": ["ui_ux", "i18n"],
            "recommended_preset": "product_surface",
            "rationale": [
                {"review_type": "ui_ux", "reason": "Interactive UI paths are visible in the current target."}
            ],
            "project_signals": ["Frameworks: react", "Changed files: src/App.tsx"],
        }
    )

    parsed = _parse_recommendation_response(f"Here is the plan:\n{response}", context)

    assert parsed is not None
    assert parsed.review_types == ["ui_ux", "localization"]
    assert parsed.recommended_preset == "product_surface"
    assert parsed.source == "ai"
    assert parsed.rationale[0].reason == "Interactive UI paths are visible in the current target."
    assert "interface surface" in parsed.rationale[1].reason.lower()
    assert parsed.project_signals == ["Frameworks: react", "Changed files: src/App.tsx"]


def test_build_fallback_recommendation_prefers_strongest_matching_preset() -> None:
    install_review_registry([])
    context = _RecommendationContext(
        scope="project",
        project_signals=["Frameworks: fastapi", "Dependency manifests: pyproject.toml"],
        available_review_types=["security", "error_handling", "data_validation", "dependency", "best_practices"],
        available_presets={
            "runtime_safety": ["security", "error_handling", "data_validation", "dependency"],
            "code_health": ["best_practices"],
        },
        scores={
            "security": 4,
            "error_handling": 3,
            "data_validation": 3,
            "dependency": 3,
            "best_practices": 1,
        },
        dependency_summary=["Dependencies: pyproject.toml defines dependency metadata (1 matching lines)"],
        diff_summary=[],
    )

    result = _build_fallback_recommendation(context)

    assert result.recommended_preset == "runtime_safety"
    assert result.review_types == ["security", "error_handling", "data_validation", "dependency"]
    assert result.source == "heuristic"
    assert len(result.rationale) == 4
