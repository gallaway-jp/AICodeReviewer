def fetch_order(order_id: int) -> dict[str, int | str]:
    return execute_query(
        "SELECT id, status, total_cents FROM orders WHERE id = ?",
        [order_id],
    )[0]


def fetch_orders(order_ids: list[int]) -> list[dict[str, int | str]]:
    return execute_query(
        "SELECT id, status, total_cents FROM orders WHERE id IN (?)",
        order_ids,
    )


def execute_query(sql: str, params: list[int]) -> list[dict[str, int | str]]:
    return [{"id": params[0], "status": "paid", "total_cents": 1200, "sql": sql}]