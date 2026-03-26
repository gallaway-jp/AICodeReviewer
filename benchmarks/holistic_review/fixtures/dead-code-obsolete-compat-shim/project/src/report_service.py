from .modern_export import render_modern_csv


def generate_report(customer_id: str) -> str:
    return render_modern_csv(customer_id)