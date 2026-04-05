"""Local HTTP API over the review execution service and registries."""

from __future__ import annotations

import io
import json
import threading
import time
from datetime import datetime
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, quote, unquote
from wsgiref.simple_server import WSGIServer, make_server

from .backends import create_backend
from .execution import (
    JobFailed,
    JobProgressUpdated,
    JobResultAvailable,
    JobStateChanged,
    ReviewExecutionRuntime,
    ReviewExecutionService,
    ReviewJob,
    ReviewJobEventRecord,
    ReviewRequest,
    get_shared_review_execution_runtime,
)
from .recommendations import ReviewRecommendationResult, recommend_review_types
from .registries import get_backend_registry, get_review_registry
from .review_presets import get_review_preset_group_label, get_review_preset_label, get_review_preset_summary, list_review_presets


JsonDict = dict[str, Any]
BackendFactory = Callable[[str], Any]


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _coerce_string_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if item is None:
                continue
            result.append(str(item))
        return result
    raise ValueError(f"Field '{field_name}' must be a list")


def _coerce_review_types(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("Field 'review_types' must be a list or comma-separated string")


def _coerce_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError("Boolean field contains an unsupported value")


def _serialize_request(request: ReviewRequest) -> JsonDict:
    return {
        "path": request.path,
        "scope": request.scope,
        "diff_file": request.diff_file,
        "commits": request.commits,
        "diff_source": request.diff_source,
        "review_types": list(request.review_types),
        "spec_content_present": request.spec_content is not None,
        "target_lang": request.target_lang,
        "backend_name": request.backend_name,
        "programmers": list(request.programmers),
        "reviewers": list(request.reviewers),
        "dry_run": request.dry_run,
    }


class LocalReviewHttpService:
    """HTTP-facing adapter over the shared review runtime."""

    def __init__(
        self,
        execution_service: ReviewExecutionService | None = None,
        *,
        backend_factory: BackendFactory = create_backend,
        max_concurrent_jobs: int = 1,
        runtime: ReviewExecutionRuntime | None = None,
    ) -> None:
        self.backend_factory = backend_factory
        self.runtime = runtime or (
            get_shared_review_execution_runtime(
                execution_service=execution_service,
                backend_factory=backend_factory,
                max_concurrent_jobs=max_concurrent_jobs,
            )
            if execution_service is None and backend_factory is create_backend and max_concurrent_jobs == 1
            else ReviewExecutionRuntime(
                execution_service=execution_service,
                backend_factory=backend_factory,
                max_concurrent_jobs=max_concurrent_jobs,
            )
        )

    def recommend_review_types(self, payload: JsonDict) -> JsonDict:
        target_lang = _coerce_optional_string(payload.get("target_lang") or payload.get("lang")) or "en"
        backend_name = _coerce_optional_string(payload.get("backend_name") or payload.get("backend")) or "bedrock"
        selected_files = _coerce_string_list(payload.get("selected_files"), field_name="selected_files")
        diff_filter_file = _coerce_optional_string(payload.get("diff_filter_file"))
        diff_filter_commits = _coerce_optional_string(payload.get("diff_filter_commits"))
        client = None
        try:
            client = self.backend_factory(backend_name)
            result = recommend_review_types(
                path=_coerce_optional_string(payload.get("path")),
                scope=_coerce_optional_string(payload.get("scope")) or "project",
                diff_file=_coerce_optional_string(payload.get("diff_file")),
                commits=_coerce_optional_string(payload.get("commits")),
                target_lang=target_lang,
                client=client,
                selected_files=selected_files,
                diff_filter_file=diff_filter_file,
                diff_filter_commits=diff_filter_commits,
            )
            return self._serialize_recommendation(result)
        finally:
            if client is not None and hasattr(client, "close"):
                try:
                    client.close()
                except Exception:
                    pass

    def submit_job(
        self,
        request: ReviewRequest,
        *,
        output_file: str | None = None,
        auto_finalize: bool = True,
    ) -> JsonDict:
        job = self.runtime.submit_job(
            request,
            output_file=output_file,
            auto_finalize=auto_finalize,
        )
        return self.get_job(job.job_id)

    def list_jobs(self) -> list[JsonDict]:
        return [self._serialize_job(job) for job in self.runtime.list_jobs()]

    def get_job(self, job_id: str) -> JsonDict:
        return self._serialize_job(self.runtime.get_job(job_id))

    def cancel_job(self, job_id: str) -> bool:
        return self.runtime.cancel_job(job_id)

    def wait_for_job(self, job_id: str, *, timeout: float = 5.0) -> JsonDict:
        self.runtime.wait_for_job(job_id, timeout=timeout)
        return self.get_job(job_id)

    def list_backends(self) -> list[JsonDict]:
        registry = get_backend_registry()
        return [
            {
                "key": descriptor.key,
                "display_name": descriptor.display_name,
                "aliases": list(descriptor.aliases),
                "capabilities": sorted(descriptor.capabilities),
            }
            for descriptor in registry.list_descriptors()
        ]

    def list_review_types(self) -> list[JsonDict]:
        registry = get_review_registry()
        return [
            {
                "key": definition.key,
                "label": definition.label,
                "group": definition.group,
                "summary_key": definition.summary_key,
                "selectable": definition.selectable,
                "parent_key": definition.parent_key,
                "aliases": list(definition.aliases),
                "requires_spec_content": definition.requires_spec_content,
            }
            for definition in registry.list_all()
        ]

    def list_review_presets(self) -> list[JsonDict]:
        return [
            {
                "key": definition.key,
                "label": get_review_preset_label(definition.key),
                "group": get_review_preset_group_label(definition.key),
                "summary": get_review_preset_summary(definition.key),
                "aliases": list(definition.aliases),
                "review_types": list(definition.review_types),
            }
            for definition in list_review_presets()
        ]

    def get_job_report(self, job_id: str) -> JsonDict:
        job = self.runtime.get_job(job_id)
        result = job.result
        if result is None or result.report is None:
            raise KeyError(job_id)
        return {
            "job_id": job.job_id,
            "status": result.status,
            "report_path": result.report_path,
            "report": result.report.to_dict(),
        }

    def list_job_artifacts(self, job_id: str) -> JsonDict:
        artifacts = self.runtime.list_job_artifacts(job_id)
        return {
            "job_id": job_id,
            "items": [
                {
                    "key": artifact.key,
                    "path": artifact.path,
                    "content_type": artifact.media_type,
                    "size_bytes": artifact.size_bytes,
                    "download_url": self._artifact_download_url(job_id, artifact.key),
                }
                for artifact in artifacts
            ],
        }

    def get_job_artifact(self, job_id: str, artifact_key: str) -> JsonDict:
        artifact, content, parsed_json = self.runtime.read_job_artifact(job_id, artifact_key)
        payload: JsonDict = {
            "job_id": job_id,
            "key": artifact.key,
            "path": artifact.path,
            "content_type": artifact.media_type,
            "size_bytes": artifact.size_bytes,
            "download_url": self._artifact_download_url(job_id, artifact.key),
            "content": content,
        }
        if parsed_json is not None:
            payload["json"] = parsed_json
        return payload

    def get_job_artifact_raw(self, job_id: str, artifact_key: str) -> tuple[JsonDict, bytes]:
        artifact, content = self.runtime.read_job_artifact_bytes(job_id, artifact_key)
        metadata = {
            "job_id": job_id,
            "key": artifact.key,
            "path": artifact.path,
            "content_type": artifact.media_type,
            "size_bytes": artifact.size_bytes,
            "download_url": self._artifact_download_url(job_id, artifact.key),
        }
        return metadata, content

    def read_events(
        self,
        *,
        job_id: str | None = None,
        after_sequence: int = 0,
        timeout: float = 0.0,
    ) -> list[ReviewJobEventRecord]:
        return self.runtime.read_events(job_id=job_id, after_sequence=after_sequence, timeout=timeout)

    def serialize_event_record(self, record: ReviewJobEventRecord) -> JsonDict:
        event = record.event
        payload: JsonDict = {
            "sequence": record.sequence,
            "job_id": event.job_id,
            "kind": event.kind,
            "timestamp": _isoformat(event.timestamp),
        }
        if isinstance(event, JobStateChanged):
            payload.update(
                {
                    "previous_state": event.previous_state,
                    "new_state": event.new_state,
                    "message": event.message,
                }
            )
        elif isinstance(event, JobProgressUpdated):
            payload.update(
                {
                    "current": event.current,
                    "total": event.total,
                    "message": event.message,
                }
            )
        elif isinstance(event, JobResultAvailable):
            payload["result"] = None if event.result is None else self._serialize_result(event.result)
        elif isinstance(event, JobFailed):
            payload.update(
                {
                    "error_message": event.error_message,
                    "exception_type": event.exception_type,
                }
            )
        return payload

    @staticmethod
    def _serialize_recommendation(result: ReviewRecommendationResult) -> JsonDict:
        return {
            "review_types": list(result.review_types),
            "recommended_review_types": list(result.review_types),
            "recommended_preset": result.recommended_preset,
            "project_signals": list(result.project_signals),
            "rationale": [
                {"review_type": item.review_type, "reason": item.reason}
                for item in result.rationale
            ],
            "source": result.source,
        }

    def shutdown(self, *, wait: bool = False, timeout: float = 1.0) -> None:
        self.runtime.shutdown(wait=wait, timeout=timeout)

    @staticmethod
    def _artifact_download_url(job_id: str, artifact_key: str) -> str:
        return f"/api/jobs/{quote(job_id, safe='')}/artifacts/{quote(artifact_key, safe='')}/raw"

    def _serialize_job(self, job: ReviewJob) -> JsonDict:
        queue_position = self.runtime.get_queue_position(job.job_id)
        state = job.state
        if queue_position is not None and state == "created":
            state = "queued"
        return {
            "job_id": job.job_id,
            "state": state,
            "lifecycle_state": job.state,
            "queue_position": queue_position,
            "cancel_requested": self.runtime.cancel_requested(job.job_id),
            "created_at": _isoformat(job.created_at),
            "started_at": _isoformat(job.started_at),
            "completed_at": _isoformat(job.completed_at),
            "error_message": job.error_message,
            "request": _serialize_request(job.request),
            "result": self._serialize_result(job.result),
        }

    @staticmethod
    def _serialize_result(result: Any) -> JsonDict | None:
        if result is None:
            return None
        result_payload = result.to_summary_dict()
        result_payload["report_path"] = result.report_path
        result_payload["has_report"] = result.report is not None
        return result_payload


class LocalHttpApiApplication:
    """Minimal WSGI application for the local review API."""

    def __init__(self, service: LocalReviewHttpService | None = None) -> None:
        self.service = service or LocalReviewHttpService()

    def __call__(self, environ: JsonDict, start_response: Callable[..., Any]) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = self._normalize_path(str(environ.get("PATH_INFO", "/")))
        query = self._parse_query_params(str(environ.get("QUERY_STRING", "")))
        segments = self._path_segments(path)
        try:
            if method == "GET" and path == "/api/backends":
                return self._json_response(start_response, 200, {"items": self.service.list_backends()})
            if method == "GET" and path == "/api/review-types":
                return self._json_response(start_response, 200, {"items": self.service.list_review_types()})
            if method == "GET" and path == "/api/review-presets":
                return self._json_response(start_response, 200, {"items": self.service.list_review_presets()})
            if method == "POST" and path == "/api/recommendations/review-types":
                payload = self._read_json_body(environ)
                return self._json_response(start_response, 200, self.service.recommend_review_types(payload))
            if method == "GET" and path == "/api/events":
                return self._event_stream_response(start_response, None, query)
            if method == "GET" and path == "/api/jobs":
                return self._json_response(start_response, 200, {"items": self.service.list_jobs()})
            if method == "POST" and path == "/api/jobs":
                payload = self._read_json_body(environ)
                request = self._parse_review_request(payload)
                output_file = _coerce_optional_string(payload.get("output_file"))
                auto_finalize = _coerce_bool(payload.get("auto_finalize"), default=True)
                job = self.service.submit_job(request, output_file=output_file, auto_finalize=auto_finalize)
                return self._json_response(start_response, 201, job)
            if len(segments) >= 3 and segments[:2] == ["api", "jobs"]:
                job_id = unquote(segments[2])
                if len(segments) == 3 and method == "GET":
                    return self._json_response(start_response, 200, self.service.get_job(job_id))
                if len(segments) == 4 and method == "POST" and segments[3] == "cancel":
                    if not self.service.cancel_job(job_id):
                        return self._json_response(start_response, 404, {"error": f"Unknown or non-cancellable job '{job_id}'"})
                    return self._json_response(start_response, 202, self.service.get_job(job_id))
                if len(segments) == 4 and method == "GET" and segments[3] == "report":
                    return self._json_response(start_response, 200, self.service.get_job_report(job_id))
                if len(segments) == 4 and method == "GET" and segments[3] == "artifacts":
                    return self._json_response(start_response, 200, self.service.list_job_artifacts(job_id))
                if len(segments) == 5 and method == "GET" and segments[3] == "artifacts":
                    artifact_key = unquote(segments[4])
                    return self._json_response(start_response, 200, self.service.get_job_artifact(job_id, artifact_key))
                if len(segments) == 6 and method == "GET" and segments[3] == "artifacts" and segments[5] == "raw":
                    artifact_key = unquote(segments[4])
                    metadata, content = self.service.get_job_artifact_raw(job_id, artifact_key)
                    filename = metadata["path"].replace("\\", "/").rsplit("/", 1)[-1]
                    return self._binary_response(
                        start_response,
                        200,
                        content,
                        content_type=str(metadata["content_type"]),
                        download_name=filename,
                    )
                if len(segments) == 4 and method == "GET" and segments[3] == "events":
                    return self._event_stream_response(start_response, job_id, query)
                if len(segments) == 4 and method == "POST" and segments[3] == "cancel":
                    return self._json_response(start_response, 404, {"error": f"Unknown or non-cancellable job '{job_id}'"})
            return self._json_response(start_response, 404, {"error": "Not found"})
        except KeyError as exc:
            return self._json_response(start_response, 404, {"error": f"Unknown resource '{exc.args[0]}'"})
        except ValueError as exc:
            return self._json_response(start_response, 400, {"error": str(exc)})
        except Exception as exc:
            return self._json_response(start_response, 500, {"error": str(exc)})

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not path:
            return "/"
        if path != "/" and path.endswith("/"):
            return path.rstrip("/")
        return path

    @staticmethod
    def _path_segments(path: str) -> list[str]:
        return [segment for segment in path.split("/") if segment]

    @staticmethod
    def _parse_query_params(query_string: str) -> dict[str, list[str]]:
        return parse_qs(query_string, keep_blank_values=False)

    @staticmethod
    def _read_json_body(environ: JsonDict) -> JsonDict:
        body_length = int(environ.get("CONTENT_LENGTH") or 0)
        body_stream = environ.get("wsgi.input")
        raw_payload = b""
        if body_stream is not None and body_length > 0:
            raw_payload = body_stream.read(body_length)
        if not raw_payload:
            return {}
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    @staticmethod
    def _parse_review_request(payload: JsonDict) -> ReviewRequest:
        target_lang = _coerce_optional_string(payload.get("target_lang") or payload.get("lang")) or "en"
        backend_name = _coerce_optional_string(payload.get("backend_name") or payload.get("backend")) or "bedrock"
        return ReviewRequest(
            path=_coerce_optional_string(payload.get("path")),
            scope=_coerce_optional_string(payload.get("scope")) or "project",
            diff_file=_coerce_optional_string(payload.get("diff_file")),
            commits=_coerce_optional_string(payload.get("commits")),
            review_types=_coerce_review_types(payload.get("review_types") or payload.get("type")),
            spec_content=_coerce_optional_string(payload.get("spec_content")),
            target_lang=target_lang,
            backend_name=backend_name,
            programmers=_coerce_string_list(payload.get("programmers"), field_name="programmers"),
            reviewers=_coerce_string_list(payload.get("reviewers"), field_name="reviewers"),
            dry_run=_coerce_bool(payload.get("dry_run"), default=False),
        )

    @staticmethod
    def _json_response(
        start_response: Callable[..., Any],
        status_code: int,
        payload: JsonDict,
    ) -> list[bytes]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status_text = {
            200: "200 OK",
            201: "201 Created",
            202: "202 Accepted",
            400: "400 Bad Request",
            404: "404 Not Found",
            405: "405 Method Not Allowed",
            500: "500 Internal Server Error",
        }.get(status_code, f"{status_code} OK")
        start_response(
            status_text,
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    @staticmethod
    def _binary_response(
        start_response: Callable[..., Any],
        status_code: int,
        payload: bytes,
        *,
        content_type: str,
        download_name: str | None = None,
    ) -> list[bytes]:
        status_text = {
            200: "200 OK",
            404: "404 Not Found",
            500: "500 Internal Server Error",
        }.get(status_code, f"{status_code} OK")
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(payload))),
        ]
        if download_name:
            headers.append(("Content-Disposition", f'attachment; filename="{download_name}"'))
        start_response(status_text, headers)
        return [payload]

    def _event_stream_response(
        self,
        start_response: Callable[..., Any],
        job_id: str | None,
        query: dict[str, list[str]],
    ) -> Iterable[bytes]:
        after_sequence = self._query_int(query, "after", default=0)
        timeout = self._query_float(query, "timeout", default=30.0)
        heartbeat = self._query_float(query, "heartbeat", default=5.0)
        if heartbeat < 0:
            raise ValueError("Heartbeat must be non-negative")

        start_response(
            "200 OK",
            [
                ("Content-Type", "text/event-stream; charset=utf-8"),
                ("Cache-Control", "no-cache"),
            ],
        )
        return self._build_sse_stream(
            job_id=job_id,
            after_sequence=after_sequence,
            timeout=timeout,
            heartbeat=heartbeat,
        )

    def _build_sse_stream(
        self,
        *,
        job_id: str | None,
        after_sequence: int,
        timeout: float,
        heartbeat: float,
    ) -> Iterable[bytes]:
        if timeout == 0:
            for record in self.service.read_events(
                job_id=job_id,
                after_sequence=after_sequence,
                timeout=0.0,
            ):
                yield self._format_sse_event(record)
            return

        deadline = time.monotonic() + timeout if timeout > 0 else None
        next_sequence = after_sequence

        while True:
            wait_timeout = 0.0
            if deadline is not None:
                remaining = max(0.0, deadline - time.monotonic())
                wait_timeout = remaining if heartbeat == 0 else min(remaining, heartbeat)
            elif heartbeat > 0:
                wait_timeout = heartbeat
            events = self.service.read_events(
                job_id=job_id,
                after_sequence=next_sequence,
                timeout=wait_timeout,
            )
            if events:
                for record in events:
                    next_sequence = record.sequence
                    yield self._format_sse_event(record)
                if deadline is not None and time.monotonic() >= deadline:
                    break
                continue
            if deadline is not None and time.monotonic() >= deadline:
                break
            if heartbeat > 0:
                yield b": keep-alive\n\n"
            else:
                break

    def _format_sse_event(self, record: ReviewJobEventRecord) -> bytes:
        payload = json.dumps(self.service.serialize_event_record(record), ensure_ascii=False)
        return (
            f"id: {record.sequence}\n"
            f"event: {record.event.kind}\n"
            f"data: {payload}\n\n"
        ).encode("utf-8")

    @staticmethod
    def _query_int(query: dict[str, list[str]], key: str, *, default: int) -> int:
        raw_value = (query.get(key) or [str(default)])[0]
        try:
            return int(raw_value)
        except ValueError as exc:
            raise ValueError(f"Query parameter '{key}' must be an integer") from exc

    @staticmethod
    def _query_float(query: dict[str, list[str]], key: str, *, default: float) -> float:
        raw_value = (query.get(key) or [str(default)])[0]
        try:
            return float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Query parameter '{key}' must be a number") from exc


def create_local_http_app(
    *,
    execution_service: ReviewExecutionService | None = None,
    backend_factory: BackendFactory = create_backend,
    max_concurrent_jobs: int = 1,
    runtime: ReviewExecutionRuntime | None = None,
) -> LocalHttpApiApplication:
    service = LocalReviewHttpService(
        execution_service=execution_service,
        backend_factory=backend_factory,
        max_concurrent_jobs=max_concurrent_jobs,
        runtime=runtime,
    )
    return LocalHttpApiApplication(service)


class LocalHttpServerHandle:
    """Owns a background WSGI server bound to the local review API."""

    def __init__(
        self,
        app: LocalHttpApiApplication,
        server: WSGIServer,
        thread: threading.Thread,
        *,
        host: str,
        port: int,
    ) -> None:
        self.app = app
        self.server = server
        self.thread = thread
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self._closed = False

    def close(self, *, wait: bool = True, timeout: float = 1.0) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.server.shutdown()
        except Exception:
            pass
        try:
            self.server.server_close()
        finally:
            self.app.service.shutdown(wait=False)
        if wait and self.thread.is_alive():
            self.thread.join(timeout=timeout)


def start_local_http_server(
    app: LocalHttpApiApplication,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    server_factory: Callable[..., WSGIServer] = make_server,
) -> LocalHttpServerHandle:
    server = server_factory(host, port, app)
    thread = threading.Thread(
        target=server.serve_forever,
        name=f"aicodereviewer-local-http-{port}",
        daemon=True,
    )
    thread.start()
    return LocalHttpServerHandle(app, server, thread, host=host, port=port)


def run_local_http_server(
    app: LocalHttpApiApplication,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    server_factory: Callable[..., WSGIServer] = make_server,
) -> None:
    server = server_factory(host, port, app)
    try:
        server.serve_forever()
    finally:
        app.service.shutdown(wait=False)
        server.server_close()
