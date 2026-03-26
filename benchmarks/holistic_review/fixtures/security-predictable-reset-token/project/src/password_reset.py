import hashlib


def build_reset_link(email: str) -> str:
    token = hashlib.sha256(email.encode("utf-8")).hexdigest()
    return f"https://example.test/reset?email={email}&token={token}"