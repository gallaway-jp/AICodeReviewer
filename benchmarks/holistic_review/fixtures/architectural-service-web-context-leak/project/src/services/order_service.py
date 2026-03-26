from src.db import execute_query


def list_orders() -> list[dict[str, str]]:
    rows = execute_query("SELECT id, status FROM orders ORDER BY created_at DESC")
    return [{"id": row["id"], "status": row["status"]} for row in rows]