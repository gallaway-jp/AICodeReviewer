from __future__ import annotations

import configparser
import json
import shutil
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aicodereviewer.config import config
from aicodereviewer.execution import ReviewExecutionRuntime, ReviewExecutionService
from aicodereviewer.gui.app import App
from aicodereviewer.i18n import t
from aicodereviewer.models import ReviewIssue


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
    config.config.read(config_path, encoding="utf-8")


def sync_ui(app: App, cycles: int = 4, delay_s: float = 0.03) -> None:
    for _ in range(cycles):
        app.update_idletasks()
        app.update()
        if delay_s > 0:
            time.sleep(delay_s)


def close_app(app: App | None) -> None:
    if app is None:
        return
    try:
        app._app_helpers().lifecycle().prepare_for_destroy()
    except Exception:
        pass
    try:
        app.destroy()
    except Exception:
        pass


def option_values(widget: Any) -> list[str]:
    try:
        values = widget.cget("values")
    except Exception:
        values = getattr(widget, "_values", [])
    return [str(value) for value in values]


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
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            return int(response.status), json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload_body = json.loads(body)
        except json.JSONDecodeError:
            payload_body = {"raw": body}
        return int(exc.code), payload_body


def request_text(base_url: str, method: str, path: str) -> tuple[int, str]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        headers={"Accept": "text/event-stream"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def wait_until(predicate: Any, *, timeout_s: float, step_s: float = 0.05, pump: Any | None = None) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if callable(pump):
            pump()
        if predicate():
            if callable(pump):
                pump()
            return True
        time.sleep(step_s)
    return False


def queue_snapshot(app: App) -> dict[str, Any]:
    widgets = getattr(app._review_submission_queue, "_widgets", None)
    if widgets is None:
        return {
            "summary": "",
            "detail": "",
            "labels": [],
            "label_to_submission_id": {},
            "selected_submission_id": None,
        }
    return {
        "summary": str(widgets.summary_label.cget("text")),
        "detail": str(widgets.detail_label.cget("text")),
        "labels": option_values(widgets.menu),
        "label_to_submission_id": dict(app._selected_review_submission.label_to_submission_id),
        "selected_submission_id": app._selected_review_submission.submission_id,
    }


def build_project_fixture(project_root: Path) -> None:
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


def main() -> None:
    output_dir = REPO_ROOT / "artifacts" / "manual-session9"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "gui-local-http-shared-queue-probe.json"

    original_config_path = config.config_path
    original_config = clone_current_config()
    release_job = {"value": False}
    runtime: ReviewExecutionRuntime | None = None
    app: App | None = None

    with tempfile.TemporaryDirectory(prefix="aicr-gui-local-http-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        temp_config = temp_dir / "config.ini"
        source_config = REPO_ROOT / "config.ini"
        shutil.copy2(source_config, temp_config)

        reset_config_to_path(temp_config)
        local_http_port = pick_free_port()
        config.set_value("backend", "type", "local")
        config.set_value("gui", "language", "en")
        config.set_value("gui", "review_language", "en")
        config.set_value("gui", "detached_pages", "")
        config.set_value("local_http", "enabled", "true")
        config.set_value("local_http", "port", str(local_http_port))
        config.save()

        project_root = temp_dir / "probe-project"
        build_project_fixture(project_root)

        def _collect_issues(*_args: Any, cancel_check: Any = None, **_kwargs: Any) -> list[ReviewIssue]:
            while not release_job["value"]:
                if cancel_check is not None and cancel_check():
                    return []
                time.sleep(0.02)
            return [
                ReviewIssue(
                    file_path=str(project_root / "admin.py"),
                    issue_type="authorization",
                    severity="high",
                    description="Audit log endpoint exposes sensitive data without role verification.",
                    code_snippet="return {'viewer': user['id'], 'records': ['sensitive']}",
                    ai_feedback="Verify admin privileges before returning audit data.",
                    context_scope="local",
                )
            ]

        runtime = ReviewExecutionRuntime(
            execution_service=ReviewExecutionService(
                scan_fn=lambda *_args: [
                    {"path": "auth.py"},
                    {"path": "admin.py"},
                ],
                collect_issues_fn=_collect_issues,
            ),
            backend_factory=lambda _backend_name: object(),
            max_concurrent_jobs=1,
        )

        try:
            app = App(testing_mode=True, review_runtime=runtime)
            sync_ui(app, cycles=8)
            app._build_tab_if_needed(t("gui.tab.review"))
            app.tabs.set(t("gui.tab.review"))
            sync_ui(app, cycles=8)

            base_url = str(app.local_http_base_url_var.get())

            backends_status, backends_payload = request_json(base_url, "GET", "/api/backends")
            review_types_status, review_types_payload = request_json(base_url, "GET", "/api/review-types")
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

            output_file = project_root / "api-report.json"
            first_status, first_payload = request_json(
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
            second_status, second_payload = request_json(
                base_url,
                "POST",
                "/api/jobs",
                payload={
                    "path": str(project_root),
                    "scope": "project",
                    "review_types": ["security"],
                    "target_lang": "en",
                    "backend_name": "local",
                    "dry_run": True,
                },
            )

            first_job_id = str(first_payload.get("job_id", ""))
            second_job_id = str(second_payload.get("job_id", ""))

            queue_visible = wait_until(
                lambda: set(queue_snapshot(app)["label_to_submission_id"].values()) == {first_job_id, second_job_id},
                timeout_s=8.0,
                step_s=0.05,
                pump=lambda: sync_ui(app, cycles=2, delay_s=0.03),
            )
            live_queue_snapshot = queue_snapshot(app)

            jobs_status, jobs_payload = request_json(base_url, "GET", "/api/jobs")
            first_detail_status, first_detail_payload = request_json(base_url, "GET", f"/api/jobs/{first_job_id}")
            second_detail_status, second_detail_payload = request_json(base_url, "GET", f"/api/jobs/{second_job_id}")
            global_events_status, global_events_text = request_text(base_url, "GET", "/api/events?after=0&timeout=0")
            first_events_status, first_events_text = request_text(base_url, "GET", f"/api/jobs/{first_job_id}/events?after=0&timeout=0")

            release_job["value"] = True
            completed = wait_until(
                lambda: (
                    request_json(base_url, "GET", f"/api/jobs/{first_job_id}")[1].get("state") == "completed"
                    and request_json(base_url, "GET", f"/api/jobs/{second_job_id}")[1].get("state") == "completed"
                ),
                timeout_s=8.0,
                step_s=0.1,
                pump=lambda: sync_ui(app, cycles=2, delay_s=0.03),
            )

            completed_first_status, completed_first_payload = request_json(base_url, "GET", f"/api/jobs/{first_job_id}")
            completed_second_status, completed_second_payload = request_json(base_url, "GET", f"/api/jobs/{second_job_id}")
            report_status, report_payload = request_json(base_url, "GET", f"/api/jobs/{first_job_id}/report")
            artifacts_status, artifacts_payload = request_json(base_url, "GET", f"/api/jobs/{first_job_id}/artifacts")

            artifact_preview_status = None
            artifact_preview_payload: Any = None
            artifact_raw_status = None
            artifact_raw_excerpt = None
            artifact_key = None
            if artifacts_status == 200 and isinstance(artifacts_payload, dict):
                items = artifacts_payload.get("items") or []
                if items:
                    artifact_key = str(items[0].get("key") or "")
            if artifact_key:
                artifact_preview_status, artifact_preview_payload = request_json(
                    base_url,
                    "GET",
                    f"/api/jobs/{first_job_id}/artifacts/{artifact_key}",
                )
                artifact_raw_status, artifact_raw_text = request_text(
                    base_url,
                    "GET",
                    f"/api/jobs/{first_job_id}/artifacts/{artifact_key}/raw",
                )
                artifact_raw_excerpt = artifact_raw_text[:600]

            results = {
                "config_source": str(source_config),
                "temp_config": str(temp_config),
                "project_root": str(project_root),
                "embedded_local_http": {
                    "status_text": str(app.local_http_status_var.get()),
                    "base_url": base_url,
                    "docs_excerpt": app.local_http_docs_box.get("0.0", "end-1c")[:800],
                },
                "requests": {
                    "backends": {
                        "status": backends_status,
                        "keys": [item.get("key") for item in backends_payload.get("items", [])] if isinstance(backends_payload, dict) else [],
                    },
                    "review_types": {
                        "status": review_types_status,
                        "keys": [item.get("key") for item in review_types_payload.get("items", [])[:8]] if isinstance(review_types_payload, dict) else [],
                    },
                    "recommendations": {
                        "status": recommendations_status,
                        "payload": recommendations_payload,
                    },
                    "submit_first": {
                        "status": first_status,
                        "payload": first_payload,
                    },
                    "submit_second": {
                        "status": second_status,
                        "payload": second_payload,
                    },
                    "list_jobs": {
                        "status": jobs_status,
                        "payload": jobs_payload,
                    },
                    "first_job": {
                        "status": first_detail_status,
                        "payload": first_detail_payload,
                    },
                    "second_job": {
                        "status": second_detail_status,
                        "payload": second_detail_payload,
                    },
                    "global_events": {
                        "status": global_events_status,
                        "excerpt": global_events_text[:1200],
                    },
                    "first_job_events": {
                        "status": first_events_status,
                        "excerpt": first_events_text[:1200],
                    },
                },
                "queue_visibility": {
                    "visible_without_manual_sync": queue_visible,
                    "queue_snapshot": live_queue_snapshot,
                    "empty_text": t("gui.review.queue_empty"),
                },
                "completion": {
                    "both_jobs_completed": completed,
                    "first_job": {
                        "status": completed_first_status,
                        "payload": completed_first_payload,
                    },
                    "second_job": {
                        "status": completed_second_status,
                        "payload": completed_second_payload,
                    },
                    "report": {
                        "status": report_status,
                        "payload": report_payload,
                    },
                    "artifacts": {
                        "status": artifacts_status,
                        "payload": artifacts_payload,
                    },
                    "artifact_preview": {
                        "status": artifact_preview_status,
                        "payload": artifact_preview_payload,
                    },
                    "artifact_raw": {
                        "status": artifact_raw_status,
                        "excerpt": artifact_raw_excerpt,
                    },
                    "output_file_exists": output_file.is_file(),
                    "output_file": str(output_file),
                },
            }

            output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(results, ensure_ascii=True, indent=2))
        finally:
            release_job["value"] = True
            if app is not None:
                try:
                    app._stop_local_http_server()
                except Exception:
                    pass
            close_app(app)
            if runtime is not None:
                runtime.shutdown(wait=True, timeout=2.0)
            config.config = original_config
            config.config_path = original_config_path


if __name__ == "__main__":
    main()