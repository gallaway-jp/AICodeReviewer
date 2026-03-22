# tests/test_local_llm.py
"""
Tests for the LocalLLMBackend.

Uses mocked HTTP responses to test OpenAI-compatible and
Anthropic-compatible API paths without a running server.
"""
import time
from typing import Any

import pytest
from unittest.mock import patch, MagicMock

from aicodereviewer.backends.local_llm import LocalLLMBackend


# ── helpers ────────────────────────────────────────────────────────────────

def _make_backend(api_type: str = "openai", **overrides: Any) -> LocalLLMBackend:
    """Create a LocalLLMBackend with test defaults."""
    defaults: dict[str, Any] = dict(
        api_url="http://localhost:9999/v1",
        api_type=api_type,
        model="test-model",
        api_key="test-key",
        enable_web_search=True,
    )
    defaults.update(overrides)
    with patch("aicodereviewer.backends.local_llm.config") as mock_cfg:
        mock_cfg.get.side_effect = lambda section, key, default=None: {
            ("local_llm", "api_url"): defaults["api_url"],
            ("local_llm", "api_type"): defaults["api_type"],
            ("local_llm", "model"): defaults["model"],
            ("local_llm", "api_key"): defaults["api_key"],
            ("local_llm", "timeout"): "30",
            ("local_llm", "max_tokens"): "512",
            ("local_llm", "enable_web_search"): defaults["enable_web_search"],
            ("performance", "min_request_interval_seconds"): 0.0,
            ("performance", "max_content_length"): 100_000,
            ("performance", "max_fix_content_length"): 100_000,
        }.get((section, key), default)
        backend = LocalLLMBackend(
            api_url=defaults["api_url"],
            api_type=defaults["api_type"],
            model=defaults["model"],
            api_key=defaults["api_key"],
            enable_web_search=defaults["enable_web_search"],
        )
    return backend


def _mock_response(status_code: int = 200, json_data: dict[str, Any] | None = None, text: str = "") -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


# ── construction ───────────────────────────────────────────────────────────

class TestLocalLLMConstruction:
    """Test backend construction and config reading."""

    def test_creates_with_explicit_params(self):
        backend = _make_backend()
        assert backend.api_url == "http://localhost:9999"
        assert backend.api_type == "openai"
        assert backend.model == "test-model"
        assert backend.api_key == "test-key"

    def test_api_type_anthropic(self):
        backend = _make_backend(api_type="anthropic")
        assert backend.api_type == "anthropic"

    def test_openai_url_normalizes_v1_suffix(self):
        backend = _make_backend(api_type="openai", api_url="http://localhost:9999/v1/")
        assert backend.api_url == "http://localhost:9999"

    def test_lmstudio_url_normalizes_api_v1_suffix(self):
        backend = _make_backend(api_type="lmstudio", api_url="http://localhost:1234/api/v1/")
        assert backend.api_url == "http://localhost:1234"

    def test_ollama_url_normalizes_api_suffix(self):
        backend = _make_backend(api_type="ollama", api_url="http://localhost:11434/api/")
        assert backend.api_url == "http://localhost:11434"


# ── OpenAI-compatible review ───────────────────────────────────────────────

class TestOpenAIReview:
    """Test get_review / get_fix with OpenAI-compatible responses."""

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_review_success(self, mock_post):
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "Review feedback"}}]
        })
        backend = _make_backend()
        result = backend.get_review("def foo(): pass", "best_practices", "en")
        assert result == "Review feedback"
        mock_post.assert_called_once()

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_get_review_appends_web_guidance_when_enabled(self, mock_get, mock_post):
        mock_get.return_value = _mock_response(
            200,
            text='''
                <html>
                    <body>
                        <div class="result__snippet">Use explicit validation at API boundaries.</div>
                        <div class="result__snippet">Keep caller and validator contracts aligned.</div>
                    </body>
                </html>
            ''',
        )
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "Review feedback"}}]
        })
        backend = _make_backend(enable_web_search=True)

        result = backend.get_review("def foo(): pass", "security", "en")

        assert result == "Review feedback"
        payload = mock_post.call_args.kwargs["json"]
        assert "EXTERNAL WEB GUIDANCE:" in payload["messages"][1]["content"]
        assert "Do not replace a locally supported issue family" in payload["messages"][1]["content"]
        assert "Use explicit validation at API boundaries." in payload["messages"][1]["content"]
        assert mock_get.call_count >= 1

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_get_review_skips_web_guidance_when_disabled(self, mock_get, mock_post):
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "Review feedback"}}]
        })
        backend = _make_backend(enable_web_search=False)

        result = backend.get_review("def foo(): pass", "security", "en")

        assert result == "Review feedback"
        payload = mock_post.call_args.kwargs["json"]
        assert "EXTERNAL WEB GUIDANCE:" not in payload["messages"][1]["content"]
        mock_get.assert_not_called()

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_get_review_continues_when_web_search_fails(self, mock_get, mock_post):
        import requests

        mock_get.side_effect = requests.RequestException("search unavailable")
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "Review feedback"}}]
        })
        backend = _make_backend(enable_web_search=True)

        result = backend.get_review("def foo(): pass", "security", "en")

        assert result == "Review feedback"
        payload = mock_post.call_args.kwargs["json"]
        assert "EXTERNAL WEB GUIDANCE:" not in payload["messages"][1]["content"]

    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_get_review_retries_without_web_guidance_when_augmented_request_fails(self, mock_get):
        mock_get.return_value = _mock_response(
            200,
            text='''
                <html>
                    <body>
                        <div class="result__snippet">Use explicit validation at API boundaries.</div>
                    </body>
                </html>
            ''',
        )
        backend = _make_backend(enable_web_search=True)

        with patch.object(
            backend,
            "_invoke",
            side_effect=["Error: HTTP 500 - upstream failure", "Recovered review feedback"],
        ) as mock_invoke:
            result = backend.get_review("def foo():\n    return payload['email']", "security", "en")

        assert result == "Recovered review feedback"
        assert mock_invoke.call_count == 2
        first_user_message = mock_invoke.call_args_list[0].args[1]
        second_user_message = mock_invoke.call_args_list[1].args[1]
        assert "EXTERNAL WEB GUIDANCE:" in first_user_message
        assert "EXTERNAL WEB GUIDANCE:" not in second_user_message

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_review_http_error(self, mock_post):
        mock_post.return_value = _mock_response(500, text="Internal Server Error")
        backend = _make_backend()
        result = backend.get_review("code", "security", "en")
        assert result.startswith("Error:")

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_review_empty_choices(self, mock_post):
        mock_post.return_value = _mock_response(200, {"choices": []})
        backend = _make_backend()
        result = backend.get_review("code", "security", "en")
        assert "Error" in result or "Empty" in result

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_fix_success(self, mock_post):
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "fixed_code()"}}]
        })
        backend = _make_backend()
        result = backend.get_fix("buggy()", "Fix the bug", "security", "en")
        assert result == "fixed_code()"

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_fix_returns_none_on_error(self, mock_post):
        mock_post.return_value = _mock_response(502, text="Bad Gateway")
        backend = _make_backend()
        result = backend.get_fix("code", "fix it", "security", "en")
        assert result is None

    def test_get_review_content_too_large(self):
        backend = _make_backend()
        huge = "x" * 200_000
        with patch("aicodereviewer.backends.local_llm.config") as mock_cfg:
            mock_cfg.get.side_effect = lambda s, k, d=None: {
                ("performance", "max_content_length"): 1000,
            }.get((s, k), d)
            result = backend.get_review(huge, "security", "en")
        assert "too large" in result.lower() or "Error" in result


# ── Anthropic-compatible review ────────────────────────────────────────────

class TestAnthropicReview:
    """Test get_review / get_fix with Anthropic-compatible responses."""

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_review_success(self, mock_post):
        mock_post.return_value = _mock_response(200, {
            "content": [{"type": "text", "text": "Anthropic review"}]
        })
        backend = _make_backend(api_type="anthropic", model="claude-3-5-sonnet")
        result = backend.get_review("def bar(): pass", "best_practices", "en")
        assert result == "Anthropic review"

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_fix_success(self, mock_post):
        mock_post.return_value = _mock_response(200, {
            "content": [{"type": "text", "text": "fixed()"}]
        })
        backend = _make_backend(api_type="anthropic", model="claude-3-5-sonnet")
        result = backend.get_fix("broken()", "Fix it", "security", "en")
        assert result == "fixed()"

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_review_empty_content(self, mock_post):
        mock_post.return_value = _mock_response(200, {"content": []})
        backend = _make_backend(api_type="anthropic", model="claude-3-5-sonnet")
        result = backend.get_review("code", "security", "en")
        assert "Error" in result or "Empty" in result

    def test_get_review_requires_explicit_anthropic_model(self):
        backend = _make_backend(api_type="anthropic", model="default")
        result = backend.get_review("code", "security", "en")
        assert "require an explicit model" in result


# ── validate_connection ────────────────────────────────────────────────────

class TestValidateConnection:
    """Test the validate_connection method."""

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_openai_validate_success(self, mock_get, mock_post):
        mock_get.return_value = _mock_response(200, {
            "data": [{"id": "model-1"}]
        })
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "hi"}}]
        })
        backend = _make_backend()
        assert backend.validate_connection() is True
        mock_post.assert_not_called()

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_openai_validate_inference_fails(self, mock_get, mock_post):
        # Empty model list but server reachable → True (server is up, just no models loaded)
        mock_get.return_value = _mock_response(200, {"data": []})
        mock_post.return_value = _mock_response(503, text="Unavailable")
        backend = _make_backend()
        assert backend.validate_connection() is True
        mock_post.assert_not_called()

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_ollama_validate_success_does_not_infer(self, mock_get, mock_post):
        mock_get.return_value = _mock_response(200, {
            "models": [{"name": "llama3"}]
        })
        backend = _make_backend(api_type="ollama", api_url="http://localhost:11434", model="default")
        assert backend.validate_connection() is True
        mock_get.assert_called_once()
        mock_post.assert_not_called()

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_anthropic_validate_success(self, mock_post):
        mock_post.return_value = _mock_response(200, {
            "content": [{"type": "text", "text": "hi"}]
        })
        backend = _make_backend(api_type="anthropic", model="claude-3-5-sonnet")
        assert backend.validate_connection() is True

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_anthropic_validate_failure(self, mock_post):
        mock_post.return_value = _mock_response(401, text="Unauthorized")
        backend = _make_backend(api_type="anthropic", model="claude-3-5-sonnet")
        assert backend.validate_connection() is False

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_anthropic_validate_requires_explicit_model(self, mock_post):
        backend = _make_backend(api_type="anthropic", model="default")
        assert backend.validate_connection() is False
        mock_post.assert_not_called()

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_connection_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.ConnectionError("refused")
        backend = _make_backend()
        assert backend.validate_connection() is False

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_timeout_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.Timeout("timed out")
        backend = _make_backend()
        assert backend.validate_connection() is False

    def test_unknown_api_type(self):
        backend = _make_backend(api_type="unknown")
        backend.api_type = "unknown"
        assert backend.validate_connection() is False


# ── headers ────────────────────────────────────────────────────────────────

class TestHeaders:
    """Test header generation for both API types."""

    def test_openai_headers_with_key(self):
        backend = _make_backend(api_key="sk-test")
        headers = backend._openai_headers()
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["Content-Type"] == "application/json"

    def test_openai_headers_no_key(self):
        backend = _make_backend(api_key="")
        backend.api_key = ""
        headers = backend._openai_headers()
        assert "Authorization" not in headers

    def test_anthropic_headers_with_key(self):
        backend = _make_backend(api_type="anthropic", api_key="ant-key")
        headers = backend._anthropic_headers()
        assert headers["x-api-key"] == "ant-key"
        assert headers["anthropic-version"] == "2023-06-01"

    def test_anthropic_headers_no_key(self):
        backend = _make_backend(api_type="anthropic", api_key="")
        backend.api_key = ""
        headers = backend._anthropic_headers()
        assert "x-api-key" not in headers


class TestWebSearchHelpers:
    def test_build_web_search_queries_prefers_framework_context(self):
        backend = _make_backend(enable_web_search=True)
        backend._detected_frameworks = ["fastapi"]

        queries = backend._build_web_search_queries("security")

        assert queries[0].startswith("fastapi ")
        assert "authentication authorization" in queries[0]

    def test_build_web_search_queries_uses_code_signals_for_validation(self):
        backend = _make_backend(enable_web_search=True)

        queries = backend._build_web_search_queries(
            "security",
            "def create_user(payload):\n    validated = validator.validate(payload)\n    return repo.save(validated)",
        )

        assert any("input validation boundary enforcement" in query for query in queries)
        assert all("python" in query for query in queries)

    def test_build_web_search_queries_uses_cache_signals_for_performance(self):
        backend = _make_backend(enable_web_search=True)

        queries = backend._build_web_search_queries(
            "performance",
            "cache.get(key)\nrepository.save(item)\ncache.invalidate(key)\n",
        )

        assert "cache invalidation state consistency" in queries[0]

    def test_infer_web_guidance_topics_ignores_wrapper_prompt_validation_text(self):
        backend = _make_backend(enable_web_search=True)

        wrapped_prompt = (
            "Review each of the following files. Also look for issues that only become visible across files in this batch, "
            "including missing guards or validation.\n"
            "=== FILE: cache.py ===\n"
            "PROFILE_CACHE = {}\n"
            "def set_user_profile(user_id, profile):\n"
            "    PROFILE_CACHE[user_id] = profile\n"
            "=== FILE: profile_service.py ===\n"
            "def update_user_profile(store, user_id, profile):\n"
            "    store[user_id] = profile\n"
        )

        topics = backend._infer_web_guidance_topics(wrapped_prompt, "performance")

        assert "cache invalidation state consistency" in topics
        assert "input validation boundary enforcement" not in topics

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_review_does_not_double_wrap_prebuilt_multi_file_prompt(self, mock_post):
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "Review feedback"}}]
        })
        backend = _make_backend(enable_web_search=False)
        prompt = (
            "Review each of the following files.\n"
            "=== FILE: a.py ===\n"
            "print('a')\n"
            "=== FILE: b.py ===\n"
            "print('b')\n"
        )

        backend.get_review(prompt, "performance", "en")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["messages"][1]["content"] == prompt

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_get_review_adds_cache_specific_output_reminder(self, mock_get, mock_post):
        mock_get.return_value = _mock_response(
            200,
            text='''
                <html>
                    <body>
                        <div class="result__snippet">Invalidate cache entries on write paths.</div>
                    </body>
                </html>
            ''',
        )
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "Review feedback"}}]
        })
        backend = _make_backend(enable_web_search=True)

        backend.get_review(
            "PROFILE_CACHE = {}\ndef update_profile(store, user_id, profile):\n    store[user_id] = profile\n",
            "performance",
            "en",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert "TOPIC-SPECIFIC OUTPUT REMINDERS:" in payload["messages"][1]["content"]
        assert "stale reads or stale state reaching callers" in payload["messages"][1]["content"]
        assert "Do not report generic input validation or auth issues unless they directly cause cache inconsistency" in payload["messages"][1]["content"]
        assert "keep issue_type aligned to performance/cache" in payload["messages"][1]["content"]
        assert "PROFILE_CACHE" in payload["messages"][1]["content"]

    def test_infer_cache_identifier_hints_prefers_shared_entity_and_cache_symbols(self):
        backend = _make_backend(enable_web_search=True)

        hints = backend._infer_cache_identifier_hints(
            "PROFILE_CACHE = {}\n"
            "def get_user_profile(user_id):\n    return PROFILE_CACHE.get(user_id)\n"
            "def set_user_profile(user_id, profile):\n    PROFILE_CACHE[user_id] = profile\n"
            "def update_user_profile(store, user_id, profile):\n    store[user_id] = profile\n"
        )

        assert hints[0] == "user_profile"
        assert "PROFILE_CACHE" in hints
        assert "get_user_profile" in hints

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_get_review_skips_web_guidance_for_cache_read_write_pair(self, mock_get, mock_post):
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "Review feedback"}}]
        })
        backend = _make_backend(enable_web_search=True)

        backend.get_review(
            "PROFILE_CACHE = {}\n"
            "def get_user_profile(user_id):\n    return PROFILE_CACHE.get(user_id)\n"
            "def set_user_profile(user_id, profile):\n    PROFILE_CACHE[user_id] = profile\n"
            "def update_user_profile(store, user_id, profile):\n    store[user_id] = profile\n",
            "performance",
            "en",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert "EXTERNAL WEB GUIDANCE:" not in payload["messages"][1]["content"]
        mock_get.assert_not_called()

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_get_review_skips_web_guidance_for_cache_write_path_with_project_context(self, mock_get, mock_post):
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "Review feedback"}}]
        })
        backend = _make_backend(enable_web_search=True)
        backend.set_project_context("Supporting files include cache.py for user profile cache reads.")

        backend.get_review(
            "def update_user_profile(store, user_id, profile):\n    store[user_id] = profile\n",
            "performance",
            "en",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert "EXTERNAL WEB GUIDANCE:" not in payload["messages"][1]["content"]
        mock_get.assert_not_called()

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_get_review_adds_validation_systemic_impact_reminder(self, mock_get, mock_post):
        mock_get.return_value = _mock_response(
            200,
            text='''
                <html>
                    <body>
                        <div class="result__snippet">Validate all fields before runtime use.</div>
                    </body>
                </html>
            ''',
        )
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "Review feedback"}}]
        })
        backend = _make_backend(enable_web_search=True)

        backend.get_review(
            "def create_account(payload):\n    validate_signup(payload)\n    return {\"email\": payload[\"email\"]}\n",
            "security",
            "en",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert "include systemic_impact that explicitly says unvalidated or incompletely validated input proceeds" in payload["messages"][1]["content"]

    def test_infer_web_guidance_topics_falls_back_to_review_default(self):
        backend = _make_backend(enable_web_search=True)

        topics = backend._infer_web_guidance_topics("plain text", "architecture")

        assert topics[0] == "dependency direction layering"

    def test_strip_html_normalizes_entities_and_whitespace(self):
        assert LocalLLMBackend._strip_html("<b>Use&nbsp;validation</b>\n") == "Use validation"


# ── rate limiting ──────────────────────────────────────────────────────────

class TestRateLimiting:
    """Test the rate-limiting mechanism."""

    @patch("aicodereviewer.backends.local_llm.LocalLLMBackend._sleep_with_cancel")
    @patch("aicodereviewer.backends.local_llm.time.time")
    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_enforce_rate_limit(self, mock_post, mock_time, mock_sleep_with_cancel):
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "ok"}}]
        })
        backend = _make_backend()
        backend.min_request_interval = 2.0
        backend.last_request_time = 100.0
        mock_time.return_value = 100.5  # Only 0.5s elapsed

        backend.get_review("code", "security", "en")
        mock_sleep_with_cancel.assert_called_once_with(pytest.approx(1.5, abs=0.1))

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_review_returns_cancelled_when_cancelled_before_request(self, mock_post):
        backend = _make_backend()
        backend.cancel()

        result = backend.get_review("code", "security", "en")

        assert result == "Error: Cancelled."
        mock_post.assert_not_called()

    @patch("aicodereviewer.backends.local_llm.LocalLLMBackend._sleep_with_cancel")
    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_review_returns_cancelled_when_rate_limit_wait_is_cancelled(self, mock_post, mock_sleep_with_cancel):
        backend = _make_backend()
        backend.min_request_interval = 2.0
        backend.last_request_time = time.time()

        def _cancel(_duration):
            backend.cancel()
            raise RuntimeError("Cancelled.")

        mock_sleep_with_cancel.side_effect = _cancel

        result = backend.get_review("code", "security", "en")

        assert result == "Error: Cancelled."
        mock_post.assert_not_called()
