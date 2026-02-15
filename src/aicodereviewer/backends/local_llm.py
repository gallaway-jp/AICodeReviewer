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
from typing import Optional

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
        self.api_url = (
            api_url
            or config.get("local_llm", "api_url", "http://localhost:1234")
        ).rstrip("/")

        self.api_type = (
            api_type
            or config.get("local_llm", "api_type", "lmstudio")
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

    # ── LM Studio native API ───────────────────────────────────────────────

    def _validate_lmstudio(self) -> bool:
        """Validate LM Studio native API endpoint."""
        headers = self._lmstudio_headers()
        model_to_test = self.model  # Use configured model if not 'default'

        # Try listing models first to get a real model if using default
        try:
            resp = requests.get(
                f"{self.api_url}/api/v1/models",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                if models:
                    model_ids = [m.get("id", "") for m in models]
                    logger.info("Available LM Studio models: %s", ", ".join(model_ids[:5]))
                    # Use first available model for testing if default is not valid
                    if self.model == "default" and model_ids:
                        model_to_test = model_ids[0]
                else:
                    # No models loaded - that's a configuration issue, but don't fail validation
                    # Just indicate we can reach the server
                    logger.warning("No models available on LM Studio server. Models need to be loaded first.")
                    # Return True if we could reach the models endpoint
                    return True
        except Exception as e:
            logger.error("Failed to list LM Studio models: %s", e)
            return False

        # Test with a tiny inference call using validated model
        try:
            payload = {
                "model": model_to_test,
                "input": "Hello",
                "max_output_tokens": 5,
                "temperature": 0,
            }
            resp = requests.post(
                f"{self.api_url}/api/v1/chat",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if resp.status_code == 200:
                return True
            else:
                logger.error(
                    "LM Studio returned HTTP %d: %s", resp.status_code, resp.text[:200],
                )
                return False
        except Exception as e:
            logger.error("LM Studio inference test failed: %s", e)
            return False

    def _invoke_lmstudio(self, system_prompt: str, user_message: str) -> str:
        """Send a chat request to LM Studio native API."""
        headers = self._lmstudio_headers()
        
        # Combine system prompt and user message
        full_input = f"{system_prompt}\n\n{user_message}"
        
        # Get the actual model to use (handles "default" case)
        model_to_use = self._get_model_to_use()
        
        payload = {
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
            return f"Error: HTTP {resp.status_code} – {resp.text[:300]}"

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

    def _lmstudio_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # ── Ollama API ─────────────────────────────────────────────────────────

    def _validate_ollama(self) -> bool:
        """Validate Ollama API endpoint."""
        headers = self._ollama_headers()
        model_to_test = self.model  # Use configured model if not 'default'

        # Try listing models first to get a real model if using default
        try:
            resp = requests.get(
                f"{self.api_url}/api/tags",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                if models:
                    model_names = [m.get("name", "") for m in models]
                    logger.info("Available Ollama models: %s", ", ".join(model_names[:5]))
                    # Use first available model for testing if default is not valid
                    if self.model == "default" and model_names:
                        model_to_test = model_names[0]
                else:
                    # No models pulled - that's a configuration issue, but server is reachable
                    logger.warning("No models available on Ollama server. Models need to be pulled first.")
                    # Return True if we could reach the models endpoint
                    return True
        except Exception as e:
            logger.error("Failed to list Ollama models: %s", e)
            return False

        # Test with a tiny inference call using validated model
        try:
            payload = {
                "model": model_to_test,
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
                "options": {"temperature": 0},
            }
            resp = requests.post(
                f"{self.api_url}/api/chat",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if resp.status_code == 200:
                return True
            else:
                logger.error(
                    "Ollama returned HTTP %d: %s", resp.status_code, resp.text[:200],
                )
                return False
        except Exception as e:
            logger.error("Ollama inference test failed: %s", e)
            return False

    def _invoke_ollama(self, system_prompt: str, user_message: str) -> str:
        """Send a chat request to Ollama API."""
        headers = self._ollama_headers()
        
        # Build messages with system prompt
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        
        # Get the actual model to use (handles "default" case)
        model_to_use = self._get_model_to_use()
        
        payload = {
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
            return f"Error: HTTP {resp.status_code} – {resp.text[:300]}"

        data = resp.json()
        self.last_request_time = time.time()

        # Extract message content
        message = data.get("message", {})
        if message:
            return message.get("content", "")
        return "Error: Empty response from Ollama."

    def _ollama_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        # Ollama typically doesn't require authentication for local use
        # but we'll add it if provided
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # ── OpenAI-compatible ──────────────────────────────────────────────────

    def _validate_openai(self) -> bool:
        """Validate an OpenAI-compatible endpoint."""
        headers = self._openai_headers()
        model_to_test = self.model  # Use configured model if not 'default'

        # Try listing models first to get a real model if using default
        try:
            resp = requests.get(
                f"{self.api_url}/v1/models",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                if models:
                    logger.info("Available models: %s", ", ".join(models[:5]))
                    # Use first available model for testing if default is not valid
                    if self.model == "default" and models:
                        model_to_test = models[0]
                else:
                    # No models available - server is reachable, that's enough for now
                    logger.warning("No models available on server. Configuration issue.")
                    return True
        except Exception as e:
            logger.error("Failed to list OpenAI-compatible models: %s", e)
            return False

        # Test with a tiny inference call using validated model
        try:
            payload = {
                "model": model_to_test,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5,
                "temperature": 0,
            }
            resp = requests.post(
                f"{self.api_url}/v1/chat/completions",
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
        except Exception as e:
            logger.error("OpenAI-compatible inference test failed: %s", e)
            return False

    def _validate_anthropic(self) -> bool:
        """Validate an Anthropic-compatible endpoint."""
        headers = self._anthropic_headers()
        model_to_test = self.model
        
        # Anthropic-compatible endpoints don't typically have a /models endpoint
        # Try a simple inference test with the configured model
        try:
            payload = {
                "model": model_to_test,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5,
            }
            resp = requests.post(
                f"{self.api_url}/v1/messages",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if resp.status_code == 200:
                return True
            else:
                logger.error(
                    "Anthropic-compatible endpoint returned HTTP %d: %s", resp.status_code, resp.text[:200],
                )
                return False
        except Exception as e:
            logger.error("Anthropic-compatible inference test failed: %s", e)
            return False

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
        headers = self._openai_headers()
        
        # Get the actual model to use (handles "default" case)
        model_to_use = self._get_model_to_use()
        
        payload = {
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
        
        # Get the actual model to use (handles "default" case)
        model_to_use = self._get_model_to_use()
        
        payload = {
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
