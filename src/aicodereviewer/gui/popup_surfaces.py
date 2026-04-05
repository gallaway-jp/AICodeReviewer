from __future__ import annotations

import codecs
import datetime
import difflib
import json
import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import tkinter as tk

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.addons import collect_addon_editor_diagnostics, emit_addon_editor_buffer_event, emit_addon_editor_event, emit_addon_patch_applied_event
from aicodereviewer.i18n import t

from .dialogs import ConfirmDialog
from .widgets import _Tooltip

logger = logging.getLogger(__name__)

POPUP_RECOVERY_FORMAT_VERSION = 1
LARGE_FILE_PROGRESS_THRESHOLD_BYTES = 512 * 1024
LARGE_FILE_EDITOR_LIMIT_BYTES = 2 * 1024 * 1024
LARGE_FILE_PAGE_BYTES = LARGE_FILE_EDITOR_LIMIT_BYTES
FILE_READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class LoadedTextPayload:
    content: str
    source_size_bytes: int = 0
    loaded_size_bytes: int = 0
    truncated: bool = False
    page_index: int = 0
    total_pages: int = 1


class PopupSurfaceRecoveryStore:
    def __init__(
        self,
        path: Path,
        session_state_factory: Callable[[], Any],
    ) -> None:
        self._path = path
        self._session_state_factory = session_state_factory

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load popup recovery state from %s: %s", self._path, exc)
            return None
        if not isinstance(raw, dict):
            return None
        return raw

    def clear(self) -> None:
        try:
            if self._path.exists():
                self._path.unlink()
        except Exception as exc:
            logger.warning("Failed to clear popup recovery state %s: %s", self._path, exc)

    def save_active_popup(self, popup_payload: dict[str, Any] | None) -> None:
        if not popup_payload:
            self.clear()
            return
        try:
            session_state = self._session_state_factory()
            serialized_session_state = session_state.to_serialized_dict(
                saved_at=datetime.datetime.now()
            )
        except Exception as exc:
            logger.warning("Failed to snapshot session state for popup recovery: %s", exc)
            return

        payload = {
            "format_version": POPUP_RECOVERY_FORMAT_VERSION,
            "saved_at": datetime.datetime.now().isoformat(),
            "session_state": serialized_session_state,
            "active_popup": popup_payload,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist popup recovery state to %s: %s", self._path, exc)


class ResultsPopupSurfaceController:
    def __init__(self, host: Any, recovery_store: PopupSurfaceRecoveryStore) -> None:
        self.host = host
        self.recovery_store = recovery_store

    def _extract_editor_sections(self, content: str, file_ext: str) -> list[tuple[str, int, int]]:
        import re

        lines = content.splitlines()
        section_starts: list[tuple[str, int]] = []

        python_pattern = re.compile(r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
        js_pattern = re.compile(
            r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][A-Za-z0-9_$]*)|^\s*(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*="
        )
        section_pattern = re.compile(r"^\s*\[([^\]]+)\]\s*$")
        heading_pattern = re.compile(r"^\s*(#+|//+|/\*+|;+)\s*(.+?)\s*$")
        key_pattern = re.compile(r"^\s*(?:-\s+)?([A-Za-z0-9_.\-\"']+)(?=\s*[:=])")

        for line_number, line in enumerate(lines, start=1):
            label: str | None = None
            if file_ext in {".py", ".pyw"}:
                match = python_pattern.match(line)
                if match:
                    label = match.group(1)
            elif file_ext in {".js", ".jsx", ".ts", ".tsx"}:
                match = js_pattern.match(line)
                if match:
                    label = match.group(1) or match.group(2)
            elif file_ext in {".ini", ".cfg", ".conf", ".toml"}:
                match = section_pattern.match(line)
                if match:
                    label = match.group(1)
                elif file_ext == ".toml":
                    key_match = key_pattern.match(line)
                    if key_match:
                        label = key_match.group(1).strip('"\'')
            elif file_ext in {".yml", ".yaml", ".json", ".jsonc"}:
                key_match = key_pattern.match(line)
                if key_match:
                    label = key_match.group(1).strip('"\'')
            if label is None:
                heading_match = heading_pattern.match(line)
                if heading_match and heading_match.group(2):
                    label = heading_match.group(2)
            if label:
                display = label if len(label) <= 36 else f"{label[:33]}..."
                section_starts.append((f"L{line_number}: {display}", line_number))

        if not section_starts:
            return []

        sections: list[tuple[str, int, int]] = []
        total_lines = max(len(lines), 1)
        for index, (label, start_line) in enumerate(section_starts):
            next_start = section_starts[index + 1][1] if index + 1 < len(section_starts) else total_lines + 1
            sections.append((label, start_line, max(start_line, next_start - 1)))
        return sections

    def open_builtin_editor(
        self,
        idx: int,
        issue: Any,
        *,
        initial_content: str | None = None,
        on_save: Any = None,
        recovery_state: dict[str, Any] | None = None,
        on_draft_change: Callable[[str, str], None] | None = None,
        on_discard: Callable[[], None] | None = None,
    ) -> None:
        fname = Path(issue.file_path).name
        file_ext = Path(issue.file_path).suffix.lower()
        requested_active_buffer = str(recovery_state.get("active_buffer", "working")) if recovery_state else "working"

        find_bar_visible = [False]
        search_positions: list[str] = []
        search_idx = [-1]
        highlight_timer: list[Any] = [None]
        diagnostics_timer: list[Any] = [None]
        editor_loaded = [False]
        editor_read_only = [False]
        loaded_payload: list[LoadedTextPayload | None] = [None]
        bookmark_lines: set[int] = set()
        bookmark_order: list[int] = []
        large_file_page_index = [int(recovery_state.get("page_index", 0)) if recovery_state else 0]
        large_file_total_pages = [1]
        current_file_size_bytes = [0]
        buffer_states: dict[str, dict[str, Any]] = {
            "working": {
                "label": t("gui.results.editor_buffer_working"),
                "content": str(recovery_state.get("content", initial_content or "")) if recovery_state else (initial_content or ""),
                "cursor_index": str(recovery_state.get("cursor_index", "1.0")) if recovery_state else "1.0",
                "read_only": False,
                "page_index": large_file_page_index[0],
                "total_pages": 1,
                "bookmarks": set(),
                "folded_sections": set(),
            }
        }
        buffer_order = ["working"]
        reference_content = (issue.code_snippet or "").rstrip("\n")
        working_seed_content = str(buffer_states["working"]["content"]).rstrip("\n")
        if reference_content and reference_content != working_seed_content:
            buffer_states["reference"] = {
                "label": t("gui.results.editor_buffer_reference"),
                "content": reference_content,
                "cursor_index": "1.0",
                "read_only": True,
                "page_index": 0,
                "total_pages": 1,
                "bookmarks": set(),
                "folded_sections": set(),
            }
            buffer_order.append("reference")
        active_buffer_key = ["working"]

        base_title = t("gui.results.editor_title", file=fname)
        win = ctk.CTkToplevel(self.host)
        win.title(base_title)
        win.geometry("980x700")
        win.minsize(700, 480)
        win.grab_set()
        self.host._schedule_titlebar_fix(win)

        dark = ctk.get_appearance_mode().lower() == "dark"
        if dark:
            bg = "#1e1e1e"
            fg = "#d4d4d4"
            ln_bg = "#252526"
            ln_fg = "#858585"
            sel_bg = "#264f78"
            cur_line = "#2a2d2e"
            insert_c = "#aeafad"
            kw_c = "#569cd6"
            str_c = "#ce9178"
            cmt_c = "#6a9955"
            bi_c = "#4ec9b0"
            num_c = "#b5cea8"
            dec_c = "#dcdcaa"
        else:
            bg = "#ffffff"
            fg = "#1f1f1f"
            ln_bg = "#f3f3f3"
            ln_fg = "#888888"
            sel_bg = "#add6ff"
            cur_line = "#f0f8ff"
            insert_c = "#000000"
            kw_c = "#0000ff"
            str_c = "#a31515"
            cmt_c = "#008000"
            bi_c = "#267f99"
            num_c = "#098658"
            dec_c = "#795e26"

        feedback_frame = ctk.CTkFrame(win, fg_color=("gray88", "gray17"), corner_radius=6)
        feedback_frame.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(
            feedback_frame,
            text=f"⚠  {issue.ai_feedback[:260]}",
            wraplength=900,
            anchor="w",
            justify="left",
            text_color=("gray30", "gray65"),
            font=ctk.CTkFont(size=11),
        ).pack(padx=10, pady=6, anchor="w")

        progress_frame = ctk.CTkFrame(win, fg_color=("#e0f2fe", "#0f172a"), corner_radius=6)
        progress_frame.pack(fill="x", padx=10, pady=(6, 0))
        progress_frame.grid_columnconfigure(0, weight=1)
        progress_label = ctk.CTkLabel(
            progress_frame,
            text=t("gui.results.large_file_loading", file=fname),
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=11),
        )
        progress_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        progress_bar = ctk.CTkProgressBar(progress_frame)
        progress_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        progress_bar.set(0)
        progress_frame.pack_forget()

        toolbar = ctk.CTkFrame(win, fg_color=("gray94", "gray14"), corner_radius=8)
        toolbar.pack(fill="x", padx=10, pady=(8, 0))
        toolbar.grid_columnconfigure(0, weight=1)

        primary_toolbar = ctk.CTkFrame(toolbar, fg_color="transparent")
        primary_toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        secondary_toolbar = ctk.CTkFrame(toolbar, fg_color="transparent")
        secondary_toolbar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        tab_frame = ctk.CTkFrame(win, fg_color=("gray92", "gray14"), corner_radius=8)
        tab_buttons: dict[str, Any] = {}
        tab_tooltips: dict[str, Any] = {}
        tab_aux_tooltips: dict[str, list[Any]] = {}
        tab_marker_strips: dict[str, Any] = {}
        tab_markers: dict[str, dict[str, Any]] = {}
        addon_diagnostics_frame = ctk.CTkFrame(win, fg_color=("#fef3c7", "#3f2d14"), corner_radius=6)
        addon_diagnostics_label = ctk.CTkLabel(
            addon_diagnostics_frame,
            text="",
            anchor="w",
            justify="left",
            wraplength=920,
            font=ctk.CTkFont(size=11),
            text_color=("#7c2d12", "#fde68a"),
        )
        addon_diagnostics_label.pack(fill="x", padx=10, pady=6)

        ctk.CTkButton(
            primary_toolbar,
            text=t("gui.results.editor_find"),
            width=96,
            height=28,
            command=lambda: toggle_find(),
        ).pack(side="left")

        ctk.CTkButton(
            primary_toolbar,
            text=t("gui.results.editor_prev_match"),
            width=96,
            height=28,
            command=lambda: do_find(-1),
        ).pack(side="left", padx=(6, 0))

        ctk.CTkButton(
            primary_toolbar,
            text=t("gui.results.editor_next_match"),
            width=96,
            height=28,
            command=lambda: do_find(1),
        ).pack(side="left", padx=(6, 0))

        ctk.CTkButton(
            primary_toolbar,
            text=t("gui.results.editor_replace"),
            width=96,
            height=28,
            command=lambda: toggle_find(show_replace=True),
        ).pack(side="left", padx=(6, 0))

        ctk.CTkLabel(
            primary_toolbar,
            text=t("gui.results.editor_go_to_line"),
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="left", padx=(16, 4))

        goto_var = tk.StringVar()
        goto_entry = ctk.CTkEntry(
            primary_toolbar,
            textvariable=goto_var,
            width=90,
            placeholder_text=t("gui.results.editor_go_to_line_ph"),
        )
        goto_entry.pack(side="left", padx=(0, 4))
        goto_default_border = goto_entry.cget("border_color")

        ctk.CTkButton(
            primary_toolbar,
            text=t("gui.results.editor_go"),
            width=64,
            height=28,
            command=lambda: go_to_line(),
        ).pack(side="left")

        goto_status_label = ctk.CTkLabel(
            primary_toolbar,
            text="",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        goto_status_label.pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            secondary_toolbar,
            text=t("gui.results.editor_toggle_bookmark"),
            width=124,
            height=28,
            command=lambda: toggle_bookmark(),
        ).pack(side="left")

        ctk.CTkButton(
            secondary_toolbar,
            text=t("gui.results.editor_prev_bookmark"),
            width=112,
            height=28,
            command=lambda: jump_bookmark(-1),
        ).pack(side="left", padx=(6, 0))

        ctk.CTkButton(
            secondary_toolbar,
            text=t("gui.results.editor_next_bookmark"),
            width=112,
            height=28,
            command=lambda: jump_bookmark(1),
        ).pack(side="left", padx=(6, 0))

        symbol_var = tk.StringVar(value=t("gui.results.editor_symbol_none"))
        symbol_menu = ctk.CTkOptionMenu(
            secondary_toolbar,
            variable=symbol_var,
            values=[t("gui.results.editor_symbol_none")],
            width=280,
        )
        symbol_menu.pack(side="left", padx=(12, 0))

        ctk.CTkButton(
            secondary_toolbar,
            text=t("gui.results.editor_fold_section"),
            width=112,
            height=28,
            command=lambda: toggle_fold_current_section(),
        ).pack(side="left", padx=(12, 0))

        ctk.CTkButton(
            secondary_toolbar,
            text=t("gui.results.editor_unfold_all"),
            width=112,
            height=28,
            command=lambda: unfold_all_sections(),
        ).pack(side="left", padx=(6, 0))

        bookmark_status_label = ctk.CTkLabel(
            secondary_toolbar,
            text="",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        bookmark_status_label.pack(side="left", padx=(8, 0))

        shortcut_hint_label = ctk.CTkLabel(
            secondary_toolbar,
            text=t("gui.results.editor_shortcuts"),
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
            anchor="e",
            justify="right",
        )
        shortcut_hint_label.pack(side="right")

        if len(buffer_order) > 1:
            tab_frame.pack(fill="x", padx=10, pady=(6, 0))

        editor_outer = tk.Frame(win, bd=0, highlightthickness=0)
        editor_outer.pack(fill="both", expand=True, padx=10, pady=(6, 0))
        editor_outer.configure(bg=ln_bg)
        editor_outer.columnconfigure(2, weight=1)
        editor_outer.rowconfigure(0, weight=1)

        vscroll = ctk.CTkScrollbar(
            editor_outer,
            orientation="vertical",
            border_spacing=0,
            fg_color=("gray90", "gray17"),
            button_color=("gray70", "gray30"),
            button_hover_color=("gray60", "gray40"),
        )
        vscroll.grid(row=0, column=3, sticky="ns")

        hscroll = ctk.CTkScrollbar(
            editor_outer,
            orientation="horizontal",
            border_spacing=0,
            fg_color=("gray90", "gray17"),
            button_color=("gray70", "gray30"),
            button_hover_color=("gray60", "gray40"),
        )
        hscroll.grid(row=1, column=2, sticky="ew")

        line_numbers = tk.Text(
            editor_outer,
            width=5,
            padx=6,
            takefocus=0,
            bg=ln_bg,
            fg=ln_fg,
            bd=0,
            highlightthickness=0,
            selectbackground=ln_bg,
            selectforeground=ln_fg,
            state="disabled",
            wrap="none",
            cursor="arrow",
            font=("Consolas", 13),
        )
        line_numbers.grid(row=0, column=0, rowspan=2, sticky="ns")

        separator = tk.Frame(editor_outer, width=1, bg="#3c3c3c" if dark else "#d0d0d0")
        separator.grid(row=0, column=1, rowspan=2, sticky="ns")

        def autohide_vscroll(*args: Any) -> None:
            vscroll.set(*args)
            lo, hi = float(args[0]), float(args[1])
            if lo <= 0.0 and hi >= 1.0:
                vscroll.grid_remove()
            else:
                vscroll.grid()
            update_line_numbers()

        def autohide_hscroll(*args: Any) -> None:
            hscroll.set(*args)
            lo, hi = float(args[0]), float(args[1])
            if lo <= 0.0 and hi >= 1.0:
                hscroll.grid_remove()
            else:
                hscroll.grid()

        text = tk.Text(
            editor_outer,
            bg=bg,
            fg=fg,
            bd=0,
            highlightthickness=0,
            insertbackground=insert_c,
            selectbackground=sel_bg,
            wrap="none",
            font=("Consolas", 13),
            undo=True,
            autoseparators=True,
            maxundo=-1,
            tabs=("4c",),
            yscrollcommand=autohide_vscroll,
            xscrollcommand=autohide_hscroll,
            padx=10,
            pady=4,
            spacing1=1,
            spacing3=2,
        )
        text.grid(row=0, column=2, sticky="nsew")
        text.configure(state="disabled")
        vscroll.configure(command=lambda *a: (text.yview(*a), update_line_numbers()))
        hscroll.configure(command=text.xview)

        tags = {
            "keyword": {"foreground": kw_c, "font": ("Consolas", 13, "bold")},
            "string": {"foreground": str_c},
            "comment": {"foreground": cmt_c, "font": ("Consolas", 13, "italic")},
            "builtin": {"foreground": bi_c},
            "number": {"foreground": num_c},
            "decorator": {"foreground": dec_c},
            "property": {"foreground": bi_c},
            "cur_line": {"background": cur_line},
            "bookmark_line": {"background": "#3b2f0d" if dark else "#fff7cc"},
            "find_match": {"background": "#f8c112", "foreground": "#000000"},
            "find_cur": {"background": "#ff8c00", "foreground": "#000000"},
        }
        for tag, options in tags.items():
            text.tag_configure(tag, **options)
        text.tag_lower("cur_line")

        keywords = frozenset(
            {
                "False", "None", "True", "and", "as", "assert", "async", "await",
                "break", "class", "continue", "def", "del", "elif", "else",
                "except", "finally", "for", "from", "global", "if", "import",
                "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise",
                "return", "try", "while", "with", "yield",
            }
        )
        builtins = frozenset(
            {
                "print", "len", "range", "int", "str", "list", "dict", "set",
                "tuple", "bool", "float", "type", "isinstance", "hasattr",
                "getattr", "setattr", "super", "zip", "map", "filter",
                "enumerate", "sorted", "reversed", "open", "input", "abs",
                "min", "max", "sum", "any", "all", "id", "hash", "repr",
                "format", "object", "property", "staticmethod", "classmethod",
                "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
                "AttributeError", "RuntimeError", "StopIteration", "OSError",
            }
        )

        javascript_like_keywords = frozenset(
            {
                "async", "await", "break", "case", "catch", "class", "const", "continue",
                "debugger", "default", "delete", "do", "else", "enum", "export", "extends",
                "false", "finally", "for", "function", "if", "implements", "import", "in",
                "instanceof", "interface", "let", "new", "null", "package", "private",
                "protected", "public", "return", "static", "super", "switch", "this", "throw",
                "true", "try", "typeof", "undefined", "var", "void", "while", "with", "yield",
            }
        )
        def clear_syntax_tags() -> None:
            for tag in ("keyword", "string", "comment", "builtin", "number", "decorator", "property"):
                text.tag_remove(tag, "1.0", "end")

        def apply_regex_tag(pattern: str, tag_name: str, *, flags: int = 0) -> None:
            import re

            source = text.get("1.0", "end")
            for match in re.finditer(pattern, source, flags):
                start = match.start(0)
                end = match.end(0)
                line_number = source.count("\n", 0, start) + 1
                column_start = start - source.rfind("\n", 0, start) - 1
                column_end = column_start + (end - start)
                text.tag_add(tag_name, f"{line_number}.{column_start}", f"{line_number}.{column_end}")

        def highlight_python() -> None:
            if text.cget("state") == "disabled":
                return
            clear_syntax_tags()
            import io
            import re
            import token as token_types
            import tokenize

            source = text.get("1.0", "end")
            try:
                tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
            except tokenize.TokenError:
                tokens = []
            for kind, value, (row1, col1), (row2, col2), _ in tokens:
                start, end = f"{row1}.{col1}", f"{row2}.{col2}"
                if kind == token_types.NAME:
                    if value in keywords:
                        text.tag_add("keyword", start, end)
                    elif value in builtins:
                        text.tag_add("builtin", start, end)
                elif kind == token_types.STRING:
                    text.tag_add("string", start, end)
                elif kind == token_types.COMMENT:
                    text.tag_add("comment", start, end)
                elif kind == token_types.NUMBER:
                    text.tag_add("number", start, end)
            for match in re.finditer(r"^[ \t]*(@\w+)", source, re.MULTILINE):
                line_number = source[: match.start()].count("\n") + 1
                column_number = match.start() - source.rfind("\n", 0, match.start()) - 1
                text.tag_add(
                    "decorator",
                    f"{line_number}.{column_number}",
                    f"{line_number}.{column_number + len(match.group(1))}",
                )

        def highlight_json_like() -> None:
            if text.cget("state") == "disabled":
                return
            clear_syntax_tags()
            import re

            apply_regex_tag(r'"(?:\\.|[^"\\])*"(?=\s*:)', "property")
            apply_regex_tag(r'"(?:\\.|[^"\\])*"', "string")
            apply_regex_tag(r'\b(?:true|false|null)\b', "keyword", flags=re.IGNORECASE)
            apply_regex_tag(r'\b-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\b', "number")

        def highlight_yaml_like() -> None:
            if text.cget("state") == "disabled":
                return
            clear_syntax_tags()
            import re

            apply_regex_tag(r'(?m)^\s*#.*$', "comment")
            apply_regex_tag(r'(?m)^\s*(?:-\s+)?[A-Za-z0-9_.\-"\'/]+(?=\s*:)', "property")
            apply_regex_tag(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', "string")
            apply_regex_tag(r'\b(?:true|false|null|none|yes|no|on|off)\b', "keyword", flags=re.IGNORECASE)
            apply_regex_tag(r'\b-?(?:0|[1-9]\d*)(?:\.\d+)?\b', "number")

        def highlight_ini_like() -> None:
            if text.cget("state") == "disabled":
                return
            clear_syntax_tags()
            import re

            apply_regex_tag(r'(?m)^\s*[#;].*$', "comment")
            apply_regex_tag(r'(?m)^\s*\[[^\]]+\]', "decorator")
            apply_regex_tag(r'(?m)^\s*[A-Za-z0-9_.\-]+(?=\s*=)', "property")
            apply_regex_tag(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', "string")
            apply_regex_tag(r'\b(?:true|false|yes|no|on|off)\b', "keyword", flags=re.IGNORECASE)
            apply_regex_tag(r'\b-?(?:0|[1-9]\d*)(?:\.\d+)?\b', "number")

        def highlight_javascript_like() -> None:
            if text.cget("state") == "disabled":
                return
            clear_syntax_tags()
            import re

            source = text.get("1.0", "end")
            apply_regex_tag(r'(?m)//.*$', "comment")
            apply_regex_tag(r'/\*.*?\*/', "comment", flags=re.DOTALL)
            apply_regex_tag(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`', "string")
            apply_regex_tag(r'\b-?(?:0|[1-9]\d*)(?:\.\d+)?\b', "number")
            apply_regex_tag(r'@[A-Za-z_][A-Za-z0-9_]*', "decorator")
            for match in re.finditer(r'\b[A-Za-z_$][A-Za-z0-9_$]*\b', source):
                value = match.group(0)
                if value not in javascript_like_keywords:
                    continue
                start = match.start(0)
                end = match.end(0)
                line_number = source.count("\n", 0, start) + 1
                column_start = start - source.rfind("\n", 0, start) - 1
                column_end = column_start + (end - start)
                text.tag_add("keyword", f"{line_number}.{column_start}", f"{line_number}.{column_end}")

        def highlight_plain_text() -> None:
            clear_syntax_tags()

        extension_labels = {
            ".py": "Python",
            ".pyw": "Python",
            ".json": "JSON",
            ".jsonc": "JSON",
            ".yml": "YAML",
            ".yaml": "YAML",
            ".toml": "TOML",
            ".ini": "INI",
            ".cfg": "Config",
            ".conf": "Config",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
        }

        if file_ext in {".py", ".pyw"}:
            syntax_highlighter = highlight_python
        elif file_ext in {".json", ".jsonc"}:
            syntax_highlighter = highlight_json_like
        elif file_ext in {".yml", ".yaml"}:
            syntax_highlighter = highlight_yaml_like
        elif file_ext in {".toml", ".ini", ".cfg", ".conf"}:
            syntax_highlighter = highlight_ini_like
        elif file_ext in {".js", ".jsx", ".ts", ".tsx"}:
            syntax_highlighter = highlight_javascript_like
        else:
            syntax_highlighter = highlight_plain_text
        language_name = extension_labels.get(file_ext, file_ext.lstrip(".").upper() or "Text")

        def schedule_highlight(*_args: Any) -> None:
            if highlight_timer[0]:
                win.after_cancel(highlight_timer[0])
            highlight_timer[0] = self.host._schedule_popup_after(
                win,
                260,
                syntax_highlighter,
            )

        def update_line_numbers(*_args: Any) -> None:
            try:
                first = int(text.index("@0,0").split(".")[0])
                last = int(text.index(f"@0,{text.winfo_height()}").split(".")[0])
                total = int(text.index("end-1c").split(".")[0])
                line_numbers.configure(state="normal")
                line_numbers.delete("1.0", "end")
                line_numbers.insert(
                    "end",
                    "\n".join(
                        f"{'●' if line in bookmark_lines else ' '}{line:>4}"
                        for line in range(first, min(last + 3, total + 1))
                    ),
                )
                line_numbers.configure(state="disabled")
            except Exception:
                pass

        def update_current_line(*_args: Any) -> None:
            if text.cget("state") == "disabled":
                update_status()
                return
            text.tag_remove("cur_line", "1.0", "end")
            row = text.index("insert").split(".")[0]
            text.tag_add("cur_line", f"{row}.0", f"{row}.end+1c")
            text.tag_lower("cur_line")
            update_status()

        status_bar = ctk.CTkFrame(win, fg_color=("gray80", "gray22"), height=24, corner_radius=0)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)

        position_label = ctk.CTkLabel(status_bar, text="Ln 1, Col 1", font=ctk.CTkFont(size=11), anchor="w")
        position_label.pack(side="left", padx=8)
        buffer_status_label = ctk.CTkLabel(
            status_bar,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray45", "gray60"),
            anchor="w",
        )
        buffer_status_label.pack(side="left", padx=(0, 8))
        setattr(win, "_acr_buffer_status_label", buffer_status_label)
        ctk.CTkLabel(
            status_bar,
            text=t("gui.results.editor_shortcuts_secondary"),
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
            anchor="e",
        ).pack(side="right", padx=10)
        language_label = ctk.CTkLabel(
            status_bar,
            text=language_name,
            font=ctk.CTkFont(size=11),
            anchor="e",
        )
        language_label.pack(side="right", padx=10)

        def current_buffer_state() -> dict[str, Any]:
            return buffer_states[active_buffer_key[0]]

        def working_buffer_state() -> dict[str, Any]:
            return buffer_states["working"]

        def working_buffer_dirty() -> bool:
            if active_buffer_key[0] == "working" and editor_loaded[0]:
                try:
                    return text.get("1.0", "end-1c") != initial_text_reference[0]
                except Exception:
                    pass
            return str(working_buffer_state().get("content", "")) != initial_text_reference[0]

        def update_window_title() -> None:
            title_mark = "● " if working_buffer_dirty() and not bool(working_buffer_state().get("read_only", False)) else ""
            if len(buffer_order) > 1:
                win.title(f"{title_mark}{base_title} [{current_buffer_state().get('label', '')}]")
            else:
                win.title(f"{title_mark}{base_title}")

        def build_editor_hook_payload(*, trigger: str) -> dict[str, Any]:
            buffer_state = current_buffer_state()
            cursor_index = str(buffer_state.get("cursor_index", "1.0"))
            try:
                cursor_line = int(cursor_index.split(".")[0])
            except Exception:
                cursor_line = 1
            return {
                "trigger": trigger,
                "issue_index": idx,
                "file_path": issue.file_path,
                "display_name": fname,
                "file_ext": file_ext,
                "line_number": getattr(issue, "line_number", None),
                "buffer_key": active_buffer_key[0],
                "buffer_label": str(buffer_state.get("label", "")),
                "buffer_count": len(buffer_order),
                "content": str(buffer_state.get("content", "")),
                "cursor_index": cursor_index,
                "cursor_line": cursor_line,
                "read_only": bool(buffer_state.get("read_only", False)),
                "page_index": int(buffer_state.get("page_index", 0)),
                "total_pages": int(buffer_state.get("total_pages", 1)),
                "bookmark_count": len(buffer_state.get("bookmarks", set())),
                "folded_section_count": len(buffer_state.get("folded_sections", set())),
                "dirty": working_buffer_dirty() if active_buffer_key[0] == "working" else False,
            }

        def render_addon_diagnostics(trigger: str) -> None:
            diagnostics = collect_addon_editor_diagnostics(build_editor_hook_payload(trigger=trigger))
            if not diagnostics:
                addon_diagnostics_frame.pack_forget()
                addon_diagnostics_label.configure(text="")
                return
            messages = []
            max_severity = "info"
            for diagnostic in diagnostics:
                messages.append(f"[{diagnostic.addon_id}] {diagnostic.message}")
                if diagnostic.severity.lower() == "error":
                    max_severity = "error"
                elif diagnostic.severity.lower() == "warning" and max_severity != "error":
                    max_severity = "warning"
            addon_diagnostics_label.configure(
                text="   ".join(messages),
                text_color=("#991b1b", "#fecaca") if max_severity == "error" else (("#7c2d12", "#fde68a") if max_severity == "warning" else ("#1d4ed8", "#bfdbfe")),
            )
            addon_diagnostics_frame.pack(fill="x", padx=10, pady=(6, 0), before=editor_outer)

        def schedule_addon_diagnostics(trigger: str) -> None:
            if self.host._testing_mode:
                render_addon_diagnostics(trigger)
                return
            if diagnostics_timer[0]:
                win.after_cancel(diagnostics_timer[0])
            diagnostics_timer[0] = self.host._schedule_popup_after(
                win,
                180,
                lambda: render_addon_diagnostics(trigger),
            )

        def cancel_popup_timers() -> None:
            for timer_ref in (highlight_timer, diagnostics_timer):
                if timer_ref[0]:
                    try:
                        win.after_cancel(timer_ref[0])
                    except tk.TclError:
                        pass
                    timer_ref[0] = None

        def build_buffer_status_text() -> str:
            buffer_state = current_buffer_state()
            marker_values = tab_marker_values(active_buffer_key[0])
            parts = [str(buffer_state.get("label", active_buffer_key[0].title()))]
            if bool(marker_values.get("dirty")):
                parts.append(t("gui.results.editor_status_dirty"))
            if bool(buffer_state.get("read_only", False)):
                parts.append(t("gui.results.editor_status_read_only"))
            if int(marker_values.get("bookmarks", 0)) > 0:
                parts.append(t("gui.results.editor_status_bookmarks", count=int(marker_values["bookmarks"])))
            if int(marker_values.get("folds", 0)) > 0:
                parts.append(t("gui.results.editor_status_folds", count=int(marker_values["folds"])))
            total_pages = int(buffer_state.get("total_pages", 1))
            if total_pages > 1:
                parts.append(
                    t(
                        "gui.results.editor_status_page",
                        current=int(buffer_state.get("page_index", 0)) + 1,
                        total=total_pages,
                    )
                )
            return "  ·  ".join(parts)

        def update_status(*_args: Any) -> None:
            try:
                row, column = text.index("insert").split(".")
                position_label.configure(text=f"Ln {row}, Col {int(column) + 1}")
            except Exception:
                pass
            buffer_status_label.configure(text=build_buffer_status_text())

        sections_ref: list[tuple[str, int, int]] = []
        folded_section_starts: set[int] = set()

        def section_for_line(line_number: int) -> tuple[str, int, int] | None:
            for section in sections_ref:
                if section[1] <= line_number <= section[2]:
                    return section
            return None

        def apply_fold_state() -> None:
            text.tag_configure("folded_section", elide=True)
            text.tag_remove("folded_section", "1.0", "end")
            active_starts = {start for _label, start, _end in sections_ref}
            folded_section_starts.intersection_update(active_starts)
            for _label, start_line, end_line in sections_ref:
                if start_line not in folded_section_starts or end_line <= start_line:
                    continue
                text.tag_add("folded_section", f"{start_line + 1}.0", f"{end_line}.end+1c")

        def jump_to_symbol(_selection: str | None = None) -> None:
            selected = symbol_var.get()
            for label, start_line, _end_line in sections_ref:
                if label != selected:
                    continue
                text.see(f"{start_line}.0")
                text.mark_set("insert", f"{start_line}.0")
                text.focus_set()
                update_current_line()
                update_status()
                return

        symbol_menu.configure(command=jump_to_symbol)

        def refresh_sections() -> None:
            sections_ref[:] = self._extract_editor_sections(text.get("1.0", "end-1c"), file_ext)
            if sections_ref:
                symbol_menu.configure(values=[label for label, _start, _end in sections_ref], state="normal")
                if symbol_var.get() not in {label for label, _start, _end in sections_ref}:
                    symbol_var.set(sections_ref[0][0])
            else:
                symbol_menu.configure(values=[t("gui.results.editor_symbol_none")], state="disabled")
                symbol_var.set(t("gui.results.editor_symbol_none"))
            apply_fold_state()
            refresh_tab_strip()
            update_status()

        def toggle_fold_current_section(*_args: Any) -> str:
            current_line = int(text.index("insert").split(".")[0])
            section = section_for_line(current_line)
            if section is None:
                return "break"
            start_line = section[1]
            if start_line in folded_section_starts:
                folded_section_starts.remove(start_line)
            else:
                folded_section_starts.add(start_line)
            apply_fold_state()
            refresh_tab_strip()
            update_status()
            return "break"

        def unfold_all_sections(*_args: Any) -> str:
            folded_section_starts.clear()
            apply_fold_state()
            refresh_tab_strip()
            update_status()
            return "break"

        def refresh_bookmarks() -> None:
            text.tag_remove("bookmark_line", "1.0", "end")
            bookmark_order[:] = sorted(bookmark_lines)
            for line_number in bookmark_order:
                text.tag_add("bookmark_line", f"{line_number}.0", f"{line_number}.end+1c")
            if bookmark_order:
                bookmark_status_label.configure(
                    text=t("gui.results.editor_bookmark_count", count=len(bookmark_order))
                )
            else:
                bookmark_status_label.configure(text=t("gui.results.editor_bookmark_count_none"))
            update_line_numbers()
            refresh_tab_strip()
            update_status()

        def toggle_bookmark(*_args: Any) -> str:
            current_line = int(text.index("insert").split(".")[0])
            if current_line in bookmark_lines:
                bookmark_lines.remove(current_line)
            else:
                bookmark_lines.add(current_line)
            refresh_bookmarks()
            return "break"

        def jump_bookmark(step: int) -> str:
            if not bookmark_order:
                bookmark_status_label.configure(text=t("gui.results.editor_bookmark_count_none"))
                return "break"
            current_line = int(text.index("insert").split(".")[0])
            if step > 0:
                candidates = [line for line in bookmark_order if line > current_line]
                target_line = candidates[0] if candidates else bookmark_order[0]
            else:
                candidates = [line for line in bookmark_order if line < current_line]
                target_line = candidates[-1] if candidates else bookmark_order[-1]
            text.see(f"{target_line}.0")
            text.mark_set("insert", f"{target_line}.0")
            text.focus_set()
            update_current_line()
            update_status()
            return "break"

        def focus_go_to_line(*_args: Any) -> str:
            goto_entry.focus_set()
            goto_entry.select_range(0, "end")
            goto_entry.icursor("end")
            return "break"

        def go_to_line(*_args: Any) -> str:
            raw_value = goto_var.get().strip()
            total_lines = max(1, int(text.index("end-1c").split(".")[0]))
            try:
                line_number = int(raw_value)
            except ValueError:
                goto_entry.configure(border_color="#dc2626")
                goto_status_label.configure(
                    text=t("gui.results.editor_go_to_line_invalid"),
                    text_color="#dc2626",
                )
                return "break"

            line_number = max(1, min(line_number, total_lines))
            goto_entry.configure(border_color=goto_default_border)
            goto_status_label.configure(
                text=t("gui.results.editor_go_to_line_status", line=line_number, total=total_lines),
                text_color=self.host._MUTED_TEXT,
            )
            text.see(f"{line_number}.0")
            text.mark_set("insert", f"{line_number}.0")
            text.focus_set()
            update_current_line()
            update_status()
            return "break"

        find_frame = ctk.CTkFrame(win, fg_color=("gray85", "gray22"), corner_radius=0)
        find_var = tk.StringVar()
        replace_var = tk.StringVar()
        find_case = tk.BooleanVar(value=False)
        replace_visible = [False]

        ctk.CTkLabel(find_frame, text=t("gui.results.editor_find_label"), font=ctk.CTkFont(size=12)).pack(side="left", padx=(8, 2))
        find_entry = ctk.CTkEntry(find_frame, textvariable=find_var, width=220, font=ctk.CTkFont(size=12))
        find_entry.pack(side="left", padx=4)
        ctk.CTkCheckBox(
            find_frame,
            text="Aa",
            variable=find_case,
            font=ctk.CTkFont(size=11),
            width=50,
            checkbox_width=16,
            checkbox_height=16,
        ).pack(side="left", padx=(2, 6))

        find_count_label = ctk.CTkLabel(
            find_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
        )
        find_count_label.pack(side="left", padx=4)

        replace_label = ctk.CTkLabel(find_frame, text=t("gui.results.editor_replace_with"), font=ctk.CTkFont(size=12))
        replace_entry = ctk.CTkEntry(find_frame, textvariable=replace_var, width=220, font=ctk.CTkFont(size=12))
        replace_button = ctk.CTkButton(find_frame, text=t("gui.results.editor_replace_one"), width=96)
        replace_all_button = ctk.CTkButton(find_frame, text=t("gui.results.editor_replace_all"), width=96)

        def do_find(direction: int = 1) -> None:
            text.tag_remove("find_match", "1.0", "end")
            text.tag_remove("find_cur", "1.0", "end")
            query = find_var.get()
            if not query:
                find_count_label.configure(text="")
                return
            search_positions.clear()
            position = "1.0"
            nocase = not find_case.get()
            while True:
                position = text.search(query, position, stopindex="end", nocase=nocase)
                if not position:
                    break
                end = f"{position}+{len(query)}c"
                text.tag_add("find_match", position, end)
                search_positions.append(position)
                position = end
            if not search_positions:
                find_count_label.configure(text="No results")
                find_entry.configure(border_color="red")
                return
            find_entry.configure(border_color=("gray50", "gray50"))
            search_idx[0] = (search_idx[0] + direction) % len(search_positions)
            current = search_positions[search_idx[0]]
            text.tag_remove("find_match", current, f"{current}+{len(query)}c")
            text.tag_add("find_cur", current, f"{current}+{len(query)}c")
            text.see(current)
            text.mark_set("insert", current)
            find_count_label.configure(text=f"{search_idx[0] + 1} / {len(search_positions)}")

        def replace_current() -> None:
            query = find_var.get()
            replacement = replace_var.get()
            if not query:
                return
            if not search_positions:
                do_find(1)
            if not search_positions:
                return
            current = search_positions[search_idx[0] if search_idx[0] >= 0 else 0]
            end = f"{current}+{len(query)}c"
            if text.get(current, end) != query and not find_case.get():
                if text.get(current, end).lower() != query.lower():
                    do_find(1)
                    return
            text.delete(current, end)
            text.insert(current, replacement)
            persist_editor_draft()
            refresh_sections()
            schedule_highlight()
            do_find(1)

        def replace_all() -> None:
            query = find_var.get()
            replacement = replace_var.get()
            if not query:
                return
            content = text.get("1.0", "end-1c")
            if find_case.get():
                replaced = content.replace(query, replacement)
            else:
                import re

                replaced = re.sub(re.escape(query), replacement, content, flags=re.IGNORECASE)
            if replaced == content:
                do_find(1)
                return
            text.delete("1.0", "end")
            text.insert("1.0", replaced)
            persist_editor_draft()
            refresh_sections()
            schedule_highlight()
            do_find(1)

        editor_context_menu = tk.Menu(win, tearoff=0)
        editor_context_menu.add_command(label=t("gui.results.editor_find"), command=lambda: toggle_find())
        editor_context_menu.add_command(label=t("gui.results.editor_replace"), command=lambda: toggle_find(show_replace=True))
        editor_context_menu.add_separator()
        editor_context_menu.add_command(label=t("gui.results.editor_prev_match"), command=lambda: do_find(-1))
        editor_context_menu.add_command(label=t("gui.results.editor_next_match"), command=lambda: do_find(1))
        editor_context_menu.add_separator()
        editor_context_menu.add_command(label=t("gui.results.editor_toggle_bookmark"), command=toggle_bookmark)
        editor_context_menu.add_command(label=t("gui.results.editor_prev_bookmark"), command=lambda: jump_bookmark(-1))
        editor_context_menu.add_command(label=t("gui.results.editor_next_bookmark"), command=lambda: jump_bookmark(1))
        editor_context_menu.add_separator()
        editor_context_menu.add_command(label=t("gui.results.editor_fold_section"), command=toggle_fold_current_section)
        editor_context_menu.add_command(label=t("gui.results.editor_unfold_all"), command=unfold_all_sections)
        editor_context_menu.add_separator()
        editor_context_menu.add_command(label=t("gui.results.editor_prev_page"), command=lambda: load_adjacent_page(-1))
        editor_context_menu.add_command(label=t("gui.results.editor_next_page"), command=lambda: load_adjacent_page(1))

        def show_editor_context_menu(event: Any) -> str:
            try:
                editor_context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                editor_context_menu.grab_release()
            return "break"

        ctk.CTkButton(find_frame, text="▲", width=32, command=lambda: do_find(-1)).pack(side="left", padx=2)
        ctk.CTkButton(find_frame, text="▼", width=32, command=lambda: do_find(1)).pack(side="left", padx=2)
        ctk.CTkButton(
            find_frame,
            text="✕",
            width=28,
            fg_color="transparent",
            hover_color=("gray70", "gray30"),
            command=lambda: toggle_find(),
        ).pack(side="right", padx=4)

        replace_button.configure(command=replace_current)
        replace_all_button.configure(command=replace_all)

        find_var.trace_add(
            "write",
            lambda *_: (
                search_idx.__setitem__(0, -1),
                do_find(1) if find_var.get() else find_count_label.configure(text=""),
            ),
        )
        goto_var.trace_add(
            "write",
            lambda *_: (
                goto_entry.configure(border_color=goto_default_border),
                goto_status_label.configure(text="", text_color=self.host._MUTED_TEXT),
            ),
        )
        find_entry.bind("<Return>", lambda _event: do_find(1))
        find_entry.bind("<Shift-Return>", lambda _event: do_find(-1))
        replace_entry.bind("<Return>", lambda _event: replace_current())
        goto_entry.bind("<Return>", go_to_line)

        def toggle_find(*_args: Any, show_replace: bool = False) -> None:
            if find_bar_visible[0]:
                find_frame.pack_forget()
                find_bar_visible[0] = False
                replace_visible[0] = False
                replace_label.pack_forget()
                replace_entry.pack_forget()
                replace_button.pack_forget()
                replace_all_button.pack_forget()
                text.focus_set()
            else:
                find_frame.pack(fill="x", side="bottom", before=status_bar)
                find_bar_visible[0] = True
                find_entry.focus_set()
                try:
                    selection = text.get("sel.first", "sel.last")
                    if selection and "\n" not in selection:
                        find_var.set(selection)
                        search_idx[0] = -1
                        do_find(1)
                except tk.TclError:
                    pass
            if show_replace and not replace_visible[0]:
                replace_label.pack(side="left", padx=(8, 2))
                replace_entry.pack(side="left", padx=4)
                replace_button.pack(side="left", padx=2)
                replace_all_button.pack(side="left", padx=2)
                replace_visible[0] = True
                replace_entry.focus_set()

        button_frame = ctk.CTkFrame(win, fg_color="transparent")
        button_frame.pack(pady=8, side="bottom")

        paging_frame = ctk.CTkFrame(win, fg_color=("gray88", "gray17"), corner_radius=6)
        paging_frame.grid_columnconfigure(1, weight=1)
        prev_page_button = ctk.CTkButton(paging_frame, text=t("gui.results.editor_prev_page"), width=112)
        page_status_label = ctk.CTkLabel(paging_frame, text="", anchor="w", justify="left", font=ctk.CTkFont(size=11))
        next_page_button = ctk.CTkButton(paging_frame, text=t("gui.results.editor_next_page"), width=112)
        prev_page_button.grid(row=0, column=0, padx=8, pady=8)
        page_status_label.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        next_page_button.grid(row=0, column=2, padx=8, pady=8)
        paging_frame.pack_forget()

        save_button = ctk.CTkButton(button_frame, text=t("gui.results.editor_save"), fg_color="green", hover_color="#1a7a1a", width=160)
        save_button.grid(row=0, column=0, padx=6)
        cancel_button = ctk.CTkButton(button_frame, text=t("common.cancel"), width=100)
        cancel_button.grid(row=0, column=1, padx=6)

        initial_text_reference = [""]

        def capture_active_buffer_state() -> None:
            if not editor_loaded[0]:
                return
            buffer_state = current_buffer_state()
            buffer_state["content"] = text.get("1.0", "end-1c")
            buffer_state["cursor_index"] = text.index("insert")
            buffer_state["read_only"] = editor_read_only[0]
            buffer_state["page_index"] = large_file_page_index[0]
            buffer_state["total_pages"] = large_file_total_pages[0]
            buffer_state["bookmarks"] = set(bookmark_lines)
            buffer_state["folded_sections"] = set(folded_section_starts)

        def update_paging_controls() -> None:
            buffer_state = current_buffer_state()
            if active_buffer_key[0] != "working" or int(buffer_state.get("total_pages", 1)) <= 1:
                paging_frame.pack_forget()
                return
            page_status_label.configure(
                text=t(
                    "gui.results.editor_page_status",
                    current=int(buffer_state.get("page_index", 0)) + 1,
                    total=int(buffer_state.get("total_pages", 1)),
                )
            )
            prev_page_button.configure(state="normal" if int(buffer_state.get("page_index", 0)) > 0 else "disabled")
            next_page_button.configure(
                state="normal" if int(buffer_state.get("page_index", 0)) + 1 < int(buffer_state.get("total_pages", 1)) else "disabled"
            )
            paging_frame.pack(fill="x", padx=10, pady=(6, 0), before=status_bar)

        def update_editor_interaction_state() -> None:
            buffer_state = current_buffer_state()
            editor_read_only[0] = bool(buffer_state.get("read_only", False))
            if editor_read_only[0]:
                text.configure(state="disabled")
            else:
                text.configure(state="normal")
            save_button.configure(
                state="normal" if active_buffer_key[0] == "working" and not editor_read_only[0] else "disabled"
            )
            update_paging_controls()
            update_status()

        def build_tab_button_text(buffer_key: str) -> str:
            buffer_state = buffer_states[buffer_key]
            label = str(buffer_state.get("label", buffer_key.title()))
            return label

        def tab_marker_values(buffer_key: str) -> dict[str, Any]:
            buffer_state = buffer_states[buffer_key]
            if buffer_key == active_buffer_key[0]:
                bookmark_count = len(bookmark_lines)
                folded_count = len(folded_section_starts)
            else:
                bookmark_count = len(buffer_state.get("bookmarks", set()))
                folded_count = len(buffer_state.get("folded_sections", set()))
            return {
                "dirty": buffer_key == "working" and working_buffer_dirty() and not bool(buffer_state.get("read_only", False)),
                "bookmarks": bookmark_count,
                "folds": folded_count,
            }

        def build_tab_hover_text(buffer_key: str) -> str:
            buffer_state = buffer_states[buffer_key]
            marker_values = tab_marker_values(buffer_key)
            bookmark_count = int(marker_values["bookmarks"])
            folded_count = int(marker_values["folds"])
            details = [str(buffer_state.get("label", buffer_key.title()))]
            if buffer_key == "working":
                details.append(
                    t("gui.results.editor_tab_dirty")
                    if bool(marker_values["dirty"])
                    else t("gui.results.editor_tab_clean")
                )
            else:
                details.append(t("gui.results.editor_tab_reference"))
            details.append(t("gui.results.editor_tab_bookmarks", count=bookmark_count))
            details.append(t("gui.results.editor_tab_folds", count=folded_count))
            if bool(buffer_state.get("read_only", False)):
                details.append(t("gui.results.editor_tab_read_only"))
            return "\n".join(details)

        def tab_marker_style(buffer_key: str) -> dict[str, dict[str, Any]]:
            is_active = buffer_key == active_buffer_key[0]
            marker_values = tab_marker_values(buffer_key)
            return {
                "dirty": {
                    "text": "*",
                    "visible": bool(marker_values["dirty"]),
                    "text_color": ("#c2410c", "#fdba74") if is_active else ("#9a3412", "#fb923c"),
                },
                "bookmarks": {
                    "text": f"B{int(marker_values['bookmarks'])}",
                    "visible": int(marker_values["bookmarks"]) > 0,
                    "text_color": ("#2563eb", "#93c5fd") if is_active else ("#1d4ed8", "#60a5fa"),
                },
                "folds": {
                    "text": f"F{int(marker_values['folds'])}",
                    "visible": int(marker_values["folds"]) > 0,
                    "text_color": ("#0f766e", "#5eead4") if is_active else ("#0f766e", "#2dd4bf"),
                },
            }

        def tab_visual_state(buffer_key: str) -> tuple[Any, Any, Any, int]:
            buffer_state = buffer_states[buffer_key]
            is_active = buffer_key == active_buffer_key[0]
            if buffer_key == active_buffer_key[0]:
                bookmark_count = len(bookmark_lines)
                folded_count = len(folded_section_starts)
            else:
                bookmark_count = len(buffer_state.get("bookmarks", set()))
                folded_count = len(buffer_state.get("folded_sections", set()))
            has_dirty = buffer_key == "working" and working_buffer_dirty() and not bool(buffer_state.get("read_only", False))
            has_markers = bookmark_count > 0 or folded_count > 0
            if has_dirty:
                if is_active:
                    return (("#f5d8d2", "#5b2f2b"), ("#efc3bb", "#6a3833"), ("#c2410c", "#fdba74"), 1)
                return (("#f7e8e5", "#3b2321"), ("#efd4ce", "#4a2b29"), ("#c2410c", "#fb923c"), 1)
            if has_markers:
                if is_active:
                    return (("#dce8f8", "#26384f"), ("#cdddf4", "#314766"), ("#2563eb", "#93c5fd"), 1)
                return (("#e8f0fb", "#1c2736"), ("#d8e6f8", "#243244"), ("#60a5fa", "#60a5fa"), 1)
            return (
                ("gray78", "gray28") if is_active else ("gray90", "gray18"),
                ("gray72", "gray32") if is_active else ("gray82", "gray24"),
                ("#94a3b8", "#475569"),
                0,
            )

        def refresh_tab_strip() -> None:
            for key, button in tab_buttons.items():
                fg_color, hover_color, border_color, border_width = tab_visual_state(key)
                button.configure(
                    text=build_tab_button_text(key),
                    fg_color=fg_color,
                    hover_color=hover_color,
                    text_color=("black", "white"),
                    border_color=border_color,
                    border_width=border_width,
                )
                tooltip = tab_tooltips.get(key)
                if tooltip is not None:
                    tooltip.text = build_tab_hover_text(key)
                for aux_tooltip in tab_aux_tooltips.get(key, []):
                    aux_tooltip.text = build_tab_hover_text(key)
                marker_strip = tab_marker_strips.get(key)
                markers = tab_markers.get(key, {})
                marker_style = tab_marker_style(key)
                visible_markers = 0
                for marker_name in ("dirty", "bookmarks", "folds"):
                    marker = markers.get(marker_name)
                    if marker is None:
                        continue
                    descriptor = marker_style[marker_name]
                    marker.configure(text=descriptor["text"], text_color=descriptor["text_color"])
                    if bool(descriptor["visible"]):
                        visible_markers += 1
                        if marker.winfo_manager() != "pack":
                            marker.pack(side="left", padx=(0, 4 if marker_name != "folds" else 0))
                    elif marker.winfo_manager() == "pack":
                        marker.pack_forget()
                if marker_strip is None:
                    continue
                if visible_markers:
                    if marker_strip.winfo_manager() != "pack":
                        marker_strip.pack(side="left", padx=(10, 6), before=button)
                elif marker_strip.winfo_manager() == "pack":
                    marker_strip.pack_forget()

        def load_buffer_content(buffer_key: str) -> None:
            buffer_state = buffer_states[buffer_key]
            active_buffer_key[0] = buffer_key
            bookmark_lines.clear()
            bookmark_lines.update(buffer_state.get("bookmarks", set()))
            bookmark_order[:] = sorted(bookmark_lines)
            folded_section_starts.clear()
            folded_section_starts.update(buffer_state.get("folded_sections", set()))
            large_file_page_index[0] = int(buffer_state.get("page_index", 0))
            large_file_total_pages[0] = int(buffer_state.get("total_pages", 1))
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", str(buffer_state.get("content", "")))
            refresh_sections()
            clear_syntax_tags()
            if not bool(buffer_state.get("read_only", False)):
                syntax_highlighter()
            target_insert = str(buffer_state.get("cursor_index", "1.0"))
            try:
                text.see(target_insert)
                text.mark_set("insert", target_insert)
            except Exception:
                pass
            update_editor_interaction_state()
            update_line_numbers()
            update_current_line()
            refresh_bookmarks()
            update_window_title()
            refresh_tab_strip()
            emit_addon_editor_buffer_event("buffer_switched", build_editor_hook_payload(trigger="buffer_switched"))
            schedule_addon_diagnostics("buffer_switched")
            text.focus_set()

        def build_tab_strip() -> None:
            if len(buffer_order) <= 1:
                return
            for key in buffer_order:
                item_frame = ctk.CTkFrame(tab_frame, fg_color="transparent")
                item_frame.pack(side="left", padx=(8, 0), pady=8)
                marker_strip = ctk.CTkFrame(item_frame, fg_color="transparent")
                marker_strip.bind("<Button-1>", lambda _event, buffer_key=key: switch_buffer(buffer_key))
                markers: dict[str, Any] = {}
                for marker_name in ("dirty", "bookmarks", "folds"):
                    marker = ctk.CTkLabel(
                        marker_strip,
                        text="",
                        fg_color="transparent",
                        font=ctk.CTkFont(size=10, weight="bold"),
                        anchor="w",
                        justify="left",
                    )
                    marker.bind("<Button-1>", lambda _event, buffer_key=key: switch_buffer(buffer_key))
                    markers[marker_name] = marker
                button = ctk.CTkButton(
                    item_frame,
                    text=build_tab_button_text(key),
                    width=150,
                    height=28,
                    corner_radius=6,
                    command=lambda buffer_key=key: switch_buffer(buffer_key),
                )
                button.pack(side="left")
                tab_buttons[key] = button
                tab_marker_strips[key] = marker_strip
                tab_markers[key] = markers
                tooltip = _Tooltip(button, build_tab_hover_text(key))
                tab_tooltips[key] = tooltip
                aux_tooltips = [_Tooltip(marker_strip, build_tab_hover_text(key))]
                for marker in markers.values():
                    aux_tooltips.append(_Tooltip(marker, build_tab_hover_text(key)))
                tab_aux_tooltips[key] = aux_tooltips
                setattr(button, "_acr_tooltip", tooltip)
                setattr(button, "_acr_tab_markers", markers)
            refresh_tab_strip()

        def build_editor_recovery_payload(current_content: str | None = None) -> dict[str, Any]:
            capture_active_buffer_state()
            working_state = working_buffer_state()
            return {
                "kind": "editor",
                "issue_index": idx,
                "file_path": issue.file_path,
                "display_name": fname,
                "line_number": getattr(issue, "line_number", None),
                "content": current_content if current_content is not None else str(working_state.get("content", "")),
                "original_content": initial_text_reference[0],
                "cursor_index": str(working_state.get("cursor_index", "1.0")),
                "read_only": bool(working_state.get("read_only", False)),
                "page_index": int(working_state.get("page_index", 0)),
                "active_buffer": active_buffer_key[0],
            }

        def load_large_file_page(target_page_index: int) -> None:
            if self.host._testing_mode or active_buffer_key[0] != "working":
                return
            target_page_index = max(0, min(target_page_index, large_file_total_pages[0] - 1))
            large_file_page_index[0] = target_page_index
            self._load_file_into_editor(
                window=win,
                file_path=Path(issue.file_path),
                apply_loaded_content=apply_loaded_content,
                progress_frame=progress_frame,
                progress_label=progress_label,
                progress_bar=progress_bar,
                file_label=fname,
                start_offset_bytes=target_page_index * LARGE_FILE_PAGE_BYTES,
                limit_bytes=LARGE_FILE_PAGE_BYTES,
            )

        def load_adjacent_page(step: int) -> None:
            load_large_file_page(large_file_page_index[0] + step)

        prev_page_button.configure(command=lambda: load_adjacent_page(-1))
        next_page_button.configure(command=lambda: load_adjacent_page(1))

        def persist_editor_draft() -> None:
            capture_active_buffer_state()
            working_state = working_buffer_state()
            if not editor_loaded[0] or bool(working_state.get("read_only", False)):
                return
            current_content = str(working_state.get("content", ""))
            cursor_index = str(working_state.get("cursor_index", "1.0"))
            if on_draft_change is not None:
                on_draft_change(current_content, cursor_index)
                return
            if current_content == initial_text_reference[0]:
                self.recovery_store.clear()
                return
            self.recovery_store.save_active_popup(build_editor_recovery_payload(current_content))

        def clear_editor_recovery() -> None:
            if on_discard is not None:
                on_discard()
                return
            self.recovery_store.clear()

        def switch_buffer(buffer_key: str) -> None:
            if buffer_key not in buffer_states or buffer_key == active_buffer_key[0]:
                return
            capture_active_buffer_state()
            if active_buffer_key[0] == "working":
                persist_editor_draft()
            load_buffer_content(buffer_key)

        def cycle_buffer(step: int) -> str:
            if len(buffer_order) <= 1:
                return "break"
            try:
                current_index = buffer_order.index(active_buffer_key[0])
            except ValueError:
                current_index = 0
            switch_buffer(buffer_order[(current_index + step) % len(buffer_order)])
            return "break"

        def jump_to_buffer(buffer_index: int) -> str:
            if 0 <= buffer_index < len(buffer_order):
                switch_buffer(buffer_order[buffer_index])
            return "break"

        def bind_tab_cycle_shortcut(sequence: str, step: int) -> None:
            handler = lambda _event: cycle_buffer(step)
            for widget in (win, text, find_entry, replace_entry, goto_entry, symbol_menu):
                widget.bind(sequence, handler, add="+")

        def bind_buffer_jump_shortcuts() -> None:
            for shortcut_index in range(1, 10):
                sequence = f"<Control-Key-{shortcut_index}>"
                handler = lambda _event, buffer_index=shortcut_index - 1: jump_to_buffer(buffer_index)
                for widget in (win, text, find_entry, replace_entry, goto_entry, symbol_menu):
                    widget.bind(sequence, handler, add="+")

        def save() -> None:
            capture_active_buffer_state()
            working_state = working_buffer_state()
            if bool(working_state.get("read_only", False)):
                clear_editor_recovery()
                win.destroy()
                return
            content_out = str(working_state.get("content", "")).rstrip("\n") + "\n"
            if on_save is not None:
                on_save(content_out)
                emit_addon_editor_buffer_event("buffer_saved", build_editor_hook_payload(trigger="buffer_saved"))
                emit_addon_patch_applied_event(
                    {
                        "source": "editor_save",
                        "issue_index": idx,
                        "file_path": issue.file_path,
                        "display_name": fname,
                        "content": content_out,
                        "write_performed": False,
                        "testing_mode": self.host._testing_mode,
                    }
                )
                cancel_popup_timers()
                clear_editor_recovery()
                win.destroy()
                return
            if self.host._testing_mode:
                issue.set_resolution(
                    status="resolved",
                    provenance="builtin_editor",
                    resolved_at=datetime.datetime.now(),
                )
                self.host._refresh_status(idx)
                self.host._show_toast(t("gui.results.editor_saved"))
                emit_addon_editor_buffer_event("buffer_saved", build_editor_hook_payload(trigger="buffer_saved"))
                emit_addon_patch_applied_event(
                    {
                        "source": "editor_save",
                        "issue_index": idx,
                        "file_path": issue.file_path,
                        "display_name": fname,
                        "content": content_out,
                        "write_performed": False,
                        "testing_mode": True,
                    }
                )
                cancel_popup_timers()
                clear_editor_recovery()
                win.destroy()
                return
            try:
                with open(issue.file_path, "w", encoding="utf-8") as handle:
                    handle.write(content_out)
                issue.set_resolution(
                    status="resolved",
                    provenance="builtin_editor",
                    resolved_at=datetime.datetime.now(),
                )
                self.host._refresh_status(idx)
                self.host._show_toast(t("gui.results.editor_saved"))
                emit_addon_editor_buffer_event("buffer_saved", build_editor_hook_payload(trigger="buffer_saved"))
                emit_addon_patch_applied_event(
                    {
                        "source": "editor_save",
                        "issue_index": idx,
                        "file_path": issue.file_path,
                        "display_name": fname,
                        "content": content_out,
                        "write_performed": True,
                        "testing_mode": False,
                    }
                )
            except Exception as exc:
                self.host._show_toast(str(exc), error=True)
                return
            cancel_popup_timers()
            clear_editor_recovery()
            win.destroy()

        def cancel() -> None:
            capture_active_buffer_state()
            if editor_loaded[0] and working_buffer_dirty():
                if not ConfirmDialog(
                    win,
                    title=t("gui.results.editor_discard_title"),
                    message=t("gui.results.editor_discard_msg"),
                ).confirmed:
                    return
            emit_addon_editor_buffer_event("buffer_closed", build_editor_hook_payload(trigger="buffer_closed"))
            cancel_popup_timers()
            clear_editor_recovery()
            win.destroy()

        save_button.configure(command=save)
        cancel_button.configure(command=cancel)

        build_tab_strip()

        def on_key(*_args: Any) -> None:
            capture_active_buffer_state()
            update_line_numbers()
            update_current_line()
            persist_editor_draft()
            schedule_highlight()
            refresh_sections()
            update_window_title()
            schedule_addon_diagnostics("key_release")

        text.bind("<KeyRelease>", on_key)
        text.bind("<ButtonRelease-1>", lambda _event: (update_current_line(), persist_editor_draft()))
        text.bind("<Configure>", update_line_numbers)
        text.bind("<MouseWheel>", lambda _event: self.host._schedule_popup_after(win, 10, update_line_numbers))
        text.bind("<Tab>", lambda _event: (text.insert("insert", "    "), "break")[1])
        text.bind("<Button-3>", show_editor_context_menu)
        line_numbers.bind("<Button-3>", show_editor_context_menu)

        def apply_loaded_content(payload: LoadedTextPayload) -> None:
            loaded_payload[0] = payload
            initial_text_reference[0] = payload.content
            working_state = working_buffer_state()
            working_state["content"] = payload.content
            working_state["read_only"] = payload.truncated
            working_state["page_index"] = payload.page_index
            working_state["total_pages"] = payload.total_pages
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", payload.content)
            refresh_sections()
            if payload.truncated:
                editor_read_only[0] = True
                text.configure(state="disabled")
                current_file_size_bytes[0] = payload.source_size_bytes
                large_file_page_index[0] = payload.page_index
                large_file_total_pages[0] = payload.total_pages
                progress_label.configure(
                    text=t(
                        "gui.results.large_file_truncated_paged",
                        file=fname,
                        current=payload.page_index + 1,
                        total_pages=payload.total_pages,
                        loaded_mb=max(1, round(payload.loaded_size_bytes / (1024 * 1024), 1)),
                        total_mb=max(1, round(payload.source_size_bytes / (1024 * 1024), 1)),
                    )
                )
                progress_bar.set(1)
                progress_frame.pack(fill="x", padx=10, pady=(6, 0), before=toolbar)
                update_paging_controls()
            else:
                text.configure(state="normal")
                progress_frame.pack_forget()
                large_file_page_index[0] = 0
                large_file_total_pages[0] = 1
                paging_frame.pack_forget()
            clear_syntax_tags()
            if not payload.truncated:
                syntax_highlighter()
            update_line_numbers()
            target_insert = None
            if recovery_state and isinstance(recovery_state.get("cursor_index"), str):
                target_insert = recovery_state["cursor_index"]
            elif not self.host._testing_mode and getattr(issue, "line_number", None):
                target_insert = f"{issue.line_number}.0"
            if target_insert:
                try:
                    text.see(target_insert)
                    text.mark_set("insert", target_insert)
                except Exception:
                    pass
            working_state["cursor_index"] = text.index("insert")
            editor_loaded[0] = True
            update_current_line()
            update_status()
            refresh_bookmarks()
            update_editor_interaction_state()
            update_window_title()
            emit_addon_editor_buffer_event("buffer_opened", build_editor_hook_payload(trigger="buffer_opened"))
            schedule_addon_diagnostics("buffer_opened")
            text.focus_set()

        def restore_inline_content() -> None:
            if initial_content is not None:
                inline_page_index = int(recovery_state.get("page_index", 0)) if recovery_state else 0
                apply_loaded_content(self._payload_from_inline_content(initial_content, page_index=inline_page_index))
                return
            if self.host._testing_mode:
                apply_loaded_content(self._payload_from_inline_content(issue.code_snippet or "(no code snippet)"))
                return
            self._load_file_into_editor(
                window=win,
                file_path=Path(issue.file_path),
                apply_loaded_content=apply_loaded_content,
                progress_frame=progress_frame,
                progress_label=progress_label,
                progress_bar=progress_bar,
                file_label=fname,
            )

        restore_inline_content()
        if requested_active_buffer in buffer_states and requested_active_buffer != "working":
            switch_buffer(requested_active_buffer)
        else:
            refresh_tab_strip()
            update_window_title()

        win.bind("<Control-s>", lambda _event: save())
        win.bind("<Control-S>", lambda _event: save())
        win.bind("<Control-f>", lambda _event: toggle_find())
        win.bind("<Control-F>", lambda _event: toggle_find())
        win.bind("<Control-h>", lambda _event: toggle_find(show_replace=True))
        win.bind("<Control-H>", lambda _event: toggle_find(show_replace=True))
        win.bind("<F3>", lambda _event: do_find(1))
        win.bind("<Shift-F3>", lambda _event: do_find(-1))
        win.bind("<Control-g>", focus_go_to_line)
        win.bind("<Control-G>", focus_go_to_line)
        win.bind("<Control-F2>", toggle_bookmark)
        win.bind("<F2>", lambda _event: jump_bookmark(1))
        win.bind("<Shift-F2>", lambda _event: jump_bookmark(-1))
        bind_tab_cycle_shortcut("<Control-Tab>", 1)
        bind_tab_cycle_shortcut("<Control-Shift-Tab>", -1)
        bind_tab_cycle_shortcut("<Control-ISO_Left_Tab>", -1)
        bind_buffer_jump_shortcuts()
        win.bind("<Control-Prior>", lambda _event: load_adjacent_page(-1))
        win.bind("<Control-Next>", lambda _event: load_adjacent_page(1))
        win.bind("<Escape>", lambda _event: (toggle_find() if find_bar_visible[0] else cancel()))
        win.bind("<Control-w>", lambda _event: cancel())
        win.protocol("WM_DELETE_WINDOW", cancel)

    def show_diff_preview(
        self,
        *,
        file_path: str,
        new_content: str,
        filename: str,
        idx: int = 0,
        on_content_update: Any = None,
        ai_fix_content: str | None = None,
        recovery_state: dict[str, Any] | None = None,
        on_preview_state_change: Callable[[dict[str, Any] | None], None] | None = None,
        on_preview_closed: Callable[[], None] | None = None,
    ) -> None:
        active_content = str(recovery_state.get("current_content", new_content)) if recovery_state else new_content
        active_ai_fix_content = (
            str(recovery_state.get("ai_fix_content"))
            if recovery_state and recovery_state.get("ai_fix_content") is not None
            else (ai_fix_content if ai_fix_content is not None else new_content)
        )

        win = ctk.CTkToplevel(self.host)
        win.title(t("gui.results.diff_preview_title", file=filename))
        win.geometry("1100x700")
        win.grab_set()
        self.host._schedule_titlebar_fix(win)
        win.bind("<Control-w>", lambda _event: close_preview())

        ctk.CTkLabel(
            win,
            text=t("gui.results.diff_preview_header", file=filename),
            font=ctk.CTkFont(weight="bold", size=14),
        ).pack(padx=10, pady=(10, 4))

        progress_frame = ctk.CTkFrame(win, fg_color=("#e0f2fe", "#0f172a"), corner_radius=6)
        progress_frame.pack(fill="x", padx=10, pady=(0, 4))
        progress_frame.grid_columnconfigure(0, weight=1)
        progress_label = ctk.CTkLabel(
            progress_frame,
            text=t("gui.results.large_file_loading", file=filename),
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=11),
        )
        progress_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        progress_bar = ctk.CTkProgressBar(progress_frame)
        progress_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        progress_bar.set(0)
        progress_frame.pack_forget()

        nav_bar = ctk.CTkFrame(win, fg_color="transparent")
        nav_bar.pack(fill="x", padx=10, pady=(0, 4))

        previous_change_button = ctk.CTkButton(
            nav_bar,
            text=t("gui.results.diff_prev_change"),
            width=120,
            height=28,
            command=lambda: jump_to_change(-1),
        )
        previous_change_button.pack(side="left")

        next_change_button = ctk.CTkButton(
            nav_bar,
            text=t("gui.results.diff_next_change"),
            width=120,
            height=28,
            command=lambda: jump_to_change(1),
        )
        next_change_button.pack(side="left", padx=(6, 0))

        change_count_label = ctk.CTkLabel(
            nav_bar,
            text=t("gui.results.diff_change_count_none"),
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        change_count_label.pack(side="left", padx=(10, 0))

        preview_page_index = [int(recovery_state.get("page_index", 0)) if recovery_state else 0]
        preview_total_pages = [1]

        prev_page_button = ctk.CTkButton(
            nav_bar,
            text=t("gui.results.editor_prev_page"),
            width=96,
            height=28,
        )
        prev_page_button.pack(side="right")

        next_page_button = ctk.CTkButton(
            nav_bar,
            text=t("gui.results.editor_next_page"),
            width=96,
            height=28,
        )
        next_page_button.pack(side="right", padx=(6, 0))

        page_status_label = ctk.CTkLabel(
            nav_bar,
            text=t("gui.results.diff_page_status", current=1, total=1),
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        page_status_label.pack(side="right", padx=(0, 10))

        preview_shortcuts_label = ctk.CTkLabel(
            nav_bar,
            text=t("gui.results.diff_shortcuts"),
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        preview_shortcuts_label.pack(side="left", padx=(12, 0))

        preview_status_label = ctk.CTkLabel(
            nav_bar,
            text="",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        preview_status_label.pack(side="left", padx=(12, 0))

        is_dark = ctk.get_appearance_mode().lower() == "dark"
        bg_color = "#1e1e1e" if is_dark else "#ffffff"
        fg_color = "#d4d4d4" if is_dark else "#1e1e1e"
        header_bg = "#252526" if is_dark else "#f0f0f0"
        header_fg = "#cccccc" if is_dark else "#444444"
        sash_color = "#555555" if is_dark else "#bbbbbb"

        outer_row = tk.Frame(win, bg=bg_color)
        outer_row.pack(fill="both", expand=True, padx=10, pady=4)
        outer_row.columnconfigure(0, weight=1)
        outer_row.rowconfigure(0, weight=1)

        paned = tk.PanedWindow(
            outer_row,
            orient="horizontal",
            bg=sash_color,
            sashwidth=6,
            sashcursor="sb_h_double_arrow",
            bd=0,
            opaqueresize=True,
        )
        paned.grid(row=0, column=0, sticky="nsew")

        vertical_scrollbar = ctk.CTkScrollbar(outer_row, orientation="vertical")
        vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        vertical_scrollbar_visible = [True]

        syncing = [False]
        all_texts: list[tk.Text] = []
        left_tags: list[str] = []
        right_tags: list[str] = []
        change_lines: list[int] = []
        current_change_index = [int(recovery_state.get("change_index", -1)) if recovery_state else -1]
        left_text_ref: list[tk.Text | None] = [None]
        right_text_ref: list[tk.Text | None] = [None]
        right_label_ref: list[Any] = [None]
        preview_panes: list[dict[str, Any]] = []
        preview_shortcut_targets: list[Any] = [win]
        preview_shortcut_specs: list[tuple[str, Callable[[Any], str]]] = []
        active_preview_pane_name = [str(recovery_state.get("active_pane", "original")) if recovery_state else "original"]
        close_button_ref: list[Any] = [None]
        user_text_ref: list[tk.Text | None] = [None]
        user_frame_ref: list[tk.Frame | None] = [None]
        undo_button_ref: list[Any] = [None]
        original_payload_ref: list[LoadedTextPayload | None] = [None]
        active_editor_payload = [dict(recovery_state.get("active_editor", {})) if recovery_state else None]
        active_display_content = [active_content]
        preview_editable = [True]
        preview_diagnostics_timer: list[Any] = [None]
        preview_opened_emitted = [False]

        preview_diagnostics_frame = ctk.CTkFrame(win, fg_color=("#ecfccb", "#1f3a21"), corner_radius=6)
        preview_diagnostics_label = ctk.CTkLabel(
            preview_diagnostics_frame,
            text="",
            anchor="w",
            justify="left",
            wraplength=1020,
            font=ctk.CTkFont(size=11),
            text_color=("#365314", "#d9f99d"),
        )
        preview_diagnostics_label.pack(fill="x", padx=10, pady=6)

        setattr(win, "_acr_preview_panes", preview_panes)
        setattr(win, "_acr_preview_active_pane", active_preview_pane_name[0])
        setattr(win, "_acr_preview_status_label", preview_status_label)

        def build_preview_hook_payload(*, trigger: str, current_content: str | None = None, target_line: int | None = None) -> dict[str, Any]:
            content_value = current_content if current_content is not None else active_display_content[0]
            return {
                "trigger": trigger,
                "surface": "diff_preview",
                "issue_index": idx,
                "file_path": file_path,
                "display_name": filename,
                "current_content": content_value,
                "ai_fix_content": active_ai_fix_content,
                "page_index": preview_page_index[0],
                "total_pages": preview_total_pages[0],
                "change_index": current_change_index[0],
                "change_count": len(change_lines),
                "target_line": target_line,
                "editable": preview_editable[0],
                "edited": content_value.rstrip("\n") != active_ai_fix_content.rstrip("\n"),
                "has_active_editor": active_editor_payload[0] is not None,
                "active_pane": active_preview_pane_name[0],
            }

        def render_preview_diagnostics(trigger: str) -> None:
            diagnostics = collect_addon_editor_diagnostics(build_preview_hook_payload(trigger=trigger))
            if not diagnostics:
                preview_diagnostics_frame.pack_forget()
                preview_diagnostics_label.configure(text="")
                return
            messages = []
            max_severity = "info"
            for diagnostic in diagnostics:
                messages.append(f"[{diagnostic.addon_id}] {diagnostic.message}")
                if diagnostic.severity.lower() == "error":
                    max_severity = "error"
                elif diagnostic.severity.lower() == "warning" and max_severity != "error":
                    max_severity = "warning"
            preview_diagnostics_label.configure(
                text="   ".join(messages),
                text_color=("#991b1b", "#fecaca") if max_severity == "error" else (("#7c2d12", "#fde68a") if max_severity == "warning" else ("#365314", "#d9f99d")),
            )
            preview_diagnostics_frame.pack(fill="x", padx=10, pady=(0, 4), before=outer_row)

        def schedule_preview_diagnostics(trigger: str) -> None:
            if self.host._testing_mode:
                render_preview_diagnostics(trigger)
                return
            if preview_diagnostics_timer[0]:
                win.after_cancel(preview_diagnostics_timer[0])
            preview_diagnostics_timer[0] = self.host._schedule_popup_after(
                win,
                180,
                lambda: render_preview_diagnostics(trigger),
            )

        def cancel_preview_timers() -> None:
            if preview_diagnostics_timer[0]:
                try:
                    win.after_cancel(preview_diagnostics_timer[0])
                except tk.TclError:
                    pass
                preview_diagnostics_timer[0] = None

        def build_preview_state(current_content: str | None = None, active_editor: dict[str, Any] | None = None) -> dict[str, Any]:
            return {
                "issue_index": idx,
                "file_path": file_path,
                "filename": filename,
                "current_content": current_content if current_content is not None else active_display_content[0],
                "ai_fix_content": active_ai_fix_content,
                "change_index": current_change_index[0],
                "page_index": preview_page_index[0],
                "active_pane": active_preview_pane_name[0],
                "active_editor": active_editor,
            }

        def register_preview_shortcut_target(widget: Any) -> None:
            if widget in preview_shortcut_targets:
                return
            preview_shortcut_targets.append(widget)
            for sequence, handler in preview_shortcut_specs:
                widget.bind(sequence, handler, add="+")

        def bind_preview_shortcut(sequence: str, handler: Callable[[Any], str]) -> None:
            preview_shortcut_specs.append((sequence, handler))
            for widget in preview_shortcut_targets:
                widget.bind(sequence, handler, add="+")

        def visible_preview_panes() -> list[dict[str, Any]]:
            return [pane for pane in preview_panes if bool(pane.get("visible", False))]

        def build_preview_status_text() -> str:
            pane_labels = {
                "original": t("gui.results.diff_pane_original"),
                "fixed": t("gui.results.diff_pane_fixed"),
                "user_fixed": t("gui.results.diff_pane_user_fixed"),
            }
            parts = [pane_labels.get(active_preview_pane_name[0], active_preview_pane_name[0].replace("_", " ").title())]
            if change_lines:
                parts.append(
                    t(
                        "gui.results.diff_status_change",
                        current=max(current_change_index[0], 0) + 1,
                        total=len(change_lines),
                    )
                )
            else:
                parts.append(t("gui.results.diff_status_no_changes"))
            if preview_total_pages[0] > 1:
                parts.append(
                    t(
                        "gui.results.diff_status_page",
                        current=preview_page_index[0] + 1,
                        total=preview_total_pages[0],
                    )
                )
            return "  ·  ".join(parts)

        def update_preview_status_label() -> None:
            preview_status_label.configure(text=build_preview_status_text())

        def update_preview_focus_state(active_name: str | None = None) -> None:
            visible_panes = visible_preview_panes()
            if not visible_panes:
                return
            visible_names = {str(pane["name"]) for pane in visible_panes}
            if active_name is None or active_name not in visible_names:
                active_name = active_preview_pane_name[0]
                if active_name not in visible_names:
                    active_name = str(visible_panes[0]["name"])
            active_preview_pane_name[0] = active_name
            setattr(win, "_acr_preview_active_pane", active_name)
            for pane in preview_panes:
                label_widget = pane.get("label")
                if label_widget is None:
                    continue
                if pane.get("name") == active_name and bool(pane.get("visible", False)):
                    label_widget.configure(
                        bg="#dce8f8" if not is_dark else "#26384f",
                        fg="#1f2937" if not is_dark else "#eff6ff",
                    )
                else:
                    label_widget.configure(bg=header_bg, fg=header_fg)
            update_preview_status_label()

        def focus_preview_pane_by_index(pane_index: int) -> str:
            visible_panes = visible_preview_panes()
            if not visible_panes or not (0 <= pane_index < len(visible_panes)):
                return "break"
            target_pane = visible_panes[pane_index]
            try:
                target_pane["text"].focus_set()
            except Exception:
                pass
            update_preview_focus_state(str(target_pane["name"]))
            emit_preview_state(active_editor=active_editor_payload[0])
            return "break"

        def cycle_preview_pane(step: int) -> str:
            visible_panes = visible_preview_panes()
            if len(visible_panes) <= 1:
                return "break"
            pane_names = [str(pane["name"]) for pane in visible_panes]
            try:
                current_index = pane_names.index(active_preview_pane_name[0])
            except ValueError:
                current_index = 0
            return focus_preview_pane_by_index((current_index + step) % len(visible_panes))

        def jump_preview_pane(pane_number: int) -> str:
            return focus_preview_pane_by_index(pane_number - 1)

        def emit_preview_state(current_content: str | None = None, active_editor: dict[str, Any] | None = None) -> None:
            if on_preview_state_change is None:
                return
            on_preview_state_change(build_preview_state(current_content, active_editor))

        def clear_preview_state() -> None:
            if on_preview_closed is not None:
                on_preview_closed()

        def update_change_count() -> None:
            if not change_lines:
                change_count_label.configure(text=t("gui.results.diff_change_count_none"))
                update_preview_status_label()
                return
            current_position = max(current_change_index[0], 0) + 1
            change_count_label.configure(
                text=t("gui.results.diff_change_count", current=current_position, total=len(change_lines))
            )
            update_preview_status_label()

        def update_preview_page_controls() -> None:
            total_pages = max(preview_total_pages[0], 1)
            current_page = min(preview_page_index[0], total_pages - 1)
            preview_page_index[0] = current_page
            page_status_label.configure(
                text=t("gui.results.diff_page_status", current=current_page + 1, total=total_pages)
            )
            update_preview_status_label()
            if total_pages <= 1:
                prev_page_button.configure(state="disabled")
                next_page_button.configure(state="disabled")
                return
            prev_page_button.configure(state="normal" if current_page > 0 else "disabled")
            next_page_button.configure(state="normal" if current_page + 1 < total_pages else "disabled")

        def jump_to_change(step: int) -> None:
            if not change_lines:
                return
            current_change_index[0] = (current_change_index[0] + step) % len(change_lines)
            line_number = change_lines[current_change_index[0]]
            for text_widget in all_texts:
                text_widget.see(f"{line_number}.0")
            update_change_count()
            emit_addon_editor_event(
                "change_navigation",
                build_preview_hook_payload(trigger="change_navigation", target_line=line_number),
            )
            emit_preview_state(active_editor=active_editor_payload[0])

        def on_vertical_scroll(*args: Any) -> None:
            for text_widget in all_texts:
                text_widget.yview(*args)

        vertical_scrollbar.configure(command=on_vertical_scroll)

        def sync_vertical_scroll(source: tk.Text, first: str, last: str) -> None:
            lo, hi = float(first), float(last)
            if lo <= 0.0 and hi >= 1.0:
                if vertical_scrollbar_visible[0]:
                    vertical_scrollbar.grid_remove()
                    vertical_scrollbar_visible[0] = False
            else:
                if not vertical_scrollbar_visible[0]:
                    vertical_scrollbar.grid()
                    vertical_scrollbar_visible[0] = True
                vertical_scrollbar.set(first, last)
            if not syncing[0]:
                syncing[0] = True
                for text_widget in all_texts:
                    if text_widget is not source:
                        text_widget.yview("moveto", first)
                syncing[0] = False

        def make_diff_pane(header: str, pane_name: str) -> tuple[tk.Text, tk.Label]:
            frame = tk.Frame(paned, bg=bg_color)
            frame.rowconfigure(1, weight=1)
            frame.columnconfigure(0, weight=1)
            paned.add(frame, stretch="always", minsize=150)

            label = tk.Label(
                frame,
                text=header,
                bg=header_bg,
                fg=header_fg,
                font=("Consolas", 10, "bold"),
                anchor="w",
                padx=8,
                pady=3,
            )
            label.grid(row=0, column=0, sticky="ew")

            text_widget = tk.Text(
                frame,
                wrap="none",
                font=("Consolas", 11),
                bg=bg_color,
                fg=fg_color,
                insertbackground=fg_color,
                selectbackground="#264f78",
                relief="flat",
                borderwidth=0,
                exportselection=False,
                takefocus=1,
            )
            text_widget.grid(row=1, column=0, sticky="nsew")
            text_widget.tag_configure("rem", background="#4b1010" if is_dark else "#ffcccc", foreground="#ff6b6b" if is_dark else "#8b0000")
            text_widget.tag_configure("add", background="#1e4620" if is_dark else "#ccffcc", foreground="#57d15b" if is_dark else "#006400")
            text_widget.tag_configure("pad", background="#2a2a2a" if is_dark else "#efefef")

            horizontal_scrollbar = ctk.CTkScrollbar(frame, orientation="horizontal", command=text_widget.xview)
            horizontal_scrollbar.grid(row=2, column=0, sticky="ew")
            horizontal_scrollbar.grid_remove()

            def xscroll(first: str, last: str, _scrollbar: Any = horizontal_scrollbar) -> None:
                if float(first) <= 0.0 and float(last) >= 1.0:
                    _scrollbar.grid_remove()
                else:
                    _scrollbar.grid()
                _scrollbar.set(first, last)

            text_widget.configure(xscrollcommand=xscroll)
            all_texts.append(text_widget)
            preview_panes.append(
                {
                    "name": pane_name,
                    "frame": frame,
                    "label": label,
                    "text": text_widget,
                    "visible": True,
                }
            )
            register_preview_shortcut_target(text_widget)
            return text_widget, label

        left_text, _ = make_diff_pane("  ─  original", "original")
        right_text, right_label = make_diff_pane("  +  fixed", "fixed")
        left_text_ref[0] = left_text
        right_text_ref[0] = right_text
        right_label_ref[0] = right_label

        left_text.configure(yscrollcommand=lambda first, last: sync_vertical_scroll(left_text, first, last))
        right_text.configure(yscrollcommand=lambda first, last: sync_vertical_scroll(right_text, first, last))

        def render_user_pane(user_content: str) -> None:
            user_text = user_text_ref[0]
            if user_text is None:
                return
            user_text.configure(state="normal")
            user_text.delete("1.0", "end")
            ai_lines = active_ai_fix_content.splitlines()
            user_lines = user_content.splitlines()
            matcher = difflib.SequenceMatcher(None, ai_lines, user_lines, autojunk=False)
            for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
                if opcode == "equal":
                    for line in user_lines[j1:j2]:
                        user_text.insert("end", line + "\n")
                elif opcode in {"replace", "insert"}:
                    left_block = ai_lines[i1:i2]
                    right_block = user_lines[j1:j2]
                    for index in range(max(len(left_block), len(right_block))):
                        line = right_block[index] if index < len(right_block) else ""
                        tag = "add" if index < len(right_block) else "pad"
                        user_text.insert("end", line + "\n", tag)
                elif opcode == "delete":
                    for _line in ai_lines[i1:i2]:
                        user_text.insert("end", "\n", "pad")
            user_text.configure(state="disabled")

        def undo_user_changes() -> None:
            active_display_content[0] = active_ai_fix_content
            active_editor_payload[0] = None
            if user_frame_ref[0] is not None:
                if user_text_ref[0] in all_texts:
                    all_texts.remove(user_text_ref[0])
                paned.remove(user_frame_ref[0])
                for pane in preview_panes:
                    if pane.get("name") == "user_fixed":
                        pane["visible"] = False
                user_frame_ref[0] = None
                user_text_ref[0] = None
            if undo_button_ref[0] is not None:
                undo_button_ref[0].grid_remove()
                undo_button_ref[0] = None
            if right_label_ref[0] is not None:
                right_label_ref[0].configure(text="  +  fixed")
            if close_button_ref[0] is not None:
                close_button_ref[0].configure(
                    text=t("common.close"),
                    fg_color=("#3b3b3b", "#565b5e"),
                    hover_color=("gray70", "gray30"),
                    command=close_preview,
                )
            update_preview_focus_state()
            schedule_preview_diagnostics("preview_reset")
            emit_preview_state(current_content=active_ai_fix_content, active_editor=None)

        def save_and_close() -> None:
            content = active_display_content[0]
            if not content:
                close_preview()
                return
            if on_content_update is not None:
                emit_addon_editor_event(
                    "preview_staged",
                    build_preview_hook_payload(trigger="preview_staged", current_content=content),
                )
                on_content_update(content)
                self.host._show_toast(t("gui.results.preview_staged"))
                close_preview()
                return
            close_preview()

        def on_editor_save(user_content: str) -> None:
            active_display_content[0] = user_content
            active_editor_payload[0] = None
            if user_content.rstrip("\n") == active_ai_fix_content.rstrip("\n"):
                undo_user_changes()
                return
            if user_text_ref[0] is None:
                user_text, _ = make_diff_pane("  ✎  ai + user fixed", "user_fixed")
                user_text_ref[0] = user_text
                user_frame_ref[0] = user_text.master
                user_text.configure(yscrollcommand=lambda first, last: sync_vertical_scroll(user_text, first, last))
                if right_label_ref[0] is not None:
                    right_label_ref[0].configure(text="  +  ai fixed")
                undo_button = ctk.CTkButton(
                    button_frame,
                    text="↩  Undo User Changes",
                    fg_color=("gray75", "gray30"),
                    hover_color=("gray60", "gray20"),
                    command=undo_user_changes,
                )
                undo_button.grid(row=0, column=2, padx=6)
                undo_button_ref[0] = undo_button
                if close_button_ref[0] is not None:
                    close_button_ref[0].configure(
                        text="✔  Save and Close",
                        fg_color="green",
                        hover_color="#1a7a1a",
                        command=save_and_close,
                    )
            for pane in preview_panes:
                if pane.get("name") == "user_fixed":
                    pane["visible"] = True
            render_user_pane(user_content)
            update_preview_focus_state(active_preview_pane_name[0])
            schedule_preview_diagnostics("preview_edited")
            emit_preview_state(current_content=user_content, active_editor=None)

        def on_editor_draft_change(current_content: str, cursor_index: str) -> None:
            active_display_content[0] = current_content
            active_editor_payload[0] = {
                "content": current_content,
                "cursor_index": cursor_index,
            }
            emit_preview_state(current_content=current_content, active_editor=active_editor_payload[0])

        def clear_editor_draft() -> None:
            active_editor_payload[0] = None
            schedule_preview_diagnostics("preview_editor_closed")
            emit_preview_state(active_editor=None)

        def open_editor() -> None:
            if not preview_editable[0]:
                return
            try:
                self.host._open_builtin_editor(
                    idx,
                    _initial_content=active_display_content[0],
                    _on_save=on_editor_save,
                    _recovery_state=active_editor_payload[0],
                    _on_draft_change=on_editor_draft_change,
                    _on_discard=clear_editor_draft,
                )
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                self.host._open_builtin_editor(
                    idx,
                    _initial_content=active_display_content[0],
                    _on_save=on_editor_save,
                )

        button_frame = ctk.CTkFrame(win, fg_color="transparent")
        button_frame.pack(pady=8)

        edit_button = ctk.CTkButton(button_frame, text="✎  Edit", command=open_editor)
        edit_button.grid(row=0, column=0, padx=6)
        close_button = ctk.CTkButton(button_frame, text=t("common.close"), command=lambda: close_preview())
        close_button.grid(row=0, column=1, padx=6)
        close_button_ref[0] = close_button
        for widget in (edit_button, close_button, previous_change_button, next_change_button, prev_page_button, next_page_button):
            register_preview_shortcut_target(widget)

        def close_preview() -> None:
            cancel_preview_timers()
            clear_preview_state()
            win.destroy()

        def load_preview_page(target_page_index: int) -> None:
            preview_page_index[0] = max(0, target_page_index)
            if self.host._testing_mode:
                original_payload = self._payload_from_inline_content(
                    self.host._issue_cards[idx]["issue"].code_snippet or "",
                    page_index=preview_page_index[0],
                    limit_bytes=LARGE_FILE_PAGE_BYTES,
                )
                populate_diff(original_payload)
                return
            self._load_file_into_editor(
                window=win,
                file_path=Path(file_path),
                apply_loaded_content=populate_diff,
                progress_frame=progress_frame,
                progress_label=progress_label,
                progress_bar=progress_bar,
                file_label=filename,
                start_offset_bytes=preview_page_index[0] * LARGE_FILE_PAGE_BYTES,
                limit_bytes=LARGE_FILE_PAGE_BYTES,
            )

        prev_page_button.configure(command=lambda: load_preview_page(preview_page_index[0] - 1))
        next_page_button.configure(command=lambda: load_preview_page(preview_page_index[0] + 1))

        def populate_diff(original_payload: LoadedTextPayload) -> None:
            original_payload_ref[0] = original_payload
            original_lines = original_payload.content.splitlines()
            candidate_payload = self._payload_from_inline_content(
                active_display_content[0],
                page_index=preview_page_index[0],
                limit_bytes=LARGE_FILE_PAGE_BYTES,
            )
            preview_page_index[0] = max(original_payload.page_index, candidate_payload.page_index)
            preview_total_pages[0] = max(original_payload.total_pages, candidate_payload.total_pages, 1)
            update_preview_page_controls()
            if candidate_payload.truncated or original_payload.truncated:
                preview_editable[0] = True
                edit_button.configure(state="normal")
                progress_label.configure(
                    text=t(
                        "gui.results.large_file_preview_paged",
                        file=filename,
                        current=preview_page_index[0] + 1,
                        total=preview_total_pages[0],
                    )
                )
                progress_bar.set(1)
                progress_frame.pack(fill="x", padx=10, pady=(0, 4), before=nav_bar)
            else:
                preview_editable[0] = True
                edit_button.configure(state="normal")
                progress_frame.pack_forget()

            left_lines: list[str] = []
            right_lines: list[str] = []
            left_tags.clear()
            right_tags.clear()

            matcher = difflib.SequenceMatcher(None, original_lines, candidate_payload.content.splitlines(), autojunk=False)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal":
                    for index in range(i2 - i1):
                        left_lines.append(original_lines[i1 + index])
                        right_lines.append(candidate_payload.content.splitlines()[j1 + index])
                        left_tags.append("ctx")
                        right_tags.append("ctx")
                elif tag == "replace":
                    left_block = original_lines[i1:i2]
                    right_block = candidate_payload.content.splitlines()[j1:j2]
                    for index in range(max(len(left_block), len(right_block))):
                        left_lines.append(left_block[index] if index < len(left_block) else "")
                        right_lines.append(right_block[index] if index < len(right_block) else "")
                        left_tags.append("rem" if index < len(left_block) else "pad")
                        right_tags.append("add" if index < len(right_block) else "pad")
                elif tag == "delete":
                    for index in range(i2 - i1):
                        left_lines.append(original_lines[i1 + index])
                        right_lines.append("")
                        left_tags.append("rem")
                        right_tags.append("pad")
                elif tag == "insert":
                    for index in range(j2 - j1):
                        left_lines.append("")
                        right_lines.append(candidate_payload.content.splitlines()[j1 + index])
                        left_tags.append("pad")
                        right_tags.append("add")

            change_lines.clear()
            change_lines.extend(
                line_number + 1
                for line_number, (left_tag, right_tag) in enumerate(zip(left_tags, right_tags))
                if left_tag != "ctx" or right_tag != "ctx"
            )
            for text_widget in all_texts:
                text_widget.configure(state="normal")
                text_widget.delete("1.0", "end")
            if left_lines:
                for left_line, right_line, left_tag, right_tag in zip(left_lines, right_lines, left_tags, right_tags):
                    left_text.insert("end", left_line + "\n", () if left_tag == "ctx" else left_tag)
                    right_text.insert("end", right_line + "\n", () if right_tag == "ctx" else right_tag)
            else:
                left_text.insert("end", t("gui.results.no_changes"))
                right_text.insert("end", t("gui.results.no_changes"))
            for text_widget in all_texts:
                text_widget.configure(state="disabled")

            def force_scrollbar_check() -> None:
                try:
                    lo, hi = left_text.yview()
                    sync_vertical_scroll(left_text, str(lo), str(hi))
                except Exception:
                    pass
                for text_widget in all_texts:
                    try:
                        text_widget.xview_moveto(text_widget.xview()[0])
                    except Exception:
                        pass

            self.host._schedule_popup_after(win, 200, force_scrollbar_check)

            if not change_lines:
                previous_change_button.configure(state="disabled")
                next_change_button.configure(state="disabled")
            else:
                previous_change_button.configure(state="normal")
                next_change_button.configure(state="normal")

            def initialize_change_navigation() -> None:
                if change_lines and current_change_index[0] < 0:
                    jump_to_change(1)
                else:
                    update_change_count()

            self.host._schedule_popup_after(win, 240, initialize_change_navigation)
            if not preview_opened_emitted[0]:
                emit_addon_editor_event(
                    "staged_preview_opened",
                    build_preview_hook_payload(trigger="staged_preview_opened"),
                )
                preview_opened_emitted[0] = True
            update_preview_focus_state(active_preview_pane_name[0])
            schedule_preview_diagnostics("staged_preview_opened")
            emit_preview_state(active_editor=active_editor_payload[0])

            if active_display_content[0].rstrip("\n") != active_ai_fix_content.rstrip("\n"):
                if user_text_ref[0] is None:
                    user_text, _ = make_diff_pane("  ✎  ai + user fixed", "user_fixed")
                    user_text_ref[0] = user_text
                    user_frame_ref[0] = user_text.master
                    user_text.configure(yscrollcommand=lambda first, last: sync_vertical_scroll(user_text, first, last))
                    if right_label_ref[0] is not None:
                        right_label_ref[0].configure(text="  +  ai fixed")
                    undo_button = ctk.CTkButton(
                        button_frame,
                        text="↩  Undo User Changes",
                        fg_color=("gray75", "gray30"),
                        hover_color=("gray60", "gray20"),
                        command=undo_user_changes,
                    )
                    undo_button.grid(row=0, column=2, padx=6)
                    undo_button_ref[0] = undo_button
                    if close_button_ref[0] is not None:
                        close_button_ref[0].configure(
                            text="✔  Save and Close",
                            fg_color="green",
                            hover_color="#1a7a1a",
                            command=save_and_close,
                        )
                render_user_pane(active_display_content[0])

            if active_editor_payload[0]:
                self.host._schedule_popup_after(win, 120, open_editor)

        load_preview_page(preview_page_index[0])

        bind_preview_shortcut("<Control-Tab>", lambda _event: cycle_preview_pane(1))
        bind_preview_shortcut("<Control-Shift-Tab>", lambda _event: cycle_preview_pane(-1))
        bind_preview_shortcut("<Control-ISO_Left_Tab>", lambda _event: cycle_preview_pane(-1))
        for preview_pane_number in range(1, 4):
            bind_preview_shortcut(
                f"<Control-Key-{preview_pane_number}>",
                lambda _event, pane_number=preview_pane_number: jump_preview_pane(pane_number),
            )

        win.bind("<F7>", lambda _event: jump_to_change(1))
        win.bind("<Shift-F7>", lambda _event: jump_to_change(-1))
        win.bind("<Control-Prior>", lambda _event: load_preview_page(preview_page_index[0] - 1))
        win.bind("<Control-Next>", lambda _event: load_preview_page(preview_page_index[0] + 1))
        win.protocol("WM_DELETE_WINDOW", close_preview)

    def _payload_from_inline_content(
        self,
        content: str,
        *,
        page_index: int = 0,
        limit_bytes: int = LARGE_FILE_EDITOR_LIMIT_BYTES,
    ) -> LoadedTextPayload:
        encoded = content.encode("utf-8", errors="replace")
        if len(encoded) <= limit_bytes:
            return LoadedTextPayload(
                content=content,
                source_size_bytes=len(encoded),
                loaded_size_bytes=len(encoded),
                truncated=False,
                page_index=0,
                total_pages=1,
            )
        total_pages = max(1, (len(encoded) + limit_bytes - 1) // limit_bytes)
        page_index = max(0, min(page_index, total_pages - 1))
        start = page_index * limit_bytes
        truncated_bytes = encoded[start:start + limit_bytes]
        truncated_content = truncated_bytes.decode("utf-8", errors="replace")
        return LoadedTextPayload(
            content=truncated_content,
            source_size_bytes=len(encoded),
            loaded_size_bytes=len(truncated_bytes),
            truncated=True,
            page_index=page_index,
            total_pages=total_pages,
        )

    def _load_file_into_editor(
        self,
        *,
        window: Any,
        file_path: Path,
        apply_loaded_content: Callable[[LoadedTextPayload], None],
        progress_frame: Any,
        progress_label: Any,
        progress_bar: Any,
        file_label: str,
        start_offset_bytes: int = 0,
        limit_bytes: int = LARGE_FILE_EDITOR_LIMIT_BYTES,
    ) -> None:
        try:
            source_size = file_path.stat().st_size
        except Exception as exc:
            apply_loaded_content(
                LoadedTextPayload(content=f"Error reading file: {exc}")
            )
            return

        total_pages = max(1, (source_size + max(limit_bytes, 1) - 1) // max(limit_bytes, 1))
        page_index = min(max(start_offset_bytes // max(limit_bytes, 1), 0), total_pages - 1)
        start_offset_bytes = page_index * max(limit_bytes, 1)
        page_bytes = max(0, min(limit_bytes, source_size - start_offset_bytes))

        if source_size <= LARGE_FILE_PROGRESS_THRESHOLD_BYTES and start_offset_bytes == 0:
            try:
                apply_loaded_content(
                    LoadedTextPayload(
                        content=file_path.read_text(encoding="utf-8", errors="replace"),
                        source_size_bytes=source_size,
                        loaded_size_bytes=source_size,
                        truncated=False,
                        page_index=0,
                        total_pages=1,
                    )
                )
            except Exception as exc:
                apply_loaded_content(LoadedTextPayload(content=f"Error reading file: {exc}"))
            return

        progress_frame.pack(fill="x", padx=10, pady=(6, 0))
        progress_label.configure(text=t("gui.results.large_file_loading", file=file_label))
        progress_bar.set(0)
        messages: queue.Queue[tuple[str, Any]] = queue.Queue()

        def worker() -> None:
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            chunks: list[str] = []
            loaded_bytes = 0
            try:
                with open(file_path, "rb") as handle:
                    handle.seek(start_offset_bytes)
                    while loaded_bytes < page_bytes:
                        raw = handle.read(min(FILE_READ_CHUNK_BYTES, page_bytes - loaded_bytes))
                        if not raw:
                            break
                        loaded_bytes += len(raw)
                        chunks.append(decoder.decode(raw))
                        messages.put(("progress", (loaded_bytes, page_bytes, source_size, page_index, total_pages)))
                    chunks.append(decoder.decode(b"", final=True))
                messages.put(
                    (
                        "done",
                        LoadedTextPayload(
                            content="".join(chunks),
                            source_size_bytes=source_size,
                            loaded_size_bytes=loaded_bytes,
                            truncated=source_size > limit_bytes,
                            page_index=page_index,
                            total_pages=total_pages,
                        ),
                    )
                )
            except Exception as exc:
                messages.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

        def poll() -> None:
            if not window.winfo_exists():
                return
            try:
                while True:
                    kind, payload = messages.get_nowait()
                    if kind == "progress":
                        loaded_bytes, active_page_bytes, total_bytes, current_page_index, total_page_count = payload
                        progress_bar.set(loaded_bytes / max(active_page_bytes, 1))
                        progress_label.configure(
                            text=t(
                                "gui.results.large_file_progress_page",
                                file=file_label,
                                current=current_page_index + 1,
                                total_pages=total_page_count,
                                loaded_mb=max(1, round(loaded_bytes / (1024 * 1024), 1)),
                                total_mb=max(1, round(total_bytes / (1024 * 1024), 1)),
                            )
                        )
                    elif kind == "done":
                        progress_bar.set(1)
                        apply_loaded_content(payload)
                        return
                    elif kind == "error":
                        apply_loaded_content(LoadedTextPayload(content=f"Error reading file: {payload}"))
                        return
            except queue.Empty:
                pass
            self.host._schedule_popup_after(window, 40, poll)

        poll()