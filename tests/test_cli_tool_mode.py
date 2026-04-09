import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import aicodereviewer.main as cli
from aicodereviewer.backends.health import CheckResult, HealthReport
from aicodereviewer.fixer import FixGenerationResult
from aicodereviewer.models import ReviewIssue, ReviewReport
from aicodereviewer.recommendations import ReviewRecommendationResult, ReviewTypeRecommendation


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
            self.execution_summary = {}

        def run(self, **kwargs):
            self.execution_summary = {
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


def test_tool_review_prefers_last_execution_over_summary_state(monkeypatch, capsys):
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
            self.last_execution = None

        def run(self, **kwargs):
            self.last_execution = SimpleNamespace(
                status="dry_run",
                files_scanned=2,
                target_paths=["./proj/a.py", "./proj/b.py"],
            )
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
    assert payload["status"] == "dry_run"
    assert payload["files_scanned"] == 2
    assert payload["target_paths"] == ["./proj/a.py", "./proj/b.py"]


def test_tool_review_includes_tool_access_audit_from_last_execution(monkeypatch, capsys):
    class _Audit:
        def to_dict(self):
            return {
                "backend_name": "copilot",
                "model_name": "gpt-5.4",
                "enabled": True,
                "used_tool_access": True,
                "file_read_count": 3,
                "denied_request_count": 0,
                "fallback_reason": None,
                "entries": [],
            }

    class FakeRunner:
        def __init__(self, client, *, scan_fn, backend_name):
            self.client = client
            self.scan_fn = scan_fn
            self.backend_name = backend_name
            self.last_execution = None

        def run(self, **kwargs):
            self.last_execution = SimpleNamespace(
                status="dry_run",
                files_scanned=2,
                target_paths=["./proj/a.py", "./proj/b.py"],
                tool_access_audit=_Audit(),
            )
            return None

    monkeypatch.setattr(cli, "create_backend", lambda _name: (_ for _ in ()).throw(AssertionError("create_backend should not be called for dry-run")))
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
    assert payload["tool_access_audit"]["backend_name"] == "copilot"
    assert payload["tool_access_audit"]["file_read_count"] == 3


def test_tool_review_recommend_types_outputs_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "create_backend", lambda _name: object())
    monkeypatch.setattr(
        cli,
        "recommend_review_types",
        lambda **kwargs: ReviewRecommendationResult(
            review_types=["ui_ux", "accessibility", "localization"],
            rationale=[
                ReviewTypeRecommendation("ui_ux", "Frontend files are in scope."),
                ReviewTypeRecommendation("accessibility", "Interactive UI surface should be checked."),
                ReviewTypeRecommendation("localization", "User-facing strings are likely present."),
            ],
            project_signals=["Frameworks: react", "Changed files: src/App.tsx"],
            recommended_preset="product_surface",
            source="ai",
        ),
    )

    exit_code = run_main_with_args([
        "review",
        "./proj",
        "--recommend-types",
        "--backend",
        "bedrock",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["status"] == "recommended"
    assert payload["recommended_preset"] == "product_surface"
    assert payload["recommended_review_types"] == ["ui_ux", "accessibility", "localization"]
    assert payload["rationale"][0]["review_type"] == "ui_ux"


def test_tool_review_recommend_types_passes_richer_context_to_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys,
):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"react": "18.3.0", "next": "15.0.0"},
                "devDependencies": {"typescript": "5.6.0", "eslint": "9.0.0"},
            }
        ),
        encoding="utf-8",
    )

    captured_contexts: list[str] = []

    class _FakeBackend:
        def get_review_recommendations(self, recommendation_context: str, *, lang: str = "en") -> str:
            captured_contexts.append(recommendation_context)
            return json.dumps(
                {
                    "recommended_review_types": ["ui_ux", "accessibility", "localization"],
                    "recommended_preset": "product_surface",
                    "rationale": [
                        {"review_type": "ui_ux", "reason": "Frontend files are in scope."},
                        {"review_type": "accessibility", "reason": "Interactive UI surface should be checked."},
                        {"review_type": "localization", "reason": "User-facing strings are likely present."},
                    ],
                    "project_signals": ["Frameworks: react", "Changed files: src/App.tsx"],
                }
            )

        def close(self) -> None:
            return None

    def _fake_scan(path: str | None, scope: str, diff_file: str | None = None, commits: str | None = None):
        if scope == "diff":
            return [
                {
                    "filename": "src/App.tsx",
                    "path": project_root / "src" / "App.tsx",
                    "hunks": [object(), object(), object()],
                    "commit_messages": "Refine onboarding panel",
                }
            ]
        return [project_root / "src" / "App.tsx"]

    class _FakeProjectContext:
        frameworks = ["react"]
        tools = ["eslint"]
        total_files = 18

    monkeypatch.setattr(cli, "create_backend", lambda _name: _FakeBackend())
    monkeypatch.setattr("aicodereviewer.recommendations.scan_project_with_scope", _fake_scan)
    monkeypatch.setattr(
        "aicodereviewer.recommendations.collect_project_context",
        lambda *_args, **_kwargs: _FakeProjectContext(),
    )

    exit_code = run_main_with_args([
        "review",
        str(project_root),
        "--scope",
        "diff",
        "--diff-file",
        "changes.diff",
        "--recommend-types",
        "--backend",
        "bedrock",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["status"] == "recommended"
    assert captured_contexts
    recommendation_context = captured_contexts[0]
    assert "DEPENDENCY SUMMARY:" in recommendation_context
    assert "Dependencies: package.json runtime deps include next, react" in recommendation_context
    assert "Tooling: package.json dev deps include eslint, typescript" in recommendation_context
    assert "DIFF SUMMARY:" in recommendation_context
    assert "Diff files: src/App.tsx" in recommendation_context
    assert "Hunks: 3 across 1 file(s)" in recommendation_context
    assert "Changed file types: .tsx x1" in recommendation_context
    assert "Commit messages: Refine onboarding panel" in recommendation_context


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
            self.execution_summary = {}

        def run(self, **kwargs):
            self.execution_summary = {
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


def test_tool_review_without_output_does_not_write_report_file(monkeypatch, capsys):
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
    generate_called = False

    class FakeRunner:
        def __init__(self, client, *, scan_fn, backend_name):
            self.client = client
            self.scan_fn = scan_fn
            self.backend_name = backend_name
            self.execution_summary = {}

        def run(self, **kwargs):
            self.execution_summary = {
                "status": "issues_found",
                "files_scanned": 1,
                "target_paths": ["src/example.py"],
            }
            return [report_issue]

        def build_report(self, issues=None):
            return report

        def generate_report(self, issues=None, output_file=None):
            nonlocal generate_called
            generate_called = True
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
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert generate_called is False
    assert payload["status"] == "completed"
    assert payload["report_path"] is None
    assert payload["report"]["project_path"] == "./proj"


def test_tool_review_cancel_file_returns_cancelled_exit(monkeypatch, capsys, tmp_path):
    cancel_file = tmp_path / "cancel.flag"
    cancel_file.write_text("stop", encoding="utf-8")

    class FakeRunner:
        def __init__(self, client, *, scan_fn, backend_name):
            self.client = client
            self.scan_fn = scan_fn
            self.backend_name = backend_name
            self.execution_summary = {}

        def run(self, **kwargs):
            kwargs["cancel_check"]()
            self.execution_summary = {
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
                category="transport",
                origin="prerequisite",
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
    assert payload["failure_categories"] == ["transport"]
    assert payload["checks"][0]["name"] == "Server Reachable"
    assert payload["checks"][0]["category"] == "transport"
    assert payload["checks"][0]["origin"] == "prerequisite"


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
        "--local-disable-web-search",
        "--timeout",
        "12",
    ])

    json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert ("backend", "type", "local") in set_calls
    assert ("local_llm", "api_url", "http://example.test:8080") in set_calls
    assert ("local_llm", "model", "llama-test") in set_calls
    assert ("local_llm", "enable_web_search", "false") in set_calls
    assert ("performance", "api_timeout_seconds", "12.0") in set_calls
    assert ("local_llm", "timeout", "12.0") in set_calls


def test_tool_health_can_enable_local_web_search(monkeypatch, capsys):
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
        "--local-enable-web-search",
    ])

    json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert ("local_llm", "enable_web_search", "true") in set_calls


def test_tool_health_accepts_backend_alias(monkeypatch, capsys):
    seen = []

    def _record_set(section, key, value):
        seen.append((section, key, value))

    monkeypatch.setattr(cli.config, "set_value", _record_set)
    monkeypatch.setattr(
        cli,
        "check_backend",
        lambda backend: HealthReport(backend=backend, ready=True, checks=[], summary="ok"),
    )

    exit_code = run_main_with_args([
        "health",
        "--backend",
        "ollama",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["backend"] == "local"
    assert ("backend", "type", "local") in seen
    assert ("local_llm", "api_type", "ollama") in seen


def test_tool_analyze_repo_outputs_generated_preview(tmp_path, capsys):
    project_root = tmp_path / "demo_repo"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        "[project]\nname = 'demo-repo'\nversion = '0.1.0'\n\n[tool.pytest.ini_options]\naddopts = '-q'\n",
        encoding="utf-8",
    )
    (project_root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "api.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "generated"
    exit_code = run_main_with_args([
        "analyze-repo",
        str(project_root),
        "--output-dir",
        str(output_dir),
        "--addon-id",
        "demo-fastapi-addon",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["command"] == "analyze-repo"
    assert payload["status"] == "generated"
    assert payload["preview_only"] is True
    assert payload["addon_id"] == "demo-fastapi-addon"
    assert "fastapi" in payload["profile"]["frameworks"]
    assert "pytest" in payload["profile"]["test_harnesses"]
    assert Path(payload["manifest_path"]).is_file()
    assert Path(payload["review_pack_path"]).is_file()
    assert Path(payload["approval_request_path"]).is_file()
    assert Path(payload["review_checklist_path"]).is_file()
    assert payload["approval_status"] == "pending_review"


def test_tool_approve_addon_preview_installs_generated_addon(tmp_path, capsys):
    project_root = tmp_path / "demo_repo"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        "[project]\nname = 'demo-repo'\nversion = '0.1.0'\n\n[tool.pytest.ini_options]\naddopts = '-q'\n",
        encoding="utf-8",
    )
    (project_root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    src_dir = project_root / "src"
    src_dir.mkdir()
    (src_dir / "api.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "generated"
    install_dir = tmp_path / "installed-addons"
    analyze_exit_code = run_main_with_args([
        "analyze-repo",
        str(project_root),
        "--output-dir",
        str(output_dir),
        "--addon-id",
        "demo-fastapi-addon",
    ])
    assert analyze_exit_code == 0
    capsys.readouterr()

    exit_code = run_main_with_args([
        "approve-addon-preview",
        str(output_dir),
        "--reviewer",
        "Colin",
        "--install-dir",
        str(install_dir),
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["command"] == "approve-addon-preview"
    assert payload["status"] == "approved"
    assert payload["approved"] is True
    assert Path(payload["approval_decision_path"]).is_file()
    assert Path(payload["install_path"]).is_dir()


def test_tool_review_accepts_backend_alias(monkeypatch, capsys):
    created = []

    report = ReviewReport(
        project_path="./proj",
        review_type="best_practices",
        scope="project",
        total_files_scanned=1,
        issues_found=[],
        generated_at=datetime(2026, 3, 26, 12, 0, 0),
        language="en",
        review_types=["best_practices"],
        programmers=["dev"],
        reviewers=["rev"],
        backend="copilot",
    )

    class FakeRunner:
        def __init__(self, client, *, scan_fn, backend_name):
            self.client = client
            self.scan_fn = scan_fn
            self.backend_name = backend_name
            self.execution_summary = {}

        def run(self, **kwargs):
            self.execution_summary = {
                "status": "no_issues",
                "files_scanned": 1,
                "target_paths": ["./proj/file.py"],
            }
            return []

        def build_report(self, issues=None):
            return report

        def generate_report(self, issues=None, output_file=None):
            return output_file or "review_report.json"

    def _fake_create_backend(name):
        created.append(name)
        return MagicMock()

    monkeypatch.setattr(cli, "create_backend", _fake_create_backend)
    monkeypatch.setattr(cli, "AppRunner", FakeRunner)

    exit_code = run_main_with_args([
        "review",
        "./proj",
        "--backend",
        "github-copilot",
        "--programmers",
        "dev",
        "--reviewers",
        "rev",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["backend"] == "copilot"
    assert created == ["copilot"]


def test_tool_review_error_payload_includes_structured_diagnostic(monkeypatch, capsys):
    def _raise_backend(_name):
        raise PermissionError("Access denied to backend")

    monkeypatch.setattr(cli, "create_backend", _raise_backend)

    exit_code = run_main_with_args([
        "review",
        "./proj",
        "--backend",
        "local",
        "--type",
        "security",
        "--programmers",
        "dev",
        "--reviewers",
        "rev",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 1
    assert payload["status"] == "error"
    assert payload["error"]["diagnostic"]["category"] == "permission"
    assert payload["error"]["diagnostic"]["origin"] == "review"


def test_tool_fix_plan_error_payload_includes_structured_diagnostic(monkeypatch, capsys):
    def _raise_report(_path):
        raise TimeoutError("request timeout")

    monkeypatch.setattr(cli, "_load_report_from_artifact", _raise_report)

    exit_code = run_main_with_args([
        "fix-plan",
        "--report-file",
        "missing.json",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 1
    assert payload["status"] == "error"
    assert payload["error"]["diagnostic"]["category"] == "timeout"
    assert payload["error"]["diagnostic"]["origin"] == "fix_plan"


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
    monkeypatch.setattr(
        cli,
        "generate_ai_fix_result",
        lambda issue, client, review_type, lang: FixGenerationResult(content="fixed()\n"),
    )

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
    monkeypatch.setattr(
        cli,
        "generate_ai_fix_result",
        lambda issue, client, review_type, lang: FixGenerationResult(content="fixed()\n"),
    )

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


def test_tool_apply_fixes_error_payload_includes_structured_diagnostic(capsys, tmp_path):
    plan_path = tmp_path / "fix-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "command": "fix-plan",
                "fixes": {"issue_id": "issue-0001"},
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
    assert payload["status"] == "error"
    assert payload["error"]["diagnostic"]["category"] == "configuration"
    assert payload["error"]["diagnostic"]["origin"] == "apply_fixes"


def test_tool_fix_plan_failed_item_includes_structured_diagnostic(monkeypatch, capsys, tmp_path):
    report_path = tmp_path / "report.json"
    source_path = tmp_path / "example.py"
    source_path.write_text("bad()\n", encoding="utf-8")
    report = ReviewReport(
        project_path=str(tmp_path),
        review_type="security",
        scope="project",
        total_files_scanned=1,
        issues_found=[
            ReviewIssue(
                file_path=str(source_path),
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
    monkeypatch.setattr(
        cli,
        "generate_ai_fix_result",
        lambda issue, client, review_type, lang: FixGenerationResult(
            content=None,
            diagnostic=cli._configuration_diagnostic("Fix generation is disabled for this file", origin="fix_generation"),
        ),
    )

    exit_code = run_main_with_args([
        "fix-plan",
        "--report-file",
        str(report_path),
        "--issue-id",
        "issue-0007",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 1
    assert payload["status"] == "partial"
    assert payload["failed_count"] == 1
    assert payload["fixes"][0]["status"] == "failed"
    assert payload["fixes"][0]["diagnostic"]["category"] == "configuration"
    assert payload["fixes"][0]["diagnostic"]["origin"] == "fix_generation"


def test_tool_apply_fixes_failed_item_includes_structured_diagnostic(capsys, tmp_path):
    plan_path = tmp_path / "fix-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "command": "fix-plan",
                "fixes": [
                    {
                        "issue_id": "issue-0001",
                        "file_path": str(tmp_path / "missing.py"),
                        "status": "generated",
                        "proposed_content": "fixed\n",
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
    assert payload["status"] == "partial"
    assert payload["results"][0]["status"] == "failed"
    assert payload["results"][0]["diagnostic"]["category"] == "configuration"
    assert payload["results"][0]["diagnostic"]["origin"] == "apply_fix_item"


def test_tool_resume_normalizes_review_artifact(capsys, tmp_path):
    report_path = tmp_path / "report.json"
    report = ReviewReport(
        project_path=str(tmp_path),
        review_type="security",
        scope="project",
        total_files_scanned=2,
        issues_found=[
            ReviewIssue(
                file_path=str(tmp_path / "example.py"),
                issue_type="security",
                severity="high",
                description="Unsafe pattern",
                code_snippet="bad()",
                ai_feedback="Use safe().",
                issue_id="issue-0001",
            ),
            ReviewIssue(
                file_path=str(tmp_path / "other.py"),
                issue_type="performance",
                severity="medium",
                description="Slow loop",
                code_snippet="for x in data",
                ai_feedback="Use batching.",
                issue_id="issue-0002",
                status="ignored",
            ),
        ],
        generated_at=datetime(2026, 3, 20, 10, 0, 0),
        language="en",
        review_types=["security", "performance"],
        backend="bedrock",
    )
    report_path.write_text(json.dumps(report.to_dict()), encoding="utf-8")

    exit_code = run_main_with_args([
        "resume",
        "--artifact-file",
        str(report_path),
        "--issue-id",
        "issue-0001",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["artifact_type"] == "review-report"
    assert payload["workflow_stage"] == "reviewed"
    assert payload["next_command"] == "fix-plan"
    assert payload["pending_issue_ids"] == ["issue-0001"]
    assert payload["issue_count"] == 1


def test_tool_resume_normalizes_review_dry_run_envelope(capsys, tmp_path):
    artifact_path = tmp_path / "review-dry-run.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "command": "review",
                "backend": "bedrock",
                "dry_run": True,
                "review_types": ["security"],
                "scope": "project",
                "path": "./proj",
                "status": "dry_run",
                "files_scanned": 1,
                "target_paths": ["./proj/file.py"],
                "issue_count": 0,
                "issues": [],
                "report": None,
                "report_path": None,
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_main_with_args([
        "resume",
        "--artifact-file",
        str(artifact_path),
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["artifact_type"] == "review"
    assert payload["workflow_stage"] == "dry-run"
    assert payload["next_command"] is None
    assert payload["can_resume"] is False
    assert payload["report"] is None
    assert payload["files_scanned"] == 1
    assert payload["target_paths"] == ["./proj/file.py"]


def test_tool_resume_normalizes_fix_plan_artifact(capsys, tmp_path):
    plan_path = tmp_path / "fix-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "command": "fix-plan",
                "backend": "local",
                "report_file": "report.json",
                "fixes": [
                    {
                        "issue_id": "issue-0001",
                        "file_path": "a.py",
                        "status": "generated",
                        "proposed_content": "fixed\n",
                    },
                    {
                        "issue_id": "issue-0002",
                        "file_path": "b.py",
                        "status": "failed",
                        "proposed_content": None,
                        "diagnostic": {
                            "category": "configuration",
                            "origin": "fix_generation",
                            "detail": "Fix generation disabled",
                            "fix_hint": "Check backend settings.",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_main_with_args([
        "resume",
        "--artifact-file",
        str(plan_path),
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["artifact_type"] == "fix-plan"
    assert payload["workflow_stage"] == "fix-planned"
    assert payload["next_command"] == "apply-fixes"
    assert payload["generated_issue_ids"] == ["issue-0001"]
    assert payload["failed_issue_ids"] == ["issue-0002"]
    assert payload["failed_diagnostics"] == [
        {
            "issue_id": "issue-0002",
            "file_path": "b.py",
            "category": "configuration",
            "origin": "fix_generation",
            "detail": "Fix generation disabled",
            "fix_hint": "Check backend settings.",
        }
    ]
    assert payload["failed_diagnostic_categories"] == [{"category": "configuration", "count": 1}]
    assert payload["fixes"][1]["diagnostic"]["origin"] == "fix_generation"


def test_tool_resume_normalizes_apply_results_artifact(capsys, tmp_path):
    results_path = tmp_path / "apply-results.json"
    results_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "command": "apply-fixes",
                "plan_file": "fix-plan.json",
                "results": [
                    {
                        "issue_id": "issue-0001",
                        "file_path": "a.py",
                        "status": "applied",
                        "backup_path": "a.py.backup",
                    },
                    {
                        "issue_id": "issue-0002",
                        "file_path": "b.py",
                        "status": "failed",
                        "error": "boom",
                        "diagnostic": {
                            "category": "provider",
                            "origin": "apply_fix_item",
                            "detail": "boom",
                            "fix_hint": "Retry later.",
                            "retryable": True,
                            "retry_delay_seconds": 10,
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_main_with_args([
        "resume",
        "--artifact-file",
        str(results_path),
        "--issue-id",
        "issue-0002",
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["artifact_type"] == "apply-fixes"
    assert payload["workflow_stage"] == "fixes-applied"
    assert payload["next_command"] is None
    assert payload["can_resume"] is False
    assert payload["failed_issue_ids"] == ["issue-0002"]
    assert payload["failed_diagnostics"] == [
        {
            "issue_id": "issue-0002",
            "file_path": "b.py",
            "category": "provider",
            "origin": "apply_fix_item",
            "detail": "boom",
            "fix_hint": "Retry later.",
            "retryable": True,
            "retry_delay_seconds": 10,
        }
    ]
    assert payload["failed_diagnostic_categories"] == [{"category": "provider", "count": 1}]
    assert payload["result_count"] == 1
    assert payload["results"][0]["diagnostic"]["origin"] == "apply_fix_item"


def test_tool_resume_rejects_unknown_artifact(capsys, tmp_path):
    artifact_path = tmp_path / "unknown.json"
    artifact_path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")

    exit_code = run_main_with_args([
        "resume",
        "--artifact-file",
        str(artifact_path),
    ])

    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 1
    assert payload["status"] == "error"