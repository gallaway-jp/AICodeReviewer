from .redirects import build_post_login_redirect


def login(request: dict[str, str]) -> tuple[dict[str, str], int]:
    user = authenticate(request["username"], request["password"])
    if user is None:
        return {"error": "invalid_credentials"}, 401
    location = build_post_login_redirect(request["return_to"])
    return {"redirect_to": location}, 302


def authenticate(username: str, password: str) -> dict[str, int] | None:
    if username == "demo" and password == "secret":
        return {"user_id": 1}
    return None