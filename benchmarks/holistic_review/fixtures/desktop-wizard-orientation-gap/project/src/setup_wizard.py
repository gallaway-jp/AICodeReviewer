import tkinter as tk

from .advanced_step import AdvancedStep


class SetupWizard(tk.Toplevel):
    def __init__(self, master: tk.Misc | None = None):
        super().__init__(master)
        self.title("Setup Wizard")
        self.geometry("420x240")
        self.cloud_sync_enabled = tk.BooleanVar(value=False)

        tk.Label(self, text="Account").pack(anchor="w", padx=12, pady=(12, 4))
        tk.Entry(self).pack(fill="x", padx=12)

        tk.Checkbutton(self, text="Enable cloud sync", variable=self.cloud_sync_enabled).pack(
            anchor="w", padx=12, pady=(16, 4)
        )

        tk.Button(self, text="Next", command=self.open_advanced_step).pack(
            anchor="e", padx=12, pady=(24, 12)
        )

    def open_advanced_step(self) -> None:
        AdvancedStep(self, cloud_sync_enabled=self.cloud_sync_enabled.get())
