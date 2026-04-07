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
    enable_web_search = true
"""
import logging
import re
import time
from html import unescape
from typing import Any, Callable, Optional, cast
from urllib.parse import urlsplit, urlunsplit

import requests

from .base import AIBackend
from aicodereviewer.auth import resolve_credential_value
from aicodereviewer.config import config

logger = logging.getLogger(__name__)

_API_URL_SUFFIXES: dict[str, tuple[str, ...]] = {
    "lmstudio": ("/api/v1", "/v1"),
    "openai": ("/v1",),
    "anthropic": ("/v1",),
    "ollama": ("/api",),
}

_WEB_GUIDANCE_TOPIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "authentication authorization",
        (
            "auth",
            "authorize",
            "authorization",
            "role",
            "permission",
            "jwt",
            "token",
            "session",
            "login",
            "current_user",
            "requires_",
            "depends(",
        ),
    ),
    (
        "input validation boundary enforcement",
        (
            "validate",
            "validation",
            "validator",
            "schema",
            "sanitize",
            "sanit",
            "serializer",
            "pydantic",
            "request.json",
            "request.args",
            "request.form",
            "parse",
        ),
    ),
    (
        "injection prevention query construction",
        (
            "sql",
            "query",
            "cursor",
            "execute(",
            "executemany(",
            "subprocess",
            "shell=True",
            "eval(",
            "exec(",
            "jinja",
            "template",
        ),
    ),
    (
        "cache invalidation state consistency",
        (
            "cache",
            "cached",
            "redis",
            "invalidate",
            "stale",
            "ttl",
            "memo",
            "etag",
            "repository",
            "commit",
            "transaction",
        ),
    ),
    (
        "api contract serialization compatibility",
        (
            "response_model",
            "serializer",
            "payload",
            "json",
            "to_dict",
            "from_dict",
            "field",
            "schema",
            "dto",
            "contract",
        ),
    ),
    (
        "session token crypto safety",
        (
            "bcrypt",
            "hash",
            "encrypt",
            "decrypt",
            "csrf",
            "cookie",
            "secret",
            "hmac",
            "signature",
        ),
    ),
)

_WEB_GUIDANCE_BASE_TERMS: dict[str, str] = {
    "security": "best practices secure coding code review",
    "best_practices": "best practices code review regression prevention",
    "performance": "best practices performance review consistency",
    "architecture": "best practices architecture review dependency direction",
    "regression": "best practices refactor regression review",
}


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
        enable_web_search: Optional[bool] = None,
    ):
        self.api_type: str = str(
            api_type
            or config.get("local_llm", "api_type", "lmstudio")
        ).strip().lower()

        raw_api_url = str(
            api_url
            or config.get("local_llm", "api_url", "http://localhost:1234")
        )
        self.api_url: str = self._normalize_api_url(raw_api_url, self.api_type)

        self.model: str = str(model or config.get("local_llm", "model", "default"))
        if api_key is None:
            configured_api_key = str(config.get("local_llm", "api_key", "") or "")
            self.api_key = resolve_credential_value(configured_api_key).secret
        else:
            self.api_key = str(api_key)
        self.timeout: int = int(float(config.get("local_llm", "timeout", "300") or "300"))
        self.max_tokens: int = int(config.get("local_llm", "max_tokens", "4096") or "4096")
        if enable_web_search is None:
            self.enable_web_search = bool(
                config.get("local_llm", "enable_web_search", True)
            )
        else:
            self.enable_web_search = bool(enable_web_search)

        # Rate-limiting state
        self.last_request_time: float = 0.0
        self.min_request_interval: float = float(
            config.get("performance", "min_request_interval_seconds")
        )
        self._cancel_requested: bool = False

        logger.info(
            "Local LLM backend: %s (type=%s, model=%s)",
            self.api_url, self.api_type, self.model,
        )

    def cancel(self) -> None:
        """Request cancellation before the next outbound HTTP call begins."""
        self._cancel_requested = True

    def close(self) -> None:
        """Release backend state by marking the current request flow cancelled."""
        self.cancel()

    @staticmethod
    def _normalize_api_url(api_url: str, api_type: str) -> str:
        """Normalize configured API URLs to a consistent base form."""
        stripped = api_url.strip().rstrip("/")
        if not stripped:
            return stripped

        parsed = urlsplit(stripped)
        path = parsed.path.rstrip("/")

        suffixes = _API_URL_SUFFIXES.get(api_type, ())

        for suffix in suffixes:
            if path.lower().endswith(suffix):
                path = path[:-len(suffix)]
                break

        normalized = urlunsplit((parsed.scheme, parsed.netloc, path or "", parsed.query, parsed.fragment))
        return normalized.rstrip("/")

    def _get_model_to_use(self) -> str:
        """Get the actual model to use for inference.
        
        If self.model is 'default', attempts to fetch the first available model
        from the API. This handles cases where the user hasn't configured a specific
        model in settings.
        """
        if self.model != "default":
            return self.model

        if self.api_type == "anthropic":
            raise ValueError(
                "Anthropic-compatible endpoints require an explicit model; 'default' cannot be auto-discovered."
            )
        
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
        tool_context=None,
    ) -> str:
        max_content: int = int(config.get("performance", "max_content_length"))
        if len(code_content) > max_content:
            return (
                f"Error: Content too large for processing "
                f"({len(code_content)} > {max_content} characters)"
            )

        system_prompt = self._build_system_prompt(
            review_type, lang, self._project_context, self._detected_frameworks,
        )
        if self._looks_like_prebuilt_review_prompt(code_content):
            base_user_message = code_content
        else:
            base_user_message = self._build_user_message(code_content, review_type, spec_content)
        user_message = self._augment_review_with_web_context(
            base_user_message,
            review_type,
            code_content,
        )
        result = self._invoke(system_prompt, user_message)
        if (
            result.startswith("Error:")
            and self.enable_web_search
            and user_message != base_user_message
        ):
            logger.warning(
                "Local LLM review failed with web guidance enabled; retrying once without web guidance"
            )
            return self._invoke(system_prompt, base_user_message)
        return result

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

    def get_review_recommendations(
        self,
        recommendation_context: str,
        lang: str = "en",
    ) -> str:
        system_prompt = self._build_recommendation_system_prompt(lang)
        user_message = self._build_recommendation_user_message(recommendation_context)
        return self._invoke(system_prompt, user_message)

    def validate_connection(self) -> bool:
        """
        Test connectivity to the local LLM server.

        Checks:
            1. Server is reachable (GET /models or similar) when supported
            2. For providers without a passive discovery endpoint, a minimal
               request succeeds
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

    def validate_connection_diagnostic(self) -> dict[str, str | bool]:
        try:
            if self.api_type == "lmstudio":
                ok = self._validate_lmstudio()
            elif self.api_type == "ollama":
                ok = self._validate_ollama()
            elif self.api_type == "openai":
                ok = self._validate_openai()
            elif self.api_type == "anthropic":
                ok = self._validate_anthropic()
            else:
                return {
                    "ok": False,
                    "category": "configuration",
                    "detail": (
                        f"Unknown api_type '{self.api_type}'. Use 'lmstudio', 'ollama', 'openai' or 'anthropic'."
                    ),
                    "fix_hint": "Set local_llm.api_type to one of: lmstudio, ollama, openai, anthropic.",
                    "origin": "connection_test",
                }

            return {
                "ok": bool(ok),
                "category": "none" if ok else "provider",
                "detail": "" if ok else "Local LLM backend did not accept the validation request.",
                "fix_hint": "Check the local server, selected model, API type, and credentials." if not ok else "",
                "origin": "connection_test",
            }
        except requests.ConnectionError:
            return {
                "ok": False,
                "category": "transport",
                "detail": f"Cannot connect to {self.api_url}. Is the LLM server running?",
                "fix_hint": "Start the local server and verify the configured base URL.",
                "origin": "connection_test",
            }
        except requests.Timeout:
            return {
                "ok": False,
                "category": "timeout",
                "detail": f"Connection to {self.api_url} timed out.",
                "fix_hint": "Increase the timeout or reduce server startup latency before retrying.",
                "origin": "connection_test",
            }
        except Exception as exc:
            lower_msg = str(exc).lower()
            category = "provider"
            if "api key" in lower_msg or "unauthorized" in lower_msg or "forbidden" in lower_msg:
                category = "auth"
            elif "timeout" in lower_msg:
                category = "timeout"
            return {
                "ok": False,
                "category": category,
                "detail": str(exc),
                "fix_hint": "Check the configured model, API type, credentials, and server compatibility.",
                "origin": "connection_test",
            }

    # ── shared validation helper ───────────────────────────────────────────

    def _validate_with_model_discovery(
        self,
        list_url: str,
        list_parser: str,
        test_url: str,
        test_payload_fn: Callable[[str], dict[str, Any]],
        headers: dict[str, str],
        label: str,
        require_inference: bool = True,
    ) -> bool:
        """Common validation logic: discover models, then optionally run inference.

        Args:
            list_url: URL to GET the model list (empty to skip discovery).
            list_parser: Key indicating response format (``'openai'``, ``'ollama'``, ``'lmstudio'``).
            test_url: URL to POST a test inference request.
            test_payload_fn: Callable ``(model_name) -> dict`` that builds the test payload.
            headers: HTTP headers for both requests.
            label: Human-readable label for log messages.
            require_inference: Whether to perform a POST validation after discovery.
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

        if not require_inference:
            return True

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
    def _parse_model_list(data: dict[str, Any], parser: str) -> list[str]:
        """Extract model identifiers from an API response."""
        if parser in ("openai", "lmstudio"):
            items = data.get("data", [])
            if not isinstance(items, list):
                return []
            typed_items = cast(list[Any], items)
            model_ids: list[str] = []
            for item in typed_items:
                if not isinstance(item, dict):
                    continue
                item_dict = cast(dict[str, Any], item)
                model_id = item_dict.get("id")
                if isinstance(model_id, str) and model_id:
                    model_ids.append(model_id)
            return model_ids
        if parser == "ollama":
            items = data.get("models", [])
            if not isinstance(items, list):
                return []
            typed_items = cast(list[Any], items)
            model_names: list[str] = []
            for item in typed_items:
                if not isinstance(item, dict):
                    continue
                item_dict = cast(dict[str, Any], item)
                model_name = item_dict.get("name")
                if isinstance(model_name, str) and model_name:
                    model_names.append(model_name)
            return model_names
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
            require_inference=False,
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
            require_inference=False,
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
            require_inference=False,
        )

    def _validate_anthropic(self) -> bool:
        """Validate an Anthropic-compatible endpoint."""
        if self.model == "default":
            logger.error(
                "Anthropic-compatible endpoints require an explicit model; set local_llm.model instead of 'default'."
            )
            return False
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
        try:
            self._enforce_rate_limit()
        except RuntimeError as exc:
            return f"Error: {exc}"

        if self._cancel_requested:
            return "Error: Cancelled."

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
            first_message = choices[0].get("message", {})
            content = first_message.get("content", "")
            if isinstance(content, list):
                text_parts: list[str] = []
                content_blocks = cast(list[Any], content)
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    block_payload = cast(dict[str, Any], block)
                    text = block_payload.get("text") or block_payload.get("content")
                    if isinstance(text, str) and text.strip():
                        text_parts.append(text.strip())
                content = "\n".join(text_parts)

            if isinstance(content, str) and content.strip():
                return content

            reasoning_content = first_message.get("reasoning_content")
            if isinstance(reasoning_content, str) and reasoning_content.strip():
                return (
                    "Error: OpenAI-compatible endpoint returned empty assistant content "
                    "and reasoning_content only. Configure a non-thinking model or "
                    "disable server-side thinking mode for tool-mode JSON reviews."
                )
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

    def _augment_review_with_web_context(
        self,
        user_message: str,
        review_type: str,
        code_content: str,
    ) -> str:
        """Append optional web-derived guidance for local LLM reviews.

        The web queries are intentionally high-level and never include source
        code or identifiers from the user's project.
        """
        if not self.enable_web_search:
            return user_message

        topics = self._infer_web_guidance_topics(code_content, review_type)
        if self._should_skip_web_guidance(
            review_type,
            topics,
            code_content,
            self._project_context,
        ):
            logger.debug(
                "Skipping web guidance for %s review because the code already contains concrete cache/state evidence",
                review_type,
            )
            return user_message
        snippets = self._fetch_web_guidance(review_type, code_content)
        if not snippets:
            return user_message

        lines = [
            user_message,
            "",
            "EXTERNAL WEB GUIDANCE:",
            "Use the following high-level reference notes only as supplemental guidance.",
            "1. Identify the primary findings from the provided code and project context before considering these notes.",
            "2. Use these notes only to validate, sharpen, or narrowly extend a code-grounded concern.",
            "3. Do not replace a locally supported issue family with a different category unless the code evidence clearly supports that change.",
            "4. Treat these notes as secondary evidence; prefer the provided code and project context when they conflict.",
        ]
        reminders = self._build_web_guidance_reminders(topics, code_content)
        if reminders:
            lines.append("TOPIC-SPECIFIC OUTPUT REMINDERS:")
            lines.extend(f"- {reminder}" for reminder in reminders)
        for index, snippet in enumerate(snippets, start=1):
            lines.append(f"{index}. {snippet}")
        return "\n".join(lines)

    def _fetch_web_guidance(self, review_type: str, code_content: str) -> list[str]:
        snippets: list[str] = []
        seen: set[str] = set()
        for query in self._build_web_search_queries(review_type, code_content):
            try:
                for snippet in self._search_duckduckgo_html(query):
                    normalized = snippet.strip()
                    if not normalized:
                        continue
                    dedupe_key = normalized.lower()
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    snippets.append(normalized)
                    if len(snippets) >= 3:
                        return snippets
            except requests.RequestException as exc:
                logger.debug("Web search guidance unavailable for query '%s': %s", query, exc)
            except Exception as exc:
                logger.debug("Failed to parse web guidance for query '%s': %s", query, exc)
        return snippets

    def _build_web_search_queries(self, review_type: str, code_content: str = "") -> list[str]:
        analysis_text = self._extract_web_guidance_analysis_text(code_content)
        base_term = _WEB_GUIDANCE_BASE_TERMS.get(
            review_type,
            f"{review_type.replace('_', ' ')} best practices code review",
        )
        frameworks = [framework for framework in (self._detected_frameworks or []) if framework]
        framework_prefix = " ".join(frameworks[:2]).strip()
        language_prefix = self._infer_guidance_language(analysis_text)
        topic_terms = self._infer_web_guidance_topics(analysis_text, review_type)

        queries: list[str] = []
        for topic in topic_terms[:2]:
            query_parts = [
                language_prefix,
                framework_prefix,
                topic,
                base_term,
            ]
            query = " ".join(part for part in query_parts if part).strip()
            if query and query not in queries:
                queries.append(query)

        fallback_query = " ".join(
            part for part in (language_prefix, framework_prefix, base_term) if part
        ).strip()
        if fallback_query and fallback_query not in queries:
            queries.append(fallback_query)
        return queries

    def _infer_web_guidance_topics(self, code_content: str, review_type: str) -> list[str]:
        lowered = self._extract_web_guidance_analysis_text(code_content).lower()
        topics: list[str] = []

        for topic, markers in _WEB_GUIDANCE_TOPIC_PATTERNS:
            if any(self._web_guidance_marker_present(lowered, marker) for marker in markers):
                topics.append(topic)

        review_defaults = {
            "security": "authentication authorization",
            "best_practices": "api contract serialization compatibility",
            "performance": "cache invalidation state consistency",
            "architecture": "dependency direction layering",
            "regression": "api contract serialization compatibility",
        }
        default_topic = review_defaults.get(review_type)
        if default_topic and default_topic not in topics:
            topics.insert(0, default_topic)

        if not topics:
            topics.append("code review defect prevention")

        return topics

    @staticmethod
    def _extract_web_guidance_analysis_text(code_content: str) -> str:
        text = code_content
        code_marker = "CODE TO REVIEW:\n"
        if code_marker in text:
            text = text.split(code_marker, 1)[1]

        for marker in ("=== FILE:", "CHANGED FILE:"):
            if marker in text:
                return text[text.index(marker):]

        return text

    @staticmethod
    def _looks_like_prebuilt_review_prompt(code_content: str) -> bool:
        return any(
            marker in code_content
            for marker in (
                "=== FILE:",
                "CHANGED FILE:",
                "Review each of the following files.",
                "Review each of the following changed files.",
                "FOCUS YOUR REVIEW ON THE CHANGED LINES.",
            )
        )

    @classmethod
    def _build_web_guidance_reminders(cls, topics: list[str], code_content: str = "") -> list[str]:
        reminders: list[str] = []
        if any("cache invalidation state consistency" == topic for topic in topics):
            reminders.append(
                "For cache or state consistency findings, keep the finding cross-file when another file performs the write or read path, include the collaborating file, and describe the systemic impact as stale reads or stale state reaching callers when supported by the code."
            )
            reminders.append(
                "For performance reviews, prioritize cache invalidation, stale state, cache coherence, or redundant state-handling defects. Do not report generic input validation or auth issues unless they directly cause cache inconsistency, stale reads, or unnecessary recomputation."
            )
            identifier_hints = cls._infer_cache_identifier_hints(code_content)
            if identifier_hints:
                reminders.append(
                    "For stale-cache findings, keep issue_type aligned to performance/cache and anchor evidence_basis to concrete code identifiers such as "
                    f"{', '.join(identifier_hints[:5])}. Prefer the shared entity token when present, and do not justify the finding with project context alone."
                )
        if any("input validation boundary enforcement" == topic for topic in topics):
            reminders.append(
                "For validation findings, include systemic_impact that explicitly says unvalidated or incompletely validated input proceeds beyond the boundary and reaches runtime use or storage."
            )
        if any("authentication authorization" == topic for topic in topics):
            reminders.append(
                "For auth findings, keep the primary issue grounded in the missing guard or permission check shown by the code, and describe which callers or routes remain exposed."
            )
        return reminders

    @classmethod
    def _infer_cache_identifier_hints(cls, code_content: str) -> list[str]:
        analysis_text = cls._extract_web_guidance_analysis_text(code_content)
        hints: list[str] = []

        entity_counts: dict[str, int] = {}
        for match in re.finditer(r"\b(?:get|set|update|invalidate|delete|save|load|fetch)_([a-z0-9_]+)\b", analysis_text):
            entity = match.group(1)
            entity_counts[entity] = entity_counts.get(entity, 0) + 1

        for entity, count in entity_counts.items():
            if count >= 2 and entity not in hints:
                hints.append(entity)

        for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*cache[A-Za-z0-9_]*\b", analysis_text, flags=re.IGNORECASE):
            identifier = match.group(0)
            if identifier not in hints:
                hints.append(identifier)

        for match in re.finditer(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", analysis_text, flags=re.MULTILINE):
            identifier = match.group(1)
            if "cache" in identifier.lower() or re.match(r"^(get|set|update|invalidate|delete|save|load|fetch)_", identifier):
                if identifier not in hints:
                    hints.append(identifier)

        return hints

    @classmethod
    def _should_skip_web_guidance(
        cls,
        review_type: str,
        topics: list[str],
        code_content: str,
        project_context: str | None = None,
    ) -> bool:
        if review_type != "performance":
            return False
        if "cache invalidation state consistency" not in topics:
            return False

        identifier_hints = cls._infer_cache_identifier_hints(code_content)
        has_shared_entity = any(
            "_" in hint
            and "cache" not in hint.lower()
            and not re.match(r"^(get|set|update|invalidate|delete|save|load|fetch)_", hint)
            for hint in identifier_hints
        )
        has_cache_symbol = any("cache" in hint.lower() for hint in identifier_hints)
        if has_shared_entity and has_cache_symbol:
            return True

        lowered_analysis = cls._extract_web_guidance_analysis_text(code_content).lower()
        lowered_project_context = (project_context or "").lower()
        has_project_cache_context = "cache" in lowered_project_context
        has_write_path = any(
            marker in lowered_analysis
            for marker in ("store[", "store [", "update_", "save_", "write_", "set_")
        )
        return has_project_cache_context and has_write_path

    @staticmethod
    def _web_guidance_marker_present(lowered_content: str, marker: str) -> bool:
        if any(char in marker for char in "(._="):
            return marker in lowered_content
        return re.search(rf"\b{re.escape(marker)}(?:\b|_)", lowered_content) is not None

    @staticmethod
    def _infer_guidance_language(code_content: str) -> str:
        lowered = code_content.lower()
        if any(marker in lowered for marker in ("def ", "import ", "from ", "self", "async def ")):
            return "python"
        if any(marker in lowered for marker in ("function ", "const ", "let ", "=>", "console.")):
            return "javascript"
        if any(marker in lowered for marker in ("public class ", "private ", "using ", "namespace ")):
            return "csharp"
        return ""

    def _search_duckduckgo_html(self, query: str) -> list[str]:
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={
                "User-Agent": "AICodeReviewer/1.0 (+https://example.local)",
                "Accept-Language": "en-US,en;q=0.8",
            },
            timeout=min(self.timeout, 10),
        )
        response.raise_for_status()

        snippets: list[str] = []
        for raw in re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>', response.text, flags=re.IGNORECASE | re.DOTALL):
            snippet_html = next((part for part in raw if part), "")
            snippet = self._strip_html(snippet_html)
            if snippet:
                snippets.append(snippet)
            if len(snippets) >= 3:
                break
        return snippets

    @staticmethod
    def _strip_html(value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

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
            self._sleep_with_cancel(self.min_request_interval - elapsed)

    def _sleep_with_cancel(self, duration: float) -> None:
        """Sleep in short increments so cancellation can stop queued work."""
        remaining = max(0.0, duration)
        while remaining > 0:
            if self._cancel_requested:
                raise RuntimeError("Cancelled.")
            sleep_chunk = min(remaining, 0.2)
            time.sleep(sleep_chunk)
            remaining -= sleep_chunk
