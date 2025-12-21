"""
Tests for Bedrock client behaviors including rate limiting and error handling.
"""
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, TokenRetrievalError

from aicodereviewer.bedrock import BedrockClient


@pytest.fixture
def mock_session(monkeypatch):
    mock_runtime = MagicMock()
    mock_session_obj = MagicMock()
    mock_session_obj.client.return_value = mock_runtime

    # Patch boto3 session creation to avoid real AWS
    monkeypatch.setattr("aicodereviewer.bedrock.boto3.Session", lambda profile_name, region_name=None: mock_session_obj)
    return mock_runtime


def test_rate_limit_respects_min_interval(monkeypatch, mock_session):
    client = BedrockClient("test")
    client.min_request_interval = 6
    client.last_request_time = 100
    client.window_start = 0
    client.request_count = 0
    client.max_requests_per_minute = 100

    mock_sleep = MagicMock()
    mock_time = MagicMock(side_effect=[101, 101])
    monkeypatch.setattr("aicodereviewer.bedrock.time.sleep", mock_sleep)
    monkeypatch.setattr("aicodereviewer.bedrock.time.time", mock_time)

    client._check_rate_limit()

    mock_sleep.assert_called_once_with(5)


def test_rate_limit_resets_minute_window(monkeypatch, mock_session):
    client = BedrockClient("test")
    client.max_requests_per_minute = 2
    client.request_count = 2
    client.window_start = 90
    client.last_request_time = 0
    client.min_request_interval = 0

    mock_sleep = MagicMock()
    mock_time = MagicMock(side_effect=[100, 150])
    monkeypatch.setattr("aicodereviewer.bedrock.time.sleep", mock_sleep)
    monkeypatch.setattr("aicodereviewer.bedrock.time.time", mock_time)

    client._check_rate_limit()

    mock_sleep.assert_called_once_with(50)
    assert client.request_count == 0
    assert client.window_start == 150


def test_validate_connection_token_error(monkeypatch, mock_session):
    client = BedrockClient("test")
    client.client.converse.side_effect = TokenRetrievalError(provider="sso", error_msg="expired")

    with pytest.raises(Exception):
        client._validate_connection()


def test_get_review_enforces_size_limit(monkeypatch, mock_session):
    client = BedrockClient("test")

    # Force a tiny max_content_length to trigger limit
    monkeypatch.setattr(
        "aicodereviewer.bedrock.config.get",
        lambda section, key, fallback=None: 1 if key == "max_content_length" else 1000,
    )

    result = client.get_review("long" * 10, review_type="security", lang="en")

    assert result.startswith("Error: Content too large")


def test_get_review_success_happy_path(monkeypatch, mock_session):
    client = BedrockClient("test")
    client.client.converse.return_value = {
        "output": {"message": {"content": [{"text": "ok"}]}}
    }

    # Skip rate limit and connection validation
    monkeypatch.setattr("aicodereviewer.bedrock.BedrockClient._check_rate_limit", lambda self: None)
    monkeypatch.setattr("aicodereviewer.bedrock.BedrockClient._validate_connection", lambda self: None)

    result = client.get_review("code", review_type="security", lang="en")

    assert result == "ok"
    assert client.request_count == 1


def test_get_review_retries_on_throttling(monkeypatch, mock_session):
    client = BedrockClient("test")

    throttling_error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Slow down"}},
        "converse",
    )
    client.client.converse.side_effect = [throttling_error, {
        "output": {"message": {"content": [{"text": "ok"}]}}
    }]

    monkeypatch.setattr("aicodereviewer.bedrock.BedrockClient._check_rate_limit", lambda self: None)
    monkeypatch.setattr("aicodereviewer.bedrock.BedrockClient._validate_connection", lambda self: None)
    sleep_mock = MagicMock()
    monkeypatch.setattr("aicodereviewer.bedrock.time.sleep", sleep_mock)

    result = client.get_review("code", review_type="security", lang="en")

    assert result == "ok"
    sleep_mock.assert_called_once()
