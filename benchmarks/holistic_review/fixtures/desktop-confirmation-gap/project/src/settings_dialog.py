import tkinter as tk

from .settings_store import reset_all_settings


class SettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc | None = None):
        super().__init__(master)
        self.title("Settings")
        self.status_var = tk.StringVar(value="Ready")

        tk.Button(self, text="Reset all settings", command=self.reset_everything).pack(
            padx=12, pady=(12, 6)
        )
        tk.Label(self, textvariable=self.status_var).pack(padx=12, pady=(0, 12))

    def reset_everything(self) -> None:
        reset_all_settings()
        self.status_var.set("All settings were reset.")
        self.destroy()
