# HTTP API Guide

The local HTTP API exposes the shared review runtime used by the desktop GUI and the non-interactive CLI flows.

If you are changing implementation seams, embedded startup behavior, or route tests, start with [Local HTTP Quick Reference](local-http-quick-reference.md) and use this page as the route-and-payload reference.

Use it when you want to:
- drive review jobs from another tool or script
- query supported backends, review types, and presets
- request review-type recommendations before running a full review
- stream job events over Server-Sent Events (SSE)

## Starting The API

Start the API explicitly from the CLI:

```bash
aicodereviewer serve-api --host 127.0.0.1 --port 8765
```

You can also enable the embedded local API from the desktop Settings panel.

When the desktop setting is enabled, GUI startup automatically launches the loopback server and keeps it attached to the same shared execution runtime and queue state that power the desktop review workflow.

Default base URL:

```text
http://127.0.0.1:8765
```

## Common Routes

- `GET /api/backends`
- `GET /api/review-types`
- `GET /api/review-presets`
- `POST /api/recommendations/review-types`
- `GET /api/jobs`
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `GET /api/jobs/{job_id}/report`
- `GET /api/jobs/{job_id}/artifacts`
- `GET /api/jobs/{job_id}/artifacts/{artifact_key}/raw`
- `GET /api/events`
- `GET /api/jobs/{job_id}/events`

## Review Recommendation Endpoint

`POST /api/recommendations/review-types` returns a focused review-type bundle before you enqueue a full review.

The request accepts the same targeting inputs already used by the GUI and CLI recommendation flows, including:
- `path`
- `scope`
- `diff_file`
- `commits`
- `backend_name` or `backend`
- `target_lang` or `lang`
- `selected_files`
- `diff_filter_file`
- `diff_filter_commits`

Example request body:

```json
{
  "path": ".",
  "scope": "project",
  "backend_name": "local",
  "target_lang": "en",
  "selected_files": ["src/app.py"],
  "diff_filter_file": "changes.diff"
}
```

Example `curl` command:

```bash
curl -X POST http://127.0.0.1:8765/api/recommendations/review-types \
  -H "Content-Type: application/json" \
  -d '{
    "path": ".",
    "scope": "project",
    "backend_name": "local",
    "target_lang": "en",
    "selected_files": ["src/app.py"],
    "diff_filter_file": "changes.diff"
  }'
```

Example response shape:

```json
{
  "review_types": ["security", "error_handling", "dependency"],
  "recommended_review_types": ["security", "error_handling", "dependency"],
  "recommended_preset": null,
  "project_signals": [
    "Frameworks: fastapi",
    "Selected files: src/app.py"
  ],
  "rationale": [
    {
      "review_type": "security",
      "reason": "Service boundaries are in scope."
    },
    {
      "review_type": "error_handling",
      "reason": "Workflow failure paths matter here."
    },
    {
      "review_type": "dependency",
      "reason": "Dependency drift is relevant for this target."
    }
  ],
  "source": "ai"
}
```

## Job Submission

Use `POST /api/jobs` to enqueue a dry run or full review.

Minimal dry-run example:

```json
{
  "path": ".",
  "scope": "project",
  "review_types": ["security"],
  "target_lang": "en",
  "backend_name": "local",
  "dry_run": true
}
```

The response includes the `job_id`, queue state, request metadata, and result summary when available.

When you provide `output_file`, the resolved path must stay within either:
- the requested review path
- the current workspace directory

Requests that try to write reports outside those roots are rejected with HTTP `400`. This keeps the local API from being used as a generic arbitrary-file write surface.

Artifact listing and raw artifact download also re-check resolved artifact paths against the same review/workspace boundary before returning them.

## Event Streaming

Use SSE endpoints to observe queue and review progress:

- `GET /api/events`
- `GET /api/jobs/{job_id}/events`

Useful query parameters:
- `after=<sequence>`
- `timeout=<seconds>`
- `heartbeat=<seconds>`

When `timeout=0`, the API returns the current event backlog immediately and closes the stream.

## Notes

- The local API binds to loopback by default.
- The embedded GUI-started API and the CLI-started `serve-api` command expose the same route surface.
- When the API is started from the desktop app, submitted jobs participate in the same scheduler-backed runtime and queue state visible in the GUI.
- The recommendation endpoint does not create a job; it only returns a suggested review bundle.
- Security-sensitive local API actions such as job submission, report fetches, and artifact access now emit audit log entries through the normal application logger.
- The response contracts are verified by the HTTP API tests in [tests/test_http_api.py](../tests/test_http_api.py).

## Related Guides

- [Local HTTP Quick Reference](local-http-quick-reference.md)
- [Configuration Reference](configuration.md)
- [GUI Guide](gui.md)
- [Architecture](architecture.md)