from __future__ import annotations

import io
import json
import logging
import threading
import time
from wsgiref.util import setup_testing_defaults

from aicodereviewer.execution import ReviewExecutionService
from aicodereviewer.http_api import LocalHttpApiApplication, LocalReviewHttpService
from aicodereviewer.models import ReviewIssue
from aicodereviewer.recommendations import ReviewRecommendationResult, ReviewTypeRecommendation
from aicodereviewer.review_definitions import install_review_registry


def _call_app(
    app: LocalHttpApiApplication,
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    environ: dict[str, object] = {}
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = method
    environ["PATH_INFO"] = path

    body = b""
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    environ["CONTENT_LENGTH"] = str(len(body))
    environ["wsgi.input"] = io.BytesIO(body)

    response_status: list[str] = []
    response_body: list[bytes] = []

    def start_response(status: str, _headers: list[tuple[str, str]]) -> None:
        response_status.append(status)

    response_body.extend(app(environ, start_response))
    status_code = int(response_status[0].split(" ", 1)[0])
    parsed = json.loads(b"".join(response_body).decode("utf-8"))
    return status_code, parsed


def _call_app_raw(
    app: LocalHttpApiApplication,
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
) -> tuple[int, str]:
    environ: dict[str, object] = {}
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = method
    environ["PATH_INFO"] = path.split("?", 1)[0]
    if "?" in path:
        environ["QUERY_STRING"] = path.split("?", 1)[1]

    body = b""
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    environ["CONTENT_LENGTH"] = str(len(body))
    environ["wsgi.input"] = io.BytesIO(body)

    response_status: list[str] = []
    response_body: list[bytes] = []

    def start_response(status: str, _headers: list[tuple[str, str]]) -> None:
        response_status.append(status)

    response_body.extend(app(environ, start_response))
    status_code = int(response_status[0].split(" ", 1)[0])
    return status_code, b"".join(response_body).decode("utf-8")


def _call_app_raw_with_headers(
    app: LocalHttpApiApplication,
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    environ: dict[str, object] = {}
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = method
    environ["PATH_INFO"] = path.split("?", 1)[0]
    if "?" in path:
        environ["QUERY_STRING"] = path.split("?", 1)[1]

    body = b""
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    environ["CONTENT_LENGTH"] = str(len(body))
    environ["wsgi.input"] = io.BytesIO(body)

    response_status: list[str] = []
    response_headers: dict[str, str] = {}
    response_body: list[bytes] = []

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        response_status.append(status)
        response_headers.update(headers)

    response_body.extend(app(environ, start_response))
    status_code = int(response_status[0].split(" ", 1)[0])
    return status_code, response_headers, b"".join(response_body)


def test_list_backends_endpoint_returns_registry_descriptors() -> None:
    install_review_registry([])
    app = LocalHttpApiApplication(LocalReviewHttpService())

    status_code, payload = _call_app(app, "GET", "/api/backends")

    assert status_code == 200
    items = payload["items"]
    assert isinstance(items, list)
    assert any(item["key"] == "bedrock" for item in items)
    assert any(item["key"] == "local" for item in items)
    app.service.shutdown(wait=True, timeout=2.0)


def test_list_review_types_endpoint_returns_registry_definitions() -> None:
    install_review_registry([])
    app = LocalHttpApiApplication(LocalReviewHttpService())

    status_code, payload = _call_app(app, "GET", "/api/review-types")

    assert status_code == 200
    items = payload["items"]
    assert isinstance(items, list)
    assert any(item["key"] == "security" for item in items)
    assert any(item["key"] == "best_practices" for item in items)
    app.service.shutdown(wait=True, timeout=2.0)


def test_list_review_presets_endpoint_returns_registry_presets() -> None:
    install_review_registry([])
    app = LocalHttpApiApplication(LocalReviewHttpService())

    status_code, payload = _call_app(app, "GET", "/api/review-presets")

    assert status_code == 200
    items = payload["items"]
    assert isinstance(items, list)
    assert any(item["key"] == "runtime_safety" for item in items)
    assert any("security" in item["review_types"] for item in items)
    app.service.shutdown(wait=True, timeout=2.0)


def test_review_recommendation_endpoint_returns_shared_envelope() -> None:
    install_review_registry([])

    class _FakeBackend:
        def get_review_recommendations(self, _context: str, *, lang: str = "en") -> str:
            return json.dumps(
                {
                    "recommended_review_types": ["security", "error_handling", "data_validation"],
                    "recommended_preset": "runtime_safety",
                    "rationale": [
                        {"review_type": "security", "reason": "Service boundaries are in scope."},
                        {"review_type": "error_handling", "reason": "Workflow failure paths matter here."},
                        {"review_type": "data_validation", "reason": "The current target accepts external input."},
                    ],
                    "project_signals": ["Frameworks: fastapi", "Dependency manifests: pyproject.toml"],
                }
            )

        def close(self) -> None:
            return None

    service = LocalReviewHttpService(backend_factory=lambda _backend_name: _FakeBackend())
    app = LocalHttpApiApplication(service)

    status_code, payload = _call_app(
        app,
        "POST",
        "/api/recommendations/review-types",
        payload={
            "path": "./proj",
            "scope": "project",
            "backend_name": "local",
            "target_lang": "en",
        },
    )

    assert status_code == 200
    assert payload["review_types"] == ["security", "error_handling", "data_validation"]
    assert payload["recommended_review_types"] == ["security", "error_handling", "data_validation"]
    assert payload["recommended_preset"] == "runtime_safety"
    assert payload["source"] == "ai"
    assert payload["rationale"][0]["review_type"] == "security"
    service.shutdown(wait=True, timeout=2.0)


def test_review_recommendation_endpoint_accepts_selected_files_and_diff_filter_inputs(
    monkeypatch,
    tmp_path,
) -> None:
    install_review_registry([])
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        """
[project]
name = "sample"
dependencies = ["fastapi", "httpx"]

[tool.pytest.ini_options]
addopts = "-q"
""".strip(),
        encoding="utf-8",
    )

    captured_contexts: list[str] = []

    class _FakeBackend:
        def get_review_recommendations(self, recommendation_context: str, *, lang: str = "en") -> str:
            captured_contexts.append(recommendation_context)
            return json.dumps(
                {
                    "recommended_review_types": ["security", "error_handling", "dependency"],
                    "recommended_preset": None,
                    "rationale": [
                        {"review_type": "security", "reason": "Service boundaries are in scope."},
                        {"review_type": "error_handling", "reason": "Workflow failure paths matter here."},
                        {"review_type": "dependency", "reason": "Dependency drift is relevant for this target."},
                    ],
                    "project_signals": ["Frameworks: fastapi", "Selected files: src/api.py"],
                }
            )

        def close(self) -> None:
            return None

    def _fake_scan(path: str | None, scope: str, diff_file: str | None = None, commits: str | None = None):
        if scope == "project":
            return [project_root / "src" / "api.py", project_root / "src" / "worker.py"]
        return [
            {
                "filename": "src/api.py",
                "path": project_root / "src" / "api.py",
                "hunks": [object(), object()],
                "commit_messages": "Tighten review recommendation inputs",
            }
        ]

    class _FakeProjectContext:
        frameworks = ["fastapi", "pytest"]
        tools = ["ruff"]
        total_files = 12

    monkeypatch.setattr("aicodereviewer.recommendations.scan_project_with_scope", _fake_scan)
    monkeypatch.setattr(
        "aicodereviewer.recommendations.collect_project_context",
        lambda *_args, **_kwargs: _FakeProjectContext(),
    )

    service = LocalReviewHttpService(backend_factory=lambda _backend_name: _FakeBackend())
    app = LocalHttpApiApplication(service)

    status_code, payload = _call_app(
        app,
        "POST",
        "/api/recommendations/review-types",
        payload={
            "path": str(project_root),
            "scope": "project",
            "backend_name": "local",
            "target_lang": "en",
            "selected_files": ["src/api.py"],
            "diff_filter_file": "changes.diff",
        },
    )

    assert status_code == 200
    assert payload["recommended_review_types"] == ["security", "error_handling", "dependency"]
    assert captured_contexts
    recommendation_context = captured_contexts[0]
    assert "Selected files: src/api.py" in recommendation_context
    assert "Diff files: src/api.py" in recommendation_context
    assert "Hunks: 2 across 1 file(s)" in recommendation_context
    assert "Commit messages: Tighten review recommendation inputs" in recommendation_context
    assert "Dependencies: pyproject.toml defines dependency metadata" in recommendation_context
    service.shutdown(wait=True, timeout=2.0)


def test_create_list_and_get_job_endpoints_round_trip_dry_run_job() -> None:
    install_review_registry([])
    service = LocalReviewHttpService(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
        ),
        backend_factory=lambda _backend_name: object(),
    )
    app = LocalHttpApiApplication(service)

    create_status, create_payload = _call_app(
        app,
        "POST",
        "/api/jobs",
        payload={
            "path": "./proj",
            "scope": "project",
            "review_types": ["security"],
            "target_lang": "en",
            "backend_name": "local",
            "dry_run": True,
        },
    )

    assert create_status == 201
    job_id = str(create_payload["job_id"])

    settled = service.wait_for_job(job_id, timeout=2.0)
    assert settled["state"] == "completed"
    assert settled["result"] is not None
    assert settled["result"]["status"] == "dry_run"

    list_status, list_payload = _call_app(app, "GET", "/api/jobs")
    assert list_status == 200
    assert any(item["job_id"] == job_id for item in list_payload["items"])

    detail_status, detail_payload = _call_app(app, "GET", f"/api/jobs/{job_id}")
    assert detail_status == 200
    assert detail_payload["job_id"] == job_id
    assert detail_payload["result"]["status"] == "dry_run"
    service.shutdown(wait=True, timeout=2.0)


def test_cancel_job_endpoint_cancels_queued_job() -> None:
    install_review_registry([])
    release_event = threading.Event()
    started_event = threading.Event()

    def _slow_collect(*_args, cancel_check=None, **_kwargs):
        started_event.set()
        while not release_event.is_set():
            if cancel_check is not None and cancel_check():
                return []
            time.sleep(0.01)
        return []

    service = LocalReviewHttpService(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
            collect_issues_fn=_slow_collect,
        ),
        backend_factory=lambda _backend_name: object(),
        max_concurrent_jobs=1,
    )
    app = LocalHttpApiApplication(service)

    first_status, first_payload = _call_app(
        app,
        "POST",
        "/api/jobs",
        payload={
            "path": "./proj",
            "scope": "project",
            "review_types": ["security"],
            "target_lang": "en",
            "backend_name": "local",
            "dry_run": False,
        },
    )
    assert first_status == 201
    assert started_event.wait(timeout=1.0)

    second_status, second_payload = _call_app(
        app,
        "POST",
        "/api/jobs",
        payload={
            "path": "./proj",
            "scope": "project",
            "review_types": ["security"],
            "target_lang": "en",
            "backend_name": "local",
            "dry_run": True,
        },
    )
    assert second_status == 201
    queued_job_id = str(second_payload["job_id"])
    assert second_payload["state"] == "queued"

    cancel_status, cancel_payload = _call_app(app, "POST", f"/api/jobs/{queued_job_id}/cancel")
    assert cancel_status == 202
    assert cancel_payload["job_id"] == queued_job_id
    assert cancel_payload["state"] == "cancelled"
    assert cancel_payload["cancel_requested"] is True

    release_event.set()
    service.shutdown(wait=True, timeout=2.0)


def test_report_and_artifact_endpoints_expose_generated_report(tmp_path) -> None:
    install_review_registry([])
    project_root = tmp_path / "project"
    project_root.mkdir()
    service = LocalReviewHttpService(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
            collect_issues_fn=lambda *_args, **_kwargs: [
                ReviewIssue(
                    file_path="src/example.py",
                    issue_type="security",
                    severity="high",
                    description="Unsafe subprocess usage",
                    code_snippet="subprocess.run(cmd, shell=True)",
                    ai_feedback="Avoid shell=True for untrusted input.",
                )
            ],
        ),
        backend_factory=lambda _backend_name: object(),
    )
    app = LocalHttpApiApplication(service)

    create_status, create_payload = _call_app(
        app,
        "POST",
        "/api/jobs",
        payload={
            "path": str(project_root),
            "scope": "project",
            "review_types": ["security"],
            "target_lang": "en",
            "backend_name": "local",
            "dry_run": False,
            "output_file": str(project_root / "report.json"),
        },
    )

    assert create_status == 201
    job_id = str(create_payload["job_id"])
    settled = service.wait_for_job(job_id, timeout=2.0)
    assert settled["state"] == "completed"
    assert settled["result"] is not None
    assert settled["result"]["has_report"] is True

    report_status, report_payload = _call_app(app, "GET", f"/api/jobs/{job_id}/report")
    assert report_status == 200
    assert report_payload["job_id"] == job_id
    assert report_payload["report"]["project_path"] == str(project_root)

    artifacts_status, artifacts_payload = _call_app(app, "GET", f"/api/jobs/{job_id}/artifacts")
    assert artifacts_status == 200
    artifact_keys = {item["key"] for item in artifacts_payload["items"]}
    assert "report_primary" in artifact_keys
    assert artifacts_payload["items"]
    assert artifacts_payload["items"][0]["download_url"].endswith("/raw")

    artifact_status, artifact_payload = _call_app(app, "GET", f"/api/jobs/{job_id}/artifacts/report_primary")
    assert artifact_status == 200
    assert artifact_payload["job_id"] == job_id
    assert artifact_payload["content"]
    assert artifact_payload["download_url"] == f"/api/jobs/{job_id}/artifacts/report_primary/raw"

    raw_status, raw_headers, raw_body = _call_app_raw_with_headers(
        app,
        "GET",
        f"/api/jobs/{job_id}/artifacts/report_primary/raw",
    )
    assert raw_status == 200
    assert raw_headers["Content-Type"] in {"application/json", "text/markdown", "text/plain"}
    assert "attachment; filename=" in raw_headers["Content-Disposition"]
    assert raw_body
    service.shutdown(wait=True, timeout=2.0)


def test_job_submission_rejects_output_file_outside_review_root(tmp_path) -> None:
    install_review_registry([])
    project_root = tmp_path / "project"
    project_root.mkdir()
    escape_root = tmp_path.parent / "escape"
    escape_root.mkdir(exist_ok=True)

    service = LocalReviewHttpService(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
        ),
        backend_factory=lambda _backend_name: object(),
    )
    app = LocalHttpApiApplication(service)

    create_status, create_payload = _call_app(
        app,
        "POST",
        "/api/jobs",
        payload={
            "path": str(project_root),
            "scope": "project",
            "review_types": ["security"],
            "target_lang": "en",
            "backend_name": "local",
            "dry_run": True,
            "output_file": str(escape_root / "report.json"),
        },
    )

    assert create_status == 400
    assert create_payload["error"] == "Field 'output_file' must stay within the review path or current workspace"
    service.shutdown(wait=True, timeout=2.0)


def test_job_submission_emits_audit_log(caplog, tmp_path) -> None:
    install_review_registry([])
    project_root = tmp_path / "project"
    project_root.mkdir()
    service = LocalReviewHttpService(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
        ),
        backend_factory=lambda _backend_name: object(),
    )
    app = LocalHttpApiApplication(service)

    with caplog.at_level(logging.INFO, logger="aicodereviewer.audit"):
        status_code, payload = _call_app(
            app,
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

    assert status_code == 201
    assert any(
        "Local HTTP audit: action=job_submit" in record.getMessage()
        and f"job_id={payload['job_id']}" in record.getMessage()
        for record in caplog.records
    )
    service.shutdown(wait=True, timeout=2.0)


def test_artifact_fetch_emits_audit_log(caplog, tmp_path) -> None:
    install_review_registry([])
    project_root = tmp_path / "project"
    project_root.mkdir()
    service = LocalReviewHttpService(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
            collect_issues_fn=lambda *_args, **_kwargs: [
                ReviewIssue(
                    file_path="src/example.py",
                    issue_type="security",
                    severity="high",
                    description="Unsafe subprocess usage",
                    code_snippet="subprocess.run(cmd, shell=True)",
                    ai_feedback="Avoid shell=True for untrusted input.",
                )
            ],
        ),
        backend_factory=lambda _backend_name: object(),
    )
    app = LocalHttpApiApplication(service)

    create_status, create_payload = _call_app(
        app,
        "POST",
        "/api/jobs",
        payload={
            "path": str(project_root),
            "scope": "project",
            "review_types": ["security"],
            "target_lang": "en",
            "backend_name": "local",
            "dry_run": False,
            "output_file": str(project_root / "report.json"),
        },
    )
    assert create_status == 201
    job_id = str(create_payload["job_id"])
    service.wait_for_job(job_id, timeout=2.0)

    with caplog.at_level(logging.INFO, logger="aicodereviewer.audit"):
        raw_status, _, _ = _call_app_raw_with_headers(
            app,
            "GET",
            f"/api/jobs/{job_id}/artifacts/report_primary/raw",
        )

    assert raw_status == 200
    assert any(
        "Local HTTP audit: action=artifact_fetch" in record.getMessage()
        and f"job_id={job_id}" in record.getMessage()
        and "artifact_key=report_primary" in record.getMessage()
        and "raw=True" in record.getMessage()
        for record in caplog.records
    )
    service.shutdown(wait=True, timeout=2.0)


def test_job_event_stream_endpoint_returns_sse_payload() -> None:
    install_review_registry([])
    service = LocalReviewHttpService(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
        ),
        backend_factory=lambda _backend_name: object(),
    )
    app = LocalHttpApiApplication(service)

    create_status, create_payload = _call_app(
        app,
        "POST",
        "/api/jobs",
        payload={
            "path": "./proj",
            "scope": "project",
            "review_types": ["security"],
            "target_lang": "en",
            "backend_name": "local",
            "dry_run": True,
        },
    )

    assert create_status == 201
    job_id = str(create_payload["job_id"])
    service.wait_for_job(job_id, timeout=2.0)

    event_status, event_body = _call_app_raw(
        app,
        "GET",
        f"/api/jobs/{job_id}/events?after=0&timeout=0",
    )

    assert event_status == 200
    assert "event: job.state_changed" in event_body
    assert "event: job.result_available" in event_body
    assert f'"job_id": "{job_id}"' in event_body
    service.shutdown(wait=True, timeout=2.0)


def test_failed_job_endpoint_and_event_payload_include_error_diagnostic() -> None:
    install_review_registry([])
    service = LocalReviewHttpService(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
            collect_issues_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("connection timeout")),
        ),
        backend_factory=lambda _backend_name: object(),
    )
    app = LocalHttpApiApplication(service)

    create_status, create_payload = _call_app(
        app,
        "POST",
        "/api/jobs",
        payload={
            "path": "./proj",
            "scope": "project",
            "review_types": ["security"],
            "target_lang": "en",
            "backend_name": "local",
            "dry_run": False,
        },
    )

    assert create_status == 201
    job_id = str(create_payload["job_id"])

    settled = service.wait_for_job(job_id, timeout=2.0)
    assert settled["state"] == "failed"
    assert settled["error_diagnostic"] is not None
    assert settled["error_diagnostic"]["category"] == "timeout"
    assert settled["error_diagnostic"]["origin"] == "review"

    events = service.read_events(job_id=job_id, after_sequence=0, timeout=0.0)
    failed_event = next(
        service.serialize_event_record(record)
        for record in events
        if record.event.kind == "job.failed"
    )
    assert failed_event["error_diagnostic"] is not None
    assert failed_event["error_diagnostic"]["category"] == "timeout"
    assert failed_event["error_diagnostic"]["detail"] == "connection timeout"
    service.shutdown(wait=True, timeout=2.0)
