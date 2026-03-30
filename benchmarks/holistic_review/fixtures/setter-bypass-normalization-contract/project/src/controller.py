from src.sync_settings import SyncSettings


def apply_settings(settings: SyncSettings, payload: dict) -> None:
    settings.mode = payload["mode"]
