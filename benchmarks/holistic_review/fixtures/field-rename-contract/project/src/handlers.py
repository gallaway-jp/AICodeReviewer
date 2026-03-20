from src.serializers import serialize_user


def build_profile_response(user: dict) -> dict:
    payload = serialize_user(user)
    return {
        "user_id": payload["id"],
        "display_name": payload["display_name"],
    }