from .report_service import generate_report


def handle_request(customer_id: str) -> str:
    return generate_report(customer_id)