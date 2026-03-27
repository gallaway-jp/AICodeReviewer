from .lease_store import claim


def handle_job(job_id: str, worker_id: str) -> str:
    if not claim(job_id, worker_id):
        return "already_claimed"
    return f"processing {job_id} on {worker_id}"