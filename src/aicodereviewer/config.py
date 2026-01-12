# src/aicodereviewer/config.py
"""
Configuration management for AICodeReviewer.

This module provides centralized configuration management with default values,
file-based overrides, and automatic type conversion for application settings.

Classes:
    Config: Main configuration manager with performance and processing settings
"""
import configparser
import os
from pathlib import Path
from typing import Dict, Any


class Config:
    """
    Configuration manager for AICodeReviewer application settings.

    Manages performance limits, API settings, and processing parameters with
    support for configuration files and automatic type conversion.

    Configuration sections:
        performance: File size limits, API rate limiting, timeouts
        processing: Batch processing and parallel execution settings
        logging: Log levels and performance monitoring
    """

    def __init__(self):
        """
        Initialize configuration with defaults and load user config file.

        Looks for config.ini in the project root directory and the current
        working directory, merging user settings with default values.
        """
        self.config = configparser.ConfigParser()
        
        # Search paths: current working directory first, then project root
        search_paths = [
            Path.cwd() / "config.ini",  # Current working directory
            Path(__file__).parent.parent.parent / "config.ini"  # Project root
        ]
        
        # Load config file from first existing path
        self.config_path = None
        for path in search_paths:
            if path.exists():
                self.config_path = path
                break
        
        # Set defaults
        self._set_defaults()

        # Load config file if found
        if self.config_path:
            self.config.read(self.config_path)

    def _set_defaults(self):
        """
        Set default configuration values for all sections.

        Defines sensible defaults for performance limits, API settings,
        and processing parameters to ensure stable operation.
        """
        self.config.add_section('performance')
        self.config.set('performance', 'max_file_size_mb', '10')
        self.config.set('performance', 'max_fix_file_size_mb', '5')
        self.config.set('performance', 'file_cache_size', '100')
        self.config.set('performance', 'min_request_interval_seconds', '6.0')
        self.config.set('performance', 'max_requests_per_minute', '10')
        self.config.set('performance', 'api_timeout_seconds', '300')
        self.config.set('performance', 'connect_timeout_seconds', '30')
        self.config.set('performance', 'max_content_length', '100000')
        self.config.set('performance', 'max_fix_content_length', '50000')

        self.config.add_section('processing')
        self.config.set('processing', 'batch_size', '5')
        self.config.set('processing', 'enable_parallel_processing', 'false')

        self.config.add_section('logging')
        self.config.set('logging', 'log_level', 'INFO')
        self.config.set('logging', 'enable_performance_logging', 'true')

        self.config.add_section('model')
        self.config.set('model', 'model_id', 'anthropic.claude-3-5-sonnet-20240620-v1:0')

        self.config.add_section('aws')
        self.config.set('aws', 'access_key_id', '')
        self.config.set('aws', 'region', 'us-east-1')
        self.config.set('aws', 'session_token', '')
        # AWS SSO configuration (optional - requires SSO session configured in AWS CLI)
        self.config.set('aws', 'sso_session', '')
        self.config.set('aws', 'sso_account_id', '')
        self.config.set('aws', 'sso_role_name', '')
        self.config.set('aws', 'sso_region', 'us-east-1')
        self.config.set('aws', 'sso_start_url', '')
        self.config.set('aws', 'sso_registration_scopes', 'sso:account:access')
        self.config.set('aws', 'output', 'json')

    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        """
        Get configuration value with automatic type conversion.

        Retrieves configuration values and converts them to appropriate types
        based on the setting name and section.

        Args:
            section (str): Configuration section name
            key (str): Configuration key name
            fallback (Any): Value to return if key not found

        Returns:
            Any: Configuration value with appropriate type conversion

        Type conversions:
            - Size values ending in '_mb': converted to bytes
            - Time/duration values: converted to float
            - Integer values: converted to int
            - Boolean values: converted to bool
        """
        try:
            value = self.config.get(section, key)
            # Strip inline comments (everything after #)
            value = value.split('#')[0].strip()
            # Type conversion based on defaults
            if section == 'performance':
                if key.endswith('_mb'):
                    return int(value) * 1024 * 1024  # Convert to bytes
                elif key.endswith('_seconds') or key.endswith('_interval_seconds'):
                    return float(value)
                elif key in ['file_cache_size', 'max_requests_per_minute', 'max_content_length', 'max_fix_content_length']:
                    return int(value)
            elif section == 'processing':
                if key == 'batch_size':
                    return int(value)
                elif key == 'enable_parallel_processing':
                    return value.lower() == 'true'
            elif section == 'logging':
                if key == 'enable_performance_logging':
                    return value.lower() == 'true'
            elif section == 'model':
                # Model ID is returned as string
                return value
            elif section == 'aws':
                # AWS credentials are returned as strings
                return value

            return value
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback


# Global config instance
config = Config()