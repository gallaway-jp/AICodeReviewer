USE_LEGACY_RENDERER = False


def render_invoice(payload: dict[str, str]) -> str:
    if USE_LEGACY_RENDERER:
        return _render_legacy_invoice(payload)
    return _render_modern_invoice(payload)


def _render_modern_invoice(payload: dict[str, str]) -> str:
    return f"Invoice:{payload['id']}:{payload['customer']}"


def _render_legacy_invoice(payload: dict[str, str]) -> str:
    return "|".join([
        "legacy",
        payload["id"],
        payload["customer"],
    ])