from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


_RELEASE_HEADING_RE = re.compile(r"^##\s+(Unreleased|v\d+\.\d+\.\d+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ReleaseMetadataStatus:
    package_version: str
    application_version: str | None
    release_headings: tuple[str, ...]
    unreleased_present: bool
    latest_release_heading: str | None
    target_version: str | None = None

    @property
    def expected_package_heading(self) -> str:
        return f"v{self.package_version}"

    @property
    def target_heading(self) -> str | None:
        if not self.target_version:
            return None
        return f"v{self.target_version}"

    def issues(self) -> list[str]:
        issues: list[str] = []
        if self.application_version is not None and self.application_version != self.package_version:
            issues.append(
                "src/aicodereviewer/__init__.py __version__ "
                f"{self.application_version} does not match pyproject.toml version {self.package_version}."
            )
        if self.latest_release_heading is None:
            issues.append("RELEASE_NOTES.md does not contain any versioned release heading.")
        elif self.latest_release_heading != self.expected_package_heading:
            issues.append(
                "pyproject.toml version "
                f"{self.package_version} does not match the latest release-notes heading {self.latest_release_heading}."
            )
        if self.target_version is not None:
            if self.package_version != self.target_version:
                issues.append(
                    f"pyproject.toml version {self.package_version} does not match target version {self.target_version}."
                )
            target_heading = self.target_heading
            if target_heading not in self.release_headings:
                issues.append(f"RELEASE_NOTES.md is missing the target heading {target_heading}.")
        return issues

    def to_dict(self) -> dict[str, object]:
        return {
            "package_version": self.package_version,
            "application_version": self.application_version,
            "release_headings": list(self.release_headings),
            "unreleased_present": self.unreleased_present,
            "latest_release_heading": self.latest_release_heading,
            "target_version": self.target_version,
            "target_heading": self.target_heading,
            "issues": self.issues(),
        }


def read_package_version(pyproject_path: Path) -> str:
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload.get("project")
    if not isinstance(project, dict):
        raise ValueError("pyproject.toml is missing a [project] table.")
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("pyproject.toml is missing project.version.")
    return version.strip()


def read_application_version(application_version_path: Path) -> str:
    module = ast.parse(application_version_path.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and node.value.value.strip():
                        return node.value.value.strip()
                    raise ValueError("src/aicodereviewer/__init__.py has a non-string __version__ value.")
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "__version__":
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.strip():
                    return value.value.strip()
                raise ValueError("src/aicodereviewer/__init__.py has a non-string __version__ value.")
    raise ValueError("src/aicodereviewer/__init__.py is missing __version__.")


def read_release_note_headings(release_notes_path: Path) -> tuple[str, ...]:
    content = release_notes_path.read_text(encoding="utf-8")
    return tuple(match.group(1) for match in _RELEASE_HEADING_RE.finditer(content))


def evaluate_release_metadata(
    pyproject_path: Path,
    release_notes_path: Path,
    *,
    application_version_path: Path | None = None,
    target_version: str | None = None,
) -> ReleaseMetadataStatus:
    package_version = read_package_version(pyproject_path)
    application_version = None
    if application_version_path is not None:
        application_version = read_application_version(application_version_path)
    release_headings = read_release_note_headings(release_notes_path)
    unreleased_present = "Unreleased" in release_headings
    latest_release_heading = next((heading for heading in release_headings if heading != "Unreleased"), None)
    return ReleaseMetadataStatus(
        package_version=package_version,
        application_version=application_version,
        release_headings=release_headings,
        unreleased_present=unreleased_present,
        latest_release_heading=latest_release_heading,
        target_version=target_version,
    )