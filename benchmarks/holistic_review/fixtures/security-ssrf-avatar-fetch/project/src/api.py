from .avatar_fetcher import fetch_avatar_preview


def preview_avatar(request: dict[str, str]):
    avatar_url = request["avatar_url"]
    return fetch_avatar_preview(avatar_url)