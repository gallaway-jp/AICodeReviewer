# Local HTTP Workflow

Use this guide when you want to drive AICodeReviewer from another local tool or script over HTTP.

## Before You Start

- AICodeReviewer installed and a backend configured (Bedrock, Kiro, Copilot, or Local LLM)
- Python 3.11+ (if running from source)
- `curl` or any HTTP client

## Expected Result

By the end of this guide you will:

- start the local HTTP API server
- submit a review job via HTTP
- poll the job state and fetch the final report
- understand how to stream events and retrieve artifacts

## Step 1: Start the Local API Server

From the project root:

```bash
aicodereviewer serve-api --host 127.0.0.1 --port 8765
```

The API is now available at `http://127.0.0.1:8765`.

## Step 2: Submit a Review Job

Use a dry run first to validate the request shape:

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

If the dry run looks correct, submit a real review:

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

The response includes a `job_id`. Save it for the next steps.

## Step 3: Poll Job State

Poll the job record until `status` indicates completion:

```bash
curl http://127.0.0.1:8765/api/jobs/<job_id>
```

When `status` is `completed`, fetch the report:

```bash
curl http://127.0.0.1:8765/api/jobs/<job_id>/report
```

## Step 4: Stream Events (Optional)

For real-time updates, stream job-specific events:

```bash
curl -N "http://127.0.0.1:8765/api/jobs/<job_id>/events"
```

Or stream the shared event feed:

```bash
curl -N "http://127.0.0.1:8765/api/events"
```

Useful query parameters:

- `after=<sequence>` — resume after a known event
- `timeout=<seconds>` — bound the connection
- `heartbeat=<seconds>` — keep the stream alive during idle periods

## Step 5: Fetch Artifacts

List available artifacts:

```bash
curl http://127.0.0.1:8765/api/jobs/<job_id>/artifacts
```

Download a specific artifact:

```bash
curl http://127.0.0.1:8765/api/jobs/<job_id>/artifacts/<artifact_key>/raw
```

## Common Patterns

- **Automation**: use `dry_run` to validate, then submit the real job; poll or stream to detect completion.
- **CI integration**: run the review as a job step, fail the build on critical findings, and upload the report as an artifact.
- **Tooling**: wrap the API calls in your preferred language; the JSON envelope is stable and includes `job_id`, `status`, and `report` when ready.

## Troubleshooting

- If the server does not start, check that the port is free and the backend is configured.
- If the job fails immediately, inspect the `error` field in the job record and the server logs.
- Output-file and artifact paths are constrained to the review root or workspace root for safety.

## Related Guides

- [HTTP API Recipes](../../http-api-recipes.md)
- [HTTP API Guide](../../http-api.md)
- [Local HTTP Quick Reference](../../local-http-quick-reference.md)
- [User Manual](../../user-manual.md)