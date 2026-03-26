from .invoice_service import download_invoice_pdf


def download_invoice(request: dict[str, str], current_account: dict[str, str]) -> bytes:
    invoice_id = request["invoice_id"]
    return download_invoice_pdf(current_account["id"], invoice_id)