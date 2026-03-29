from src.service import build_sync_plan


def queue_sync(account_id: int) -> dict:
    status, next_run_at = build_sync_plan(account_id)
    return {
        "status": status,
        "next_run_at": next_run_at,
    }