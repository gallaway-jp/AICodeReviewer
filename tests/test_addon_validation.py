from __future__ import annotations

import json
from pathlib import Path

from aicodereviewer.addon_validation import (
    ExternalRepositoryTarget,
    evaluate_external_repository_thresholds,
    evaluate_external_repository,
    load_external_repository_catalog,
    render_external_repository_summary_markdown,
    summarize_external_repository_results,
)


def test_load_external_repository_catalog_reads_expected_targets(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repositories": [
                    {
                        "id": "demo-service",
                        "repo_url": "https://example.com/demo-service.git",
                        "checkout_dir": "demo-service",
                        "expected": {
                            "languages": ["Python"],
                            "frameworks": ["fastapi"],
                            "relevant_review_types": ["best_practices", "api_design"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    targets = load_external_repository_catalog(catalog_path)

    assert len(targets) == 1
    assert targets[0].repo_id == "demo-service"
    assert targets[0].frameworks == ("fastapi",)


def test_evaluate_external_repository_scores_generated_bundle_against_default(tmp_path: Path) -> None:
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

    target = ExternalRepositoryTarget(
        repo_id="demo-service",
        repo_url="https://example.com/demo-service.git",
        checkout_dir="demo-service",
        languages=("Python",),
        frameworks=("fastapi", "pytest"),
        test_harnesses=("pytest",),
        manifests=("pyproject.toml",),
        relevant_review_types=(
            "best_practices",
            "maintainability",
            "testing",
            "api_design",
            "data_validation",
            "error_handling",
        ),
    )

    result = evaluate_external_repository(target, project_root, tmp_path / "validation-output")

    assert result["heuristic_scores"]["languages"]["recall"] == 1.0
    assert result["bundle_relevance"]["generated"]["recall"] > result["bundle_relevance"]["default"]["recall"]
    assert result["bundle_relevance"]["f1_delta"] > 0

    summary = summarize_external_repository_results([result])
    assert summary["bundle_relevance_summary"]["repositories_generated_better"] == 1


def test_external_repository_thresholds_and_markdown_summary() -> None:
    summary = {
        "status": "completed",
        "repositories_evaluated": 2,
        "heuristic_summary": {
            "languages": {"average_precision": 1.0, "average_recall": 1.0, "average_f1": 1.0},
            "frameworks": {"average_precision": 0.5, "average_recall": 0.5, "average_f1": 0.5},
            "tools": {"average_precision": 0.4, "average_recall": 0.4, "average_f1": 0.4},
            "test_harnesses": {"average_precision": 1.0, "average_recall": 0.5, "average_f1": 0.6667},
            "manifests": {"average_precision": 1.0, "average_recall": 0.9, "average_f1": 0.9474},
        },
        "bundle_relevance_summary": {
            "generated_average_f1": 0.7,
            "default_average_f1": 0.72,
            "generated_average_recall": 0.8,
            "default_average_recall": 0.8,
            "average_f1_delta": -0.02,
            "average_recall_delta": 0.0,
            "repositories_generated_better": 0,
            "repositories_tied": 1,
            "repositories_default_better": 1,
        },
        "failures": [{"repo_id": "demo", "error": "clone failed"}],
    }

    thresholds = evaluate_external_repository_thresholds(summary)
    rendered = render_external_repository_summary_markdown({**summary, "thresholds": thresholds})

    assert thresholds["passed"] is False
    assert any(item["key"] == "frameworks_f1" for item in thresholds["failures"])
    assert any(item["key"] == "tools_f1" for item in thresholds["warnings"])
    assert "Threshold Failures" in rendered
    assert "Repository Failures" in rendered