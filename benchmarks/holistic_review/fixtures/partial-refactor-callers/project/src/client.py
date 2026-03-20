from src.service import build_result


def render_total(total: int) -> str:
    response = build_result(total)
    return f"Total: {response['result']}"