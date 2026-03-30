class SubscriptionRegistry:
    def __init__(self) -> None:
        self._subscriptions = [
            {"channel": "email", "active": True},
            {"channel": "sms", "active": False},
        ]

    def iter_active_channels(self) -> list[str]:
        return [entry["channel"] for entry in self._subscriptions if entry["active"]]
