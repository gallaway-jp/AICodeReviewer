from src.sync import fetch_profile_with_retry


class SuccessfulClient:
    def fetch_profile(self, account_id: str) -> dict:
        return {"account_id": account_id, "status": "ready"}


def test_fetch_profile_returns_profile_on_first_attempt() -> None:
    result = fetch_profile_with_retry(SuccessfulClient(), "acct-123")

    assert result == {"account_id": "acct-123", "status": "ready"}