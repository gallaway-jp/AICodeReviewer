def validate_signup(payload: dict) -> None:
    required_fields = ["username", "password"]
    for field in required_fields:
        if not payload.get(field):
            raise ValueError(f"Missing required field: {field}")