def list_orders(repository) -> list[dict]:
    return repository.fetch_orders()