from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


def _run_git_command(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"git {' '.join(args)} failed"
        raise ValueError(detail)
    return completed.stdout.strip()


def read_git_current_branch(repo_root: Path) -> str | None:
    current_branch = _run_git_command(repo_root, "branch", "--show-current")
    return current_branch or None


def read_git_local_branches(repo_root: Path) -> tuple[str, ...]:
    output = _run_git_command(repo_root, "branch", "--format=%(refname:short)")
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def read_git_tags(repo_root: Path) -> tuple[str, ...]:
    output = _run_git_command(repo_root, "tag", "--list")
    return tuple(line.strip() for line in output.splitlines() if line.strip())


@dataclass(frozen=True)
class ReleaseGitState:
    current_branch: str | None
    local_branches: tuple[str, ...]
    git_tags: tuple[str, ...]
    target_version: str | None = None

    @property
    def release_branch_name(self) -> str | None:
        if not self.target_version:
            return None
        return f"release/{self.target_version}"

    @property
    def release_tag_name(self) -> str | None:
        if not self.target_version:
            return None
        return f"v{self.target_version}"

    @property
    def release_branch_present(self) -> bool:
        release_branch_name = self.release_branch_name
        return release_branch_name in self.local_branches if release_branch_name else False

    @property
    def release_tag_present(self) -> bool:
        release_tag_name = self.release_tag_name
        return release_tag_name in self.git_tags if release_tag_name else False

    def issues(
        self,
        *,
        require_release_branch: bool = False,
        require_release_tag: bool = False,
    ) -> list[str]:
        issues: list[str] = []
        if require_release_branch:
            if not self.target_version:
                issues.append("A target version is required to validate the release branch state.")
            elif not self.release_branch_present:
                issues.append(f"The local release branch {self.release_branch_name} does not exist.")
            elif self.current_branch != self.release_branch_name:
                current_branch = self.current_branch or "(detached HEAD)"
                issues.append(
                    f"Current branch {current_branch} does not match the required release branch {self.release_branch_name}."
                )
        if require_release_tag:
            if not self.target_version:
                issues.append("A target version is required to validate the release tag state.")
            elif not self.release_tag_present:
                issues.append(f"The git tag {self.release_tag_name} does not exist.")
        return issues

    def to_dict(
        self,
        *,
        require_release_branch: bool = False,
        require_release_tag: bool = False,
    ) -> dict[str, object]:
        return {
            "current_branch": self.current_branch,
            "local_branches": list(self.local_branches),
            "git_tags": list(self.git_tags),
            "release_branch_name": self.release_branch_name,
            "release_branch_present": self.release_branch_present,
            "release_tag_name": self.release_tag_name,
            "release_tag_present": self.release_tag_present,
            "git_issues": self.issues(
                require_release_branch=require_release_branch,
                require_release_tag=require_release_tag,
            ),
        }


def evaluate_release_git_state(repo_root: Path, *, target_version: str | None = None) -> ReleaseGitState:
    return ReleaseGitState(
        current_branch=read_git_current_branch(repo_root),
        local_branches=read_git_local_branches(repo_root),
        git_tags=read_git_tags(repo_root),
        target_version=target_version,
    )