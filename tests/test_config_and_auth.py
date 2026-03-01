"""
Tests for configuration, authentication, language detection, and performance utilities.

Updated for v2.0: Config has new sections (backend, kiro, copilot),
auth module is English-first with get/set/clear profile functions.
"""
import time
from unittest.mock import patch

from aicodereviewer.config import Config
from aicodereviewer.auth import get_system_language, set_profile_name
from aicodereviewer.performance import PerformanceMonitor


# ── Config ─────────────────────────────────────────────────────────────────

def test_config_type_conversions_and_fallback():
    config = Config()

    # Size and time conversions
    assert config.get('performance', 'max_file_size_mb') == 10 * 1024 * 1024
    assert config.get('performance', 'min_request_interval_seconds') == 6.0
    assert config.get('processing', 'batch_size') == 5
    assert config.get('logging', 'enable_performance_logging') is True

    # Missing keys fall back cleanly
    assert config.get('missing', 'key', fallback=123) == 123


def test_config_new_sections():
    """v2.0 new sections should have defaults."""
    # Reset config to defaults by clearing any loaded config
    with patch('configparser.ConfigParser.read'):
        config = Config()
        assert config.get('backend', 'type') == 'bedrock'
        assert config.get('kiro', 'cli_command') == 'kiro'
        assert config.get('copilot', 'copilot_path') == 'copilot'


def test_config_set_value():
    config = Config()
    config.set_value('backend', 'type', 'kiro')
    assert config.get('backend', 'type') == 'kiro'


# ── Auth / Language ────────────────────────────────────────────────────────

def test_get_system_language_prefers_japanese():
    with patch('aicodereviewer.auth.os.name', 'posix'), \
         patch('aicodereviewer.auth.locale.setlocale') as _setloc, \
         patch('aicodereviewer.auth.locale.getlocale', return_value=('ja_JP', 'UTF-8')), \
         patch.dict('aicodereviewer.auth.os.environ', {'LANG': 'ja_JP'}, clear=False):
        assert get_system_language() == 'ja'


def test_get_system_language_defaults_to_english():
    with patch('aicodereviewer.auth.os.name', 'posix'), \
         patch('aicodereviewer.auth.locale.setlocale') as _setloc, \
         patch('aicodereviewer.auth.locale.getlocale', return_value=('en_US', 'UTF-8')), \
         patch.dict('aicodereviewer.auth.os.environ', {'LANG': 'en_US'}, clear=False):
        assert get_system_language() == 'en'


def test_set_profile_name_uses_keyring_without_prompt():
    with patch('aicodereviewer.auth.keyring.set_password') as mock_set_password:
        profile = set_profile_name('test-profile')

    assert profile == 'test-profile'
    mock_set_password.assert_called_once_with('AICodeReviewer', 'aws_profile', 'test-profile')


# ── PerformanceMonitor ─────────────────────────────────────────────────────

def test_performance_monitor_collects_metrics():
    monitor = PerformanceMonitor()

    context = monitor.track_operation('unit_test_op')

    with context:
        time.sleep(0.01)

    metrics = monitor.get_metrics()

    if monitor.enabled:
        assert 'unit_test_op' in metrics
        assert 'duration_seconds' in metrics['unit_test_op']
        assert 'memory_delta_bytes' in metrics['unit_test_op']
    else:
        assert metrics == {}
