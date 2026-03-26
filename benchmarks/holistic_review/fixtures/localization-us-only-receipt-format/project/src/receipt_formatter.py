from datetime import datetime


def render_receipt(total_amount, purchased_at):
    date_text = purchased_at.strftime("%m/%d/%Y")
    amount_text = f"${total_amount:.2f}"
    return f"Receipt date: {date_text}\nTotal: {amount_text}"
