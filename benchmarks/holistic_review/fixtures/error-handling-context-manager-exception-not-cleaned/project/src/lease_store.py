ACTIVE_EXPORTS: set[str] = set()


class ExportLease:
    def __init__(self, export_id: str):
        self.export_id = export_id

    def __enter__(self):
        ACTIVE_EXPORTS.add(self.export_id)
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            ACTIVE_EXPORTS.discard(self.export_id)
        return False


def export_is_running(export_id: str) -> bool:
    return export_id in ACTIVE_EXPORTS