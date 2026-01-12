"""
Tests for CLI argument validation in main entrypoint.
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
    # Stub heavy dependencies to avoid network/file operations
    monkeypatch.setattr(cli, "BedrockClient", lambda: SimpleNamespace())
    monkeypatch.setattr(cli, "cleanup_old_backups", lambda path: None)
    monkeypatch.setattr(cli, "scan_project_with_scope", lambda path, scope, diff_file=None, commits=None: [])
    monkeypatch.setattr(cli, "get_profile_name", lambda: "default")

    # Should not raise; prints "No files found to review." and returns
    run_main_with_args([
        "./proj",
        "--programmers", "dev",
        "--reviewers", "rev",
    ])
