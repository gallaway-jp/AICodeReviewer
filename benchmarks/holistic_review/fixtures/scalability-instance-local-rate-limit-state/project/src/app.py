from time import time


WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 100
RATE_LIMIT_STATE: dict[str, list[float]] = {}


def is_rate_limited(account_id: str) -> bool:
    now = time()
    bucket = RATE_LIMIT_STATE.setdefault(account_id, [])
    bucket[:] = [timestamp for timestamp in bucket if now - timestamp < WINDOW_SECONDS]

    if len(bucket) >= MAX_REQUESTS_PER_WINDOW:
        return True

    bucket.append(now)
    return False


def handle_request(account_id: str) -> dict[str, object]:
    if is_rate_limited(account_id):
        return {"status": 429, "body": "rate limited"}
    return {"status": 200, "body": "ok"}