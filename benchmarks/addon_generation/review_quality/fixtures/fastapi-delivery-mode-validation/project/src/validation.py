def validate_workflow(payload: dict) -> None:
    required_fields = ["name", "delivery_mode"]
    for field in required_fields:
        if field not in payload:
            raise ValueError(f"Missing required field: {field}")

    str(payload["name"])
    str(payload["delivery_mode"])