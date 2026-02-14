# tests/test_local_llm.py
"""
Tests for the LocalLLMBackend.

Uses mocked HTTP responses to test OpenAI-compatible and
Anthropic-compatible API paths without a running server.
"""
import pytest
from unittest.mock import patch, MagicMock

from aicodereviewer.backends.local_llm import LocalLLMBackend


# ── helpers ────────────────────────────────────────────────────────────────

def _make_backend(api_type="openai", **overrides):
    """Create a LocalLLMBackend with test defaults."""
    defaults = dict(
        api_url="http://localhost:9999/v1",
        api_type=api_type,
        model="test-model",
        api_key="test-key",
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
            ("performance", "min_request_interval_seconds"): 0.0,
            ("performance", "max_content_length"): 100_000,
            ("performance", "max_fix_content_length"): 100_000,
        }.get((section, key), default)
        backend = LocalLLMBackend(**defaults)
    return backend


def _mock_response(status_code=200, json_data=None, text=""):
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
        assert backend.api_url == "http://localhost:9999/v1"
        assert backend.api_type == "openai"
        assert backend.model == "test-model"
        assert backend.api_key == "test-key"

    def test_api_type_anthropic(self):
        backend = _make_backend(api_type="anthropic")
        assert backend.api_type == "anthropic"


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
        backend = _make_backend(api_type="anthropic")
        result = backend.get_review("def bar(): pass", "best_practices", "en")
        assert result == "Anthropic review"

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_fix_success(self, mock_post):
        mock_post.return_value = _mock_response(200, {
            "content": [{"type": "text", "text": "fixed()"}]
        })
        backend = _make_backend(api_type="anthropic")
        result = backend.get_fix("broken()", "Fix it", "security", "en")
        assert result == "fixed()"

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_get_review_empty_content(self, mock_post):
        mock_post.return_value = _mock_response(200, {"content": []})
        backend = _make_backend(api_type="anthropic")
        result = backend.get_review("code", "security", "en")
        assert "Error" in result or "Empty" in result


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

    @patch("aicodereviewer.backends.local_llm.requests.post")
    @patch("aicodereviewer.backends.local_llm.requests.get")
    def test_openai_validate_inference_fails(self, mock_get, mock_post):
        mock_get.return_value = _mock_response(200, {"data": []})
        mock_post.return_value = _mock_response(503, text="Unavailable")
        backend = _make_backend()
        assert backend.validate_connection() is False

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_anthropic_validate_success(self, mock_post):
        mock_post.return_value = _mock_response(200, {
            "content": [{"type": "text", "text": "hi"}]
        })
        backend = _make_backend(api_type="anthropic")
        assert backend.validate_connection() is True

    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_anthropic_validate_failure(self, mock_post):
        mock_post.return_value = _mock_response(401, text="Unauthorized")
        backend = _make_backend(api_type="anthropic")
        assert backend.validate_connection() is False

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


# ── rate limiting ──────────────────────────────────────────────────────────

class TestRateLimiting:
    """Test the rate-limiting mechanism."""

    @patch("aicodereviewer.backends.local_llm.time.sleep")
    @patch("aicodereviewer.backends.local_llm.time.time")
    @patch("aicodereviewer.backends.local_llm.requests.post")
    def test_enforce_rate_limit(self, mock_post, mock_time, mock_sleep):
        mock_post.return_value = _mock_response(200, {
            "choices": [{"message": {"content": "ok"}}]
        })
        backend = _make_backend()
        backend.min_request_interval = 2.0
        backend.last_request_time = 100.0
        mock_time.return_value = 100.5  # Only 0.5s elapsed

        backend.get_review("code", "security", "en")
        mock_sleep.assert_called_once_with(pytest.approx(1.5, abs=0.1))
