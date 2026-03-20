from src.repository import OrderRepository


def place_order(repository: OrderRepository, order: dict) -> None:
    repository._write_order(order)
    repository._write_items(order["items"])