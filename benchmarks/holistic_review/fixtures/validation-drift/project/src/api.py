from src.validation import validate_signup


def create_account(payload: dict) -> dict:
    validate_signup(payload)
    normalized = {
        "username": payload["username"],
        "password": payload["password"],
        "email": payload["email"],
    }
    return normalized