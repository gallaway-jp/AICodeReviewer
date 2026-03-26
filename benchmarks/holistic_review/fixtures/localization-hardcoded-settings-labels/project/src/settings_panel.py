from ui import Button, Label
from i18n import t


def build_settings_panel(parent):
    Label(parent, text=t("settings.title"))
    Label(parent, text=t("settings.description"))
    Button(parent, text="Sync now")
    Button(parent, text="Delete cache")
    Label(parent, text="Last synced successfully")
