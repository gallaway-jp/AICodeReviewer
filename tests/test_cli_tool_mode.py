import json
import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import aicodereviewer.main as cli
from aicodereviewer.backends.health import CheckResult, HealthReport
from aicodereviewer.models import ReviewIssue, ReviewReport


def run_main_with_args(args):
    argv_backup = sys.argv
    sys.argv = ["aicodereviewer"] + args
    try:
        return cli.main()
    finally:
        sys.argv = argv_backup


def test_tool_review_dry_run_outputs_json_and_skips_backend(monkeypatch, capsys):
    create_backend_called = False

    def _fake_create_backend(_name):
        nonlocal create_backend_called
        create_backend_called = True
        raise AssertionError("create_backend should not be called for dry-run")

    class FakeRunner:
        def __init__(self, client, *, scan_fn, backend_name):
            self.client = client
            self.scan_fn = scan_fn
            self.backend_name = backend_name
            self._last_run_state = {}

        def run(self, **kwargs):
            self._last_run_state = {
                "status": "dry_run",
                "files_scanned": 1,
                "target_paths": ["./proj/file.py"],
            }
            return None

    monkeypatch.setattr(cli, "create_backend", _fake_create_backend)
    monkeypatch.setattr(cli, "AppRunner", FakeRunner)

    exit_code = run_main_with_args([
        "review",
        "./proj",
        "--type",
        "security",
        "--dry-run",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert create_backend_called is False
    assert payload["command"] == "review"
    assert payload["status"] == "dry_run"
    assert payload["files_scanned"] == 1
    assert payload["issue_count"] == 0
    assert payload["target_paths"] == ["./proj/file.py"]


def test_tool_review_outputs_report_and_issue_ids(monkeypatch, capsys):
    report_issue = ReviewIssue(
        file_path="src/example.py",
        line_number=12,
        issue_type="security",
        severity="high",
        description="Unsafe subprocess usage",
        code_snippet="subprocess.run(cmd, shell=True)",
        ai_feedback="Avoid shell=True for untrusted input.",
    )

    report = ReviewReport(
        project_path="./proj",
        review_type="security",
        scope="project",
        total_files_scanned=1,
        issues_found=[report_issue],
        generated_at=datetime(2026, 3, 20, 10, 0, 0),
        language="en",
        review_types=["security"],
        quality_score=90,
        programmers=["dev"],
        reviewers=["rev"],
        backend="bedrock",
    )

    class FakeRunner:
        def __init__(self, client, *, scan_fn, backend_name):
            self.client = client
            self.scan_fn = scan_fn
            self.backend_name = backend_name
            self._last_run_state = {}

        def run(self, **kwargs):
            self._last_run_state = {
                "status": "issues_found",
                "files_scanned": 1,
                "target_paths": ["src/example.py"],
            }
            return [report_issue]

        def build_report(self, issues=None):
            return report

        def generate_report(self, issues=None, output_file=None):
            return output_file or "review_report_20260320_100000.json"

    monkeypatch.setattr(cli, "create_backend", lambda _name: MagicMock())
    monkeypatch.setattr(cli, "AppRunner", FakeRunner)

    exit_code = run_main_with_args([
        "review",
        "./proj",
        "--type",
        "security",
        "--programmers",
        "dev",
        "--reviewers",
        "rev",
        "--output",
        "tool_review.json",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["issue_count"] == 1
    assert payload["report_path"] == "tool_review.json"
    assert payload["report"]["project_path"] == "./proj"
    assert payload["issues"][0]["issue_id"] == "issue-0001"


def test_tool_review_cancel_file_returns_cancelled_exit(monkeypatch, capsys, tmp_path):
    cancel_file = tmp_path / "cancel.flag"
    cancel_file.write_text("stop", encoding="utf-8")

    class FakeRunner:
        def __init__(self, client, *, scan_fn, backend_name):
            self.client = client
            self.scan_fn = scan_fn
            self.backend_name = backend_name
            self._last_run_state = {}

        def run(self, **kwargs):
            kwargs["cancel_check"]()
            self._last_run_state = {
                "status": "issues_found",
                "files_scanned": 1,
                "target_paths": ["src/example.py"],
            }
            return None

    monkeypatch.setattr(cli, "create_backend", lambda _name: MagicMock())
    monkeypatch.setattr(cli, "AppRunner", FakeRunner)

    exit_code = run_main_with_args([
        "review",
        "./proj",
        "--type",
        "security",
        "--programmers",
        "dev",
        "--reviewers",
        "rev",
        "--cancel-file",
        str(cancel_file),
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == cli.EXIT_CANCELLED
    assert payload["status"] == "cancelled"
    assert payload["cancel_reason"].startswith("cancel_file:")


def test_tool_health_outputs_structured_report(monkeypatch, capsys):
    report = HealthReport(
        backend="local",
        ready=False,
        checks=[
            CheckResult(
                name="Server Reachable",
                passed=False,
                detail="http://localhost:1234 is unreachable",
                fix_hint="Start the local server.",
            )
        ],
        summary="Local backend is not ready.",
    )

    monkeypatch.setattr(cli, "check_backend", lambda _backend: report)

    exit_code = run_main_with_args([
        "health",
        "--backend",
        "local",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 1
    assert payload["command"] == "health"
    assert payload["backend"] == "local"
    assert payload["ready"] is False
    assert payload["checks"][0]["name"] == "Server Reachable"


def test_tool_health_applies_runtime_overrides(monkeypatch, capsys):
    set_calls = []

    def _record_set(section, key, value):
        set_calls.append((section, key, value))

    monkeypatch.setattr(cli.config, "set_value", _record_set)
    monkeypatch.setattr(
        cli,
        "check_backend",
        lambda _backend: HealthReport(backend="local", ready=True, checks=[], summary="ok"),
    )

    exit_code = run_main_with_args([
        "health",
        "--backend",
        "local",
        "--api-url",
        "http://example.test:8080",
        "--local-model",
        "llama-test",
        "--timeout",
        "12",
    ])

    json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert ("backend", "type", "local") in set_calls
    assert ("local_llm", "api_url", "http://example.test:8080") in set_calls
    assert ("local_llm", "model", "llama-test") in set_calls
    assert ("performance", "api_timeout_seconds", "12.0") in set_calls
    assert ("local_llm", "timeout", "12.0") in set_calls


def test_tool_fix_plan_generates_fixes_from_report_artifact(monkeypatch, capsys, tmp_path):
    report_path = tmp_path / "report.json"
    report = ReviewReport(
        project_path=str(tmp_path),
        review_type="security",
        scope="project",
        total_files_scanned=1,
        issues_found=[
            ReviewIssue(
                file_path=str(tmp_path / "example.py"),
                issue_type="security",
                severity="high",
                description="Unsafe pattern",
                code_snippet="bad()",
                ai_feedback="Use safe().",
                issue_id="issue-0007",
            )
        ],
        generated_at=datetime(2026, 3, 20, 10, 0, 0),
        language="en",
        review_types=["security"],
        backend="bedrock",
    )
    report_path.write_text(json.dumps(report.to_dict()), encoding="utf-8")

    monkeypatch.setattr(cli, "create_backend", lambda _name: MagicMock())
    monkeypatch.setattr(cli, "apply_ai_fix", lambda issue, client, review_type, lang: "fixed()\n")

    exit_code = run_main_with_args([
        "fix-plan",
        "--report-file",
        str(report_path),
        "--issue-id",
        "issue-0007",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["command"] == "fix-plan"
    assert payload["generated_count"] == 1
    assert payload["fixes"][0]["issue_id"] == "issue-0007"
    assert payload["fixes"][0]["status"] == "generated"
    assert payload["fixes"][0]["proposed_content"] == "fixed()\n"


def test_tool_fix_plan_reads_review_envelope_artifact(monkeypatch, capsys, tmp_path):
    report = ReviewReport(
        project_path=str(tmp_path),
        review_type="security",
        scope="project",
        total_files_scanned=1,
        issues_found=[
            ReviewIssue(
                file_path=str(tmp_path / "example.py"),
                issue_type="security",
                severity="high",
                description="Unsafe pattern",
                code_snippet="bad()",
                ai_feedback="Use safe().",
            )
        ],
        generated_at=datetime(2026, 3, 20, 10, 0, 0),
        language="en",
        review_types=["security"],
        backend="bedrock",
    )
    artifact_path = tmp_path / "review-envelope.json"
    artifact_path.write_text(
        json.dumps({"schema_version": 1, "command": "review", "report": report.to_dict()}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "create_backend", lambda _name: MagicMock())
    monkeypatch.setattr(cli, "apply_ai_fix", lambda issue, client, review_type, lang: "fixed()\n")

    exit_code = run_main_with_args([
        "fix-plan",
        "--report-file",
        str(artifact_path),
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["generated_count"] == 1
    assert payload["fixes"][0]["issue_id"] == "issue-0001"


def test_tool_apply_fixes_writes_selected_files_and_backups(capsys, tmp_path):
    file_one = tmp_path / "one.py"
    file_two = tmp_path / "two.py"
    file_one.write_text("old one\n", encoding="utf-8")
    file_two.write_text("old two\n", encoding="utf-8")

    plan_path = tmp_path / "fix-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "command": "fix-plan",
                "fixes": [
                    {
                        "issue_id": "issue-0001",
                        "file_path": str(file_one),
                        "status": "generated",
                        "proposed_content": "new one\n",
                    },
                    {
                        "issue_id": "issue-0002",
                        "file_path": str(file_two),
                        "status": "generated",
                        "proposed_content": "new two\n",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_main_with_args([
        "apply-fixes",
        "--plan-file",
        str(plan_path),
        "--issue-id",
        "issue-0002",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["applied_count"] == 1
    assert file_one.read_text(encoding="utf-8") == "old one\n"
    assert file_two.read_text(encoding="utf-8") == "new two\n"
    assert (tmp_path / "two.py.backup").read_text(encoding="utf-8") == "old two\n"


def test_tool_apply_fixes_reports_no_applicable_fixes(capsys, tmp_path):
    plan_path = tmp_path / "fix-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "command": "fix-plan",
                "fixes": [
                    {
                        "issue_id": "issue-0001",
                        "file_path": str(tmp_path / "one.py"),
                        "status": "failed",
                        "proposed_content": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_main_with_args([
        "apply-fixes",
        "--plan-file",
        str(plan_path),
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 1
    assert payload["status"] == "no_applicable_fixes"


