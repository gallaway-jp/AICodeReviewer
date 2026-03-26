import tkinter as tk
from tkinter import ttk

from .sync_tab import SyncTab


class SettingsWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc | None = None):
        super().__init__(master)
        self.title("Settings")
        self.performance_mode = tk.StringVar(value="balanced")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        general_tab = ttk.Frame(notebook)
        notebook.add(general_tab, text="General")
        ttk.Label(general_tab, text="Performance mode").pack(anchor="w", pady=(8, 4))
        ttk.Radiobutton(general_tab, text="Balanced", variable=self.performance_mode, value="balanced").pack(anchor="w")
        ttk.Radiobutton(general_tab, text="Lite", variable=self.performance_mode, value="lite").pack(anchor="w")

        self.sync_tab = SyncTab(notebook)
        notebook.add(self.sync_tab, text="Sync")

        ttk.Button(self, text="Save", command=self.save_settings).pack(anchor="e", padx=12, pady=(0, 12))

    def save_settings(self) -> dict[str, object]:
        payload = self.sync_tab.collect_settings()
        payload["performance_mode"] = self.performance_mode.get()
        if self.performance_mode.get() == "lite":
            payload["sync_enabled"] = False
        return payload
