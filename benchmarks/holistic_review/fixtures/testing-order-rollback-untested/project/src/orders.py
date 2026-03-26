def submit_order(repository, payment_gateway, order: dict) -> dict:
    repository.begin()
    try:
        payment_gateway.charge(order["customer_id"], order["total_cents"])
        repository.save(order)
        repository.commit()
        return {"status": "accepted"}
    except Exception:
        repository.rollback()
        raise