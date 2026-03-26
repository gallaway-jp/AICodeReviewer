from .sync_worker import run_sync


def sync_now(batch_id: str) -> dict[str, object]:
    result = run_sync(batch_id)
    if result["status"] == "failed":
        disable_background_sync()
        return {"message": "Background sync disabled"}
    return {"message": "Sync finished"}


def disable_background_sync() -> None:
    return None