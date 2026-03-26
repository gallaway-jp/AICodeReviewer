def validate_rollout(payload: dict) -> None:
    required_fields = ["target_hosts", "rollout_percent"]
    for field in required_fields:
        if field not in payload:
            raise ValueError(f"Missing required field: {field}")

    int(payload["target_hosts"])
    int(payload["rollout_percent"])