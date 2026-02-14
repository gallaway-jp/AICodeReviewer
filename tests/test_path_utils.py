# tests/test_path_utils.py
"""
Tests for WSL path conversion utilities.
"""
import sys
import pytest
from unittest.mock import patch, MagicMock

from aicodereviewer.path_utils import (
    windows_to_wsl_path,
    wsl_to_windows_path,
    is_wsl_available,
)


class TestWindowsToWslPath:
    """Test Windows → WSL path conversion."""

    def test_drive_letter_lowercase(self):
        assert windows_to_wsl_path("d:\\Projects\\myapp") == "/mnt/d/Projects/myapp"

    def test_drive_letter_uppercase(self):
        assert windows_to_wsl_path("D:\\Folder\\file.py") == "/mnt/d/Folder/file.py"

    def test_forward_slashes(self):
        assert windows_to_wsl_path("C:/Users/me/code") == "/mnt/c/Users/me/code"

    def test_already_wsl_path_raises(self):
        """Paths that already look like Unix should raise ValueError."""
        with pytest.raises(ValueError):
            windows_to_wsl_path("/mnt/c/foo")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            windows_to_wsl_path("")


class TestWslToWindowsPath:
    """Test WSL → Windows path conversion."""

    def test_mnt_drive(self):
        assert wsl_to_windows_path("/mnt/d/Projects/myapp") == "D:\\Projects\\myapp"

    def test_non_mnt_raises(self):
        """Paths not under /mnt/ should raise ValueError."""
        with pytest.raises(ValueError):
            wsl_to_windows_path("/home/user/code")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            wsl_to_windows_path("")


class TestIsWslAvailable:
    """Test WSL availability detection."""

    @patch("aicodereviewer.path_utils.subprocess.run")
    def test_wsl_available(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        assert is_wsl_available() is True

    @patch("aicodereviewer.path_utils.subprocess.run")
    def test_wsl_not_available(self, mock_run):
        mock_run.side_effect = FileNotFoundError()

        assert is_wsl_available() is False
