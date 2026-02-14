"""
Tests for CLI argument validation in main entrypoint.

Updated for v2.0 API: --backend flag, --type comma-separated,
create_backend() factory instead of BedrockClient().
"""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import aicodereviewer.main as cli


def run_main_with_args(args):
    argv_backup = sys.argv
    sys.argv = ["aicodereviewer"] + args
    try:
        cli.main()
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
    run_main_with_args([
        "./proj",
        "--programmers", "dev",
        "--reviewers", "rev",
    ])


def test_parse_review_types_single():
    """Single type string returns a one-element list."""
    result = cli._parse_review_types("security")
    assert result == ["security"]


def test_parse_review_types_comma_separated():
    """Comma-separated types are split and deduplicated."""
    result = cli._parse_review_types("security,performance,security")
    assert result == ["security", "performance"]


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

    run_main_with_args(["--check-connection", "--backend", "bedrock"])

    captured = capsys.readouterr()
    assert "✅" in captured.out or "success" in captured.out.lower()


def test_check_connection_failure(monkeypatch, capsys):
    """--check-connection with a failing backend prints failure and hints."""
    mock_backend = MagicMock()
    mock_backend.validate_connection.return_value = False
    monkeypatch.setattr(cli, "create_backend", lambda name: mock_backend)

    run_main_with_args(["--check-connection", "--backend", "local"])

    captured = capsys.readouterr()
    assert "❌" in captured.out or "fail" in captured.out.lower()
    # Should include local backend hints
    assert "Hint" in captured.out or "ヒント" in captured.out


def test_check_connection_is_standalone(monkeypatch):
    """--check-connection should NOT require --programmers/--reviewers/path."""
    mock_backend = MagicMock()
    mock_backend.validate_connection.return_value = True
    monkeypatch.setattr(cli, "create_backend", lambda name: mock_backend)

    # Should not raise SystemExit
    run_main_with_args(["--check-connection", "--backend", "kiro"])
