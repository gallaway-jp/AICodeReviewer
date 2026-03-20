from src.auth import require_login


def get_audit_log(user: dict) -> dict:
    require_login(user)
    return {"entries": ["sensitive-event"]}