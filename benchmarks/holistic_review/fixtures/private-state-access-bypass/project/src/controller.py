from src.subscription_registry import SubscriptionRegistry


def list_channels(registry: SubscriptionRegistry) -> list[str]:
    return [entry["channel"] for entry in registry._subscriptions]
