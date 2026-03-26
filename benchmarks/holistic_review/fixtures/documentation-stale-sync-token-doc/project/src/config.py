import os


def load_sync_token() -> str:
    token = os.getenv("SYNC_TOKEN")
    if not token:
        raise RuntimeError("SYNC_TOKEN is required")
    return token
