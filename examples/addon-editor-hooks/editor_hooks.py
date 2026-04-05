from __future__ import annotations

from typing import Any


class ExampleEditorHooks:
    def on_editor_event(self, payload: dict[str, Any]) -> None:
        return None

    def collect_diagnostics(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        diagnostics: list[dict[str, str]] = []
        content = str(payload.get("content") or payload.get("current_content") or "")
        surface = str(payload.get("surface") or "editor")

        if "TODO" in content:
            diagnostics.append(
                {
                    "severity": "warning",
                    "message": "TODO markers are still present in the active review buffer.",
                }
            )

        if surface == "diff_preview" and int(payload.get("change_count") or 0) > 0:
            diagnostics.append(
                {
                    "severity": "info",
                    "message": "Review the staged diff changes before applying the AI fix.",
                }
            )

        return diagnostics

    def on_patch_applied(self, payload: dict[str, Any]) -> None:
        return None


def build_editor_hooks() -> ExampleEditorHooks:
    return ExampleEditorHooks()
