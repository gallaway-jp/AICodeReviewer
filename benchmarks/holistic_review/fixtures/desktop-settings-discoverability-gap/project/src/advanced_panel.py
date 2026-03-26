import tkinter as tk


class AdvancedPanel(tk.Toplevel):
    def __init__(self, master: tk.Misc | None = None):
        super().__init__(master)
        self.title("Advanced")
        self.geometry("260x320")

        tk.Label(self, text="Network").pack(anchor="w", padx=12, pady=(12, 4))
        tk.Entry(self).pack(fill="x", padx=12)

        tk.Label(self, text="Storage").pack(anchor="w", padx=12, pady=(12, 4))
        tk.Entry(self).pack(fill="x", padx=12)

        tk.Checkbutton(self, text="Allow beta features").pack(anchor="w", padx=12, pady=(16, 0))
        tk.Checkbutton(self, text="Write debug logs").pack(anchor="w", padx=12)
