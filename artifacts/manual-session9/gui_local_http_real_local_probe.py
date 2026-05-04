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
from aicodereviewer.gui.app import App
from aicodereviewer.i18n import t


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


def request_text(base_url: str, method: str, path: str) -> tuple[int, str]:
    request = urllib.request.Request(f"{base_url}{path}", headers={"Accept": "text/event-stream"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def wait_until(predicate: Any, *, timeout_s: float, step_s: float = 0.1, pump: Any | None = None) -> bool:
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
        return {"summary": "", "detail": "", "labels": [], "label_to_submission_id": {}, "selected_submission_id": None}
    return {
        "summary": str(widgets.summary_label.cget("text")),
        "detail": str(widgets.detail_label.cget("text")),
        "labels": option_values(widgets.menu),
        "label_to_submission_id": dict(app._selected_review_submission.label_to_submission_id),
        "selected_submission_id": app._selected_review_submission.submission_id,
    }


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


def main() -> None:
    output_dir = REPO_ROOT / "artifacts" / "manual-session9"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "gui-local-http-real-local-probe.json"

    original_config_path = config.config_path
    original_config = clone_current_config()
    app: App | None = None

    with tempfile.TemporaryDirectory(prefix="aicr-gui-real-local-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        temp_config = temp_dir / "config.ini"
        source_config = REPO_ROOT / "config.ini"
        shutil.copy2(source_config, temp_config)

        reset_config_to_path(temp_config)
        local_http_port = pick_free_port()
        config.set_value("backend", "type", "local")
        config.set_value("local_llm", "model", "qwen/qwen3.5-9b")
        config.set_value("gui", "language", "en")
        config.set_value("gui", "review_language", "en")
        config.set_value("gui", "detached_pages", "")
        config.set_value("local_http", "enabled", "true")
        config.set_value("local_http", "port", str(local_http_port))
        config.save()

        project_root = temp_dir / "probe-project"
        output_file = project_root / "api-report.json"
        write_probe_project(project_root)

        try:
            app = App(testing_mode=True)
            sync_ui(app, cycles=8)
            app._build_tab_if_needed(t("gui.tab.review"))
            app.tabs.set(t("gui.tab.review"))
            sync_ui(app, cycles=8)

            base_url = str(app.local_http_base_url_var.get())
            docs_excerpt = app.local_http_docs_box.get("0.0", "end-1c")[:1000]

            backends_status, backends_payload = request_json(base_url, "GET", "/api/backends")
            review_types_status, review_types_payload = request_json(base_url, "GET", "/api/review-types")
            presets_status, presets_payload = request_json(base_url, "GET", "/api/review-presets")
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

            queue_visible = wait_until(
                lambda: job_id in set(queue_snapshot(app)["label_to_submission_id"].values()),
                timeout_s=30.0,
                step_s=0.1,
                pump=lambda: sync_ui(app, cycles=2, delay_s=0.05),
            )
            active_queue_snapshot = queue_snapshot(app)

            job_visible_via_api = wait_until(
                lambda: request_json(base_url, "GET", f"/api/jobs/{job_id}")[1].get("job_id") == job_id,
                timeout_s=15.0,
                step_s=0.1,
            )
            global_events_status, global_events_text = request_text(base_url, "GET", "/api/events?after=0&timeout=0")
            job_events_status, job_events_text = request_text(base_url, "GET", f"/api/jobs/{job_id}/events?after=0&timeout=0")

            completed = wait_until(
                lambda: request_json(base_url, "GET", f"/api/jobs/{job_id}")[1].get("state") in {"completed", "failed", "cancelled"},
                timeout_s=240.0,
                step_s=1.0,
                pump=lambda: sync_ui(app, cycles=2, delay_s=0.05),
            )
            job_status, job_payload = request_json(base_url, "GET", f"/api/jobs/{job_id}")
            report_status, report_payload = request_json(base_url, "GET", f"/api/jobs/{job_id}/report")
            artifacts_status, artifacts_payload = request_json(base_url, "GET", f"/api/jobs/{job_id}/artifacts")

            artifact_key = None
            artifact_preview_status = None
            artifact_preview_payload: Any = None
            artifact_raw_status = None
            artifact_raw_excerpt = None
            if artifacts_status == 200 and isinstance(artifacts_payload, dict):
                items = artifacts_payload.get("items") or []
                if items:
                    artifact_key = str(items[0].get("key") or "")
            if artifact_key:
                artifact_preview_status, artifact_preview_payload = request_json(base_url, "GET", f"/api/jobs/{job_id}/artifacts/{artifact_key}")
                artifact_raw_status, artifact_raw_text = request_text(base_url, "GET", f"/api/jobs/{job_id}/artifacts/{artifact_key}/raw")
                artifact_raw_excerpt = artifact_raw_text[:600]

            results = {
                "config_source": str(source_config),
                "temp_config": str(temp_config),
                "project_root": str(project_root),
                "embedded_local_http": {
                    "status_text": str(app.local_http_status_var.get()),
                    "base_url": base_url,
                    "docs_excerpt": docs_excerpt,
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
                    "review_presets": {
                        "status": presets_status,
                        "count": len(presets_payload.get("items", [])) if isinstance(presets_payload, dict) else 0,
                    },
                    "recommendations": {
                        "status": recommendations_status,
                        "payload": recommendations_payload,
                    },
                    "submit_review": {
                        "status": submit_status,
                        "payload": submit_payload,
                    },
                    "global_events": {
                        "status": global_events_status,
                        "excerpt": global_events_text[:1200],
                    },
                    "job_events": {
                        "status": job_events_status,
                        "excerpt": job_events_text[:1200],
                    },
                },
                "queue_visibility": {
                    "job_visible_in_gui_queue": queue_visible,
                    "job_visible_via_api": job_visible_via_api,
                    "queue_snapshot": active_queue_snapshot,
                    "empty_text": t("gui.review.queue_empty"),
                },
                "completion": {
                    "job_reached_terminal_state": completed,
                    "job": {
                        "status": job_status,
                        "payload": job_payload,
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
            if app is not None:
                try:
                    app._stop_local_http_server()
                except Exception:
                    pass
            close_app(app)
            config.config = original_config
            config.config_path = original_config_path


if __name__ == "__main__":
    main()