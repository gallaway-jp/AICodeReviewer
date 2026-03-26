from src.config import load_sync_token


def start_worker() -> str:
    token = load_sync_token()
    return f"worker started with {token[:4]}"