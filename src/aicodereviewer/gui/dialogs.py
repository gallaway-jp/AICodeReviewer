# src/aicodereviewer/gui/dialogs.py
"""Stand-alone dialog windows used by the AICodeReviewer GUI.

Contains:
- ``FileSelector`` – project file tree with checkboxes
- ``ConfirmDialog`` – modal Yes / No confirmation
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.i18n import t
from aicodereviewer.scanner import scan_project

from .widgets import _fix_titlebar

__all__ = [
    "FileSelector",
    "ConfirmDialog",
]


class FileSelector(ctk.CTkToplevel):
    """Custom file selector window with tree structure and checkboxes."""

    def __init__(self, parent: Any, project_path: str, preselected: List[str]):
        super().__init__(parent)
        self.result: list = []
        self.project_path = Path(project_path)
        self.preselected = set(preselected)
        self.file_vars: dict = {}  # Maps file path to BooleanVar

        self.title("Select Files for Review")
        self.geometry("700x600")

        # Make window modal
        self.transient(parent)
        self.grab_set()
        self.after(10, lambda: _fix_titlebar(self))

        # Build UI
        self._build_ui()

        # Centre window
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        """Build the file selector UI shell, then scan for files in the background."""
        # Header with select all / deselect all
        header_frame = ctk.CTkFrame(self)
        header_frame.pack(fill="x", padx=10, pady=10)

        self.select_all_var = ctk.BooleanVar(value=False)
        select_all_cb = ctk.CTkCheckBox(header_frame, text="Select All / Deselect All",
                                        variable=self.select_all_var,
                                        command=self._toggle_all)
        select_all_cb.pack(side="left", padx=5)

        # Scrollable file tree (populated asynchronously)
        self._file_frame = ctk.CTkScrollableFrame(self, label_text="Reviewable Files")
        self._file_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Loading indicator shown while the background scan runs
        self._loading_lbl = ctk.CTkLabel(
            self._file_frame, text="⏳ Scanning project files…",
            text_color=("gray40", "gray60"))
        self._loading_lbl.pack(pady=20)

        # Bottom buttons — OK disabled until scan completes
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        self._ok_btn = ctk.CTkButton(btn_frame, text="OK", width=100,
                                     state="disabled", command=self._on_ok)
        self._ok_btn.pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", width=100,
                      command=self._on_cancel).pack(side="right", padx=5)

        # Run the potentially-slow scan off the main thread
        threading.Thread(target=self._scan_files, daemon=True).start()

    def _scan_files(self) -> None:
        """Run scan_project in a background thread, then hand results to GUI thread."""
        try:
            files = scan_project(str(self.project_path))
        except Exception:
            files = []
        # Schedule the tree population back on the Tk main thread
        try:
            self.after(0, lambda: self._populate_tree(files))
        except Exception:
            pass  # window may have been closed before scan finished

    def _populate_tree(self, files: List[Path]) -> None:
        """Called on the main thread once the background scan finishes."""
        self._loading_lbl.destroy()
        if not files:
            ctk.CTkLabel(self._file_frame,
                         text="No reviewable files found in project").pack(pady=20)
        else:
            self._build_file_tree(self._file_frame, files)
        self._ok_btn.configure(state="normal")

    def _build_file_tree(self, parent_frame: Any, files: List[Path]):
        """Build the file tree with checkboxes."""
        tree_dict: Dict[str, Any] = {}
        for file_path in sorted(files):
            try:
                rel_path = file_path.relative_to(self.project_path)
            except ValueError:
                continue
            parts = rel_path.parts
            current = tree_dict
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            filename = parts[-1]
            current[filename] = str(file_path)
        self._render_tree(parent_frame, tree_dict, indent=0)

    def _render_tree(self, parent_frame: Any, tree_dict: Dict[str, Any], indent: int):
        """Recursively render the file tree."""
        for key in sorted(tree_dict.keys()):
            value = tree_dict[key]
            if isinstance(value, dict):
                dir_label = ctk.CTkLabel(parent_frame, text="📁 " + key,
                                        anchor="w", text_color=("gray30", "gray70"))
                dir_label.pack(fill="x", padx=(indent * 20, 0), pady=1)
                self._render_tree(parent_frame, value, indent + 1)
            else:
                file_path = value
                is_selected = file_path in self.preselected
                var = ctk.BooleanVar(value=is_selected)
                self.file_vars[file_path] = var
                cb = ctk.CTkCheckBox(parent_frame, text="📄 " + key,
                                    variable=var, width=500)
                cb.pack(fill="x", anchor="w", padx=(indent * 20, 0), pady=1)

    def _toggle_all(self):
        value = self.select_all_var.get()
        for var in self.file_vars.values():
            var.set(value)

    def _on_ok(self):
        self.result = [path for path, var in self.file_vars.items() if var.get()]
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = self.preselected
        self.grab_release()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════

class ConfirmDialog(ctk.CTkToplevel):
    """Modal Yes/No confirmation dialog that matches the CTk theme.

    Usage::

        dlg = ConfirmDialog(parent, title="...", message="...")
        if dlg.confirmed:
            ...
    """

    def __init__(self, parent: ctk.CTk, *, title: str, message: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.after(10, lambda: _fix_titlebar(self))
        self.confirmed: bool = False

        self.grid_columnconfigure(0, weight=1)

        msg_lbl = ctk.CTkLabel(
            self,
            text=message,
            wraplength=340,
            justify="left",
            font=ctk.CTkFont(size=13),
        )
        msg_lbl.grid(row=0, column=0, padx=24, pady=(24, 16), sticky="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=1, column=0, padx=24, pady=(0, 20), sticky="e")

        ctk.CTkButton(
            btn_frame,
            text=t("common.yes"),
            width=90,
            command=self._yes,
        ).grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text=t("common.no"),
            width=90,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            text_color=("gray10", "gray90"),
            command=self._no,
        ).grid(row=0, column=1)

        # Centre over parent
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        dw = self.winfo_width()
        dh = self.winfo_height()
        self.geometry(f"+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")

        self.protocol("WM_DELETE_WINDOW", self._no)
        self.wait_window()

    def _yes(self) -> None:
        self.confirmed = True
        self.destroy()

    def _no(self) -> None:
        self.confirmed = False
        self.destroy()
