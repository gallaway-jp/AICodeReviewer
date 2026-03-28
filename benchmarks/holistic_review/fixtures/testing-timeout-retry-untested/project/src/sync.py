def fetch_profile_with_retry(client, account_id: str) -> dict:
    for attempt in range(2):
        try:
            return client.fetch_profile(account_id)
        except TimeoutError:
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")