import requests


def fetch_avatar_preview(avatar_url: str) -> bytes:
    response = requests.get(avatar_url, timeout=5)
    response.raise_for_status()
    return response.content