from typing import Any


pending_events: list[dict[str, Any]] = []


def queue_event(account_id: str, payload: dict[str, Any]) -> dict[str, int | bool]:
    pending_events.append({"account_id": account_id, "payload": payload})
    return {"accepted": True, "buffered": len(pending_events)}


def flush_pending(send_batch) -> int:
    batch = pending_events[:100]
    if not batch:
        return 0

    send_batch(batch)
    del pending_events[: len(batch)]
    return len(batch)