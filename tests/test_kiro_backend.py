import subprocess
from unittest.mock import MagicMock, patch

from aicodereviewer.backends.kiro import KiroBackend
from aicodereviewer.path_utils import CancelledProcessError


def _make_backend(model: str | None = None) -> KiroBackend:
    values = {
        ("kiro", "wsl_distro"): "Ubuntu",
        ("kiro", "cli_command"): "kiro",
        ("kiro", "model"): model or "",
        ("kiro", "timeout"): "300",
    }

    with patch("aicodereviewer.backends.kiro.config") as mock_cfg, \
         patch("aicodereviewer.backends.kiro.is_wsl_available", return_value=True):
        mock_cfg.get.side_effect = lambda section, key, default=None: values.get((section, key), default)
        return KiroBackend()


class TestKiroCommandBuilding:
    def test_chat_command_quotes_model_name(self):
        backend = _make_backend(model="Claude 3.5 Sonnet")

        command = backend._build_bash_command("chat")

        assert command == "kiro chat --model 'Claude 3.5 Sonnet' --no-interactive"

    def test_review_command_quotes_file_path(self):
        backend = _make_backend(model="Claude 3.5 Sonnet")

        command = backend._build_bash_command("review", file_path="/mnt/d/Code Review/file name.py")

        assert command == "kiro review --model 'Claude 3.5 Sonnet' '/mnt/d/Code Review/file name.py'"


class TestKiroExecution:
    @patch("aicodereviewer.backends.kiro.run_in_wsl")
    def test_run_kiro_prompt_uses_quoted_command_in_wsl(self, mock_run_in_wsl):
        backend = _make_backend(model="Claude 3.5 Sonnet")
        mock_run_in_wsl.return_value = (0, "ok", "")

        with patch("aicodereviewer.backends.kiro.os.name", "nt"):
            result = backend._run_kiro_prompt("hello")

        assert result == "ok"
        command = mock_run_in_wsl.call_args.args[0]
        assert command == ["bash", "-lc", "kiro chat --model 'Claude 3.5 Sonnet' --no-interactive"]
        assert callable(mock_run_in_wsl.call_args.kwargs["cancel_check"])

    @patch("aicodereviewer.backends.kiro.windows_to_wsl_path", return_value="/mnt/d/Code Review/file name.py")
    @patch("aicodereviewer.backends.kiro.run_in_wsl")
    def test_review_file_uses_quoted_path_in_wsl(self, mock_run_in_wsl, _mock_wsl_path):
        backend = _make_backend(model="Claude 3.5 Sonnet")
        mock_run_in_wsl.return_value = (0, "review", "")

        with patch("aicodereviewer.backends.kiro.os.name", "nt"):
            result = backend.review_file(r"D:\Code Review\file name.py")

        assert result == "review"
        command = mock_run_in_wsl.call_args.args[0]
        assert command == [
            "bash",
            "-lc",
            "kiro review --model 'Claude 3.5 Sonnet' '/mnt/d/Code Review/file name.py'",
        ]

    @patch("aicodereviewer.backends.kiro.KiroBackend._run_native_bash")
    def test_run_kiro_prompt_uses_quoted_command_natively(self, mock_run_native):
        backend = _make_backend(model="Claude 3.5 Sonnet")
        mock_run_native.return_value = "ok"

        with patch("aicodereviewer.backends.kiro.os.name", "posix"):
            result = backend._run_kiro_prompt("hello")

        assert result == "ok"
        assert mock_run_native.call_args.args == (
            "kiro chat --model 'Claude 3.5 Sonnet' --no-interactive",
            "hello",
        )

    @patch("aicodereviewer.backends.kiro.run_in_wsl")
    def test_run_kiro_prompt_returns_cancelled_when_wsl_process_is_cancelled(self, mock_run_in_wsl):
        backend = _make_backend(model="Claude 3.5 Sonnet")

        def _cancelled(*_args, **_kwargs):
            backend.cancel()
            raise CancelledProcessError()

        mock_run_in_wsl.side_effect = _cancelled

        with patch("aicodereviewer.backends.kiro.os.name", "nt"):
            result = backend._run_kiro_prompt("hello")

        assert result == "Error: Cancelled."

    @patch("subprocess.Popen")
    def test_run_kiro_prompt_returns_cancelled_when_native_process_is_cancelled(self, mock_popen):
        backend = _make_backend(model="Claude 3.5 Sonnet")

        process = MagicMock()

        def _communicate(*_args, **kwargs):
            backend.cancel()
            raise subprocess.TimeoutExpired(cmd=["bash"], timeout=kwargs.get("timeout", 0.2))

        process.communicate.side_effect = _communicate
        mock_popen.return_value = process

        with patch("aicodereviewer.backends.kiro.os.name", "posix"):
            result = backend._run_kiro_prompt("hello")

        assert result == "Error: Cancelled."
        process.terminate.assert_called_once()