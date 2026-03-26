def run_sync(batch_id: str) -> dict[str, object]:
    try:
        push_sync_batch(batch_id)
        return {"status": "completed"}
    except TimeoutError:
        return {
            "status": "failed",
            "retryable": True,
            "reason": "timeout",
        }


def push_sync_batch(batch_id: str) -> None:
    raise TimeoutError(f"Remote sync timed out for {batch_id}")