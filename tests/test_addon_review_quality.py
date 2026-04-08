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


def test_summarize_review_quality_results_groups_by_stack() -> None:
    summary = review_quality.summarize_review_quality_results(
        [
            {
                "stack": "fastapi",
                "default": {"score": 0.0},
                "generated": {"score": 1.0},
                "score_delta": 1.0,
            },
            {
                "stack": "react",
                "default": {"score": 1.0},
                "generated": {"score": 1.0},
                "score_delta": 0.0,
            },
        ]
    )

    assert summary["stack_summary"]["fastapi"]["generated_better_count"] == 1
    assert summary["stack_summary"]["react"]["ties"] == 1


def test_update_review_quality_history_tracks_runs_by_backend(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    summary = {
        "targets_evaluated": 2,
        "generated_average_score": 0.75,
        "default_average_score": 0.5,
        "average_score_delta": 0.25,
        "generated_better_count": 1,
        "default_better_count": 0,
        "ties": 1,
        "stack_summary": {"fastapi": {"targets_evaluated": 2, "average_score_delta": 0.25}},
    }

    payload = review_quality.update_review_quality_history(
        history_path,
        backend_name="copilot",
        summary=summary,
        recorded_at="2026-04-08T00:00:00+00:00",
    )
    payload = review_quality.update_review_quality_history(
        history_path,
        backend_name="copilot",
        summary=summary,
        recorded_at="2026-04-09T00:00:00+00:00",
        max_runs=2,
    )

    assert len(payload["backends"]["copilot"]["runs"]) == 2
    assert payload["backends"]["copilot"]["runs"][-1]["recorded_at"] == "2026-04-09T00:00:00+00:00"


def test_build_review_quality_trend_compares_against_previous_run(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    first_summary = {
        "targets_evaluated": 2,
        "generated_average_score": 0.5,
        "default_average_score": 0.4,
        "average_score_delta": 0.1,
        "generated_better_count": 1,
        "default_better_count": 0,
        "ties": 1,
        "stack_summary": {"fastapi": {"targets_evaluated": 2, "average_score_delta": 0.1}},
    }
    second_summary = {
        "targets_evaluated": 2,
        "generated_average_score": 0.8,
        "default_average_score": 0.5,
        "average_score_delta": 0.3,
        "generated_better_count": 2,
        "default_better_count": 0,
        "ties": 0,
        "stack_summary": {"fastapi": {"targets_evaluated": 2, "average_score_delta": 0.3}},
    }

    review_quality.update_review_quality_history(
        history_path,
        backend_name="copilot",
        summary=first_summary,
        recorded_at="2026-04-08T00:00:00+00:00",
    )
    payload = review_quality.update_review_quality_history(
        history_path,
        backend_name="copilot",
        summary=second_summary,
        recorded_at="2026-04-09T00:00:00+00:00",
    )

    trend = review_quality.build_review_quality_trend(payload, backend_name="copilot")

    assert trend["run_count"] == 2
    assert trend["change_since_previous"]["generated_average_score"] == 0.3
    assert trend["change_since_previous"]["average_score_delta"] == 0.2
    assert trend["stack_changes"]["fastapi"]["average_score_delta_change"] == 0.2


def test_render_review_quality_markdown_includes_stack_trends() -> None:
    summary = {
        "targets_evaluated": 2,
        "generated_average_score": 0.8,
        "default_average_score": 0.5,
        "average_score_delta": 0.3,
        "generated_better_count": 2,
        "default_better_count": 0,
        "ties": 0,
    }
    trend = {
        "backend": "copilot",
        "run_count": 2,
        "latest": {"recorded_at": "2026-04-09T00:00:00+00:00"},
        "previous": {"recorded_at": "2026-04-08T00:00:00+00:00"},
        "change_since_previous": {
            "generated_average_score": 0.3,
            "default_average_score": 0.1,
            "average_score_delta": 0.2,
        },
        "stack_changes": {
            "fastapi": {
                "latest_average_score_delta": 0.3,
                "previous_average_score_delta": 0.1,
                "average_score_delta_change": 0.2,
                "latest_targets_evaluated": 2,
            }
        },
    }

    markdown = review_quality.render_review_quality_markdown(
        backend_name="copilot",
        summary=summary,
        trend=trend,
    )

    assert "# Generated Addon Review Quality" in markdown
    assert "Change vs previous score delta: `+0.2000`" in markdown
    assert "| fastapi | +0.3000 | +0.1000 | +0.2000 | 2 |" in markdown