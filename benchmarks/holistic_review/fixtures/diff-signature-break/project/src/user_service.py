def fetch_user(user_id: str, tenant_id: str) -> dict:
    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
    }