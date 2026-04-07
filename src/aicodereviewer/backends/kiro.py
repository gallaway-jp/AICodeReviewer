# src/aicodereviewer/backends/kiro.py
"""
Kiro CLI backend for code review via WSL.

Kiro is Amazon's AI-powered development tool.  On Windows the CLI runs
inside WSL while accessing Windows-local files through ``/mnt/`` paths.

This backend shells out to ``kiro`` inside WSL, converts Windows paths
transparently, and parses the plain-text output.
"""
import logging
import os
import shlex
import subprocess
import time
from typing import Optional

from .base import AIBackend
from aicodereviewer.config import config
from aicodereviewer.path_utils import (
    windows_to_wsl_path,
    is_wsl_available,
    run_in_wsl,
    ensure_wsl_tool,
    CancelledProcessError,
)

logger = logging.getLogger(__name__)


class KiroBackend(AIBackend):
    """
    AI backend that delegates to the Kiro CLI running in WSL.

    Configuration (``config.ini``):

    .. code-block:: ini

        [backend]
        type = kiro

        [kiro]
        wsl_distro = Ubuntu
        cli_command = kiro
        model = claude-3-5-sonnet
        timeout = 300
    """

    def __init__(self, **kwargs):
        self.distro: Optional[str] = (
            config.get("kiro", "wsl_distro", "").strip() or None
        )
        self.cli_cmd: str = config.get("kiro", "cli_command", "kiro").strip()
        self.model: str = config.get("kiro", "model", "").strip() or None
        self.timeout: int = int(float(config.get("kiro", "timeout", "300")))
        self._cancel_requested: bool = False

        if os.name == "nt" and not is_wsl_available():
            raise RuntimeError(
                "WSL is not available. Kiro backend requires Windows Subsystem "
                "for Linux. Install WSL with: wsl --install"
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
            # Running natively on Linux/macOS – just check PATH
            import shutil
            if not shutil.which(self.cli_cmd):
                logger.error("Kiro CLI ('%s') not found in PATH.", self.cli_cmd)
                return False
        return True

    def validate_connection_diagnostic(self) -> dict[str, str | bool]:
        if os.name == "nt":
            if not is_wsl_available():
                return {
                    "ok": False,
                    "category": "tool_compatibility",
                    "detail": "WSL is not available.",
                    "fix_hint": "Install and enable WSL before using the Kiro backend.",
                    "origin": "connection_test",
                }
            if not ensure_wsl_tool(self.cli_cmd, self.distro):
                return {
                    "ok": False,
                    "category": "tool_compatibility",
                    "detail": (
                        f"Kiro CLI ('{self.cli_cmd}') was not found in WSL"
                        f" ({self.distro})." if self.distro else f"Kiro CLI ('{self.cli_cmd}') was not found in WSL."
                    ),
                    "fix_hint": "Install Kiro CLI inside the target WSL distribution and verify the configured command.",
                    "origin": "connection_test",
                }
        else:
            import shutil

            if not shutil.which(self.cli_cmd):
                return {
                    "ok": False,
                    "category": "tool_compatibility",
                    "detail": f"Kiro CLI ('{self.cli_cmd}') was not found in PATH.",
                    "fix_hint": "Install Kiro CLI or update the configured CLI command.",
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

    def _run_native_bash(self, bash_cmd: str, prompt: str) -> str:
        """Run a native bash command with cancellation polling."""
        process = subprocess.Popen(
            ["bash", "-lc", bash_cmd],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
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
                raise subprocess.TimeoutExpired(["bash", "-lc", bash_cmd], self.timeout)

            try:
                stdout, stderr = process.communicate(
                    input=pending_input,
                    timeout=min(0.2, remaining),
                )
                if process.returncode != 0:
                    err_msg = stderr.strip() or f"Kiro exited with code {process.returncode}"
                    return f"Error: Kiro CLI – {err_msg}"
                return stdout.strip()
            except subprocess.TimeoutExpired:
                pending_input = None
                continue

    def _run_kiro_prompt(self, prompt: str) -> str:
        """
        Send a prompt to Kiro CLI and capture the response.

        The prompt is written to a temporary file that is shared with WSL
        through the /mnt/ path mechanism, then passed via stdin to the
        Kiro CLI.
        """
        try:
            # Build the kiro-cli invocation; use bash -lc on both platforms so
            # that ~/.local/bin (where kiro-cli lives) is always on the PATH.
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

        On Windows the path is transparently converted to a WSL mount path.
        """
        try:
            if os.name == "nt":
                wsl_path = windows_to_wsl_path(file_path)
            else:
                wsl_path = file_path

            system_prompt = self._build_system_prompt(
                review_type, lang, self._project_context, self._detected_frameworks,
            )
            prompt = f"{system_prompt}\n\nReview the file at: {wsl_path}"

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
