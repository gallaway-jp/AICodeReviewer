from __future__ import annotations

from pathlib import Path
from typing import Any

import aicodereviewer.release_git_state as release_git_state
from aicodereviewer.release_metadata import (
    evaluate_release_metadata,
    read_application_version,
    read_package_version,
    read_release_note_headings,
)


def test_read_package_version_returns_project_version(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'demo'\nversion = '0.2.0'\n", encoding="utf-8")

    assert read_package_version(pyproject) == "0.2.0"


def test_read_release_note_headings_returns_unreleased_and_versions(tmp_path: Path) -> None:
    release_notes = tmp_path / "RELEASE_NOTES.md"
    release_notes.write_text(
        "# Release Notes\n\n## Unreleased\n\ntext\n\n## v0.2.0\n\ntext\n\n## v2.0.1\n",
        encoding="utf-8",
    )

    assert read_release_note_headings(release_notes) == ("Unreleased", "v0.2.0", "v2.0.1")


def test_read_application_version_returns_module_version(tmp_path: Path) -> None:
    module = tmp_path / "__init__.py"
    module.write_text("__version__ = '0.2.0'\n", encoding="utf-8")

    assert read_application_version(module) == "0.2.0"


def test_evaluate_release_metadata_reports_latest_heading_mismatch(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    release_notes = tmp_path / "RELEASE_NOTES.md"
    pyproject.write_text("[project]\nname = 'demo'\nversion = '2.0.0'\n", encoding="utf-8")
    release_notes.write_text(
        "# Release Notes\n\n## Unreleased\n\ntext\n\n## v2.0.1\n\ntext\n",
        encoding="utf-8",
    )

    status = evaluate_release_metadata(pyproject, release_notes)

    assert status.package_version == "2.0.0"
    assert status.latest_release_heading == "v2.0.1"
    assert status.unreleased_present is True
    assert status.issues() == [
        "pyproject.toml version 2.0.0 does not match the latest release-notes heading v2.0.1."
    ]


def test_evaluate_release_metadata_accepts_aligned_target_version(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    release_notes = tmp_path / "RELEASE_NOTES.md"
    module = tmp_path / "__init__.py"
    pyproject.write_text("[project]\nname = 'demo'\nversion = '0.2.0'\n", encoding="utf-8")
    module.write_text("__version__ = '0.2.0'\n", encoding="utf-8")
    release_notes.write_text(
        "# Release Notes\n\n## Unreleased\n\ntext\n\n## v0.2.0\n\ntext\n\n## v2.0.1\n\ntext\n",
        encoding="utf-8",
    )

    status = evaluate_release_metadata(
        pyproject,
        release_notes,
        application_version_path=module,
        target_version="0.2.0",
    )

    assert status.application_version == "0.2.0"
    assert status.latest_release_heading == "v0.2.0"
    assert status.target_heading == "v0.2.0"
    assert status.issues() == []


def test_evaluate_release_metadata_reports_application_version_mismatch(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    release_notes = tmp_path / "RELEASE_NOTES.md"
    module = tmp_path / "__init__.py"
    pyproject.write_text("[project]\nname = 'demo'\nversion = '0.2.0'\n", encoding="utf-8")
    module.write_text("__version__ = '0.1.9'\n", encoding="utf-8")
    release_notes.write_text("# Release Notes\n\n## Unreleased\n\ntext\n\n## v0.2.0\n\ntext\n", encoding="utf-8")

    status = evaluate_release_metadata(
        pyproject,
        release_notes,
        application_version_path=module,
        target_version="0.2.0",
    )

    assert status.issues() == [
        "src/aicodereviewer/__init__.py __version__ 0.1.9 does not match pyproject.toml version 0.2.0."
    ]


def test_evaluate_release_git_state_reports_missing_release_branch_and_tag(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(release_git_state, "read_git_current_branch", lambda _repo_root: "main")
    monkeypatch.setattr(release_git_state, "read_git_local_branches", lambda _repo_root: ("main",))
    monkeypatch.setattr(release_git_state, "read_git_tags", lambda _repo_root: ("v0.1.0",))

    status = release_git_state.evaluate_release_git_state(tmp_path, target_version="0.2.0")

    assert status.release_branch_present is False
    assert status.release_tag_present is False
    assert status.issues(require_release_branch=True, require_release_tag=True) == [
        "The local release branch release/0.2.0 does not exist.",
        "The git tag v0.2.0 does not exist.",
    ]


def test_evaluate_release_git_state_accepts_present_release_branch_and_tag(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(release_git_state, "read_git_current_branch", lambda _repo_root: "release/0.2.0")
    monkeypatch.setattr(
        release_git_state,
        "read_git_local_branches",
        lambda _repo_root: ("main", "release/0.2.0"),
    )
    monkeypatch.setattr(release_git_state, "read_git_tags", lambda _repo_root: ("v0.1.0", "v0.2.0"))

    status = release_git_state.evaluate_release_git_state(tmp_path, target_version="0.2.0")

    assert status.release_branch_present is True
    assert status.release_tag_present is True
    assert status.issues(require_release_branch=True, require_release_tag=True) == []


def test_evaluate_release_git_state_requires_current_release_branch_when_requested(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(release_git_state, "read_git_current_branch", lambda _repo_root: "main")
    monkeypatch.setattr(
        release_git_state,
        "read_git_local_branches",
        lambda _repo_root: ("main", "release/0.2.0"),
    )
    monkeypatch.setattr(release_git_state, "read_git_tags", lambda _repo_root: ("v0.1.0",))

    status = release_git_state.evaluate_release_git_state(tmp_path, target_version="0.2.0")

    assert status.issues(require_release_branch=True) == [
        "Current branch main does not match the required release branch release/0.2.0."
    ]