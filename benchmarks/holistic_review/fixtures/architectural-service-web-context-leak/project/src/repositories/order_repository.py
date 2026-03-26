from src.db import execute_query


def fetch_recent_orders() -> list[dict[str, str]]:
    return execute_query("SELECT id, status FROM orders ORDER BY created_at DESC")