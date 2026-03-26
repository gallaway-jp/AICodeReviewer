"""Tests for the holistic benchmark runner."""

from __future__ import annotations

import json
import subprocess
import sys
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


def test_runner_forwards_fixture_spec_file(monkeypatch, capsys, tmp_path):
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
                                "file_path": "src/service.py",
                                "issue_type": "specification",
                                "severity": "high",
                                "description": "The implementation returns partial success even though the spec requires atomic failure.",
                                "context_scope": "local",
                                "related_files": [],
                                "systemic_impact": "Callers observe behavior that diverges from the documented contract.",
                                "evidence_basis": "service.py returns status='partial_success' while the requirements document says the batch must fail atomically.",
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
            "specification-batch-atomicity-contract",
            "--skip-health-check",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["score_summary"]["fixtures_passed"] == 1
    assert "--spec-file" in captured_args[0]
    forwarded_path = Path(captured_args[0][captured_args[0].index("--spec-file") + 1])
    assert forwarded_path.name == "requirements.md"


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


def test_invoke_review_tool_uses_subprocess_isolation(monkeypatch):
    calls = {}

    def _fake_run(command, capture_output, text, cwd, env, check):
        calls["command"] = command
        calls["capture_output"] = capture_output
        calls["text"] = text
        calls["cwd"] = cwd
        calls["env"] = env
        calls["check"] = check
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"status": "completed", "success": True}),
            stderr="",
        )

    monkeypatch.setattr(run_holistic_benchmarks.subprocess, "run", _fake_run)
    exit_code, payload = run_holistic_benchmarks._invoke_review_tool(["review", "demo"])

    assert exit_code == 0
    assert payload["status"] == "completed"
    assert calls["command"][0] == sys.executable
    assert calls["command"][1:4] == [
        "-c",
        "from aicodereviewer.main import main; import sys; sys.exit(main())",
        "review",
    ]
    assert calls["command"][4] == "demo"
    assert calls["capture_output"] is True
    assert calls["text"] is True
    assert calls["check"] is False
    assert Path(calls["cwd"]).name == "AICodeReviewer"
    assert str(Path(calls["cwd"]) / "src") in calls["env"]["PYTHONPATH"]