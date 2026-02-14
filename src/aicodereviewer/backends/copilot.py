# src/aicodereviewer/backends/copilot.py
"""
GitHub Copilot CLI backend for code review.

Uses the ``gh copilot`` extension (GitHub Copilot in the CLI) on Windows
to perform AI-powered code review and fix generation.

Prerequisites:
    1. GitHub CLI installed (``gh``)
    2. Copilot CLI extension installed (``gh extension install github/gh-copilot``)
    3. Authenticated (``gh auth login``)
    4. Active GitHub Copilot Pro / Business / Enterprise subscription
"""
import json
import logging
import subprocess
import os
import shutil
from typing import Optional

from .base import AIBackend
from aicodereviewer.config import config

logger = logging.getLogger(__name__)


class CopilotBackend(AIBackend):
    """
    AI backend that delegates to GitHub Copilot via the ``gh`` CLI.

    Configuration (``config.ini``):

    .. code-block:: ini

        [backend]
        type = copilot

        [copilot]
        gh_path = gh
        timeout = 300
        model = gpt-4
    """

    def __init__(self, **kwargs):
        self.gh_path: str = config.get("copilot", "gh_path", "gh").strip()
        self.timeout: int = int(config.get("copilot", "timeout", "300"))
        self.model: str = config.get("copilot", "model", "").strip()

    # ── AIBackend interface ────────────────────────────────────────────────

    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
    ) -> str:
        system_prompt = self._build_system_prompt(review_type, lang)
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
        """Check gh CLI is installed, authenticated, and Copilot extension is available."""
        # 1. Check gh CLI exists
        if not shutil.which(self.gh_path):
            logger.error("GitHub CLI ('%s') not found in PATH.", self.gh_path)
            logger.error(
                "Install from https://cli.github.com/ and run 'gh auth login'."
            )
            return False

        # 2. Check authentication
        try:
            result = subprocess.run(
                [self.gh_path, "auth", "status"],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                logger.error(
                    "GitHub CLI not authenticated. Run 'gh auth login' first."
                )
                return False
        except Exception as exc:
            logger.error("Failed to check gh auth status: %s", exc)
            return False

        # 3. Check Copilot extension
        try:
            result = subprocess.run(
                [self.gh_path, "copilot", "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                logger.error(
                    "GitHub Copilot CLI extension not found. "
                    "Install with: gh extension install github/gh-copilot"
                )
                return False
        except Exception as exc:
            logger.error("Copilot extension check failed: %s", exc)
            return False

        return True

    # ── private helpers ────────────────────────────────────────────────────

    def _run_copilot(self, prompt: str) -> str:
        """
        Send a prompt to GitHub Copilot CLI and capture the response.

        Uses ``gh copilot suggest`` in shell mode for general prompts, or
        ``gh copilot explain`` for code review prompts. The approach pipes
        the prompt via flags/stdin.
        """
        try:
            # Build command – gh copilot suggest -t code "<prompt>"
            cmd = [self.gh_path, "copilot", "suggest", "-t", "code"]
            if self.model:
                cmd.extend(["--model", self.model])

            env = os.environ.copy()
            # Disable interactive mode for automation
            env["GH_PROMPT_DISABLED"] = "1"
            env["NO_COLOR"] = "1"

            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            if result.returncode != 0:
                # Try the explain subcommand as fallback
                return self._run_copilot_explain(prompt)

            output = result.stdout.strip()
            if output:
                return output

            # Fallback to explain subcommand
            return self._run_copilot_explain(prompt)

        except subprocess.TimeoutExpired:
            return "Error: GitHub Copilot CLI timed out."
        except Exception as exc:
            logger.error("Copilot backend error: %s", exc)
            return f"Error: {exc}"

    def _run_copilot_explain(self, prompt: str) -> str:
        """Fallback using ``gh copilot explain``."""
        try:
            cmd = [self.gh_path, "copilot", "explain"]

            env = os.environ.copy()
            env["GH_PROMPT_DISABLED"] = "1"
            env["NO_COLOR"] = "1"

            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            if result.returncode != 0:
                err = result.stderr.strip() or f"gh copilot exited with code {result.returncode}"
                return f"Error: GitHub Copilot CLI – {err}"

            return result.stdout.strip() or "Error: No output from GitHub Copilot CLI."

        except subprocess.TimeoutExpired:
            return "Error: GitHub Copilot CLI timed out."
        except Exception as exc:
            return f"Error: {exc}"
