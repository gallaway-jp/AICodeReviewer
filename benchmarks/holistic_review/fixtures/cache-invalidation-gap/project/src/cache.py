PROFILE_CACHE: dict[int, dict] = {}


def get_user_profile(user_id: int) -> dict | None:
    return PROFILE_CACHE.get(user_id)


def set_user_profile(user_id: int, profile: dict) -> None:
    PROFILE_CACHE[user_id] = profile