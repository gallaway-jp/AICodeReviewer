class OrderRepository:
    def save_order(self, order: dict) -> None:
        self._begin()
        self._write_order(order)
        self._write_items(order["items"])
        self._commit()

    def _begin(self) -> None:
        pass

    def _write_order(self, order: dict) -> None:
        pass

    def _write_items(self, items: list[dict]) -> None:
        pass

    def _commit(self) -> None:
        pass