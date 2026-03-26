from .invoice_store import load_invoice_record


def download_invoice_pdf(account_id: str, invoice_id: str) -> bytes:
    invoice = load_invoice_record(invoice_id)
    return invoice["pdf_bytes"]