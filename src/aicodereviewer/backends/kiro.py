# src/aicodereviewer/backends/kiro.py
"""Kiro CLI backend for code review.

On Windows, the backend prefers the native ``kiro-cli.exe`` installation and
falls back to WSL only when no native CLI is available.
"""
import logging
import os
import shlex
import shutil
import subprocess
import time
from typing import Optional

from .base import AIBackend
from .models import _resolve_kiro_exe
from aicodereviewer.config import config
from aicodereviewer.diagnostics import backend_connection_detail, backend_connection_fix_hint
from aicodereviewer.i18n import t
from aicodereviewer.path_utils import (
    windows_to_wsl_path,
    is_wsl_available,
    run_in_wsl,
    ensure_wsl_tool,
    CancelledProcessError,
)

logger = logging.getLogger(__name__)


class KiroBackend(AIBackend):
    """AI backend that delegates to the Kiro CLI.

    Configuration (``config.ini``):

    .. code-block:: ini

        [backend]
        type = kiro

        [kiro]
        wsl_distro = Ubuntu
        cli_command = kiro-cli
        model = claude-haiku-4.5
        timeout = 300
    """

    def __init__(self, **kwargs):
        self.distro: Optional[str] = (
            config.get("kiro", "wsl_distro", "").strip() or None
        )
        self.cli_cmd: str = config.get("kiro", "cli_command", "kiro-cli").strip()
        self.model: str = config.get("kiro", "model", "").strip() or None
        self.timeout: int = int(float(config.get("kiro", "timeout", "300")))
        self._cancel_requested: bool = False
        self.native_cmd: Optional[str] = None
        self._use_native_windows = False

        if os.name == "nt":
            resolved = _resolve_kiro_exe(self.cli_cmd)
            if resolved and os.path.isfile(resolved):
                self.native_cmd = resolved
                self._use_native_windows = True
            elif not is_wsl_available():
                raise RuntimeError(
                    "Kiro CLI was not found natively on Windows and WSL is not available. "
                    "Install kiro-cli for Windows or enable WSL."
                )

    def cancel(self) -> None:
        """Request cancellation for the active Kiro subprocess."""
        self._cancel_requested = True

    def close(self) -> None:
        """Release any active subprocess by requesting cancellation."""
        self.cancel()

    # ── AIBackend interface ────────────────────────────────────────────────

    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
        tool_context=None,
    ) -> str:
        system_prompt = self._build_system_prompt(
            review_type, lang, self._project_context, self._detected_frameworks,
        )
        user_message = self._build_user_message(code_content, review_type, spec_content)
        full_prompt = f"{system_prompt}\n\n{user_message}"
        return self._run_kiro_prompt(full_prompt)

    def get_fix(
        self,
        code_content: str,
        issue_feedback: str,
        review_type: str = "best_practices",
        lang: str = "en",
    ) -> Optional[str]:
        system_prompt = self._build_system_prompt("fix", lang)
        user_message = self._build_fix_message(code_content, issue_feedback, review_type)
        full_prompt = f"{system_prompt}\n\n{user_message}"
        result = self._run_kiro_prompt(full_prompt)
        if result and not result.startswith("Error:"):
            return result.strip()
        return None

    def get_review_recommendations(
        self,
        recommendation_context: str,
        lang: str = "en",
    ) -> str:
        system_prompt = self._build_recommendation_system_prompt(lang)
        user_message = self._build_recommendation_user_message(recommendation_context)
        return self._run_kiro_prompt(f"{system_prompt}\n\n{user_message}")

    def validate_connection(self) -> bool:
        if os.name == "nt":
            if self._use_native_windows and self.native_cmd:
                rc, stdout, _stderr = self._run_native_command([self.native_cmd, "whoami"])
                return rc == 0 and bool(stdout.strip())
            if not is_wsl_available():
                logger.error("WSL is not available.")
                return False
            if not ensure_wsl_tool(self.cli_cmd, self.distro):
                logger.error(
                    "Kiro CLI ('%s') not found in WSL%s.",
                    self.cli_cmd,
                    f" ({self.distro})" if self.distro else "",
                )
                return False
        else:
            if not shutil.which(self.cli_cmd):
                logger.error("Kiro CLI ('%s') not found in PATH.", self.cli_cmd)
                return False
        return True

    def validate_connection_diagnostic(self) -> dict[str, str | bool]:
        if os.name == "nt":
            if self._use_native_windows and self.native_cmd:
                rc, stdout, stderr = self._run_native_command([self.native_cmd, "whoami"])
                if rc == 0 and bool(stdout.strip()):
                    return {
                        "ok": True,
                        "category": "none",
                        "detail": "",
                        "fix_hint": "",
                        "origin": "connection_test",
                    }
                return {
                    "ok": False,
                    "category": "auth",
                    "detail": stderr.strip() or t("health.kiro_auth_fail"),
                    "fix_hint": backend_connection_fix_hint("kiro", "auth"),
                    "origin": "connection_test",
                }
            if not is_wsl_available():
                return {
                    "ok": False,
                    "category": "tool_compatibility",
                    "detail": backend_connection_detail("kiro", "no_runtime"),
                    "fix_hint": backend_connection_fix_hint("kiro", "tool_compatibility"),
                    "origin": "connection_test",
                }
            if not ensure_wsl_tool(self.cli_cmd, self.distro):
                return {
                    "ok": False,
                    "category": "tool_compatibility",
                    "detail": backend_connection_detail(
                        "kiro",
                        "wsl_cli_not_found",
                        command=self.cli_cmd,
                        distro_suffix=(f" ({self.distro})" if self.distro else ""),
                    ),
                    "fix_hint": backend_connection_fix_hint("kiro", "tool_compatibility"),
                    "origin": "connection_test",
                }
        else:
            import shutil

            if not shutil.which(self.cli_cmd):
                return {
                    "ok": False,
                    "category": "tool_compatibility",
                    "detail": backend_connection_detail("kiro", "cli_not_found", command=self.cli_cmd),
                    "fix_hint": backend_connection_fix_hint("kiro", "tool_compatibility"),
                    "origin": "connection_test",
                }

        return {
            "ok": True,
            "category": "none",
            "detail": "",
            "fix_hint": "",
            "origin": "connection_test",
        }

    # ── private helpers ────────────────────────────────────────────────────

    def _build_bash_command(self, subcommand: str, *, file_path: Optional[str] = None) -> str:
        """Build a bash-safe Kiro command string for execution via ``bash -lc``."""
        parts = [self.cli_cmd, subcommand]
        if self.model:
            parts.extend(["--model", self.model])
        if subcommand == "chat":
            parts.append("--no-interactive")
        if file_path is not None:
            parts.append(file_path)
        return shlex.join(parts)

    def _build_native_command(self, subcommand: str, *, file_path: Optional[str] = None) -> list[str]:
        """Build a native command list for direct Kiro CLI execution."""
        parts = [self.native_cmd or self.cli_cmd, subcommand]
        if self.model:
            parts.extend(["--model", self.model])
        if subcommand == "chat":
            parts.append("--no-interactive")
        if file_path is not None:
            parts.append(file_path)
        return parts

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=2)
            except Exception:
                pass

    def _run_native_command(self, command: list[str], prompt: Optional[str] = None) -> tuple[int, str, str]:
        """Run a native command with cancellation polling."""
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + self.timeout
        pending_input = prompt

        while True:
            if self._cancel_requested:
                self._terminate_process(process)
                raise CancelledProcessError()

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._terminate_process(process)
                raise subprocess.TimeoutExpired(command, self.timeout)

            try:
                stdout, stderr = process.communicate(
                    input=pending_input,
                    timeout=min(0.2, remaining),
                )
                return process.returncode, stdout, stderr
            except subprocess.TimeoutExpired:
                pending_input = None
                continue

    def _run_native_bash(self, bash_cmd: str, prompt: str) -> str:
        """Run a native bash command with cancellation polling."""
        rc, stdout, stderr = self._run_native_command(["bash", "-lc", bash_cmd], prompt)
        if rc != 0:
            err_msg = stderr.strip() or f"Kiro exited with code {rc}"
            return f"Error: Kiro CLI – {err_msg}"
        return stdout.strip()

    def _run_native_cli(self, command: list[str], prompt: str) -> str:
        """Run the native Windows Kiro CLI directly."""
        rc, stdout, stderr = self._run_native_command(command, prompt)
        if rc != 0:
            err_msg = stderr.strip() or f"Kiro exited with code {rc}"
            logger.error("Kiro CLI error: %s", err_msg)
            return f"Error: Kiro CLI – {err_msg}"
        return stdout.strip()

    def _run_kiro_prompt(self, prompt: str) -> str:
        """
        Send a prompt to Kiro CLI and capture the response.

        The prompt is written to a temporary file that is shared with WSL
        through the /mnt/ path mechanism, then passed via stdin to the
        Kiro CLI.
        """
        try:
            if os.name == "nt" and self._use_native_windows:
                return self._run_native_cli(self._build_native_command("chat"), prompt)

            bash_cmd = self._build_bash_command("chat")

            if os.name == "nt":
                rc, stdout, stderr = run_in_wsl(
                    ["bash", "-lc", bash_cmd],
                    distro=self.distro,
                    timeout=self.timeout,
                    stdin_data=prompt,
                    cancel_check=lambda: self._cancel_requested,
                )
                if rc != 0:
                    err_msg = stderr.strip() or f"Kiro exited with code {rc}"
                    logger.error("Kiro CLI error: %s", err_msg)
                    return f"Error: Kiro CLI – {err_msg}"
                return stdout.strip()
            else:
                return self._run_native_bash(bash_cmd, prompt)

        except CancelledProcessError:
            return "Error: Cancelled."

        except Exception as exc:
            logger.error("Kiro backend error: %s", exc)
            return f"Error: {exc}"

    def review_file(self, file_path: str, review_type: str = "best_practices", lang: str = "en") -> str:
        """
        Review a file by passing its path directly to Kiro.

        On Windows the path is passed natively when a Windows Kiro install is
        available, otherwise it is converted to a WSL mount path.
        """
        try:
            if os.name == "nt" and not self._use_native_windows:
                wsl_path = windows_to_wsl_path(file_path)
            else:
                wsl_path = file_path

            system_prompt = self._build_system_prompt(
                review_type, lang, self._project_context, self._detected_frameworks,
            )
            prompt = f"{system_prompt}\n\nReview the file at: {wsl_path}"

            if os.name == "nt" and self._use_native_windows:
                return self._run_native_cli(
                    self._build_native_command("review", file_path=file_path),
                    prompt,
                )

            bash_cmd = self._build_bash_command("review", file_path=wsl_path)

            if os.name == "nt":
                rc, stdout, stderr = run_in_wsl(
                    ["bash", "-lc", bash_cmd],
                    distro=self.distro,
                    timeout=self.timeout,
                    stdin_data=prompt,
                    cancel_check=lambda: self._cancel_requested,
                )
                if rc != 0:
                    return f"Error: Kiro CLI – {stderr.strip()}"
                return stdout.strip()
            else:
                return self._run_native_bash(bash_cmd, prompt)

        except CancelledProcessError:
            return "Error: Cancelled."

        except Exception as exc:
            logger.error("Kiro file review error: %s", exc)
            return f"Error: {exc}"
