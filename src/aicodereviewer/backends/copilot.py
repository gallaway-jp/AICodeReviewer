# src/aicodereviewer/backends/copilot.py
"""
GitHub Copilot CLI backend for code review.

Uses the standalone GitHub Copilot CLI (``copilot``) in **programmatic mode**
(``copilot -p "…"``) to perform AI-powered code review and fix generation.

Prerequisites:
    1. GitHub Copilot CLI installed (``winget install GitHub.Copilot`` on Windows,
       ``brew install copilot-cli`` on macOS/Linux, or ``npm install -g @github/copilot``)
    2. Authenticated (run ``copilot`` and use ``/login``, or set ``GH_TOKEN``
       / ``GITHUB_TOKEN`` env-var with a PAT that has *Copilot Requests* permission)
    3. Active GitHub Copilot Pro / Business / Enterprise subscription
"""
import logging
import subprocess
import os
import shutil
import tempfile
from typing import Any, Optional

from .base import AIBackend
from aicodereviewer.config import config

logger = logging.getLogger(__name__)


class CopilotBackend(AIBackend):
    """
    AI backend that delegates to the standalone GitHub Copilot CLI.

    Configuration (``config.ini``):

    .. code-block:: ini

        [backend]
        type = copilot

        [copilot]
        copilot_path = copilot
        timeout = 300
        model = auto
    """

    def __init__(self, **kwargs: Any) -> None:
        self.copilot_path: str = config.get("copilot", "copilot_path", "copilot").strip()
        self.timeout: int = int(config.get("copilot", "timeout", "300"))
        self.model: str = config.get("copilot", "model", "auto").strip()
        self._current_process = None  # Track subprocess for cancellation

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
        return self._run_copilot(full_prompt)

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
        result = self._run_copilot(full_prompt)
        if result and not result.startswith("Error:"):
            return result.strip()
        return None

    def validate_connection(self) -> bool:
        """Check Copilot CLI is installed and authenticated."""
        # 1. Check copilot CLI exists and is the genuine standalone CLI
        found = shutil.which(self.copilot_path)
        if not found:
            logger.error(
                "GitHub Copilot CLI ('%s') not found in PATH.", self.copilot_path
            )
            logger.error(
                "Install from https://docs.github.com/en/copilot/github-copilot-in-the-cli"
            )
            return False

        # Verify it responds to --version (filters out leftover .BAT stubs)
        try:
            result = subprocess.run(
                [found, "--version"],
                capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                logger.error(
                    "Found '%s' but it does not appear to be the standalone "
                    "GitHub Copilot CLI. Install from "
                    "https://docs.github.com/en/copilot/github-copilot-in-the-cli",
                    found,
                )
                return False
        except Exception as exc:
            logger.error("Failed to verify Copilot CLI at '%s': %s", found, exc)
            return False

        # 2. Check authentication (config dir or env token)
        home = os.path.expanduser("~")
        copilot_config_dirs = [
            os.path.join(home, ".copilot"),
            os.path.join(home, ".config", "github-copilot"),
        ]
        has_config = any(os.path.isdir(d) for d in copilot_config_dirs)
        has_token = bool(
            os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        )
        if not has_config and not has_token:
            logger.error(
                "GitHub Copilot CLI is not authenticated. "
                "Run 'copilot' and use /login, or set GH_TOKEN / GITHUB_TOKEN."
            )
            return False

        return True

    # ── private helpers ────────────────────────────────────────────────────

    def _run_copilot(self, prompt: str) -> str:
        """
        Send a prompt to GitHub Copilot CLI in programmatic mode.

        Uses ``copilot -p "…"`` which runs non-interactively, returning
        the agent's text response on stdout.
        
        For very long prompts (>5000 chars), writes to a temporary file
        and uses ``copilot -p "$(cat file)"`` approach to avoid Windows
        command line length limitations (WinError 206).
        """
        try:
            env = os.environ.copy()
            # Suppress colour codes for clean parsing
            env["NO_COLOR"] = "1"

            # Windows has command line length limits (~8191 chars for cmd.exe).
            # Use a temporary file for long prompts to avoid WinError 206.
            use_temp_file = len(prompt) > 5000

            if use_temp_file:
                # Write prompt to a temporary file, then read it back
                # This avoids command line length limits while still using -p
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.txt', delete=False,
                    encoding='utf-8'
                ) as f:
                    f.write(prompt)
                    temp_path = f.name

                try:
                    # On Windows, use PowerShell to read file content
                    # On Unix, use cat
                    if os.name == 'nt':
                        # Use PowerShell to read file and pass to copilot
                        # -NoProfile -NonInteractive for faster startup
                        ps_cmd = f'$content = Get-Content -Raw -Path "{temp_path}"; & "{self.copilot_path}" -p $content'
                        if self.model and self.model.lower() != "auto":
                            ps_cmd = f'$content = Get-Content -Raw -Path "{temp_path}"; & "{self.copilot_path}" -p $content --model "{self.model}"'
                        
                        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd]
                    else:
                        # Unix: use shell substitution
                        cmd = f'{self.copilot_path} -p "$(cat {temp_path})"'
                        if self.model and self.model.lower() != "auto":
                            cmd += f' --model "{self.model}"'
                        cmd = ["sh", "-c", cmd]

                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env=env,
                        encoding="utf-8", errors="replace",
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    self._current_process = proc
                    try:
                        stdout, stderr = proc.communicate(timeout=self.timeout)
                        returncode = proc.returncode
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()  # Clean up
                        return "Error: GitHub Copilot CLI timed out."
                    finally:
                        self._current_process = None
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
            else:
                # Pass prompt as command line argument (original behavior)
                cmd = [self.copilot_path, "-p", prompt]
                if self.model and self.model.lower() != "auto":
                    cmd.extend(["--model", self.model])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=env,
                    encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                returncode = result.returncode
                stdout = result.stdout
                stderr = result.stderr

            if returncode != 0:
                err = (
                    (stderr or "").strip()
                    or f"copilot exited with code {returncode}"
                )
                return f"Error: GitHub Copilot CLI – {err}"

            output = (stdout or "").strip()
            return output or "Error: No output from GitHub Copilot CLI."

        except subprocess.TimeoutExpired:
            return "Error: GitHub Copilot CLI timed out."
        except Exception as exc:
            logger.error("Copilot backend error: %s", exc)
            return f"Error: {exc}"

    def cancel(self):
        """Terminate the currently running subprocess if any."""
        if self._current_process:
            try:
                self._current_process.terminate()
                logger.info("Cancelled Copilot subprocess")
            except Exception as exc:
                logger.warning("Failed to terminate Copilot process: %s", exc)
