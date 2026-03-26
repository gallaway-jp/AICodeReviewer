LEGACY_EXPORT_ENABLED = False


def render_legacy_csv(customer_id: str) -> str:
    return _legacy_header(customer_id)


def _legacy_header(customer_id: str) -> str:
    return f"customer,{customer_id},legacy"