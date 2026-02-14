"""
Tests for Bedrock backend behaviours including rate limiting, error handling,
retry logic, and the backward-compatibility shim.
"""
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, TokenRetrievalError

# Import via the NEW location
from aicodereviewer.backends.bedrock import BedrockBackend

# Also verify the backward-compatibility shim still works
from aicodereviewer.bedrock import BedrockClient


MODULE = "aicodereviewer.backends.bedrock"


@pytest.fixture
def mock_session(monkeypatch):
    """Patch create_aws_session and return the mock bedrock-runtime client."""
    mock_runtime = MagicMock()
    mock_session_obj = MagicMock()
    mock_session_obj.client.return_value = mock_runtime

    monkeypatch.setattr(
        f"{MODULE}.create_aws_session",
        lambda region="us-east-1": (mock_session_obj, "mock auth"),
    )
    return mock_runtime


# ── shim compat ────────────────────────────────────────────────────────────

def test_shim_import_is_same_class():
    """BedrockClient shim should resolve to BedrockBackend."""
    assert BedrockClient is BedrockBackend


# ── rate limiting ──────────────────────────────────────────────────────────

def test_rate_limit_respects_min_interval(monkeypatch, mock_session):
    client = BedrockBackend()
    client.min_request_interval = 6
    client.last_request_time = 100
    client.window_start = 0
    client.request_count = 0
    client.max_requests_per_minute = 100

    mock_sleep = MagicMock()
    mock_time = MagicMock(side_effect=[101, 101])
    monkeypatch.setattr(f"{MODULE}.time.sleep", mock_sleep)
    monkeypatch.setattr(f"{MODULE}.time.time", mock_time)

    client._enforce_rate_limit()

    mock_sleep.assert_called_once_with(5)


def test_rate_limit_resets_minute_window(monkeypatch, mock_session):
    client = BedrockBackend()
    client.max_requests_per_minute = 2
    client.request_count = 2
    client.window_start = 90
    client.last_request_time = 0
    client.min_request_interval = 0

    mock_sleep = MagicMock()
    mock_time = MagicMock(side_effect=[100, 150])
    monkeypatch.setattr(f"{MODULE}.time.sleep", mock_sleep)
    monkeypatch.setattr(f"{MODULE}.time.time", mock_time)

    client._enforce_rate_limit()

    mock_sleep.assert_called_once_with(50)
    assert client.request_count == 0
    assert client.window_start == 150


# ── connection validation ──────────────────────────────────────────────────

def test_validate_connection_token_error(monkeypatch, mock_session):
    client = BedrockBackend()
    client.client.converse.side_effect = TokenRetrievalError(
        provider="sso", error_msg="expired"
    )

    assert client.validate_connection() is False


def test_validate_connection_success(monkeypatch, mock_session):
    client = BedrockBackend()
    client.client.converse.return_value = {
        "output": {"message": {"content": [{"text": "ok"}]}}
    }

    assert client.validate_connection() is True


# ── get_review ─────────────────────────────────────────────────────────────

def test_get_review_enforces_size_limit(monkeypatch, mock_session):
    client = BedrockBackend()

    monkeypatch.setattr(
        f"{MODULE}.config.get",
        lambda section, key, fallback=None: 1 if key == "max_content_length" else 1000,
    )

    result = client.get_review("long" * 10, review_type="security", lang="en")

    assert result.startswith("Error: Content too large")


def test_get_review_success_happy_path(monkeypatch, mock_session):
    client = BedrockBackend()
    client.client.converse.return_value = {
        "output": {"message": {"content": [{"text": "ok"}]}}
    }

    monkeypatch.setattr(f"{MODULE}.BedrockBackend._enforce_rate_limit", lambda self: None)
    monkeypatch.setattr(f"{MODULE}.BedrockBackend.validate_connection", lambda self: True)
    client._validated = True

    result = client.get_review("code", review_type="security", lang="en")

    assert result == "ok"
    assert client.request_count == 1


def test_get_review_retries_on_throttling(monkeypatch, mock_session):
    client = BedrockBackend()

    throttling_error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Slow down"}},
        "converse",
    )
    client.client.converse.side_effect = [
        throttling_error,
        {"output": {"message": {"content": [{"text": "ok"}]}}},
    ]

    monkeypatch.setattr(f"{MODULE}.BedrockBackend._enforce_rate_limit", lambda self: None)
    client._validated = True
    sleep_mock = MagicMock()
    monkeypatch.setattr(f"{MODULE}.time.sleep", sleep_mock)

    result = client.get_review("code", review_type="security", lang="en")

    assert result == "ok"
    sleep_mock.assert_called_once()


# ── get_fix ────────────────────────────────────────────────────────────────

def test_get_fix_returns_stripped(monkeypatch, mock_session):
    client = BedrockBackend()
    client.client.converse.return_value = {
        "output": {"message": {"content": [{"text": "  fixed_code()  \n"}]}}
    }
    monkeypatch.setattr(f"{MODULE}.BedrockBackend._enforce_rate_limit", lambda self: None)
    client._validated = True

    result = client.get_fix("code", issue_feedback="Some issue", review_type="security", lang="en")

    assert result == "fixed_code()"


def test_get_fix_returns_none_on_error(monkeypatch, mock_session):
    client = BedrockBackend()
    client.client.converse.return_value = {
        "output": {"message": {"content": [{"text": "Error: something"}]}}
    }
    monkeypatch.setattr(f"{MODULE}.BedrockBackend._enforce_rate_limit", lambda self: None)
    client._validated = True

    result = client.get_fix("code", issue_feedback="issue", review_type="security", lang="en")

    assert result is None
