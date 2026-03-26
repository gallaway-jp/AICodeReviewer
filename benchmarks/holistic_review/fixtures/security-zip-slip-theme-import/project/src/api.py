from .theme_importer import import_theme_bundle


def upload_theme_bundle(request: dict[str, str], current_account: dict[str, str]):
    archive_path = request["archive_path"]
    return import_theme_bundle(current_account["id"], archive_path)