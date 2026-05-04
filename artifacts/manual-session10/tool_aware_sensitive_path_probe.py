from __future__ import annotations

import configparser
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aicodereviewer.backends import create_backend
from aicodereviewer.config import config
from aicodereviewer.reviewer import collect_review_issues


def clone_current_config() -> configparser.ConfigParser:
    cloned = configparser.ConfigParser()
    for section in config.config.sections():
        cloned.add_section(section)
        for key, value in config.config.items(section):
            cloned.set(section, key, value)
    return cloned


def reset_config_to_path(config_path: Path) -> None:
    config.config_path = config_path
    config.config = configparser.ConfigParser()
    config._set_defaults()
    if config_path.exists():
        config.config.read(config_path, encoding="utf-8")


def restore_config(config_path: Path, snapshot: configparser.ConfigParser) -> None:
    config.config_path = config_path
    config.config = configparser.ConfigParser()
    config._set_defaults()
    for section in snapshot.sections():
        if not config.config.has_section(section):
            config.config.add_section(section)
        for key, value in snapshot.items(section):
            config.config.set(section, key, value)


def write_probe_project(project_root: Path) -> dict[str, Path]:
    app_dir = project_root / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    api_path = app_dir / "api.py"
    runner_path = app_dir / "runner.py"
    env_path = project_root / ".env"

    api_path.write_text(
        "from runner import export_report\n\n"
        "def export_endpoint(user_args: str) -> str:\n"
        "    return export_report(user_args)\n",
        encoding="utf-8",
    )
    runner_path.write_text(
        "import subprocess\n\n"
        "def export_report(user_args: str) -> str:\n"
        "    command = f\"report-tool {user_args}\"\n"
        "    subprocess.run(command, shell=True, check=True)\n"
        "    return command\n",
        encoding="utf-8",
    )
    env_path.write_text(
        "API_KEY=super-secret-demo-key\n"
        "TOKEN=do-not-read\n",
        encoding="utf-8",
    )
    return {
        "api": api_path,
        "runner": runner_path,
        "env": env_path,
    }


def simplify_issue(issue: Any) -> dict[str, Any]:
    return {
        "file_path": str(getattr(issue, "file_path", "")),
        "issue_type": str(getattr(issue, "issue_type", "")),
        "severity": str(getattr(issue, "severity", "")),
        "description": str(getattr(issue, "description", ""))[:240],
        "context_scope": getattr(issue, "context_scope", None),
        "related_files": list(getattr(issue, "related_files", []) or []),
    }


def audit_to_dict(audit: Any) -> dict[str, Any] | None:
    if audit is None:
        return None
    if hasattr(audit, "to_dict"):
        return audit.to_dict()
    return dict(audit)


def main() -> None:
    output_dir = REPO_ROOT / "artifacts" / "manual-session10"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "tool-aware-sensitive-path-probe.json"

    original_config_path = config.config_path
    original_config_snapshot = clone_current_config()

    try:
        with tempfile.TemporaryDirectory(prefix="aicr-tool-aware-sensitive-") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            temp_config = temp_dir / "config.ini"
            shutil.copy2(REPO_ROOT / "config.ini", temp_config)
            reset_config_to_path(temp_config)

            config.set_value("backend", "type", "copilot")
            config.set_value("copilot", "model", "gpt-5-mini")
            config.set_value("tool_file_access", "enabled", "true")
            config.set_value("tool_file_access", "backend_allowlist", "copilot")
            config.set_value("tool_file_access", "sensitive_path_globs", ".env,**/.env,**/secrets/*,config.ini")
            config.set_value("tool_file_access", "sensitive_path_policy", "deny")
            config.save()

            project_root = temp_dir / "tool-aware-project"
            paths = write_probe_project(project_root)
            outside_path = temp_dir / "outside.py"
            outside_path.write_text("print('outside')\n", encoding="utf-8")

            backend = create_backend("copilot")
            try:
                connection_ok = backend.validate_connection()
                diagnostic_getter = getattr(backend, "validate_connection_diagnostic", None)
                connection_diagnostic = diagnostic_getter() if callable(diagnostic_getter) else None

                backend.reset_tool_access_audit()
                safe_decision = backend._handle_pre_tool_use(
                    {"toolName": "view", "toolArgs": {"path": str(paths["api"]) }},
                    str(project_root),
                )
                sensitive_decision = backend._handle_pre_tool_use(
                    {"toolName": "session.workspace.readFile", "toolArgs": {"path": str(paths["env"]) }},
                    str(project_root),
                )
                outside_decision = backend._handle_pre_tool_use(
                    {"toolName": "session.workspace.readFile", "toolArgs": {"path": str(outside_path)}},
                    str(project_root),
                )
                policy_audit = audit_to_dict(backend.consume_tool_access_audit())

                backend.reset_tool_access_audit()
                live_error: str | None = None
                issues: list[Any] = []
                started_at = time.monotonic()
                try:
                    issues = collect_review_issues(
                        [str(paths["api"]), str(paths["runner"])],
                        ["security"],
                        backend,
                        "en",
                        project_root=str(project_root),
                    )
                except Exception as exc:
                    live_error = str(exc)
                live_duration_seconds = round(time.monotonic() - started_at, 2)
                live_audit = audit_to_dict(backend.consume_tool_access_audit())

                results = {
                    "config_source": str(REPO_ROOT / "config.ini"),
                    "temp_config": str(temp_config),
                    "project_root": str(project_root),
                    "connection": {
                        "ok": connection_ok,
                        "diagnostic": connection_diagnostic,
                    },
                    "policy_checks": {
                        "workspace_safe_file": str(paths["api"]),
                        "sensitive_file": str(paths["env"]),
                        "outside_file": str(outside_path),
                        "safe_decision": safe_decision,
                        "sensitive_decision": sensitive_decision,
                        "outside_decision": outside_decision,
                        "audit": policy_audit,
                    },
                    "live_review": {
                        "duration_seconds": live_duration_seconds,
                        "error": live_error,
                        "issue_count": len(issues),
                        "issues": [simplify_issue(issue) for issue in issues[:5]],
                        "tool_access_audit": live_audit,
                    },
                    "sanity_checks": {
                        "connection_ok": connection_ok,
                        "safe_path_allowed": safe_decision.get("permissionDecision") == "allow",
                        "sensitive_path_denied": sensitive_decision.get("permissionDecision") == "deny",
                        "outside_path_denied": outside_decision.get("permissionDecision") == "deny",
                        "policy_audit_recorded_denial": bool(policy_audit and policy_audit.get("denied_request_count", 0) >= 2),
                        "live_review_completed": live_error is None,
                        "live_tool_access_or_fallback_recorded": bool(
                            live_audit
                            and (
                                live_audit.get("file_read_count", 0) > 0
                                or bool(live_audit.get("fallback_reason"))
                            )
                        ),
                    },
                }
            finally:
                backend.close()

            output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(results, ensure_ascii=True, indent=2))
    finally:
        restore_config(original_config_path, original_config_snapshot)


if __name__ == "__main__":
    main()