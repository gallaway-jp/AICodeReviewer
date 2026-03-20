def update_user_profile(store: dict[int, dict], user_id: int, profile: dict) -> None:
    store[user_id] = profile