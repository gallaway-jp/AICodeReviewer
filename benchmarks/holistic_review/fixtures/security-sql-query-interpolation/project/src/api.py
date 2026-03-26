from .user_repository import list_users_by_status


def search_users(request: dict[str, str]):
    status = request.get("status", "active")
    return list_users_by_status(status)