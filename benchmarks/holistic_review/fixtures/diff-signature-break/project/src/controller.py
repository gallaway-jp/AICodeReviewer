from src.user_service import fetch_user


def get_profile(user_id: str) -> dict:
    return fetch_user(user_id)