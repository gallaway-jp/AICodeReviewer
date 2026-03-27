LEASES: dict[str, str] = {}


def claim(job_id: str, worker_id: str) -> bool:
    if job_id in LEASES:
        return False
    LEASES[job_id] = worker_id
    return True