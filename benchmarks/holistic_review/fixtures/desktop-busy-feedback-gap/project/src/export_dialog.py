import tkinter as tk
from .export_service import export_report


class ExportDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc | None = None):
        super().__init__(master)
        self.title("Export report")
        self.status_var = tk.StringVar(value="Ready")

        self.export_button = tk.Button(self, text="Export", command=self.start_export)
        self.export_button.pack(padx=12, pady=(12, 6))

        self.close_button = tk.Button(self, text="Close", command=self.destroy)
        self.close_button.pack(padx=12, pady=6)

        self.status_label = tk.Label(self, textvariable=self.status_var)
        self.status_label.pack(padx=12, pady=(6, 12))

    def start_export(self) -> None:
        self.status_var.set("Exporting...")
        export_report()
        self.status_var.set("Done")
