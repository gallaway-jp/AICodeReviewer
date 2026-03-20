# tests/test_copilot_backend.py
"""
Unit tests for CopilotBackend (github-copilot-sdk integration).

The ``copilot`` package (github-copilot-sdk) is mocked throughout so
these tests run without a real Copilot CLI or subscription.
"""
import sys
import types
from typing import Callable, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Attr:
    """Lightweight struct for mock event data."""
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _MockEvent:
    """Simple stand-in for SDK event objects."""
    def __init__(self, type_str: str, content: str = "", delta: str = ""):
        self.type = _Attr(value=type_str)
        self.data = _Attr(content=content, delta_content=delta)


def _make_mock_session(full_reply: str = '{"issues": []}') -> MagicMock:
    """Return a mock session that fires correct events when send() is awaited."""
    _handlers: List[Callable] = []

    async def _send(payload):
        # Emit a short streaming delta, the full message, then the idle signal.
        for handler in list(_handlers):
            if full_reply:
                handler(_MockEvent("assistant.message_delta", delta=full_reply[:6]))
            handler(_MockEvent("assistant.message", content=full_reply))
            handler(_MockEvent("session.idle"))

    session = MagicMock()
    session.destroy = AsyncMock()
    # Use a plain lambda to avoid MagicMock attribute-storage quirks.
    session.on = lambda cb: _handlers.append(cb)
    session.send = AsyncMock(side_effect=_send)
    return session


def _make_mock_client(
    session: MagicMock | None = None,
    model_names: list | None = None,
) -> MagicMock:
    """Return an async-mock CopilotClient."""
    client = MagicMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.list_models = AsyncMock(return_value=model_names or ["gpt-5", "claude-sonnet-4-5"])
    if session is not None:
        client.create_session = AsyncMock(return_value=session)
    return client


def _fake_copilot_module(client_instance: MagicMock) -> types.ModuleType:
    mod = types.ModuleType("copilot")
    mod.CopilotClient = MagicMock(return_value=client_instance)
    return mod


def _make_backend(mock_cli: MagicMock):
    """Import and instantiate CopilotBackend with the fake copilot module in sys.modules."""
    # Always remove the cached module so the re-import picks up the fake.
    sys.modules.pop("aicodereviewer.backends.copilot", None)
    from aicodereviewer.backends.copilot import CopilotBackend
    b = CopilotBackend()
    b.timeout = 5  # short timeout so tests fail fast; never rely on 300s default
    return b


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_sess():
    return _make_mock_session('{"issues": []}')


@pytest.fixture()
def mock_cli(mock_sess):
    return _make_mock_client(session=mock_sess)


@pytest.fixture()
def backend(mock_cli):
    """Yield a CopilotBackend with the github-copilot-sdk fully mocked."""
    fake_mod = _fake_copilot_module(mock_cli)
    with patch.dict(sys.modules, {"copilot": fake_mod}):
        b = _make_backend(mock_cli)
        yield b
    b.close()


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

class TestInit:
    def test_loop_thread_is_daemon(self, backend):
        assert backend._loop_thread.daemon is True
        assert backend._loop_thread.is_alive()

    def test_client_is_none_before_first_use(self, backend):
        assert backend._client is None

    def test_stream_callback_starts_none(self, backend):
        assert backend._stream_callback is None


# ---------------------------------------------------------------------------
# set_stream_callback
# ---------------------------------------------------------------------------

class TestSetStreamCallback:
    def test_stores_callable(self, backend):
        cb = lambda t: None  # noqa: E731
        backend.set_stream_callback(cb)
        assert backend._stream_callback is cb

    def test_clears_with_none(self, backend):
        backend.set_stream_callback(lambda t: None)
        backend.set_stream_callback(None)
        assert backend._stream_callback is None

    def test_base_class_noop_exists(self):
        """set_stream_callback is a concrete no-op on AIBackend."""
        from aicodereviewer.backends.base import AIBackend
        assert hasattr(AIBackend, "set_stream_callback")


# ---------------------------------------------------------------------------
# _ensure_client (lazy init)
# ---------------------------------------------------------------------------

class TestEnsureClient:
    def test_client_created_on_first_review(self, backend, mock_cli):
        assert backend._client is None
        backend.get_review("x = 1")
        assert backend._client is mock_cli

    def test_client_start_called_exactly_once(self, backend, mock_cli):
        backend.get_review("x = 1")
        backend.get_review("x = 2")
        mock_cli.start.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_review
# ---------------------------------------------------------------------------

class TestGetReview:
    def test_returns_str(self, backend):
        result = backend.get_review("def foo(): pass")
        assert isinstance(result, str)

    def test_returns_session_content(self, backend):
        result = backend.get_review("x = 1")
        assert result == '{"issues": []}'

    def test_error_prefix_on_session_failure(self, backend, mock_cli):
        mock_cli.create_session = AsyncMock(side_effect=RuntimeError("cli crash"))
        result = backend.get_review("x = 1")
        assert result.startswith("Error:")

    def test_custom_reply(self):
        custom_reply = '{"issues":[{"severity":"high"}]}'
        sess = _make_mock_session(custom_reply)
        cli = _make_mock_client(session=sess)
        fake_mod = _fake_copilot_module(cli)

        with patch.dict(sys.modules, {"copilot": fake_mod}):
            b = _make_backend(cli)
            try:
                assert b.get_review("some code") == custom_reply
            finally:
                b.close()


# ---------------------------------------------------------------------------
# get_fix
# ---------------------------------------------------------------------------

class TestGetFix:
    def test_returns_stripped_code(self):
        reply = "  x = 2  \n"
        sess = _make_mock_session(reply)
        cli = _make_mock_client(session=sess)
        fake_mod = _fake_copilot_module(cli)

        with patch.dict(sys.modules, {"copilot": fake_mod}):
            b = _make_backend(cli)
            try:
                assert b.get_fix("x = 1", "unused variable") == reply.strip()
            finally:
                b.close()

    def test_returns_none_on_error(self, backend, mock_cli):
        mock_cli.create_session = AsyncMock(side_effect=RuntimeError("boom"))
        assert backend.get_fix("x = 1", "issue") is None


# ---------------------------------------------------------------------------
# validate_connection
# ---------------------------------------------------------------------------

class TestValidateConnection:
    def test_true_when_healthy(self, backend, mock_cli):
        with patch("shutil.which", return_value="/usr/bin/copilot"):
            assert backend.validate_connection() is True
        mock_cli.list_models.assert_awaited()

    def test_false_when_cli_missing(self, backend):
        with patch("shutil.which", return_value=None):
            assert backend.validate_connection() is False

    def test_false_when_list_models_raises(self, backend, mock_cli):
        mock_cli.list_models = AsyncMock(side_effect=ConnectionError("no auth"))
        with patch("shutil.which", return_value="/usr/bin/copilot"):
            assert backend.validate_connection() is False

    def test_false_when_list_models_returns_none(self, backend, mock_cli):
        mock_cli.list_models = AsyncMock(return_value=None)
        with patch("shutil.which", return_value="/usr/bin/copilot"):
            assert backend.validate_connection() is False


# ---------------------------------------------------------------------------
# Streaming callback
# ---------------------------------------------------------------------------

class TestStreaming:
    def test_callback_invoked_with_deltas(self, backend):
        tokens: list[str] = []
        backend.set_stream_callback(tokens.append)
        backend.get_review("def foo(): pass")
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)

    def test_faulty_callback_does_not_abort_review(self, backend):
        def _bad(t: str) -> None:
            raise ValueError("GUI broke")

        backend.set_stream_callback(_bad)
        result = backend.get_review("x = 1")
        assert isinstance(result, str)
        assert not result.startswith("Error:")


# ---------------------------------------------------------------------------
# cancel()
# ---------------------------------------------------------------------------

class TestCancel:
    def test_cancel_with_no_active_session_is_safe(self, backend):
        backend.cancel()  # must not raise

    def test_cancel_destroys_active_session(self, backend, mock_sess):
        backend._active_session = mock_sess
        backend.cancel()
        import time; time.sleep(0.2)
        mock_sess.destroy.assert_awaited()


class TestClose:
    def test_close_stops_loop_thread(self, backend, mock_cli):
        backend.get_review("x = 1")

        backend.close()

        assert backend._loop_thread.is_alive() is False
        mock_cli.stop.assert_awaited()


# ---------------------------------------------------------------------------
# get_copilot_models
# ---------------------------------------------------------------------------

class TestGetCopilotModels:
    def setup_method(self):
        from aicodereviewer.backends import models as m
        m._copilot_models_cache.clear()

    def teardown_method(self):
        from aicodereviewer.backends import models as m
        m._copilot_models_cache.clear()

    def test_cache_returned_on_second_call(self):
        from aicodereviewer.backends import models as m
        m._copilot_models_cache["copilot"] = ["gpt-5", "o3"]
        with patch.object(m, "_discover_copilot_models") as mock_disc:
            result = m.get_copilot_models("copilot")
        mock_disc.assert_not_called()
        assert result == ["gpt-5", "o3"]

    def test_discovery_called_when_cache_empty(self):
        from aicodereviewer.backends import models as m

        def _fill_cache(path):
            m._copilot_models_cache[path] = ["gpt-5"]
            return ["gpt-5"]

        with patch.object(m, "_discover_copilot_models", side_effect=_fill_cache):
            result = m.get_copilot_models("copilot")

        assert result == ["gpt-5"]
