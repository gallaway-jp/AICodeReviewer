# src/aicodereviewer/backends/local_llm.py
"""
Local LLM backend for code review and fix generation.

Supports OpenAI-compatible and Anthropic-compatible HTTP API endpoints,
enabling use with LM Studio, Ollama, vLLM, text-generation-webui,
LocalAI, and other local inference servers.

Configuration (``config.ini`` ``[local_llm]`` section)::

    [local_llm]
    api_url   = http://localhost:1234/v1
    api_type  = openai          # openai | anthropic
    model     = default
    api_key   =                 # optional – some servers require a dummy key
    timeout   = 300
    max_tokens = 4096
"""
import logging
import time
from typing import Optional

import requests

from .base import AIBackend
from aicodereviewer.config import config

logger = logging.getLogger(__name__)


class LocalLLMBackend(AIBackend):
    """
    Local LLM backend using OpenAI-compatible or Anthropic-compatible APIs.

    Works out-of-the-box with:
    - **LM Studio** (OpenAI-compatible)
    - **Ollama** (``/v1/chat/completions``)
    - **vLLM** (OpenAI-compatible)
    - **text-generation-webui** (OpenAI extension)
    - **LocalAI** (OpenAI-compatible)
    - Any Anthropic-compatible local proxy
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_type: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.api_url = (
            api_url
            or config.get("local_llm", "api_url", "http://localhost:1234/v1")
        ).rstrip("/")

        self.api_type = (
            api_type
            or config.get("local_llm", "api_type", "openai")
        ).strip().lower()

        self.model = model or config.get("local_llm", "model", "default")
        self.api_key = api_key or config.get("local_llm", "api_key", "")
        self.timeout = int(config.get("local_llm", "timeout", "300") or "300")
        self.max_tokens = int(config.get("local_llm", "max_tokens", "4096") or "4096")

        # Rate-limiting state
        self.last_request_time: float = 0.0
        self.min_request_interval: float = config.get(
            "performance", "min_request_interval_seconds"
        )

        logger.info(
            "Local LLM backend: %s (type=%s, model=%s)",
            self.api_url, self.api_type, self.model,
        )

    # ── AIBackend interface ────────────────────────────────────────────────

    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
    ) -> str:
        max_content = config.get("performance", "max_content_length")
        if len(code_content) > max_content:
            return (
                f"Error: Content too large for processing "
                f"({len(code_content)} > {max_content} characters)"
            )

        system_prompt = self._build_system_prompt(review_type, lang)
        user_message = self._build_user_message(code_content, review_type, spec_content)
        return self._invoke(system_prompt, user_message)

    def get_fix(
        self,
        code_content: str,
        issue_feedback: str,
        review_type: str = "best_practices",
        lang: str = "en",
    ) -> Optional[str]:
        max_content = config.get("performance", "max_fix_content_length")
        if len(code_content) > max_content:
            logger.warning("File too large for AI fix (%d chars)", len(code_content))
            return None

        system_prompt = self._build_system_prompt("fix", lang)
        user_message = self._build_fix_message(code_content, issue_feedback, review_type)
        result = self._invoke(system_prompt, user_message)
        if result and not result.startswith("Error:"):
            return result.strip()
        return None

    def validate_connection(self) -> bool:
        """
        Test connectivity to the local LLM server.

        Checks:
            1. Server is reachable (GET /models or similar)
            2. A short inference call succeeds
        """
        try:
            if self.api_type == "openai":
                return self._validate_openai()
            elif self.api_type == "anthropic":
                return self._validate_anthropic()
            else:
                logger.error("Unknown api_type '%s'. Use 'openai' or 'anthropic'.", self.api_type)
                return False
        except requests.ConnectionError:
            logger.error(
                "Cannot connect to %s. Is the LLM server running?", self.api_url,
            )
            return False
        except requests.Timeout:
            logger.error("Connection to %s timed out.", self.api_url)
            return False
        except Exception as exc:
            logger.error("Local LLM connection test failed: %s", exc)
            return False

    # ── OpenAI-compatible ──────────────────────────────────────────────────

    def _validate_openai(self) -> bool:
        """Validate an OpenAI-compatible endpoint."""
        headers = self._openai_headers()

        # Try listing models first
        try:
            resp = requests.get(
                f"{self.api_url}/models",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                if models:
                    logger.info("Available models: %s", ", ".join(models[:5]))
        except Exception:
            pass  # Not all servers support /models

        # Test with a tiny inference call
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5,
            "temperature": 0,
        }
        resp = requests.post(
            f"{self.api_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            return True
        else:
            logger.error(
                "Local LLM returned HTTP %d: %s", resp.status_code, resp.text[:200],
            )
            return False

    def _validate_anthropic(self) -> bool:
        """Validate an Anthropic-compatible endpoint."""
        headers = self._anthropic_headers()
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5,
        }
        resp = requests.post(
            f"{self.api_url}/messages",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            return True
        else:
            logger.error(
                "Local LLM returned HTTP %d: %s", resp.status_code, resp.text[:200],
            )
            return False

    # ── invocation ─────────────────────────────────────────────────────────

    def _invoke(self, system_prompt: str, user_message: str) -> str:
        """Dispatch to the appropriate API implementation."""
        self._enforce_rate_limit()
        try:
            if self.api_type == "openai":
                return self._invoke_openai(system_prompt, user_message)
            elif self.api_type == "anthropic":
                return self._invoke_anthropic(system_prompt, user_message)
            else:
                return f"Error: Unknown api_type '{self.api_type}'"
        except requests.ConnectionError:
            return f"Error: Cannot connect to {self.api_url}. Is the LLM server running?"
        except requests.Timeout:
            return f"Error: Request to {self.api_url} timed out after {self.timeout}s."
        except Exception as exc:
            return f"Error: {exc}"

    def _invoke_openai(self, system_prompt: str, user_message: str) -> str:
        """Send a chat completion request to an OpenAI-compatible endpoint."""
        headers = self._openai_headers()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.max_tokens,
            "temperature": 0.1,
        }

        resp = requests.post(
            f"{self.api_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            return f"Error: HTTP {resp.status_code} – {resp.text[:300]}"

        data = resp.json()
        self.last_request_time = time.time()

        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return "Error: Empty response from local LLM."

    def _invoke_anthropic(self, system_prompt: str, user_message: str) -> str:
        """Send a messages request to an Anthropic-compatible endpoint."""
        headers = self._anthropic_headers()
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.max_tokens,
            "temperature": 0.1,
        }

        resp = requests.post(
            f"{self.api_url}/messages",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            return f"Error: HTTP {resp.status_code} – {resp.text[:300]}"

        data = resp.json()
        self.last_request_time = time.time()

        content = data.get("content", [])
        if content:
            # Anthropic returns a list of content blocks
            texts = [block.get("text", "") for block in content if block.get("type") == "text"]
            return "\n".join(texts)
        return "Error: Empty response from local LLM."

    # ── helpers ────────────────────────────────────────────────────────────

    def _openai_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _anthropic_headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _enforce_rate_limit(self):
        """Enforce minimum request interval."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
