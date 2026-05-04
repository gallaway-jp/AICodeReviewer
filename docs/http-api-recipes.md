# HTTP API Recipes

Use this page when you want concrete local API workflows before diving into the full route reference.

Use [HTTP API Guide](http-api.md) when you need the complete route inventory, payload contract, or boundary rules.

## Recipe 1: Start The API And Submit A Dry Run

Start the server:

```bash
aicodereviewer serve-api --host 127.0.0.1 --port 8765
```

Submit a dry run:

```bash
curl -X POST http://127.0.0.1:8765/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": ".",
    "scope": "project",
    "review_types": ["security"],
    "target_lang": "en",
    "backend_name": "local",
    "dry_run": true
  }'
```

Use this first when you want to verify that the API accepts the request shape and target selection before spending backend time on a real review.

## Recipe 2: Submit A Real Review And Poll Job State

Submit the review:

```bash
curl -X POST http://127.0.0.1:8765/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": ".",
    "scope": "project",
    "review_types": ["security", "testing"],
    "target_lang": "en",
    "backend_name": "local",
    "programmers": ["Alice"],
    "reviewers": ["Bob"]
  }'
```

Take the returned `job_id` and poll the job record:

```bash
curl http://127.0.0.1:8765/api/jobs/<job_id>
```

When the review is complete, fetch the report:

```bash
curl http://127.0.0.1:8765/api/jobs/<job_id>/report
```

Use this pattern when your client only needs request-response polling and does not want to keep an SSE connection open.

## Recipe 3: Stream Events And Fetch Artifacts

Submit the review job first, then stream job-specific events:

```bash
curl -N "http://127.0.0.1:8765/api/jobs/<job_id>/events"
```

Or stream the shared event feed:

```bash
curl -N "http://127.0.0.1:8765/api/events"
```

Useful query parameters:

- `after=<sequence>` to resume after a known event
- `timeout=<seconds>` to bound the connection
- `heartbeat=<seconds>` to keep the stream active through idle periods

After the run completes, list artifacts:

```bash
curl http://127.0.0.1:8765/api/jobs/<job_id>/artifacts
```

Then fetch a specific artifact payload:

```bash
curl http://127.0.0.1:8765/api/jobs/<job_id>/artifacts/<artifact_key>/raw
```

Use this pattern when you want progress updates during the run and then need the generated report or supporting artifact outputs afterward.

## Recipe 4: Ask For Review-Type Recommendations First

Use the recommendation endpoint when your client wants guidance before creating a job:

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

This endpoint does not create a job. It only returns the suggested review bundle and rationale so your client can decide what to submit next.

## Common Rules To Keep In Mind

- output-file paths are constrained to the review root or workspace root
- artifact fetches are re-checked against those same boundaries
- the API binds to loopback by default
- the GUI-started embedded API and the CLI-started `serve-api` command expose the same route surface

## Related Guides

- [HTTP API Guide](http-api.md)
- [Local HTTP Quick Reference](local-http-quick-reference.md)
- [Configuration Reference](configuration.md)
- [User Manual](user-manual.md#local-http-workflow)