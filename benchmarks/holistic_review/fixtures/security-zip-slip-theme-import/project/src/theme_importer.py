import zipfile
from pathlib import Path


THEMES_ROOT = Path("/srv/app/themes")


def import_theme_bundle(account_id: str, archive_path: str) -> None:
    destination = THEMES_ROOT / account_id
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(destination)