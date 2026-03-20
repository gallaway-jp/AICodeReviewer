from src.db import execute_query


def orders_page() -> list[dict]:
    return execute_query("SELECT * FROM orders")