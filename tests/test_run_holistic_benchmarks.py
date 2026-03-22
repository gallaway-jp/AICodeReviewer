"""Tests for the holistic benchmark runner."""

from __future__ import annotations

import json
from pathlib import Path

from tools import run_holistic_benchmarks


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "holistic_review" / "fixtures"


def test_runner_returns_backend_not_ready(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        run_holistic_benchmarks,
        "_health_payload",
        lambda backend_name: {
            "backend": backend_name,
            "ready": False,
            "summary": "not ready",
            "checks": [],
        },
    )

    exit_code = run_holistic_benchmarks.main(
        [
            "--fixtures-root",
            str(FIXTURES_ROOT),
            "--output-dir",
            str(tmp_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "backend_not_ready"
    assert payload["generated_reports"] == []


def test_runner_executes_selected_fixture_and_scores(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        run_holistic_benchmarks,
        "_health_payload",
        lambda backend_name: {
            "backend": backend_name,
            "ready": True,
            "summary": "ready",
            "checks": [],
        },
    )

    captured_args = []

    def _fake_invoke_review_tool(args):
        captured_args.append(args)
        output_path = Path(args[args.index("--json-out") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "status": "completed",
                    "success": True,
                    "issue_count": 1,
                    "report": {
                        "issues_found": [
                            {
                                "file_path": "src/admin.py",
                                "issue_type": "security",
                                "severity": "high",
                                "description": "The admin endpoint bypasses the admin guard by skipping require_admin and accepts any authenticated user.",
                                "context_scope": "cross_file",
                                "related_files": ["src/auth.py"],
                                "systemic_impact": "Privilege checks are inconsistent across admin routes.",
                                "evidence_basis": "admin.py stopped calling require_admin before returning sensitive data.",
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        return 0, {"status": "completed", "success": True, "issue_count": 1}

    monkeypatch.setattr(run_holistic_benchmarks, "_invoke_review_tool", _fake_invoke_review_tool)

    exit_code = run_holistic_benchmarks.main(
        [
            "--fixtures-root",
            str(FIXTURES_ROOT),
            "--output-dir",
            str(tmp_path),
            "--fixture",
            "auth-guard-regression",
            "--local-disable-web-search",
            "--skip-health-check",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["score_summary"]["fixtures_passed"] == 1
    assert payload["generated_reports"][0]["fixture_id"] == "auth-guard-regression"
    assert "--lang" in captured_args[0]
    assert captured_args[0][captured_args[0].index("--lang") + 1] == "en"
    assert "--local-disable-web-search" in captured_args[0]


def test_runner_repeats_runs_and_emits_stability_summary(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        run_holistic_benchmarks,
        "_health_payload",
        lambda backend_name: {
            "backend": backend_name,
            "ready": True,
            "summary": "ready",
            "checks": [],
        },
    )

    captured_args = []

    def _fake_invoke_review_tool(args):
        captured_args.append(args)
        output_path = Path(args[args.index("--json-out") + 1])
        run_dir_name = output_path.parent.name
        run_index = int(run_dir_name.split("-")[-1])
        if run_index == 1:
            report_payload = {
                "status": "completed",
                "success": True,
                "issue_count": 1,
                "report": {
                    "issues_found": [
                        {
                            "file_path": "src/admin.py",
                            "issue_type": "security",
                            "severity": "high",
                            "description": "The admin endpoint bypasses the admin guard by skipping require_admin and accepts any authenticated user.",
                            "context_scope": "cross_file",
                            "related_files": ["src/auth.py"],
                            "systemic_impact": "Privilege checks are inconsistent across admin routes.",
                            "evidence_basis": "admin.py stopped calling require_admin before returning sensitive data.",
                        }
                    ]
                },
            }
        else:
            report_payload = {
                "status": "completed",
                "success": True,
                "issue_count": 1,
                "report": {
                    "issues_found": [
                        {
                            "file_path": "src/admin.py",
                            "issue_type": "security",
                            "severity": "high",
                            "description": "The admin endpoint no longer enforces admin authorization.",
                            "context_scope": "cross_file",
                            "related_files": ["src/auth.py"],
                            "systemic_impact": "Privilege checks are inconsistent across admin routes.",
                            "evidence_basis": "The route returns sensitive data without require_admin.",
                        }
                    ]
                },
            }
        output_path.write_text(json.dumps(report_payload), encoding="utf-8")
        return 0, {
            "status": "completed",
            "success": True,
            "issue_count": 1,
        }

    monkeypatch.setattr(run_holistic_benchmarks, "_invoke_review_tool", _fake_invoke_review_tool)

    exit_code = run_holistic_benchmarks.main(
        [
            "--fixtures-root",
            str(FIXTURES_ROOT),
            "--output-dir",
            str(tmp_path),
            "--fixture",
            "auth-guard-regression",
            "--runs",
            "2",
            "--skip-health-check",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["runs"] == 2
    assert len(payload["run_summaries"]) == 2
    assert payload["stability_summary"]["fixtures_evaluated"] == 1
    assert payload["stability_summary"]["fixtures"][0]["pass_rate"] == 0.5
    assert payload["generated_reports"][0]["run_index"] == 1
    assert payload["generated_reports"][1]["run_index"] == 2
    assert Path(payload["run_summaries"][0]["output_dir"]).name == "run-001"
    assert Path(payload["run_summaries"][1]["output_dir"]).name == "run-002"