from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
for bootstrap_path in (str(REPO_ROOT), str(SRC_ROOT)):
    if bootstrap_path not in sys.path:
        sys.path.insert(0, bootstrap_path)

from aicodereviewer.release_metadata import evaluate_release_metadata
from aicodereviewer.release_git_state import evaluate_release_git_state


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check release metadata alignment between pyproject.toml and RELEASE_NOTES.md.")
    parser.add_argument("--pyproject", default=str(REPO_ROOT / "pyproject.toml"))
    parser.add_argument("--release-notes", default=str(REPO_ROOT / "RELEASE_NOTES.md"))
    parser.add_argument("--application-version-file", default=str(SRC_ROOT / "aicodereviewer" / "__init__.py"))
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--target-version")
    parser.add_argument("--check-git", action="store_true")
    parser.add_argument("--require-release-branch", action="store_true")
    parser.add_argument("--require-release-tag", action="store_true")
    parser.add_argument("--require-aligned", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _collect_issues(status, git_status, *, require_release_branch: bool, require_release_tag: bool) -> list[str]:
    issues = list(status.issues())
    if git_status is not None:
        issues.extend(
            git_status.issues(
                require_release_branch=require_release_branch,
                require_release_tag=require_release_tag,
            )
        )
    return issues


def _render_human(status, git_status, *, require_release_branch: bool, require_release_tag: bool) -> str:
    lines = [
        f"Package version: {status.package_version}",
        f"Application version: {status.application_version or '(not checked)'}",
        f"Release headings: {', '.join(status.release_headings) if status.release_headings else '(none)'}",
        f"Latest versioned heading: {status.latest_release_heading or '(none)'}",
        f"Unreleased present: {'yes' if status.unreleased_present else 'no'}",
    ]
    if status.target_version is not None:
        lines.append(f"Target version: {status.target_version}")
    if git_status is not None:
        lines.append(f"Current git branch: {git_status.current_branch or '(detached HEAD)'}")
        lines.append(
            f"Local release branch present: {'yes' if git_status.release_branch_present else 'no'}"
        )
        lines.append(f"Local release tag present: {'yes' if git_status.release_tag_present else 'no'}")
        lines.append(f"Known git tags: {', '.join(git_status.git_tags) if git_status.git_tags else '(none)'}")
    issues = _collect_issues(
        status,
        git_status,
        require_release_branch=require_release_branch,
        require_release_tag=require_release_tag,
    )
    if issues:
        lines.append("Issues:")
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("Issues: none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if (args.require_release_branch or args.require_release_tag) and not args.target_version:
        parser.error("--target-version is required when validating release branch or tag state.")
    status = evaluate_release_metadata(
        Path(args.pyproject),
        Path(args.release_notes),
        application_version_path=Path(args.application_version_file),
        target_version=args.target_version,
    )
    git_status = None
    if args.check_git or args.require_release_branch or args.require_release_tag:
        git_status = evaluate_release_git_state(Path(args.repo_root), target_version=args.target_version)
    issues = _collect_issues(
        status,
        git_status,
        require_release_branch=args.require_release_branch,
        require_release_tag=args.require_release_tag,
    )
    if args.json:
        payload = status.to_dict()
        if git_status is not None:
            payload.update(
                git_status.to_dict(
                    require_release_branch=args.require_release_branch,
                    require_release_tag=args.require_release_tag,
                )
            )
            payload["issues"] = issues
        print(json.dumps(payload, indent=2))
    else:
        print(
            _render_human(
                status,
                git_status,
                require_release_branch=args.require_release_branch,
                require_release_tag=args.require_release_tag,
            )
        )
    if (args.require_aligned or args.require_release_branch or args.require_release_tag) and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())