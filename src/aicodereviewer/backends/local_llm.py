# src/aicodereviewer/backends/local_llm.py
"""
Local LLM backend for code review and fix generation.

Supports LM Studio native API, Ollama, OpenAI-compatible and Anthropic-compatible 
HTTP API endpoints, enabling use with LM Studio, Ollama, vLLM, 
text-generation-webui, LocalAI, and other local inference servers.

Configuration (``config.ini`` ``[local_llm]`` section)::

    [local_llm]
    api_url   = http://localhost:1234
    api_type  = lmstudio       # lmstudio | ollama | openai | anthropic
    model     = default
    api_key   =                # optional – some servers require a dummy key
    timeout   = 300
    max_tokens = 4096
"""
import logging
import time
from typing import Any, Optional

import requests

from .base import AIBackend
from aicodereviewer.config import config

logger = logging.getLogger(__name__)


class LocalLLMBackend(AIBackend):
    """
    Local LLM backend using LM Studio native, Ollama, OpenAI-compatible, or Anthropic-compatible APIs.

    Works out-of-the-box with:
    - **LM Studio** (native API, OpenAI-compatible, or Anthropic-compatible)
    - **Ollama** (native API)
    - **vLLM** (OpenAI-compatible)
    - **text-generation-webui** (OpenAI extension)
    - **LocalAI** (OpenAI-compatible)
    - Any Anthropic-compatible local proxy
    
    URL Configuration (use base address + port only, no path suffix):
    - lmstudio: http://localhost:1234 → calls /api/v1/chat
    - ollama: http://localhost:11434 → calls /api/chat
    - openai: http://localhost:1234 → calls /v1/chat/completions
    - anthropic: http://localhost:1234 → calls /v1/messages
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_type: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        # Store base URL without any path suffix (e.g., http://localhost:1234, not http://localhost:1234/v1)
        self.api_url: str = str(
            api_url
            or config.get("local_llm", "api_url", "http://localhost:1234")
        ).rstrip("/")

        self.api_type: str = str(
            api_type
            or config.get("local_llm", "api_type", "lmstudio")
        ).strip().lower()

        self.model: str = str(model or config.get("local_llm", "model", "default"))
        self.api_key: str = str(api_key or config.get("local_llm", "api_key", ""))
        self.timeout: int = int(config.get("local_llm", "timeout", "300") or "300")
        self.max_tokens: int = int(config.get("local_llm", "max_tokens", "4096") or "4096")

        # Rate-limiting state
        self.last_request_time: float = 0.0
        self.min_request_interval: float = float(
            config.get("performance", "min_request_interval_seconds")
        )

        logger.info(
            "Local LLM backend: %s (type=%s, model=%s)",
            self.api_url, self.api_type, self.model,
        )

    def _get_model_to_use(self) -> str:
        """Get the actual model to use for inference.
        
        If self.model is 'default', attempts to fetch the first available model
        from the API. This handles cases where the user hasn't configured a specific
        model in settings.
        """
        if self.model != "default":
            return self.model
        
        # For default model, try to get the first available model from the API
        try:
            if self.api_type == "lmstudio":
                resp = requests.get(
                    f"{self.api_url}/api/v1/models",
                    headers=self._lmstudio_headers(),
                    timeout=5,
                )
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    if models:
                        return models[0].get("id", "default")
            elif self.api_type == "ollama":
                resp = requests.get(
                    f"{self.api_url}/api/tags",
                    headers=self._ollama_headers(),
                    timeout=5,
                )
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    if models:
                        return models[0].get("name", "default")
            elif self.api_type == "openai":
                resp = requests.get(
                    f"{self.api_url}/v1/models",
                    headers=self._openai_headers(),
                    timeout=5,
                )
                if resp.status_code == 200:
                    models = resp.json().get("data", [])
                    if models:
                        return models[0].get("id", "default")
        except Exception as e:
            logger.debug("Could not fetch model list for default model: %s", e)
        
        # Fall back to "default" if we couldn't fetch the model list
        return "default"

    # ── AIBackend interface ────────────────────────────────────────────────

    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
    ) -> str:
        max_content: int = int(config.get("performance", "max_content_length"))
        if len(code_content) > max_content:
            return (
                f"Error: Content too large for processing "
                f"({len(code_content)} > {max_content} characters)"
            )

        system_prompt = self._build_system_prompt(review_type, lang, self._project_context)
        user_message = self._build_user_message(code_content, review_type, spec_content)
        return self._invoke(system_prompt, user_message)

    def get_fix(
        self,
        code_content: str,
        issue_feedback: str,
        review_type: str = "best_practices",
        lang: str = "en",
    ) -> Optional[str]:
        max_content: int = int(config.get("performance", "max_fix_content_length"))
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
            if self.api_type == "lmstudio":
                return self._validate_lmstudio()
            elif self.api_type == "ollama":
                return self._validate_ollama()
            elif self.api_type == "openai":
                return self._validate_openai()
            elif self.api_type == "anthropic":
                return self._validate_anthropic()
            else:
                logger.error("Unknown api_type '%s'. Use 'lmstudio', 'ollama', 'openai' or 'anthropic'.", self.api_type)
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

    # ── shared validation helper ───────────────────────────────────────────

    def _validate_with_model_discovery(
        self,
        list_url: str,
        list_parser: str,
        test_url: str,
        test_payload_fn: Any,
        headers: dict[str, str],
        label: str,
    ) -> bool:
        """Common validation logic: discover models, then run a test inference.

        Args:
            list_url: URL to GET the model list (empty to skip discovery).
            list_parser: Key indicating response format (``'openai'``, ``'ollama'``, ``'lmstudio'``).
            test_url: URL to POST a test inference request.
            test_payload_fn: Callable ``(model_name) -> dict`` that builds the test payload.
            headers: HTTP headers for both requests.
            label: Human-readable label for log messages.
        """
        model_to_test = self.model

        # Step 1 – discover available models
        if list_url:
            try:
                resp = requests.get(list_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    models = self._parse_model_list(resp.json(), list_parser)
                    if models:
                        logger.info("Available %s models: %s", label, ", ".join(models[:5]))
                        if self.model == "default":
                            model_to_test = models[0]
                    else:
                        logger.warning("No models available on %s server.", label)
                        return True  # server reachable, that's enough
            except Exception as exc:
                logger.error("Failed to list %s models: %s", label, exc)
                return False

        # Step 2 – tiny inference test
        try:
            payload = test_payload_fn(model_to_test)
            resp = requests.post(test_url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return True
            logger.error("%s returned HTTP %d: %s", label, resp.status_code, resp.text[:200])
            return False
        except Exception as exc:
            logger.error("%s inference test failed: %s", label, exc)
            return False

    @staticmethod
    def _parse_model_list(data: dict, parser: str) -> list[str]:
        """Extract model identifiers from an API response."""
        if parser in ("openai", "lmstudio"):
            return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        if parser == "ollama":
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        return []

    # ── LM Studio native API ───────────────────────────────────────────────

    def _validate_lmstudio(self) -> bool:
        """Validate LM Studio native API endpoint."""
        headers = self._lmstudio_headers()
        return self._validate_with_model_discovery(
            list_url=f"{self.api_url}/api/v1/models",
            list_parser="lmstudio",
            test_url=f"{self.api_url}/api/v1/chat",
            test_payload_fn=lambda model: {
                "model": model, "input": "Hello",
                "max_output_tokens": 5, "temperature": 0,
            },
            headers=headers,
            label="LM Studio",
        )

    def _invoke_lmstudio(self, system_prompt: str, user_message: str) -> str:
        """Send a chat request to LM Studio native API."""
        headers: dict[str, str] = self._lmstudio_headers()
        
        # Combine system prompt and user message
        full_input = f"{system_prompt}\n\n{user_message}"
        
        # Get the actual model to use (handles "default" case)
        model_to_use = self._get_model_to_use()
        
        payload: dict[str, Any] = {
            "model": model_to_use,
            "input": full_input,
            "max_output_tokens": self.max_tokens,
            "temperature": 0.1,
        }

        resp = requests.post(
            f"{self.api_url}/api/v1/chat",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            return f"Error: HTTP {resp.status_code} \u2013 {resp.text[:300]}"

        data = resp.json()
        self.last_request_time = time.time()

        # Extract message content from output array
        output = data.get("output", [])
        if output:
            # Find the first message type output
            for item in output:
                if item.get("type") == "message":
                    return item.get("content", "")
        return "Error: Empty response from LM Studio."

    def _lmstudio_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # ── Ollama API ─────────────────────────────────────────────────────────

    def _validate_ollama(self) -> bool:
        """Validate Ollama API endpoint."""
        headers = self._ollama_headers()
        return self._validate_with_model_discovery(
            list_url=f"{self.api_url}/api/tags",
            list_parser="ollama",
            test_url=f"{self.api_url}/api/chat",
            test_payload_fn=lambda model: {
                "model": model,
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
                "options": {"temperature": 0},
            },
            headers=headers,
            label="Ollama",
        )

    def _invoke_ollama(self, system_prompt: str, user_message: str) -> str:
        """Send a chat request to Ollama API."""
        headers: dict[str, str] = self._ollama_headers()
        
        # Build messages with system prompt
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        
        # Get the actual model to use (handles "default" case)
        model_to_use = self._get_model_to_use()
        
        payload: dict[str, Any] = {
            "model": model_to_use,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": self.max_tokens,
            },
        }

        resp = requests.post(
            f"{self.api_url}/api/chat",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            return f"Error: HTTP {resp.status_code} \u2013 {resp.text[:300]}"

        data = resp.json()
        self.last_request_time = time.time()

        # Extract message content
        message = data.get("message", {})
        if message:
            return message.get("content", "")
        return "Error: Empty response from Ollama."

    def _ollama_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        # Ollama typically doesn't require authentication for local use
        # but we'll add it if provided
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # ── OpenAI-compatible ──────────────────────────────────────────────────

    def _validate_openai(self) -> bool:
        """Validate an OpenAI-compatible endpoint."""
        headers = self._openai_headers()
        return self._validate_with_model_discovery(
            list_url=f"{self.api_url}/v1/models",
            list_parser="openai",
            test_url=f"{self.api_url}/v1/chat/completions",
            test_payload_fn=lambda model: {
                "model": model,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5,
                "temperature": 0,
            },
            headers=headers,
            label="OpenAI-compatible",
        )

    def _validate_anthropic(self) -> bool:
        """Validate an Anthropic-compatible endpoint."""
        headers = self._anthropic_headers()
        return self._validate_with_model_discovery(
            list_url="",  # Anthropic endpoints don't have a /models endpoint
            list_parser="",
            test_url=f"{self.api_url}/v1/messages",
            test_payload_fn=lambda model: {
                "model": model,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5,
            },
            headers=headers,
            label="Anthropic-compatible",
        )

    # ── invocation ─────────────────────────────────────────────────────────

    def _invoke(self, system_prompt: str, user_message: str) -> str:
        """Dispatch to the appropriate API implementation."""
        self._enforce_rate_limit()
        try:
            if self.api_type == "lmstudio":
                return self._invoke_lmstudio(system_prompt, user_message)
            elif self.api_type == "ollama":
                return self._invoke_ollama(system_prompt, user_message)
            elif self.api_type == "openai":
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
        headers: dict[str, str] = self._openai_headers()
        
        # Get the actual model to use (handles "default" case)
        model_to_use = self._get_model_to_use()
        
        payload: dict[str, Any] = {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.max_tokens,
            "temperature": 0.1,
        }

        resp = requests.post(
            f"{self.api_url}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            return f"Error: HTTP {resp.status_code} \u2013 {resp.text[:300]}"

        data = resp.json()
        self.last_request_time = time.time()

        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return "Error: Empty response from local LLM."

    def _invoke_anthropic(self, system_prompt: str, user_message: str) -> str:
        """Send a messages request to an Anthropic-compatible endpoint."""
        headers: dict[str, str] = self._anthropic_headers()
        
        # Get the actual model to use (handles "default" case)
        model_to_use = self._get_model_to_use()
        
        payload: dict[str, Any] = {
            "model": model_to_use,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.max_tokens,
            "temperature": 0.1,
        }

        resp = requests.post(
            f"{self.api_url}/v1/messages",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            return f"Error: HTTP {resp.status_code} \u2013 {resp.text[:300]}"

        data = resp.json()
        self.last_request_time = time.time()

        content = data.get("content", [])
        if content:
            # Anthropic returns a list of content blocks
            texts = [block.get("text", "") for block in content if block.get("type") == "text"]
            return "\n".join(texts)
        return "Error: Empty response from local LLM."

    # ── helpers ────────────────────────────────────────────────────────────

    def _openai_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _anthropic_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _enforce_rate_limit(self) -> None:
        """Enforce minimum request interval."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
