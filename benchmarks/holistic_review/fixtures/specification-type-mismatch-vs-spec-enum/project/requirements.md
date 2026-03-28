# Sync Job Response Contract

Clients read the response from `build_sync_job_response(job)`.

- The response must include `job_id` as a string.
- The response must include `sync_mode` as a string enum.
- `sync_mode` must be one of `manual`, `scheduled`, or `disabled`.
- Boolean flags must not be returned in place of the `sync_mode` enum because clients branch on the documented string values.