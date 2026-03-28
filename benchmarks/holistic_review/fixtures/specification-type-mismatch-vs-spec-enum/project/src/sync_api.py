def build_sync_job_response(job) -> dict[str, object]:
    return {
        "job_id": str(job.job_id),
        "sync_mode": bool(job.schedule_enabled),
    }