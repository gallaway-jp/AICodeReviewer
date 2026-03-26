def validate_rollout(payload: dict) -> None:
    required_fields = ["target_hosts", "rollout_percent"]
    for field in required_fields:
        if field not in payload:
            raise ValueError(f"Missing required field: {field}")

    target_hosts = int(payload["target_hosts"])
    rollout_percent = int(payload["rollout_percent"])

    if target_hosts <= 0:
        raise ValueError("target_hosts must be positive")

    if rollout_percent < 0 or rollout_percent > 100:
        raise ValueError("rollout_percent must be between 0 and 100")