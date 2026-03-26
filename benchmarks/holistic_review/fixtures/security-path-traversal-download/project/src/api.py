from .attachment_store import load_attachment


def download_attachment(request: dict[str, str], current_account: dict[str, str]):
    filename = request["filename"]
    return load_attachment(current_account["id"], filename)