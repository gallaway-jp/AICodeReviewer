from __future__ import annotations

import configparser
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXE = Path(sys.executable)


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read().decode("utf-8")
            return int(response.status), json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload_body = json.loads(body)
        except json.JSONDecodeError:
            payload_body = {"raw": body}
        return int(exc.code), payload_body
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc.reason)}


def request_text(base_url: str, method: str, path: str, accept: str = "text/plain") -> tuple[int, str]:
    request = urllib.request.Request(f"{base_url}{path}", headers={"Accept": accept}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, str(exc.reason)


def wait_until(predicate: Any, *, timeout_s: float, step_s: float = 0.2) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step_s)
    return False


def write_probe_project(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "auth.py").write_text(
        "def require_login(user_id):\n"
        "    if not user_id:\n"
        "        raise PermissionError('missing user')\n"
        "    return {'id': user_id, 'role': 'user'}\n",
        encoding="utf-8",
    )
    (project_root / "admin.py").write_text(
        "from auth import require_login\n\n"
        "def get_audit_log(user_id):\n"
        "    user = require_login(user_id)\n"
        "    return {'viewer': user['id'], 'records': ['sensitive']}\n",
        encoding="utf-8",
    )


def configure_temp_config(temp_config: Path, *, audit_log_path: Path) -> configparser.ConfigParser:
    source_config = REPO_ROOT / "config.ini"
    shutil.copy2(source_config, temp_config)
    parser = configparser.ConfigParser()
    parser.read(temp_config, encoding="utf-8")

    if not parser.has_section("backend"):
        parser.add_section("backend")
    parser.set("backend", "type", "local")

    if not parser.has_section("gui"):
        parser.add_section("gui")
    parser.set("gui", "language", "en")
    parser.set("gui", "review_language", "en")

    if not parser.has_section("logging"):
        parser.add_section("logging")
    parser.set("logging", "enable_api_audit_file_logging", "true")
    parser.set("logging", "api_audit_log_file", str(audit_log_path))
    parser.set("logging", "api_audit_log_max_bytes", "1048576")
    parser.set("logging", "api_audit_log_backup_count", "1")

    with temp_config.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    return parser


def build_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    repo_src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = repo_src if not current_pythonpath else os.pathsep.join([repo_src, current_pythonpath])
    env.setdefault("PYTHONUTF8", "1")
    return env


def launch_server(temp_dir: Path, *, port: int) -> tuple[subprocess.Popen[str], Path, Path]:
    stdout_path = temp_dir / "serve-api-stdout.log"
    stderr_path = temp_dir / "serve-api-stderr.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            str(PYTHON_EXE),
            "-m",
            "aicodereviewer",
            "serve-api",
            "--backend",
            "local",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=temp_dir,
        env=build_subprocess_env(),
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
    )
    stdout_handle.close()
    stderr_handle.close()
    return process, stdout_path, stderr_path


def stop_server(process: subprocess.Popen[str]) -> dict[str, Any]:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return {"returncode": process.returncode}


def main() -> None:
    output_dir = REPO_ROOT / "artifacts" / "manual-session9"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "cli-local-http-real-local-probe.json"

    with tempfile.TemporaryDirectory(prefix="aicr-cli-http-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        temp_config = temp_dir / "config.ini"
        audit_log_path = temp_dir / "aicodereviewer-audit.log"
        config_snapshot = configure_temp_config(temp_config, audit_log_path=audit_log_path)

        project_root = temp_dir / "probe-project"
        output_file = project_root / "cli-api-report.json"
        write_probe_project(project_root)

        port = pick_free_port()
        base_url = f"http://127.0.0.1:{port}"
        process, stdout_path, stderr_path = launch_server(temp_dir, port=port)
        shutdown_result: dict[str, Any] | None = None
        results: dict[str, Any] = {
            "config_source": str(REPO_ROOT / "config.ini"),
            "temp_config": str(temp_config),
            "base_url": base_url,
            "project_root": str(project_root),
            "report_output_file": str(output_file),
        }

        try:
            server_ready = wait_until(
                lambda: request_json(base_url, "GET", "/api/backends")[0] == 200,
                timeout_s=20.0,
                step_s=0.25,
            )

            backends_status, backends_payload = request_json(base_url, "GET", "/api/backends")
            review_types_status, review_types_payload = request_json(base_url, "GET", "/api/review-types")
            review_presets_status, review_presets_payload = request_json(base_url, "GET", "/api/review-presets")
            recommendations_status, recommendations_payload = request_json(
                base_url,
                "POST",
                "/api/recommendations/review-types",
                payload={
                    "path": str(project_root),
                    "scope": "project",
                    "backend_name": "local",
                    "target_lang": "en",
                },
            )

            submit_status, submit_payload = request_json(
                base_url,
                "POST",
                "/api/jobs",
                payload={
                    "path": str(project_root),
                    "scope": "project",
                    "review_types": ["security"],
                    "target_lang": "en",
                    "backend_name": "local",
                    "dry_run": False,
                    "output_file": str(output_file),
                },
            )
            job_id = str(submit_payload.get("job_id", ""))

            jobs_status, jobs_payload = request_json(base_url, "GET", "/api/jobs")
            global_events_status, global_events_text = request_text(
                base_url,
                "GET",
                "/api/events?after=0&timeout=0",
                accept="text/event-stream",
            )

            completed = wait_until(
                lambda: request_json(base_url, "GET", f"/api/jobs/{job_id}")[1].get("state") in {"completed", "failed", "cancelled"},
                timeout_s=240.0,
                step_s=1.0,
            )

            job_status, job_payload = request_json(base_url, "GET", f"/api/jobs/{job_id}")
            job_events_status, job_events_text = request_text(
                base_url,
                "GET",
                f"/api/jobs/{job_id}/events?after=0&timeout=0",
                accept="text/event-stream",
            )
            report_status, report_payload = request_json(base_url, "GET", f"/api/jobs/{job_id}/report")
            artifacts_status, artifacts_payload = request_json(base_url, "GET", f"/api/jobs/{job_id}/artifacts")

            artifact_key = None
            artifact_preview_status = None
            artifact_preview_payload: Any = None
            artifact_raw_status = None
            artifact_raw_excerpt = None
            items = artifacts_payload.get("items") if isinstance(artifacts_payload, dict) else None
            if items:
                artifact_key = str(items[0].get("key") or "")
            if artifact_key:
                artifact_preview_status, artifact_preview_payload = request_json(
                    base_url,
                    "GET",
                    f"/api/jobs/{job_id}/artifacts/{artifact_key}",
                )
                artifact_raw_status, artifact_raw_text = request_text(
                    base_url,
                    "GET",
                    f"/api/jobs/{job_id}/artifacts/{artifact_key}/raw",
                    accept="application/octet-stream",
                )
                artifact_raw_excerpt = artifact_raw_text[:600]

            audit_log_text = audit_log_path.read_text(encoding="utf-8", errors="replace") if audit_log_path.exists() else ""
            stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
            stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""

            results.update({
                "server_command": [
                    str(PYTHON_EXE),
                    "-m",
                    "aicodereviewer",
                    "serve-api",
                    "--backend",
                    "local",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                "server_ready": server_ready,
                "metadata": {
                    "backends_status": backends_status,
                    "backends_payload": backends_payload,
                    "review_types_status": review_types_status,
                    "review_types_payload": review_types_payload,
                    "review_presets_status": review_presets_status,
                    "review_presets_payload": review_presets_payload,
                    "recommendations_status": recommendations_status,
                    "recommendations_payload": recommendations_payload,
                },
                "job_submission": {
                    "submit_status": submit_status,
                    "submit_payload": submit_payload,
                    "jobs_status": jobs_status,
                    "jobs_payload": jobs_payload,
                    "job_visible_in_list": any(
                        str(item.get("job_id")) == job_id for item in (jobs_payload.get("items") or [])
                    ) if isinstance(jobs_payload, dict) else False,
                },
                "events": {
                    "global_events_status": global_events_status,
                    "global_events_excerpt": global_events_text[:1200],
                    "job_events_status": job_events_status,
                    "job_events_excerpt": job_events_text[:1200],
                },
                "job_result": {
                    "job_id": job_id,
                    "completed": completed,
                    "job_status": job_status,
                    "job_payload": job_payload,
                    "report_status": report_status,
                    "report_payload": report_payload,
                    "artifacts_status": artifacts_status,
                    "artifacts_payload": artifacts_payload,
                    "artifact_key": artifact_key,
                    "artifact_preview_status": artifact_preview_status,
                    "artifact_preview_payload": artifact_preview_payload,
                    "artifact_raw_status": artifact_raw_status,
                    "artifact_raw_excerpt": artifact_raw_excerpt,
                },
                "audit_log": {
                    "path": str(audit_log_path),
                    "excerpt": audit_log_text[-2000:],
                    "contains_job_submit": "action=job_submit" in audit_log_text,
                    "contains_report_fetch": "action=report_fetch" in audit_log_text,
                    "contains_artifact_list": "action=artifact_list" in audit_log_text,
                    "contains_artifact_fetch": "action=artifact_fetch" in audit_log_text,
                },
                "server_logs": {
                    "stdout_excerpt": stdout_text[-2000:],
                    "stderr_excerpt": stderr_text[-2000:],
                },
                "config_effective": {
                    "backend_type": config_snapshot.get("backend", "type", fallback=""),
                    "local_api_url": config_snapshot.get("local_llm", "api_url", fallback=""),
                    "local_model": config_snapshot.get("local_llm", "model", fallback=""),
                    "local_api_type": config_snapshot.get("local_llm", "api_type", fallback=""),
                },
                "sanity_checks": {
                    "server_ready": server_ready,
                    "metadata_routes_ok": all(status == 200 for status in [backends_status, review_types_status, review_presets_status]),
                    "recommendations_ok": recommendations_status == 200,
                    "job_created": submit_status == 201 and bool(job_id),
                    "job_visible_in_list": any(
                        str(item.get("job_id")) == job_id for item in (jobs_payload.get("items") or [])
                    ) if isinstance(jobs_payload, dict) else False,
                    "job_completed": completed and job_status == 200 and job_payload.get("state") == "completed",
                    "report_available": report_status == 200,
                    "artifacts_available": artifacts_status == 200 and bool(items),
                    "artifact_preview_available": artifact_preview_status == 200 if artifact_preview_status is not None else False,
                    "artifact_raw_available": artifact_raw_status == 200 if artifact_raw_status is not None else False,
                    "audit_log_captured": all(
                        marker in audit_log_text
                        for marker in ["action=job_submit", "action=report_fetch", "action=artifact_list", "action=artifact_fetch"]
                    ),
                },
            })
        finally:
            shutdown_result = stop_server(process)

        results["shutdown"] = shutdown_result
        output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()