DATABASE: list[str] = []


def persist_order(order_id: str) -> None:
    DATABASE.append(order_id)


def submit_batch(orders: list[dict[str, int | str]]) -> dict[str, object]:
    accepted: list[str] = []
    rejected: list[str] = []

    for order in orders:
        if int(order.get("total_cents", 0)) <= 0:
            rejected.append(str(order.get("id", "unknown")))
            continue

        order_id = str(order["id"])
        persist_order(order_id)
        accepted.append(order_id)

    if rejected:
        return {
            "status": "partial_success",
            "accepted": accepted,
            "rejected": rejected,
        }

    return {"status": "ok", "accepted": accepted, "rejected": rejected}