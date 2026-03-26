def build_profile_response(user) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "name": user.display_name,
    }