from src.settings_defaults import load_default_preferences


def initialize_sync(sync_scheduler) -> None:
    preferences = load_default_preferences()
    if not preferences["sync_enabled"]:
        sync_scheduler.start()