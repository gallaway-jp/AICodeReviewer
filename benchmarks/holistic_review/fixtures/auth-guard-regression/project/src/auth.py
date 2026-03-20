def require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise PermissionError("admin role required")


def require_login(user: dict) -> None:
    if not user.get("id"):
        raise PermissionError("login required")