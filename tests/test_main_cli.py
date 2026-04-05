"""
Tests for CLI argument validation in main entrypoint.

Updated for v2.0 API: --backend flag, --type comma-separated,
create_backend() factory instead of BedrockClient().
"""
import io
import json
import sys
import configparser
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import aicodereviewer.main as cli
from aicodereviewer.addons import AddonDiagnostic, AddonRuntime, get_active_addon_runtime, install_addon_runtime
from aicodereviewer.config import config
from aicodereviewer.i18n import set_locale, t
from aicodereviewer.recommendations import ReviewRecommendationResult, ReviewTypeRecommendation
from aicodereviewer.review_definitions import install_review_registry
from aicodereviewer.review_presets import get_review_preset_group_label


def run_main_with_args(args):
    argv_backup = sys.argv
    sys.argv = ["aicodereviewer"] + args
    try:
        return cli.main()
    finally:
        sys.argv = argv_backup


def _reset_config_to_path(config_path: Path) -> None:
    config.config_path = config_path
    config.config = configparser.ConfigParser()
    config._set_defaults()
    if config_path.exists():
        config.config.read(config_path, encoding="utf-8")


def test_project_scope_requires_path(monkeypatch):
    with pytest.raises(SystemExit):
        run_main_with_args([
            "--programmers", "dev",
            "--reviewers", "rev",
        ])


def test_diff_scope_requires_source(monkeypatch):
    with pytest.raises(SystemExit):
        run_main_with_args([
            "--scope", "diff",
            "--programmers", "dev",
            "--reviewers", "rev",
        ])


def test_diff_scope_rejects_both_sources(monkeypatch):
    with pytest.raises(SystemExit):
        run_main_with_args([
            "--scope", "diff",
            "--diff-file", "a.patch",
            "--commits", "HEAD~1..HEAD",
            "--programmers", "dev",
            "--reviewers", "rev",
            "./proj",
        ])


def test_specification_requires_file(monkeypatch):
    with pytest.raises(SystemExit):
        run_main_with_args([
            "--type", "specification",
            "--programmers", "dev",
            "--reviewers", "rev",
            "./proj",
        ])


def test_happy_path_exits_when_no_files(monkeypatch):
    """Ensure the review short-circuits gracefully when no files are found."""
    mock_backend = MagicMock()
    monkeypatch.setattr(cli, "create_backend", lambda name: mock_backend)
    monkeypatch.setattr(cli, "cleanup_old_backups", lambda path: None)
    monkeypatch.setattr(cli, "scan_project_with_scope", lambda path, scope, diff_file=None, commits=None: [])

    # Should not raise; prints "No files found to review." and returns
    exit_code = run_main_with_args([
        "./proj",
        "--programmers", "dev",
        "--reviewers", "rev",
    ])

    assert exit_code == 0


def test_dry_run_does_not_require_backend(monkeypatch):
    """CLI dry-run should proceed without creating a backend client."""
    create_backend_called = False

    def _fake_create_backend(_name):
        nonlocal create_backend_called
        create_backend_called = True
        raise AssertionError("create_backend should not be called for dry-run")

    monkeypatch.setattr(cli, "create_backend", _fake_create_backend)
    monkeypatch.setattr(cli, "scan_project_with_scope", lambda path, scope, diff_file=None, commits=None: ["./proj/file.py"])

    exit_code = run_main_with_args([
        "./proj",
        "--type", "security",
        "--dry-run",
    ])

    assert create_backend_called is False
    assert exit_code == 0


def test_recommend_types_prints_recommendation_summary(monkeypatch, capsys):
    class _FakeBackend:
        pass

    monkeypatch.setattr(cli, "create_backend", lambda name: _FakeBackend())
    monkeypatch.setattr(
        cli,
        "recommend_review_types",
        lambda **kwargs: ReviewRecommendationResult(
            review_types=["security", "error_handling", "data_validation"],
            rationale=[
                ReviewTypeRecommendation("security", "FastAPI-style service boundaries are in scope."),
                ReviewTypeRecommendation("error_handling", "Workflow boundaries suggest failure propagation checks."),
                ReviewTypeRecommendation("data_validation", "Input-heavy endpoints benefit from validation review."),
            ],
            project_signals=["Frameworks: fastapi", "Dependency manifests: pyproject.toml"],
            recommended_preset="runtime_safety",
            source="ai",
        ),
    )

    exit_code = run_main_with_args([
        "./proj",
        "--recommend-types",
        "--backend",
        "bedrock",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert t("cli.recommendation_header") in captured.out
    assert "runtime_safety" in captured.out
    assert "security, error_handling, data_validation" in captured.out


def test_recommend_types_does_not_require_review_metadata(monkeypatch):
    monkeypatch.setattr(cli, "create_backend", lambda name: object())
    monkeypatch.setattr(
        cli,
        "recommend_review_types",
        lambda **kwargs: ReviewRecommendationResult(
            review_types=["best_practices"],
            rationale=[
                ReviewTypeRecommendation("best_practices", "Baseline pass."),
            ],
            project_signals=["Approximate project size: 10 files"],
            recommended_preset=None,
            source="heuristic",
        ),
    )

    assert run_main_with_args(["./proj", "--recommend-types"]) == 0


def test_recommend_types_passes_richer_dependency_and_diff_summaries_to_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_root = tmp_path / "proj"
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

    captured_contexts: list[str] = []

    class _FakeBackend:
        def get_review_recommendations(self, recommendation_context: str, *, lang: str = "en") -> str:
            captured_contexts.append(recommendation_context)
            return json.dumps(
                {
                    "recommended_review_types": ["security", "error_handling"],
                    "rationale": [
                        {"review_type": "security", "reason": "Service boundaries are in scope."},
                        {"review_type": "error_handling", "reason": "Workflow failure propagation matters."},
                    ],
                    "project_signals": ["Frameworks: fastapi", "Changed files: src/api.py"],
                }
            )

        def close(self) -> None:
            return None

    def _fake_scan(path: str | None, scope: str, diff_file: str | None = None, commits: str | None = None):
        if scope == "diff":
            return [
                {
                    "filename": "src/api.py",
                    "path": project_root / "src" / "api.py",
                    "hunks": [object(), object()],
                    "commit_messages": "Harden request validation\n\nMore details",
                },
                {
                    "filename": "src/ui.tsx",
                    "path": project_root / "src" / "ui.tsx",
                    "hunks": [object()],
                },
            ]
        return [project_root / "src" / "api.py", project_root / "src" / "ui.tsx"]

    class _FakeProjectContext:
        frameworks = ["fastapi", "pytest", "react"]
        tools = ["ruff"]
        total_files = 42

    monkeypatch.setattr(cli, "create_backend", lambda _name: _FakeBackend())
    monkeypatch.setattr("aicodereviewer.recommendations.scan_project_with_scope", _fake_scan)
    monkeypatch.setattr(
        "aicodereviewer.recommendations.collect_project_context",
        lambda *_args, **_kwargs: _FakeProjectContext(),
    )

    exit_code = run_main_with_args([
        str(project_root),
        "--scope",
        "diff",
        "--diff-file",
        "changes.diff",
        "--recommend-types",
        "--backend",
        "bedrock",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert t("cli.recommendation_header") in captured.out
    assert captured_contexts
    recommendation_context = captured_contexts[0]
    assert "DEPENDENCY SUMMARY:" in recommendation_context
    assert "Dependencies: requirements.txt lists fastapi==0.115.0, httpx==0.28.0" in recommendation_context
    assert "Tooling: pyproject.toml sections include [tool.pytest.ini_options]" in recommendation_context
    assert "DIFF SUMMARY:" in recommendation_context
    assert "Diff files: src/api.py, src/ui.tsx" in recommendation_context
    assert "Hunks: 3 across 2 file(s)" in recommendation_context
    assert "Changed file types: .py x1, .tsx x1" in recommendation_context
    assert "Commit messages: Harden request validation" in recommendation_context


def test_parse_review_types_single():
    """Single type string returns a one-element list."""
    result = cli._parse_review_types("security")
    assert result == ["security"]


def test_parse_review_types_comma_separated():
    """Comma-separated types are split and deduplicated."""
    result = cli._parse_review_types("security,performance,security")
    assert result == ["security", "performance"]


def test_parse_review_types_ui_ux():
    """The UI/UX review type should parse like any other selectable type."""
    result = cli._parse_review_types("ui_ux")
    assert result == ["ui_ux"]


def test_parse_review_types_dead_code():
    """The dead_code review type should parse like any other selectable type."""
    result = cli._parse_review_types("dead_code")
    assert result == ["dead_code"]


def test_parse_review_types_resolves_aliases_to_canonical_keys():
    """Known aliases should normalize to their canonical review types."""
    result = cli._parse_review_types("spec,i18n")
    assert result == ["specification", "localization"]


def test_parse_review_types_deduplicates_alias_and_canonical_mix():
    """Alias and canonical entries should collapse to one canonical type."""
    result = cli._parse_review_types("specification,spec")
    assert result == ["specification"]


def test_parse_review_types_all():
    """'all' expands to the complete type list."""
    from aicodereviewer.backends.base import REVIEW_TYPE_KEYS
    result = cli._parse_review_types("all")
    assert result == list(REVIEW_TYPE_KEYS)


def test_parse_review_types_preset():
    """Named presets expand to their documented review type bundles."""
    result = cli._parse_review_types("runtime_safety")
    assert result == ["security", "error_handling", "data_validation", "dependency"]


def test_parse_review_types_preset_and_explicit_type_deduplicate():
    """Presets and explicit types deduplicate while preserving bundle order."""
    result = cli._parse_review_types("runtime_safety,security,testing")
    assert result == ["security", "error_handling", "data_validation", "dependency", "testing"]


def test_parse_review_types_custom_preset(monkeypatch, tmp_path: Path):
    pack_path = tmp_path / "review-pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "version": 1,
                "review_definitions": [
                    {
                        "key": "secure_defaults",
                        "parent_key": "security",
                        "prompt_append": "Check unsafe defaults.",
                    }
                ],
                "review_presets": [
                    {
                        "key": "secure_runtime",
                        "aliases": ["secure-runtime"],
                        "review_types": ["secure_defaults", "data_validation"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    install_review_registry([pack_path])
    try:
        result = cli._parse_review_types("secure_runtime")
    finally:
        install_review_registry([])

    assert result == ["secure_defaults", "data_validation"]


def test_parse_review_types_custom_preset_alias(tmp_path: Path):
    pack_path = tmp_path / "review-pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "version": 1,
                "review_definitions": [
                    {
                        "key": "secure_defaults",
                        "parent_key": "security",
                        "prompt_append": "Check unsafe defaults.",
                    }
                ],
                "review_presets": [
                    {
                        "key": "secure_runtime",
                        "aliases": ["secure-runtime"],
                        "review_types": ["secure_defaults", "data_validation"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    install_review_registry([pack_path])
    try:
        result = cli._parse_review_types("secure-runtime")
    finally:
        install_review_registry([])

    assert result == ["secure_defaults", "data_validation"]


def test_list_type_presets_prints_definitions(capsys):
    """Listing presets should print the preset names and included review types."""
    exit_code = run_main_with_args(["--list-type-presets"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "runtime_safety" in captured.out
    assert f"[{get_review_preset_group_label('runtime_safety')}]" in captured.out
    assert "security, error_handling, data_validation, dependency" in captured.out
    assert "product_surface" in captured.out


def test_parse_review_types_unknown_falls_back():
    """Unknown types are skipped; empty result falls back to best_practices."""
    result = cli._parse_review_types("nonexistent_type")
    assert result == ["best_practices"]


def test_list_addons_prints_runtime_summary(monkeypatch, capsys):
    runtime = AddonRuntime(
        manifests=(),
        diagnostics=(
            AddonDiagnostic(
                severity="error",
                message="Invalid addon manifest",
            ),
        ),
    )

    monkeypatch.setattr(cli, "install_addon_runtime", lambda: runtime)
    monkeypatch.setattr(cli, "install_review_registry", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "get_system_language", lambda: "en")

    exit_code = run_main_with_args(["--list-addons"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Discovered Addons:" in captured.out
    assert "No addons were discovered." in captured.out
    assert "Addon Diagnostics:" in captured.out
    assert "Invalid addon manifest" in captured.out


def test_list_addons_reads_checked_in_example_addon_from_configured_paths(monkeypatch, tmp_path: Path, capsys):
    repo_root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "config.ini"
    original_config_path = config.config_path
    original_config_parser = config.config
    original_runtime = get_active_addon_runtime()

    _reset_config_to_path(config_path)
    config.set_value("addons", "paths", str(repo_root / "examples" / "addon-echo-backend"))
    config.save()
    monkeypatch.setattr(cli, "get_system_language", lambda: "en")

    try:
        exit_code = run_main_with_args(["--list-addons"])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Echo Backend Addon [echo-backend-addon] v1.0.0" in captured.out
        assert "backend providers: 1" in captured.out
        assert "Echo Addon Backend [echo-addon]" in captured.out
        assert "ui contributors: 1" in captured.out
        assert "settings_section: Echo Backend Addon" in captured.out
        assert "No addon diagnostics." in captured.out
    finally:
        config.config_path = original_config_path
        config.config = original_config_parser
        install_addon_runtime([manifest.manifest_path for manifest in original_runtime.manifests])
        install_review_registry([])


# ── --check-connection tests ───────────────────────────────────────────────

def test_check_connection_success(monkeypatch, capsys):
    """--check-connection with a successful backend prints success."""
    mock_backend = MagicMock()
    mock_backend.validate_connection.return_value = True
    monkeypatch.setattr(cli, "create_backend", lambda name: mock_backend)

    exit_code = run_main_with_args(["--check-connection", "--backend", "bedrock"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "✅" in captured.out or "success" in captured.out.lower()


def test_check_connection_failure(monkeypatch, capsys):
    """--check-connection with a failing backend prints failure and hints."""
    mock_backend = MagicMock()
    mock_backend.validate_connection.return_value = False
    monkeypatch.setattr(cli, "create_backend", lambda name: mock_backend)

    exit_code = run_main_with_args(["--check-connection", "--backend", "local"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "❌" in captured.out or "fail" in captured.out.lower()
    # Should include local backend hints
    assert "Hint" in captured.out or "ヒント" in captured.out


def test_check_connection_is_standalone(monkeypatch):
    """--check-connection should NOT require --programmers/--reviewers/path."""
    mock_backend = MagicMock()
    mock_backend.validate_connection.return_value = True
    monkeypatch.setattr(cli, "create_backend", lambda name: mock_backend)

    # Should not raise SystemExit
    assert run_main_with_args(["--check-connection", "--backend", "kiro"]) == 0


def test_check_connection_accepts_backend_alias(monkeypatch):
    received_names = []
    mock_backend = MagicMock()
    mock_backend.validate_connection.return_value = True

    def _fake_create_backend(name):
        received_names.append(name)
        return mock_backend

    monkeypatch.setattr(cli, "create_backend", _fake_create_backend)

    exit_code = run_main_with_args(["--check-connection", "--backend", "ollama"])

    assert exit_code == 0
    assert received_names == ["local"]


def test_backend_startup_failure_returns_nonzero(monkeypatch, capsys):
    """Backend creation failures should be reported cleanly and stop the run."""
    monkeypatch.setattr(cli, "create_backend", lambda _name: (_ for _ in ()).throw(RuntimeError("boom")))

    exit_code = run_main_with_args([
        "./proj",
        "--programmers", "dev",
        "--reviewers", "rev",
    ])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Failed to create backend" in captured.err


def test_help_is_localized_before_argparse_renders(monkeypatch, capsys):
    """--lang should affect help output, not just post-parse runtime behavior."""
    monkeypatch.setattr(cli, "get_system_language", lambda: "en")

    with pytest.raises(SystemExit) as exc_info:
        run_main_with_args(["--lang", "ja", "--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "多言語対応AIコードレビュー" in captured.out


def test_epilog_includes_review_type_summaries():
    set_locale("en")

    epilog = cli._build_epilog()

    assert "ui_ux" in epilog
    assert "dead_code" in epilog
    assert "Usability, interaction flow, hierarchy, and interface clarity." in epilog
    assert "Unused, unreachable, or obsolete code paths with concrete evidence." in epilog
    assert "WCAG-oriented UI and interaction concerns." in epilog


def test_epilog_summaries_are_localized():
    set_locale("ja")

    epilog = cli._build_epilog()

    assert "利用可能なレビュータイプ" in epilog
    assert "デッドコード" in epilog
    assert "使いやすさ、操作フロー、情報階層、インターフェースの明確さ。" in epilog
    assert "未使用、到達不能、または役目を終えたコード経路を根拠付きで検出します。" in epilog


def test_epilog_renders_custom_subtype_under_parent(tmp_path: Path):
    pack_path = tmp_path / "custom-pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "version": 1,
                "review_definitions": [
                    {
                        "key": "secure_defaults",
                        "parent_key": "security",
                        "label": "Secure Defaults",
                        "summary_key": "",
                        "prompt_append": "Check opt-out security defaults.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    set_locale("en")
    install_review_registry([pack_path])
    try:
        epilog = cli._build_epilog()
    finally:
        install_review_registry([])

    assert "  security" in epilog
    assert "    secure_defaults" in epilog


def test_list_type_presets_uses_invocation_review_pack(capsys, tmp_path: Path) -> None:
    pack_path = tmp_path / "preset-pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "version": 1,
                "review_definitions": [
                    {
                        "key": "secure_defaults",
                        "parent_key": "security",
                        "prompt_append": "Check unsafe defaults.",
                    }
                ],
                "review_presets": [
                    {
                        "key": "secure_runtime",
                        "group": "Custom Bundles",
                        "label": "Secure Runtime",
                        "summary": "Security defaults plus validation.",
                        "review_types": ["secure_defaults", "data_validation"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run_main_with_args(["--review-pack", str(pack_path), "--list-type-presets"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "secure_runtime" in captured.out
    assert "[Custom Bundles]" in captured.out
    assert "secure_defaults, data_validation" in captured.out


def test_print_console_replaces_unencodable_characters(monkeypatch):
    """Console output should not raise when the terminal encoding rejects emoji."""
    buffer = io.BytesIO()

    class FakeStdout:
        encoding = "cp932"

        def __init__(self, raw_buffer):
            self.buffer = raw_buffer

        def flush(self):
            return None

    monkeypatch.setattr(cli.sys, "stdout", FakeStdout(buffer))

    cli._print_console("✅ Connection successful!")

    output = buffer.getvalue().decode("cp932")
    assert "Connection successful!" in output
