from .password_reset import build_reset_link


def request_password_reset(request: dict[str, str]) -> dict[str, str]:
    email = request["email"]
    return {"reset_link": build_reset_link(email)}