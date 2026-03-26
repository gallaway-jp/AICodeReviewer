from src.validation import validate_rollout


def create_rollout(payload: dict) -> dict:
    validate_rollout(payload)
    batch_size = int(payload["target_hosts"]) * int(payload["rollout_percent"]) // 100
    return {
        "status": "scheduled",
        "batch_size": batch_size,
    }