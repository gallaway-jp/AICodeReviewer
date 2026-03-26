from src.orders import submit_order


class FakeRepository:
    def __init__(self) -> None:
        self.events: list[str] = []

    def begin(self) -> None:
        self.events.append("begin")

    def save(self, order: dict) -> None:
        self.events.append(f"save:{order['customer_id']}")

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")


class SuccessfulGateway:
    def charge(self, customer_id: str, total_cents: int) -> None:
        return None


def test_submit_order_commits_successful_checkout() -> None:
    repository = FakeRepository()

    result = submit_order(
        repository,
        SuccessfulGateway(),
        {"customer_id": "cust-123", "total_cents": 4500},
    )

    assert result == {"status": "accepted"}
    assert repository.events == ["begin", "save:cust-123", "commit"]