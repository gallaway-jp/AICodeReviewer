"""
Tests for CLI argument validation in main entrypoint.

Updated for v2.0 API: --backend flag, --type comma-separated,
create_backend() factory instead of BedrockClient().
"""
import io
import sys
from unittest.mock import MagicMock

import pytest

import aicodereviewer.main as cli


def run_main_with_args(args):
    argv_backup = sys.argv
    sys.argv = ["aicodereviewer"] + args
    try:
        return cli.main()
    finally:
        sys.argv = argv_backup


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


def test_parse_review_types_all():
    """'all' expands to the complete type list."""
    from aicodereviewer.backends.base import REVIEW_TYPE_KEYS
    result = cli._parse_review_types("all")
    assert result == list(REVIEW_TYPE_KEYS)


def test_parse_review_types_unknown_falls_back():
    """Unknown types are skipped; empty result falls back to best_practices."""
    result = cli._parse_review_types("nonexistent_type")
    assert result == ["best_practices"]


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
