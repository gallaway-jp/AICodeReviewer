class SyncSettings:
    def __init__(self) -> None:
        self.mode = "manual"

    def set_mode(self, raw_mode: str) -> None:
        normalized = raw_mode.strip().lower()
        if normalized not in {"manual", "scheduled"}:
            raise ValueError(f"unsupported sync mode: {raw_mode}")
        self.mode = normalized
