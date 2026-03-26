import tkinter as tk

from .advanced_panel import AdvancedPanel


class SettingsWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc | None = None):
        super().__init__(master)
        self.title("Preferences")
        self.geometry("420x220")

        tk.Label(self, text="General").pack(anchor="w", padx=12, pady=(12, 4))
        tk.Checkbutton(self, text="Use smart mode").pack(anchor="w", padx=12)
        tk.Checkbutton(self, text="Sync on launch").pack(anchor="w", padx=12)

        tk.Button(self, text="Advanced", command=self.open_advanced).pack(
            anchor="e", padx=12, pady=(24, 0)
        )
        tk.Button(self, text="OK", command=self.destroy).pack(
            anchor="e", padx=12, pady=8
        )

    def open_advanced(self) -> None:
        AdvancedPanel(self)
