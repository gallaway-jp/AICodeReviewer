"""
Tests for configuration, authentication language detection, and performance utilities.
"""
import time
from unittest.mock import patch

from aicodereviewer.config import Config
from aicodereviewer.auth import get_system_language, set_profile_name
from aicodereviewer.performance import PerformanceMonitor


def test_config_type_conversions_and_fallback():
    config = Config()

    # Size and time conversions
    assert config.get('performance', 'max_file_size_mb') == 10 * 1024 * 1024
    assert config.get('performance', 'min_request_interval_seconds') == 6.0
    assert config.get('processing', 'batch_size') == 5
    assert config.get('logging', 'enable_performance_logging') is True

    # Missing keys fall back cleanly
    assert config.get('missing', 'key', fallback=123) == 123


def test_get_system_language_prefers_japanese():
    with patch('aicodereviewer.auth.locale.setlocale') as _setloc, \
         patch('aicodereviewer.auth.locale.getlocale', return_value=('ja_JP', 'UTF-8')), \
         patch.dict('aicodereviewer.auth.os.environ', {'LANG': 'ja_JP'}, clear=False):
        assert get_system_language() == 'ja'


def test_get_system_language_defaults_to_english():
    with patch('aicodereviewer.auth.locale.setlocale') as _setloc, \
         patch('aicodereviewer.auth.locale.getlocale', return_value=('en_US', 'UTF-8')), \
         patch.dict('aicodereviewer.auth.os.environ', {'LANG': 'en_US'}, clear=False):
        assert get_system_language() == 'en'


def test_set_profile_name_uses_keyring_without_prompt():
    with patch('aicodereviewer.auth.keyring.set_password') as mock_set_password:
        profile = set_profile_name('test-profile')

    assert profile == 'test-profile'
    mock_set_password.assert_called_once_with('AICodeReviewer', 'aws_profile', 'test-profile')


def test_performance_monitor_collects_metrics():
    monitor = PerformanceMonitor()

    context = monitor.track_operation('unit_test_op')

    # When monitoring is disabled, context manager still functions
    # Default config enables logging, but we allow for either case
    with context:
        time.sleep(0.01)

    metrics = monitor.get_metrics()

    if monitor.enabled:
        assert 'unit_test_op' in metrics
        assert 'duration_seconds' in metrics['unit_test_op']
        assert 'memory_delta_bytes' in metrics['unit_test_op']
    else:
        assert metrics == {}
