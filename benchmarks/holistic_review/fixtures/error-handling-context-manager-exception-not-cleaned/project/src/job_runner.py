from .lease_store import ExportLease, export_is_running


def run_export(export_id: str, send_archive) -> dict[str, str]:
    if export_is_running(export_id):
        return {"status": "blocked", "reason": "already-running"}

    with ExportLease(export_id):
        send_archive(export_id)
        return {"status": "completed"}