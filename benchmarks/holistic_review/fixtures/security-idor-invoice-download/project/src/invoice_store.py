INVOICES = {
    "inv-100": {"account_id": "acct-100", "pdf_bytes": b"invoice-100"},
    "inv-200": {"account_id": "acct-200", "pdf_bytes": b"invoice-200"},
}


def load_invoice_record(invoice_id: str) -> dict[str, object]:
    return INVOICES[invoice_id]