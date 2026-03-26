def validate_window(payload: dict) -> None:
    required_fields = ["start_hour", "end_hour"]
    for field in required_fields:
        if field not in payload:
            raise ValueError(f"Missing required field: {field}")

    int(payload["start_hour"])
    int(payload["end_hour"])