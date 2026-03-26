import tkinter as tk


class AdvancedStep(tk.Toplevel):
    def __init__(self, master: tk.Misc | None = None, *, cloud_sync_enabled: bool = False):
        super().__init__(master)
        self.title("Advanced")
        self.geometry("320x220")

        tk.Label(self, text="Advanced settings").pack(anchor="w", padx=12, pady=(12, 4))
        tk.Checkbutton(
            self,
            text="Sync over metered networks",
            state="normal" if cloud_sync_enabled else "disabled",
        ).pack(anchor="w", padx=12, pady=(8, 0))
        tk.Checkbutton(
            self,
            text="Sync in background",
            state="normal" if cloud_sync_enabled else "disabled",
        ).pack(anchor="w", padx=12)

        tk.Button(self, text="Finish", command=self.destroy).pack(
            anchor="e", padx=12, pady=(28, 12)
        )