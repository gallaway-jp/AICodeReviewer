"""
Tests for configuration, authentication, language detection, and performance utilities.

Updated for v2.0: Config has new sections (backend, kiro, copilot),
auth module is English-first with get/set/clear profile functions.
"""
import time
from unittest.mock import MagicMock
from unittest.mock import patch

from aicodereviewer.config import Config
import aicodereviewer.auth as auth
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


def test_store_config_credential_returns_keyring_reference():
    with patch('aicodereviewer.auth.keyring.set_password') as mock_set_password:
        reference = auth.store_config_credential('local_llm', 'api_key', 'secret-token')

    assert reference == auth.build_credential_reference('local_llm', 'api_key')
    mock_set_password.assert_called_once_with(
        'AICodeReviewer',
        'credential:local_llm.api_key',
        'secret-token',
    )


def test_resolve_credential_value_reads_keyring_reference():
    reference = auth.build_credential_reference('local_llm', 'api_key')

    with patch('aicodereviewer.auth.keyring.get_password', return_value='resolved-secret'):
        credential = auth.resolve_credential_value(reference)

    assert credential.secret == 'resolved-secret'
    assert credential.source == 'keyring'
    assert credential.reference == reference
    assert credential.missing_reference is False


def test_resolve_credential_value_reports_missing_keyring_reference():
    reference = auth.build_credential_reference('local_llm', 'api_key')

    with patch('aicodereviewer.auth.keyring.get_password', return_value=None):
        credential = auth.resolve_credential_value(reference)

    assert credential.secret == ''
    assert credential.source == 'keyring'
    assert credential.reference == reference
    assert credential.missing_reference is True


def test_get_profile_name_noninteractive_requires_stored_profile():
    with patch('aicodereviewer.auth.keyring.get_password', return_value=None):
        try:
            auth.get_profile_name(interactive=False)
            assert False, 'Expected RuntimeError'
        except RuntimeError as exc:
            assert 'No AWS profile is stored' in str(exc)


def test_create_aws_session_noninteractive_uses_stored_profile_without_prompt(monkeypatch):
    fake_session = MagicMock()
    fake_session.client.return_value.get_caller_identity.return_value = {'Account': '123'}

    with patch('aicodereviewer.auth.keyring.get_password', return_value='saved-profile'), \
         patch('boto3.Session', return_value=fake_session) as mock_session, \
         patch('builtins.input', side_effect=AssertionError('input should not be called')):
        session, description = auth.create_aws_session('us-east-1')

    assert session is fake_session
    assert description == 'Profile (saved-profile)'
    mock_session.assert_called_once_with(profile_name='saved-profile', region_name='us-east-1')


def test_create_aws_session_uses_env_secret_for_direct_credentials(monkeypatch):
    fake_session = MagicMock()
    fake_session.client.return_value.get_caller_identity.return_value = {'Account': '123'}
    cfg = auth.config
    original_access_key = cfg.get('aws', 'access_key_id', '')
    original_region = cfg.get('aws', 'region', 'us-east-1')
    original_sso_session = cfg.get('aws', 'sso_session', '')
    original_session_token = cfg.get('aws', 'session_token', '')
    cfg.set_value('aws', 'access_key_id', 'AKIAEXAMPLE')
    cfg.set_value('aws', 'region', 'us-east-1')
    cfg.set_value('aws', 'sso_session', '')
    cfg.set_value('aws', 'session_token', 'token-123')

    try:
        with patch.dict('os.environ', {'AWS_SECRET_ACCESS_KEY': 'secret-123'}, clear=False), \
             patch('boto3.Session', return_value=fake_session) as mock_session, \
             patch('builtins.input', side_effect=AssertionError('input should not be called')):
            session, description = auth.create_aws_session('us-east-1')
    finally:
        cfg.set_value('aws', 'access_key_id', original_access_key)
        cfg.set_value('aws', 'region', original_region)
        cfg.set_value('aws', 'sso_session', original_sso_session)
        cfg.set_value('aws', 'session_token', original_session_token)

    assert session is fake_session
    assert description == 'Direct credentials (AKIAEXAM…)'
    mock_session.assert_called_once_with(
        aws_access_key_id='AKIAEXAMPLE',
        aws_secret_access_key='secret-123',
        aws_session_token='token-123',
        region_name='us-east-1',
    )


def test_create_aws_session_ignores_unsupported_sso_session_and_falls_back(monkeypatch):
    fake_session = MagicMock()
    fake_session.client.return_value.get_caller_identity.return_value = {'Account': '123'}
    cfg = auth.config
    original_access_key = cfg.get('aws', 'access_key_id', '')
    original_region = cfg.get('aws', 'region', 'us-east-1')
    original_sso_session = cfg.get('aws', 'sso_session', '')
    cfg.set_value('aws', 'access_key_id', '')
    cfg.set_value('aws', 'region', 'us-east-1')
    cfg.set_value('aws', 'sso_session', 'my-sso-session')

    try:
        with patch('aicodereviewer.auth.keyring.get_password', return_value='saved-profile'), \
             patch('boto3.Session', return_value=fake_session) as mock_session, \
             patch('builtins.input', side_effect=AssertionError('input should not be called')):
            session, description = auth.create_aws_session('us-east-1')
    finally:
        cfg.set_value('aws', 'access_key_id', original_access_key)
        cfg.set_value('aws', 'region', original_region)
        cfg.set_value('aws', 'sso_session', original_sso_session)

    assert session is fake_session
    assert description == 'Profile (saved-profile)'
    mock_session.assert_called_once_with(profile_name='saved-profile', region_name='us-east-1')


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
