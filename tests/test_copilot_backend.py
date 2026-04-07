# tests/test_copilot_backend.py
"""
Unit tests for CopilotBackend (github-copilot-sdk integration).

The ``copilot`` package (github-copilot-sdk) is mocked throughout so
these tests run without a real Copilot CLI or subscription.
"""
import asyncio
import json
import sys
import types
from pathlib import Path
from typing import Callable, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aicodereviewer.review_definitions import install_review_registry
from aicodereviewer.tool_access import ToolReviewContext, ToolReviewTarget


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
    """Return a mock session that fires correct events when send_and_wait() is awaited."""
    _handlers: List[Callable] = []

    def _on(callback: Callable):
        _handlers.append(callback)

        def _unsubscribe() -> None:
            if callback in _handlers:
                _handlers.remove(callback)

        return _unsubscribe

    async def _send_and_wait(prompt, *, attachments=None, mode=None, timeout=60.0):
        # Emit a short streaming delta, the full message, then the idle signal.
        for handler in list(_handlers):
            if full_reply:
                handler(_MockEvent("assistant.message_delta", delta=full_reply[:6]))
            handler(_MockEvent("assistant.message", content=full_reply))
            handler(_MockEvent("session.idle"))
        return _MockEvent("assistant.message", content=full_reply)

    session = MagicMock()
    session.destroy = AsyncMock()
    # Use a plain function to avoid MagicMock attribute-storage quirks.
    session.on = _on
    session.send_and_wait = AsyncMock(side_effect=_send_and_wait)
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
    mod.SubprocessConfig = MagicMock(side_effect=lambda **kwargs: types.SimpleNamespace(**kwargs))
    mod.PermissionHandler = types.SimpleNamespace(approve_all="approve_all")
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
    install_review_registry()
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

    def test_create_session_receives_permission_handler(self, backend, mock_cli):
        backend.get_review("x = 1")
        session_config = mock_cli.create_session.await_args.kwargs
        assert session_config["on_permission_request"] == "approve_all"

    def test_review_sends_raw_prompt_string(self, backend, mock_sess):
        backend.get_review("x = 1")
        send_args = mock_sess.send_and_wait.await_args
        assert isinstance(send_args.args[0], str)
        assert "CODE TO REVIEW:" in send_args.args[0]

    def test_tool_aware_review_configures_workspace_hooks(self, backend, mock_cli, tmp_path):
        tool_context = ToolReviewContext(
            workspace_root=str(tmp_path),
            targets=(ToolReviewTarget(path="src/example.py"),),
        )

        result = backend.get_review(
            "tool-aware prompt",
            tool_context=tool_context,
        )

        session_config = mock_cli.create_session.await_args.kwargs
        assert callable(session_config["on_permission_request"])
        assert session_config["working_directory"] == str(tmp_path)
        assert "hooks" in session_config
        assert callable(session_config["hooks"]["on_pre_tool_use"])
        assert callable(session_config["hooks"]["on_post_tool_use"])
        assert result == "Error: Tool-aware file access was not used by the selected model."

    def test_pre_tool_use_denies_sensitive_paths(self, backend, tmp_path):
        workspace_root = str(tmp_path)
        sensitive_path = str(Path(tmp_path) / ".env")

        decision = backend._handle_pre_tool_use(
            {"toolName": "session.workspace.readFile", "toolArgs": {"path": sensitive_path}},
            workspace_root,
        )

        assert decision["permissionDecision"] == "deny"
        assert backend.current_tool_access_audit() is not None
        assert backend.current_tool_access_audit().denied_request_count == 1

    def test_pre_tool_use_allows_view_tool_with_workspace_path(self, backend, tmp_path):
        workspace_root = str(tmp_path)
        target_path = str(Path(tmp_path) / "src" / "example.py")

        decision = backend._handle_pre_tool_use(
            {"toolName": "view", "toolArgs": {"path": target_path}},
            workspace_root,
        )

        audit = backend.current_tool_access_audit()
        assert decision["permissionDecision"] == "allow"
        assert audit is not None
        assert audit.file_read_count == 1
        assert audit.used_tool_access is True

    def test_pre_tool_use_allows_view_tool_with_attribute_args(self, backend, tmp_path):
        workspace_root = str(tmp_path)
        target_path = str(Path(tmp_path) / "src" / "example.py")

        decision = backend._handle_pre_tool_use(
            {"toolName": "view", "toolArgs": types.SimpleNamespace(path=target_path)},
            workspace_root,
        )

        audit = backend.current_tool_access_audit()
        assert decision["permissionDecision"] == "allow"
        assert audit is not None
        assert audit.file_read_count == 1
        assert audit.used_tool_access is True

    def test_pre_tool_use_allows_view_tool_with_json_string_args(self, backend, tmp_path):
        workspace_root = str(tmp_path)
        target_path = str(Path(tmp_path) / "src" / "example.py")

        decision = backend._handle_pre_tool_use(
            {"toolName": "view", "toolArgs": json.dumps({"path": target_path})},
            workspace_root,
        )

        audit = backend.current_tool_access_audit()
        assert decision["permissionDecision"] == "allow"
        assert audit is not None
        assert audit.file_read_count == 1
        assert audit.used_tool_access is True

    def test_pre_tool_use_allows_report_intent_tool(self, backend, tmp_path):
        decision = backend._handle_pre_tool_use(
            {"toolName": "report_intent", "toolArgs": {"intent": "Reading files"}},
            str(tmp_path),
        )

        audit = backend.current_tool_access_audit()
        assert decision["permissionDecision"] == "allow"
        assert audit is not None
        assert audit.file_read_count == 0
        assert audit.denied_request_count == 0

    def test_pre_tool_use_denies_out_of_workspace_paths(self, backend, tmp_path):
        outside_path = str(tmp_path.parent / "outside.py")

        decision = backend._handle_pre_tool_use(
            {"toolName": "session.workspace.readFile", "toolArgs": {"path": outside_path}},
            str(tmp_path),
        )

        assert decision["permissionDecision"] == "deny"


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

    def test_sdk_discovery_uses_subprocess_config(self, monkeypatch):
        from aicodereviewer.backends import models as m

        client = MagicMock()
        client.start = AsyncMock()
        client.stop = AsyncMock()
        client.list_models = AsyncMock(return_value=["gpt-5-mini", "o3"])

        fake_mod = types.ModuleType("copilot")
        fake_mod.CopilotClient = MagicMock(return_value=client)
        fake_mod.SubprocessConfig = MagicMock(side_effect=lambda **kwargs: types.SimpleNamespace(**kwargs))

        monkeypatch.setenv("GH_TOKEN", "test-token")

        with patch.dict(sys.modules, {"copilot": fake_mod}):
            result = asyncio.run(m._discover_copilot_models_via_sdk("copilot.exe"))

        assert result == ["gpt-5-mini", "o3"]
        fake_mod.SubprocessConfig.assert_called_once_with(
            cli_path="copilot.exe",
            log_level="warning",
        )
        config_arg = fake_mod.CopilotClient.call_args.args[0]
        assert getattr(config_arg, "github_token", None) == "test-token"
        client.start.assert_awaited_once()
        client.stop.assert_awaited_once()
        client.list_models.assert_awaited_once()
