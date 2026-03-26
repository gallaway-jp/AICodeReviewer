from .token_service import load_session_claims


def load_account_dashboard(request: dict[str, str]):
    raw_token = request["authorization"].removeprefix("Bearer ")
    claims = load_session_claims(raw_token)
    if claims.get("role") == "admin":
        return {"sections": ["overview", "billing", "audit"]}
    return {"sections": ["overview"]}