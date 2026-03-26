from pathlib import Path


ATTACHMENTS_ROOT = Path("/srv/app/attachments")


def load_attachment(account_id: str, filename: str) -> bytes:
    attachment_path = ATTACHMENTS_ROOT / account_id / filename
    with open(attachment_path, "rb") as attachment_file:
        return attachment_file.read()