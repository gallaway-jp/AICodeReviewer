import jwt


def load_session_claims(raw_token: str) -> dict[str, str]:
    return jwt.decode(
        raw_token,
        options={"verify_signature": False},
        algorithms=["HS256"],
    )