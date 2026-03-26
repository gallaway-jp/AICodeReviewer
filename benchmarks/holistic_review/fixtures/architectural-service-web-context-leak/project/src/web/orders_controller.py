from src.repositories.order_repository import fetch_recent_orders


def orders_page() -> dict[str, list[dict[str, str]]]:
    return {"orders": fetch_recent_orders()}