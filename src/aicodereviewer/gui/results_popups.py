from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk  # type: ignore[import-untyped]

from aicodereviewer.addons import emit_addon_patch_applied_event
from aicodereviewer.execution import ReviewSessionState
from aicodereviewer.i18n import t
from aicodereviewer.models import ReviewIssue

from .popup_surfaces import PopupSurfaceRecoveryStore, ResultsPopupSurfaceController

logger = logging.getLogger(__name__)


class ResultsPopupHelper:
    """Own popup recovery and Results-tab popup workflows for the host app."""

    def __init__(self, host: Any) -> None:
        self.host = host

    @property
    def popup_recovery_path(self) -> Path:
        return self.host._session_path.with_name("popup-recovery.json")

    def ensure_surface_controller(self) -> ResultsPopupSurfaceController:
        controller = getattr(self.host, "_results_popup_controller", None)
        if controller is not None:
            return controller
        recovery_store = PopupSurfaceRecoveryStore(self.popup_recovery_path, self.host._get_session_state)
        self.host._popup_recovery_store = recovery_store
        self.host._results_popup_controller = ResultsPopupSurfaceController(self.host, recovery_store)
        return self.host._results_popup_controller

    def restore_recovery_if_available(self) -> None:
        if getattr(self.host, "_popup_recovery_restored", False):
            return
        if self.host._issues:
            return

        controller = self.ensure_surface_controller()
        payload = controller.recovery_store.load()
        self.host._popup_recovery_restored = True
        if not payload:
            return

        session_payload = payload.get("session_state")
        if not isinstance(session_payload, dict):
            controller.recovery_store.clear()
            return

        try:
            session_state = self.host._validate_loaded_session_state(
                ReviewSessionState.from_serialized_dict(session_payload)
            )
        except Exception as exc:
            logger.warning("Failed to restore popup recovery session state: %s", exc)
            controller.recovery_store.clear()
            return

        self.host._restore_session_state(session_state)
        self.host._issues = list(session_state.issues)
        self.host._show_issues(session_state.issues)

        active_popup = payload.get("active_popup")
        if not isinstance(active_popup, dict):
            return

        if active_popup.get("kind") == "batch_fix":
            self.restore_batch_fix_recovery(active_popup)
        elif active_popup.get("kind") == "editor":
            self.restore_editor_recovery(active_popup)

        self.host._show_toast(t("gui.results.popup_recovery_restored"))

    def restore_editor_recovery(self, recovery_state: dict[str, Any]) -> None:
        issue_index = recovery_state.get("issue_index")
        if not isinstance(issue_index, int) or issue_index < 0 or issue_index >= len(self.host._issue_cards):
            self.ensure_surface_controller().recovery_store.clear()
            return
        self.ensure_surface_controller().open_builtin_editor(
            issue_index,
            self.host._issue_cards[issue_index]["issue"],
            initial_content=str(recovery_state.get("content") or ""),
            recovery_state=recovery_state,
        )

    def restore_batch_fix_recovery(self, recovery_state: dict[str, Any]) -> None:
        generated_results_raw = recovery_state.get("generated_results")
        if not isinstance(generated_results_raw, dict):
            self.ensure_surface_controller().recovery_store.clear()
            return

        if not self.host._ai_fix_mode:
            self.host._enter_ai_fix_mode()

        selected_issue_indexes = recovery_state.get("selected_issue_indexes")
        valid_indexes = [
            index
            for index in (selected_issue_indexes or [])
            if isinstance(index, int) and 0 <= index < len(self.host._issue_cards)
        ]
        if not valid_indexes:
            valid_indexes = [
                int(index)
                for index in generated_results_raw.keys()
                if str(index).isdigit() and 0 <= int(index) < len(self.host._issue_cards)
            ]
        selected = [(index, self.host._issue_cards[index]) for index in valid_indexes]
        results = {
            int(index): value
            for index, value in generated_results_raw.items()
            if str(index).isdigit() and 0 <= int(index) < len(self.host._issue_cards)
        }
        if not selected or not results:
            self.ensure_surface_controller().recovery_store.clear()
            return
        self.show_batch_fix_popup(selected, results, recovery_state=recovery_state)

    def show_batch_fix_popup(
        self,
        selected: list[tuple[int, Any]],
        results: dict[int, Any],
        *,
        recovery_state: dict[str, Any] | None = None,
    ) -> None:
        normalized_results = {
            idx: self._normalize_batch_fix_result(value)
            for idx, value in results.items()
        }
        success_count = sum(
            1 for value in normalized_results.values() if self._batch_fix_result_content(value)
        )
        fail_count = len(normalized_results) - success_count

        if success_count == 0:
            self._restore_selected_card_statuses(selected)
            self.host._show_toast(
                self._build_batch_fix_failure_toast(normalized_results),
                error=True,
            )
            self.host.start_ai_fix_btn.configure(state="normal")
            self.host.cancel_ai_fix_btn.configure(state="normal", text=t("gui.results.cancel_ai_fix"))
            self.host._finish_active_ai_fix()
            logger.info("Batch AI Fix: no fixes generated.")
            self.host.status_var.set(t("common.ready"))
            return

        logger.info("Batch AI Fix: %d/%d fixes generated.", success_count, len(normalized_results))

        self.host.cancel_ai_fix_btn.configure(state="normal", text=t("gui.results.cancel_ai_fix"))

        win = ctk.CTkToplevel(self.host)
        win.title(t("gui.results.batch_fix_title", count=success_count))
        win.geometry("950x650")
        win.grab_set()
        self.host._schedule_titlebar_fix(win)

        ctk.CTkLabel(
            win,
            text=t("gui.results.batch_fix_summary", success=success_count, failed=fail_count),
            font=ctk.CTkFont(weight="bold"),
        ).pack(padx=10, pady=(10, 4))

        batch_status_frame = ctk.CTkFrame(win, fg_color="transparent")
        batch_status_frame.pack(fill="x", padx=10, pady=(0, 4))

        batch_shortcuts_label = ctk.CTkLabel(
            batch_status_frame,
            text=t("gui.results.batch_fix_shortcuts"),
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        batch_shortcuts_label.pack(side="left")

        batch_active_issue_label = ctk.CTkLabel(
            batch_status_frame,
            text="",
            text_color=self.host._MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        batch_active_issue_label.pack(side="left", padx=(12, 0))

        scroll = ctk.CTkFrame(win) if self.host._testing_mode else ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=10, pady=4)
        scroll.grid_columnconfigure(0, weight=1)

        controller = self.ensure_surface_controller()
        original_generated_results = {
            idx: dict(value) for idx, value in normalized_results.items()
        }
        recovery_selected_indexes = recovery_state.get("selected_issue_indexes") if isinstance(recovery_state, dict) else None
        recovery_enabled_indexes = recovery_state.get("enabled_issue_indexes") if isinstance(recovery_state, dict) else None
        recovery_current_fixes = recovery_state.get("current_fixes") if isinstance(recovery_state, dict) else None
        recovery_original_fixes = recovery_state.get("original_ai_fixes") if isinstance(recovery_state, dict) else None
        active_preview_state = [
            dict(recovery_state.get("active_preview", {}))
            if isinstance(recovery_state, dict) and isinstance(recovery_state.get("active_preview"), dict)
            else None
        ]

        recovery_current_fixes_map = self._normalize_int_keyed_map(recovery_current_fixes)
        recovery_original_fixes_map = self._normalize_int_keyed_map(recovery_original_fixes)
        enabled_indexes = {
            index for index in (recovery_enabled_indexes or []) if isinstance(index, int)
        }
        selected_indexes = {index for index, _record in selected}
        if isinstance(recovery_selected_indexes, list):
            selected_indexes.update(index for index in recovery_selected_indexes if isinstance(index, int))

        fix_checks: dict[int, list[Any]] = {}
        issue_jump_order: list[int] = []
        issue_rows: dict[int, dict[str, Any]] = {}
        batch_shortcut_targets: list[Any] = [win, scroll]
        batch_shortcut_specs: list[tuple[str, Any]] = []
        active_issue_index = [
            recovery_state.get("active_issue_index", -1)
            if isinstance(recovery_state, dict) and isinstance(recovery_state.get("active_issue_index"), int)
            else -1
        ]

        setattr(win, "_acr_batch_fix_status_label", batch_active_issue_label)
        setattr(win, "_acr_batch_fix_active_issue", active_issue_index[0])

        def _build_batch_popup_payload(active_preview: dict[str, Any] | None = None) -> dict[str, Any]:
            return {
                "kind": "batch_fix",
                "selected_issue_indexes": sorted(selected_indexes),
                "active_issue_index": active_issue_index[0],
                "enabled_issue_indexes": sorted(
                    idx for idx, (var, _current, _original) in fix_checks.items() if var.get()
                ),
                "generated_results": dict(original_generated_results),
                "current_fixes": {
                    idx: current_fix for idx, (_var, current_fix, _original) in fix_checks.items()
                },
                "original_ai_fixes": {
                    idx: original_fix for idx, (_var, _current, original_fix) in fix_checks.items()
                },
                "active_preview": active_preview,
            }

        def _persist_batch_popup(active_preview: dict[str, Any] | None = None) -> None:
            controller.recovery_store.save_active_popup(_build_batch_popup_payload(active_preview))

        def _clear_batch_popup_recovery() -> None:
            controller.recovery_store.clear()

        def _register_batch_shortcut_target(widget: Any) -> None:
            if widget in batch_shortcut_targets:
                return
            batch_shortcut_targets.append(widget)
            for sequence, handler in batch_shortcut_specs:
                widget.bind(sequence, handler, add="+")

        def _bind_batch_shortcut(sequence: str, handler: Any) -> None:
            batch_shortcut_specs.append((sequence, handler))
            for widget in batch_shortcut_targets:
                widget.bind(sequence, handler, add="+")

        def _build_batch_issue_status_text() -> str:
            if not issue_jump_order:
                return t("gui.results.batch_fix_status_none")
            if active_issue_index[0] not in issue_rows:
                active_issue_index[0] = issue_jump_order[0]
            current_issue = active_issue_index[0]
            current_position = issue_jump_order.index(current_issue) + 1
            current_var, current_fix, original_fix = fix_checks[current_issue]
            parts = [
                t("gui.results.batch_fix_status_issue", current=current_position, total=len(issue_jump_order)),
                issue_rows[current_issue]["filename"],
            ]
            if not current_var.get():
                parts.append(t("gui.results.batch_fix_status_disabled"))
            if current_fix.rstrip("\n") != original_fix.rstrip("\n"):
                parts.append(t("gui.results.batch_fix_status_edited"))
            return "  ·  ".join(parts)

        def _refresh_active_issue_visuals() -> None:
            for issue_index, row in issue_rows.items():
                row["frame"].configure(
                    border_width=2 if issue_index == active_issue_index[0] else 1,
                    border_color="#2563eb" if issue_index == active_issue_index[0] else row["base_border_color"],
                )

        def _update_batch_issue_status() -> None:
            batch_active_issue_label.configure(text=_build_batch_issue_status_text())
            setattr(win, "_acr_batch_fix_active_issue", active_issue_index[0])
            setattr(win, "_acr_batch_fix_issue_order", list(issue_jump_order))

        def _set_active_batch_issue(issue_index: int, *, focus_widget: bool = True, persist: bool = True) -> str:
            if issue_index not in issue_rows:
                return "break"
            active_issue_index[0] = issue_index
            _refresh_active_issue_visuals()
            _update_batch_issue_status()
            if focus_widget:
                focus_target = issue_rows[issue_index].get("preview_button") or issue_rows[issue_index].get("checkbox")
                if focus_target is not None:
                    try:
                        focus_target.focus_set()
                    except Exception:
                        pass
            if persist:
                _persist_batch_popup(active_preview_state[0])
            return "break"

        def _cycle_batch_issue(step: int) -> str:
            if len(issue_jump_order) <= 1:
                return "break"
            if active_issue_index[0] not in issue_jump_order:
                return _set_active_batch_issue(issue_jump_order[0])
            current_position = issue_jump_order.index(active_issue_index[0])
            return _set_active_batch_issue(issue_jump_order[(current_position + step) % len(issue_jump_order)])

        def _jump_batch_issue(issue_number: int) -> str:
            if 1 <= issue_number <= len(issue_jump_order):
                return _set_active_batch_issue(issue_jump_order[issue_number - 1])
            return "break"

        row_num = 0
        for idx, record in selected:
            result_value = normalized_results.get(idx, self._normalize_batch_fix_result(None))
            fix_text = self._batch_fix_result_content(result_value)
            diagnostic = self._batch_fix_result_diagnostic(result_value)
            issue = record["issue"]
            fname = Path(issue.file_path).name

            if fix_text:
                current_fix = str(recovery_current_fixes_map.get(idx, fix_text))
                original_ai_fix = str(recovery_original_fixes_map.get(idx, fix_text))
                var = ctk.BooleanVar(value=(idx in enabled_indexes) if enabled_indexes else True)
                fix_checks[idx] = [var, current_fix, original_ai_fix]

                frame = ctk.CTkFrame(scroll, border_width=1, border_color="#7c3aed")
                frame.grid(row=row_num, column=0, sticky="ew", padx=4, pady=3)
                frame.grid_columnconfigure(1, weight=1)

                def _open_preview(issue_path=issue.file_path, short_name=fname, issue_index=idx):
                    _set_active_batch_issue(issue_index, focus_widget=False)
                    preview_recovery = active_preview_state[0]
                    if preview_recovery and preview_recovery.get("issue_index") != issue_index:
                        preview_recovery = None
                    self.host._show_diff_preview(
                        issue_path,
                        fix_checks[issue_index][1],
                        short_name,
                        issue_index,
                        _on_content_update=lambda content, _ix=issue_index: (
                            fix_checks[_ix].__setitem__(1, content),
                            _update_batch_issue_status(),
                            _persist_batch_popup(active_preview_state[0]),
                        ),
                        _ai_fix_content=fix_checks[issue_index][2],
                        _recovery_state=preview_recovery,
                        _on_preview_state_change=lambda state: (
                            active_preview_state.__setitem__(0, state),
                            _persist_batch_popup(state),
                        ),
                        _on_preview_closed=lambda: (
                            active_preview_state.__setitem__(0, None),
                            _persist_batch_popup(None),
                        ),
                    )

                checkbox = ctk.CTkCheckBox(
                    frame,
                    text=fname,
                    variable=var,
                    font=ctk.CTkFont(weight="bold"),
                )
                checkbox.grid(row=0, column=0, sticky="w", padx=6, pady=(4, 0))

                preview_btn = ctk.CTkButton(
                    frame,
                    text=t("gui.results.preview_changes"),
                    width=120,
                    height=24,
                    font=ctk.CTkFont(size=11),
                    fg_color="#2563eb",
                    command=_open_preview,
                )
                preview_btn.grid(row=0, column=1, sticky="e", padx=6, pady=(4, 0))

                desc = issue.description or issue.ai_feedback or ""
                ctk.CTkLabel(
                    frame,
                    text=desc,
                    anchor="w",
                    justify="left",
                    wraplength=700,
                    text_color=("gray40", "gray60"),
                    font=ctk.CTkFont(size=11),
                ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))

                issue_jump_order.append(idx)
                issue_rows[idx] = {
                    "frame": frame,
                    "checkbox": checkbox,
                    "preview_button": preview_btn,
                    "filename": fname,
                    "base_border_color": "#7c3aed",
                }
                _register_batch_shortcut_target(frame)
                _register_batch_shortcut_target(checkbox)
                _register_batch_shortcut_target(preview_btn)
                for widget in (frame, checkbox, preview_btn):
                    widget.bind(
                        "<Button-1>",
                        lambda _event, issue_index=idx: _set_active_batch_issue(issue_index, focus_widget=False, persist=False),
                        add="+",
                    )
                    widget.bind(
                        "<FocusIn>",
                        lambda _event, issue_index=idx: _set_active_batch_issue(issue_index, focus_widget=False, persist=False),
                        add="+",
                    )
                var.trace_add(
                    "write",
                    lambda *_args, issue_index=idx: (
                        _update_batch_issue_status() if active_issue_index[0] == issue_index else None,
                        _persist_batch_popup(active_preview_state[0]),
                    ),
                )
            else:
                frame = ctk.CTkFrame(scroll, border_width=1, border_color="#dc2626")
                frame.grid(row=row_num, column=0, sticky="ew", padx=4, pady=3)
                frame.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(
                    frame,
                    text=f"✗ {fname} — {t('gui.results.no_fix')}",
                    text_color="#dc2626",
                ).grid(row=0, column=0, sticky="w", padx=6, pady=4)
                detail_text = self._format_batch_fix_failure_detail(diagnostic)
                if detail_text:
                    ctk.CTkLabel(
                        frame,
                        text=detail_text,
                        anchor="w",
                        justify="left",
                        wraplength=700,
                        text_color="#b91c1c",
                        font=ctk.CTkFont(size=11),
                    ).grid(row=1, column=0, sticky="w", padx=6, pady=(0, 2))
                hint_text = self._format_batch_fix_failure_hint(diagnostic)
                if hint_text:
                    ctk.CTkLabel(
                        frame,
                        text=hint_text,
                        anchor="w",
                        justify="left",
                        wraplength=700,
                        text_color=self.host._MUTED_TEXT,
                        font=ctk.CTkFont(size=11),
                    ).grid(row=2, column=0, sticky="w", padx=6, pady=(0, 4))
                retry_text = self._format_batch_fix_failure_retry(diagnostic)
                if retry_text:
                    ctk.CTkLabel(
                        frame,
                        text=retry_text,
                        anchor="w",
                        justify="left",
                        wraplength=700,
                        text_color=self.host._MUTED_TEXT,
                        font=ctk.CTkFont(size=11),
                    ).grid(row=3, column=0, sticky="w", padx=6, pady=(0, 4))

            row_num += 1

        _bind_batch_shortcut("<Control-Tab>", lambda _event: _cycle_batch_issue(1))
        _bind_batch_shortcut("<Control-Shift-Tab>", lambda _event: _cycle_batch_issue(-1))
        _bind_batch_shortcut("<Control-ISO_Left_Tab>", lambda _event: _cycle_batch_issue(-1))
        for issue_number in range(1, 10):
            _bind_batch_shortcut(
                f"<Control-Key-{issue_number}>",
                lambda _event, target_issue=issue_number: _jump_batch_issue(target_issue),
            )

        if issue_jump_order:
            initial_active_issue = active_issue_index[0] if active_issue_index[0] in issue_rows else issue_jump_order[0]
            _set_active_batch_issue(initial_active_issue, focus_widget=False, persist=False)
        else:
            _update_batch_issue_status()

        _persist_batch_popup(active_preview_state[0])

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=8)

        def _apply_selected() -> None:
            applied = 0
            for idx, (var, fix_text, original_ai_fix) in fix_checks.items():
                if not var.get():
                    continue
                record = self.host._issue_cards[idx]
                issue = record["issue"]
                provenance = "ai_applied" if fix_text.rstrip("\n") == original_ai_fix.rstrip("\n") else "ai_edited"
                if self.host._testing_mode:
                    issue.set_resolution(
                        status="resolved",
                        provenance=provenance,
                        ai_fix_suggested=original_ai_fix,
                        ai_fix_applied=fix_text,
                    )
                    applied += 1
                    logger.info("Applied AI fix (simulated): %s", issue.file_path)
                    emit_addon_patch_applied_event(
                        {
                            "source": "batch_ai_fix",
                            "issue_index": idx,
                            "file_path": issue.file_path,
                            "display_name": Path(issue.file_path).name,
                            "content": fix_text,
                            "write_performed": False,
                            "testing_mode": True,
                        }
                    )
                else:
                    try:
                        with open(issue.file_path, "w", encoding="utf-8") as handle:
                            handle.write(fix_text)
                        issue.set_resolution(
                            status="resolved",
                            provenance=provenance,
                            ai_fix_suggested=original_ai_fix,
                            ai_fix_applied=fix_text,
                        )
                        applied += 1
                        logger.info("Applied AI fix: %s", issue.file_path)
                        emit_addon_patch_applied_event(
                            {
                                "source": "batch_ai_fix",
                                "issue_index": idx,
                                "file_path": issue.file_path,
                                "display_name": Path(issue.file_path).name,
                                "content": fix_text,
                                "write_performed": True,
                                "testing_mode": False,
                            }
                        )
                    except Exception as exc:
                        logger.error("Failed to apply fix to %s: %s", issue.file_path, exc)
                        self.host._show_toast(str(exc), error=True)
                self.host._refresh_status(idx)
            _clear_batch_popup_recovery()
            win.destroy()
            self.host._finish_active_ai_fix()
            self.host._exit_ai_fix_mode()
            self.host._show_toast(t("gui.results.batch_fix_applied", count=applied))
            logger.info("Batch AI Fix: %d fixes applied.", applied)
            self.host.status_var.set(t("common.ready"))

        def _cancel() -> None:
            _clear_batch_popup_recovery()
            win.destroy()
            self._restore_selected_card_statuses(selected)
            self.host.start_ai_fix_btn.configure(state="normal")
            self.host._finish_active_ai_fix()
            self.host.status_var.set(t("common.ready"))

        ctk.CTkButton(btn_frame, text=t("gui.results.apply_fixes"), fg_color="green", command=_apply_selected).grid(
            row=0, column=0, padx=6
        )
        ctk.CTkButton(btn_frame, text=t("common.cancel"), command=_cancel).grid(row=0, column=1, padx=6)
        win.bind("<Control-w>", lambda _event: _cancel())
        win.protocol("WM_DELETE_WINDOW", _cancel)

    def show_issue_detail(self, issue: ReviewIssue) -> None:
        win = ctk.CTkToplevel(self.host)
        win.title(t("gui.results.issue_title", type=issue.issue_type))
        win.geometry("700x500")
        win.grab_set()
        self.host._schedule_titlebar_fix(win)
        win.bind("<Control-w>", lambda _event: win.destroy())

        text = ctk.CTkTextbox(win, wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)

        content = self._build_issue_detail_content(issue)
        text.insert("0.0", content)
        text.configure(state="disabled")

        ctk.CTkButton(win, text=t("common.close"), command=win.destroy).pack(pady=8)

    @staticmethod
    def _build_issue_detail_content(issue: ReviewIssue) -> str:
        lines = [
            t("gui.detail.file", path=issue.file_path),
            t("gui.detail.type", type=issue.issue_type),
            t("gui.detail.severity", severity=issue.severity),
            t("gui.detail.status", status=issue.status),
        ]
        if issue.resolution_reason:
            lines.append(t("gui.detail.reason", reason=issue.resolution_reason))
        if issue.resolved_at:
            lines.append(
                t(
                    "gui.detail.resolved_at",
                    resolved_at=issue.resolved_at.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )
        if issue.resolution_provenance:
            provenance_key = f"gui.detail.provenance_{issue.resolution_provenance}"
            provenance_label = t(provenance_key)
            if provenance_label == provenance_key:
                provenance_label = issue.resolution_provenance.replace("_", " ").title()
            lines.append(t("gui.detail.resolution_path", resolution_path=provenance_label))

        content = "\n".join(lines) + "\n"

        related_issues = getattr(issue, "related_issues", None) or []
        interaction_summary = getattr(issue, "interaction_summary", None) or ""
        if related_issues or interaction_summary:
            content += f"\n{t('gui.detail.related', count=len(related_issues))}\n"
            if interaction_summary:
                content += f"{interaction_summary}\n"

        if issue.ai_fix_suggested:
            content += f"\n{t('gui.detail.ai_fix_suggested')}\n{issue.ai_fix_suggested}\n"
        if issue.ai_fix_applied:
            content += f"\n{t('gui.detail.ai_fix_applied')}\n{issue.ai_fix_applied}\n"

        content += (
            f"\n{t('gui.detail.ai_feedback')}\n{issue.ai_feedback}\n"
            f"\n{t('gui.detail.code_snippet')}\n{issue.code_snippet}\n"
        )
        return content

    @staticmethod
    def _normalize_int_keyed_map(source: Any) -> dict[int, Any]:
        if not isinstance(source, dict):
            return {}
        normalized: dict[int, Any] = {}
        for raw_key, value in source.items():
            if isinstance(raw_key, int):
                normalized[raw_key] = value
            elif str(raw_key).isdigit():
                normalized[int(raw_key)] = value
        return normalized

    @staticmethod
    def _normalize_batch_fix_result(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            normalized = dict(value)
            content = normalized.get("content")
            normalized["content"] = content if isinstance(content, str) and content else None
            diagnostic = normalized.get("diagnostic")
            normalized["diagnostic"] = diagnostic if isinstance(diagnostic, dict) else None
            status = normalized.get("status")
            if status not in {"generated", "failed"}:
                normalized["status"] = "generated" if normalized["content"] else "failed"
            return normalized
        if isinstance(value, str) and value:
            return {"status": "generated", "content": value, "diagnostic": None}
        return {"status": "failed", "content": None, "diagnostic": None}

    @staticmethod
    def _batch_fix_result_content(value: dict[str, Any]) -> str | None:
        content = value.get("content")
        return content if isinstance(content, str) and content else None

    @staticmethod
    def _batch_fix_result_diagnostic(value: dict[str, Any]) -> dict[str, Any] | None:
        diagnostic = value.get("diagnostic")
        return diagnostic if isinstance(diagnostic, dict) else None

    def _build_batch_fix_failure_toast(self, results: dict[int, dict[str, Any]]) -> str:
        diagnostics = [
            diagnostic
            for diagnostic in (self._batch_fix_result_diagnostic(value) for value in results.values())
            if diagnostic
        ]
        if not diagnostics:
            return t("gui.results.no_fix")
        if len(diagnostics) == 1:
            detail_text = self._format_batch_fix_failure_detail(diagnostics[0])
            if detail_text:
                return f"{t('gui.results.no_fix')} {detail_text}"
        category_counts: dict[str, int] = {}
        for diagnostic in diagnostics:
            category = self._diagnostic_category_label(str(diagnostic.get("category") or "provider"))
            category_counts[category] = category_counts.get(category, 0) + 1
        summary = ", ".join(
            f"{category} ({count})"
            for category, count in sorted(category_counts.items())
        )
        return t("gui.results.batch_fix_failure_summary", summary=summary)

    def _format_batch_fix_failure_detail(self, diagnostic: dict[str, Any] | None) -> str:
        if not diagnostic:
            return ""
        detail = str(diagnostic.get("detail") or "").strip()
        if not detail:
            return ""
        category = self._diagnostic_category_label(str(diagnostic.get("category") or "provider"))
        return t("gui.results.batch_fix_failure_detail", category=category, detail=detail)

    def _format_batch_fix_failure_hint(self, diagnostic: dict[str, Any] | None) -> str:
        if not diagnostic:
            return ""
        hint = str(diagnostic.get("fix_hint") or "").strip()
        if not hint:
            return ""
        return t("gui.results.batch_fix_failure_hint", hint=hint)

    def _format_batch_fix_failure_retry(self, diagnostic: dict[str, Any] | None) -> str:
        if not diagnostic or not diagnostic.get("retryable"):
            return ""
        retry_delay = diagnostic.get("retry_delay_seconds")
        if isinstance(retry_delay, int) and retry_delay > 0:
            return t("gui.results.batch_fix_failure_retry_after", seconds=retry_delay)
        return t("gui.results.batch_fix_failure_retry")

    @staticmethod
    def _diagnostic_category_label(category: str) -> str:
        category_key = f"gui.results.diagnostic_category_{category}"
        label = t(category_key)
        if label == category_key:
            return category.replace("_", " ").title()
        return label

    def _restore_selected_card_statuses(self, selected: list[tuple[int, Any]]) -> None:
        for idx, record in selected:
            status_key, status_color = self.host._status_display(record["issue"], record["color"])
            record["status_lbl"].configure(text=t(status_key), text_color=status_color)