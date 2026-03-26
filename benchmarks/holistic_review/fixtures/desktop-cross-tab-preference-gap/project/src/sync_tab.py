import tkinter as tk
from tkinter import ttk


class SyncTab(ttk.Frame):
    def __init__(self, master: tk.Misc | None = None):
        super().__init__(master)
        self.sync_enabled = tk.BooleanVar(value=True)
        self.sync_on_startup = tk.BooleanVar(value=True)

        ttk.Checkbutton(self, text="Enable sync", variable=self.sync_enabled).pack(anchor="w", padx=8, pady=(8, 4))
        ttk.Checkbutton(self, text="Sync on startup", variable=self.sync_on_startup).pack(anchor="w", padx=8)
        ttk.Label(self, text="Choose how and when data should sync.").pack(anchor="w", padx=8, pady=(12, 0))

    def collect_settings(self) -> dict[str, object]:
        return {
            "sync_enabled": self.sync_enabled.get(),
            "sync_on_startup": self.sync_on_startup.get(),
        }
