from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tools import evaluate_generated_addon_review_quality as review_quality


def test_load_review_quality_catalog_reads_targets(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "targets": [
                    {
                        "id": "fastapi-sample",
                        "fixture_id": "fixture-1",
                        "label": "FastAPI sample",
                        "stack": "fastapi",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    targets = review_quality.load_review_quality_catalog(catalog_path)

    assert len(targets) == 1
    assert targets[0].target_id == "fastapi-sample"


def test_evaluate_review_quality_target_scores_generated_bundle_against_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture_root = tmp_path / "fixtures"
    fixture_dir = fixture_root / "fastapi-sample"
    project_dir = fixture_dir / "project"
    project_dir.mkdir(parents=True)
    (fixture_dir / "fixture.json").write_text(
        json.dumps(
            {
                "id": "fastapi-sample",
                "title": "FastAPI sample",
                "description": "Representative FastAPI API design issue.",
                "scope": "project",
                "review_types": ["api_design"],
                "project_dir": "project",
                "minimum_score": 1.0,
                "expected_findings": [
                    {
                        "id": "api-design-match",
                        "file_path_contains_any": ["api.py"],
                        "issue_type": "api_design",
                        "minimum_severity": "medium",
                        "evidence_basis_contains": "@app.patch",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (project_dir / "pyproject.toml").write_text(
        "[project]\nname = 'fastapi-sample'\nversion = '0.1.0'\n\n[tool.pytest.ini_options]\naddopts = '-q'\n",
        encoding="utf-8",
    )
    (project_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    src_dir = project_dir / "src"
    src_dir.mkdir()
    (src_dir / "api.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n@app.patch('/items/{item_id}')\ndef patch_item(item_id: int, payload: dict):\n    return payload\n",
        encoding="utf-8",
    )

    fixtures = review_quality.discover_fixtures(fixture_root)
    fixture = fixtures[0]
    target = review_quality.ReviewQualityTarget(
        target_id="fastapi-sample",
        fixture_id="fastapi-sample",
        label="FastAPI sample",
        stack="fastapi",
    )

    def _fake_invoke_review_tool(args: list[str]) -> tuple[int, dict]:
        output_path = Path(args[args.index("--json-out") + 1])
        generated = "--review-pack" in args
        issues = []
        if generated:
            issues = [
                {
                    "issue_id": "issue-1",
                    "file_path": "src/api.py",
                    "issue_type": "api_design",
                    "severity": "medium",
                    "description": "PATCH contract clears omitted fields.",
                    "evidence_basis": "@app.patch('/items/{item_id}') replaces stored data.",
                    "context_scope": "local",
                    "related_issues": [],
                }
            ]
        payload = {
            "status": "completed",
            "success": True,
            "issue_count": len(issues),
            "report": {"issues_found": issues},
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 0, payload

    monkeypatch.setattr(review_quality.benchmark_runner, "_invoke_review_tool", _fake_invoke_review_tool)
    runner_args = SimpleNamespace(
        programmer="benchmark-bot",
        reviewer="benchmark-bot",
        backend=None,
        lang="en",
        fixture_timeout_seconds=None,
        timeout=None,
        model=None,
        api_url=None,
        api_type=None,
        local_model=None,
        local_enable_web_search=None,
        copilot_model=None,
        kiro_cli_command=None,
    )

    result = review_quality.evaluate_review_quality_target(target, fixture, tmp_path / "output", runner_args)

    assert result["default"]["score"] == 0.0
    assert result["generated"]["score"] == 1.0
    assert result["score_delta"] > 0

    summary = review_quality.summarize_review_quality_results([result])
    assert summary["generated_better_count"] == 1