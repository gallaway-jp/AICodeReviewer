from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXE = Path(sys.executable)


def _run_command(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        list(args),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "args": list(args),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    output_dir = REPO_ROOT / "artifacts" / "manual-session8"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "fixture-authoring-sanity-probe.json"

    with tempfile.TemporaryDirectory(prefix="aicr-fixture-authoring-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        fixtures_root = temp_dir / "fixtures"
        fixture_root = fixtures_root / "api-design-get-create-endpoint-sanity"
        project_root = fixture_root / "project"
        reports_dir = temp_dir / "reports"
        report_file = reports_dir / "api-design-get-create-endpoint-sanity.json"

        project_root.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

        (project_root / "api.py").write_text(
            "from fastapi import FastAPI\n\n"
            "app = FastAPI()\n\n"
            "INVITATIONS = []\n\n"
            "@app.get('/api/invitations/create')\n"
            "def create_invitation(email: str):\n"
            "    invitation = {'email': email}\n"
            "    INVITATIONS.append(invitation)\n"
            "    return invitation\n",
            encoding="utf-8",
        )

        fixture_payload = {
            "id": "api-design-get-create-endpoint-sanity",
            "title": "API Design GET Create Endpoint Sanity",
            "description": "A minimal authoring sanity fixture for a GET route that mutates server state.",
            "scope": "project",
            "review_types": ["api_design"],
            "project_dir": "project",
            "minimum_score": 1.0,
            "expected_findings": [
                {
                    "id": "get-create-endpoint",
                    "file_path_contains_any": ["api.py"],
                    "issue_type": "api_design",
                    "minimum_severity": "medium",
                }
            ],
        }
        _write_json(fixture_root / "fixture.json", fixture_payload)

        report_payload = {
            "project_path": str(project_root),
            "review_type": "api_design",
            "scope": "project",
            "total_files_scanned": 1,
            "issues_found": [
                {
                    "file_path": str(project_root / "api.py"),
                    "line_number": 6,
                    "issue_type": "api_design",
                    "severity": "high",
                    "description": "GET route mutates server state by creating invitations instead of using a write-oriented method.",
                    "code_snippet": "@app.get('/api/invitations/create')",
                    "ai_feedback": "Creation endpoints should use POST and return explicit creation semantics.",
                    "context_scope": "local",
                    "related_files": [],
                }
            ],
            "generated_at": "2026-05-04T00:00:00",
            "language": "en",
            "review_types": ["api_design"],
            "backend": "local",
        }
        _write_json(report_file, report_payload)

        list_command = _run_command(
            str(PYTHON_EXE),
            "tools/evaluate_holistic_benchmarks.py",
            "--fixtures-root",
            str(fixtures_root),
            "--list-fixtures",
        )
        single_command = _run_command(
            str(PYTHON_EXE),
            "tools/evaluate_holistic_benchmarks.py",
            "--fixtures-root",
            str(fixtures_root),
            "--fixture",
            "api-design-get-create-endpoint-sanity",
            "--report-file",
            str(report_file),
        )
        directory_command = _run_command(
            str(PYTHON_EXE),
            "tools/evaluate_holistic_benchmarks.py",
            "--fixtures-root",
            str(fixtures_root),
            "--report-dir",
            str(reports_dir),
        )

        single_payload = json.loads(single_command["stdout"])
        directory_payload = json.loads(directory_command["stdout"])

        results = {
            "fixtures_root": str(fixtures_root),
            "fixture_root": str(fixture_root),
            "fixture_manifest": str(fixture_root / "fixture.json"),
            "project_root": str(project_root),
            "report_file": str(report_file),
            "commands": {
                "list_fixtures": list_command,
                "evaluate_single": single_command,
                "evaluate_directory": directory_command,
            },
            "list_fixture_ids": json.loads(list_command["stdout"]).get("fixtures", []),
            "single_evaluation": single_payload,
            "directory_evaluation": directory_payload,
            "sanity_checks": {
                "list_returncode_zero": list_command["returncode"] == 0,
                "single_returncode_zero": single_command["returncode"] == 0,
                "directory_returncode_zero": directory_command["returncode"] == 0,
                "single_fixture_passed": bool(single_payload.get("results", [{}])[0].get("passed")) if single_payload.get("results") else False,
                "directory_fixture_passed": bool(directory_payload.get("results", [{}])[0].get("passed")) if directory_payload.get("results") else False,
            },
        }

        output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()