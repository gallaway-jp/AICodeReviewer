# src/aicodereviewer/backends/kiro.py
"""
Kiro CLI backend for code review via WSL.

Kiro is Amazon's AI-powered development tool.  On Windows the CLI runs
inside WSL while accessing Windows-local files through ``/mnt/`` paths.

This backend shells out to ``kiro`` inside WSL, converts Windows paths
transparently, and parses the plain-text output.
"""
import json
import logging
import tempfile
import os
from typing import Optional

from .base import AIBackend
from aicodereviewer.config import config
from aicodereviewer.path_utils import (
    windows_to_wsl_path,
    is_wsl_available,
    run_in_wsl,
    ensure_wsl_tool,
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
        timeout = 300
    """

    def __init__(self, **kwargs):
        self.distro: Optional[str] = (
            config.get("kiro", "wsl_distro", "").strip() or None
        )
        self.cli_cmd: str = config.get("kiro", "cli_command", "kiro").strip()
        self.timeout: int = int(config.get("kiro", "timeout", "300"))

        if os.name == "nt" and not is_wsl_available():
            raise RuntimeError(
                "WSL is not available. Kiro backend requires Windows Subsystem "
                "for Linux. Install WSL with: wsl --install"
            )

    # ── AIBackend interface ────────────────────────────────────────────────

    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
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

    # ── private helpers ────────────────────────────────────────────────────

    def _run_kiro_prompt(self, prompt: str) -> str:
        """
        Send a prompt to Kiro CLI and capture the response.

        The prompt is written to a temporary file that is shared with WSL
        through the /mnt/ path mechanism, then passed via stdin to the
        Kiro CLI.
        """
        try:
            if os.name == "nt":
                # Write prompt to a temp file so we can pass it via stdin
                # through WSL boundary cleanly
                rc, stdout, stderr = run_in_wsl(
                    [self.cli_cmd, "chat", "--no-interactive"],
                    distro=self.distro,
                    timeout=self.timeout,
                    stdin_data=prompt,
                )
                if rc != 0:
                    err_msg = stderr.strip() or f"Kiro exited with code {rc}"
                    logger.error("Kiro CLI error: %s", err_msg)
                    return f"Error: Kiro CLI – {err_msg}"
                return stdout.strip()
            else:
                # Native Linux/macOS execution
                import subprocess
                result = subprocess.run(
                    [self.cli_cmd, "chat", "--no-interactive"],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                if result.returncode != 0:
                    err_msg = result.stderr.strip() or f"Kiro exited with code {result.returncode}"
                    return f"Error: Kiro CLI – {err_msg}"
                return result.stdout.strip()

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

            if os.name == "nt":
                rc, stdout, stderr = run_in_wsl(
                    [self.cli_cmd, "review", wsl_path],
                    distro=self.distro,
                    timeout=self.timeout,
                    stdin_data=prompt,
                )
                if rc != 0:
                    return f"Error: Kiro CLI – {stderr.strip()}"
                return stdout.strip()
            else:
                import subprocess
                result = subprocess.run(
                    [self.cli_cmd, "review", wsl_path],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                if result.returncode != 0:
                    return f"Error: Kiro CLI – {result.stderr.strip()}"
                return result.stdout.strip()

        except Exception as exc:
            logger.error("Kiro file review error: %s", exc)
            return f"Error: {exc}"
