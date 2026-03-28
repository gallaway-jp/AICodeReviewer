from src.retry_policy import build_retry_delay


def schedule_retry(job: dict) -> dict:
    delay_seconds = build_retry_delay(job["retry_count"], job["network_profile"])
    return {
        "status": "scheduled",
        "delay_seconds": delay_seconds,
    }