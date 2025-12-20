# src/aicodereviewer/config.py
import configparser
import os
from pathlib import Path
from typing import Dict, Any

class Config:
    """Configuration manager for AICodeReviewer"""

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config_path = Path(__file__).parent.parent / "config.ini"

        # Set defaults
        self._set_defaults()

        # Load config file if it exists
        if self.config_path.exists():
            self.config.read(self.config_path)

    def _set_defaults(self):
        """Set default configuration values"""
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

    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        """Get configuration value with type conversion"""
        try:
            value = self.config.get(section, key)
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

            return value
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

# Global config instance
config = Config()