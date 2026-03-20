def serialize_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "full_name": user["full_name"],
    }