# Local HTTP Quick Reference

This page is the short contributor-oriented companion to the full [HTTP API Guide](http-api.md).

Use it when you are changing the local API implementation, GUI embedding, or test coverage and need the main seams quickly.

## What The Local API Is

The local HTTP service is a thin frontend over the same typed execution runtime used by the desktop GUI and non-interactive review flows.

Keep these invariants intact:

- the API must not grow a separate frontend-owned scheduler or review pipeline
- GUI-started and CLI-started API sessions should expose the same route surface
- when the desktop GUI embeds the API, submitted jobs share the same runtime and queue state visible in the Review tab

## How To Start It

CLI:

```bash
aicodereviewer serve-api --host 127.0.0.1 --port 8765
```

GUI:

- enable `local_http.enabled = true`
- set `local_http.port`
- restart the desktop app so the embedded loopback server starts during GUI startup

## Main Code Paths

Use these files as the primary source of truth:

- `src/aicodereviewer/http_api.py` — route handling, job submission, report and artifact guards, SSE streaming, server startup helpers
- `src/aicodereviewer/main.py` — `serve-api` CLI command wiring
- `src/aicodereviewer/gui/app_local_http.py` — embedded server lifecycle for the desktop app
- `src/aicodereviewer/gui/settings_mixin.py` — Settings-surface discovery text, status, and base-URL copy flow
- `src/aicodereviewer/execution/` — typed runtime, job, and event models the API exposes
- `tests/test_http_api.py` — response-contract and route-regression coverage

## Route Families

Stable route families in the current baseline:

- metadata: `/api/backends`, `/api/review-types`, `/api/review-presets`
- recommendations: `/api/recommendations/review-types`
- job control: `/api/jobs`, `/api/jobs/{job_id}`, `/api/jobs/{job_id}/cancel`
- reports and artifacts: `/api/jobs/{job_id}/report`, `/api/jobs/{job_id}/artifacts`, `/api/jobs/{job_id}/artifacts/{artifact_key}/raw`
- event streams: `/api/events`, `/api/jobs/{job_id}/events`

If you add, remove, or reshape a route:

- update [docs/http-api.md](http-api.md)
- update Settings-surface discovery text if the user-facing quick route list changes
- update or add route tests in `tests/test_http_api.py`

## Behavior Constraints Worth Preserving

- output-file requests are constrained to the requested review root or current workspace root
- artifact fetches re-check resolved paths against the same boundary
- sensitive local API actions emit audit log entries through the normal application logger
- SSE endpoints are backed by the runtime event stream rather than a separate polling cache

These are part of the shipped local-API contract, not optional implementation details.

## Common Contributor Checks

Run the local API regression file when changing routes or envelopes:

```bash
pytest tests/test_http_api.py -v
```

Useful adjacent checks:

```bash
pytest tests/test_gui_workflows.py -k local_http -v
```

If the GUI Settings panel or embedded startup behavior changes, also verify:

- the Settings status text still matches runtime reality
- the copied base URL matches the configured loopback port
- the embedded server still shares the desktop runtime instead of creating a second one

## When To Update Which Docs

Update [docs/http-api.md](http-api.md) when you change:

- request or response contracts
- route inventory
- example payloads
- curl examples or event-stream semantics

Update this page when you change:

- startup seams
- runtime-sharing guarantees
- contributor debugging workflow
- primary source-of-truth modules or tests

Update [docs/configuration.md](configuration.md) and [docs/gui.md](gui.md) when you change:

- `local_http.enabled` or `local_http.port`
- embedded desktop startup behavior
- Settings discovery text or local API visibility in the GUI

## Related Guides

- [HTTP API Guide](http-api.md)
- [Configuration Reference](configuration.md)
- [GUI Guide](gui.md)
- [Architecture](architecture.md)
- [Contributing](contributing.md)