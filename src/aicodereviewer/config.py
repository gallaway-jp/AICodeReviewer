# src/aicodereviewer/config.py
"""
Centralised configuration management for AICodeReviewer.

Reads ``config.ini`` from the current working directory or the project root
and provides typed access to all sections with sensible defaults.
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any

__all__ = ["Config", "config"]


# ── type conversion rules ────────────────────────────────────────────────
# Maps (section, key_pattern | exact_key) → converter.
# Checked in order; first match wins.

def _to_bytes_mb(v: str) -> int:
    """Convert a megabyte string to bytes."""
    return int(v) * 1024 * 1024


def _to_bool(v: str) -> bool:
    return v.lower() in ("true", "1", "yes")


_CONVERTERS: list[tuple[str, str, Any]] = [
    # (section, key suffix/name, converter)
    # Performance section
    ("performance", "*_mb",              _to_bytes_mb),
    ("performance", "*_seconds",         float),
    ("performance", "file_cache_size",   int),
    ("performance", "max_requests_per_minute", int),
    ("performance", "max_content_length", int),
    ("performance", "max_fix_content_length", int),
    # Processing section
    ("processing",  "batch_size",        int),
    ("processing",  "enable_*",          _to_bool),
    # Logging section
    ("logging",     "enable_*",          _to_bool),
]


def _find_converter(section: str, key: str) -> Any | None:
    """Look up the appropriate type converter for a (section, key) pair."""
    for rule_section, pattern, converter in _CONVERTERS:
        if rule_section != section:
            continue
        if pattern.startswith("*") and key.endswith(pattern[1:]):
            return converter
        if pattern.endswith("*") and key.startswith(pattern[:-1]):
            return converter
        if pattern == key:
            return converter
    return None


class Config:
    """
    Configuration manager with automatic type conversion.

    Sections:
        backend       – AI backend selection
        performance   – file size limits, rate limiting, timeouts
        processing    – batch processing settings
        logging       – log levels, file logging
        model         – Bedrock model ID
        aws           – AWS credentials / SSO
        kiro          – Kiro CLI/WSL settings
        copilot       – GitHub Copilot CLI settings
        local_llm     – Local LLM server settings
    """

    def __init__(self):
        self.config = configparser.ConfigParser()

        search_paths = [
            Path.cwd() / "config.ini",
            Path(__file__).parent.parent.parent / "config.ini",
        ]

        self.config_path = None
        for p in search_paths:
            if p.exists():
                self.config_path = p
                break

        self._set_defaults()

        if self.config_path:
            self.config.read(self.config_path, encoding="utf-8")

    # ── defaults ───────────────────────────────────────────────────────────

    def _add(self, section: str, key: str, value: str):
        """Helper to add a default without raising on duplicate sections."""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, value)

    def _set_defaults(self):
        # ── backend ────────────────────────────────────────────────────────
        self._add("backend", "type", "bedrock")

        # ── performance ────────────────────────────────────────────────────
        self._add("performance", "max_file_size_mb", "10")
        self._add("performance", "max_fix_file_size_mb", "5")
        self._add("performance", "file_cache_size", "100")
        self._add("performance", "min_request_interval_seconds", "6.0")
        self._add("performance", "max_requests_per_minute", "10")
        self._add("performance", "api_timeout_seconds", "300")
        self._add("performance", "connect_timeout_seconds", "30")
        self._add("performance", "max_content_length", "100000")
        self._add("performance", "max_fix_content_length", "50000")

        # ── processing ─────────────────────────────────────────────────────
        self._add("processing", "batch_size", "5")
        self._add("processing", "enable_parallel_processing", "false")
        self._add("processing", "enable_interaction_analysis", "false")
        self._add("processing", "enable_architectural_review", "false")

        # ── logging ────────────────────────────────────────────────────────
        self._add("logging", "log_level", "INFO")
        self._add("logging", "enable_performance_logging", "true")
        self._add("logging", "enable_file_logging", "false")
        self._add("logging", "log_file", "aicodereviewer.log")

        # ── model (Bedrock) ────────────────────────────────────────────────
        self._add("model", "model_id", "anthropic.claude-3-5-sonnet-20240620-v1:0")

        # ── aws ────────────────────────────────────────────────────────────
        self._add("aws", "access_key_id", "")
        self._add("aws", "region", "us-east-1")
        self._add("aws", "session_token", "")
        self._add("aws", "sso_session", "")
        self._add("aws", "sso_account_id", "")
        self._add("aws", "sso_role_name", "")
        self._add("aws", "sso_region", "us-east-1")
        self._add("aws", "sso_start_url", "")
        self._add("aws", "sso_registration_scopes", "sso:account:access")
        self._add("aws", "output", "json")

        # ── kiro ───────────────────────────────────────────────────────────
        self._add("kiro", "wsl_distro", "")
        self._add("kiro", "cli_command", "kiro")
        self._add("kiro", "timeout", "300")

        # ── copilot ────────────────────────────────────────────────────────
        self._add("copilot", "copilot_path", "copilot")
        self._add("copilot", "timeout", "300")
        self._add("copilot", "model", "auto")

        # ── local_llm ─────────────────────────────────────────────────────
        self._add("local_llm", "api_url", "http://localhost:1234")
        self._add("local_llm", "api_type", "lmstudio")
        self._add("local_llm", "model", "default")
        self._add("local_llm", "api_key", "")
        self._add("local_llm", "timeout", "300")
        self._add("local_llm", "max_tokens", "4096")

        # ── gui ────────────────────────────────────────────────────────────
        self._add("gui", "theme", "system")
        self._add("gui", "language", "system")
        self._add("gui", "review_language", "system")

    # ── typed access ───────────────────────────────────────────────────────

    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        """
        Retrieve a configuration value with automatic type conversion.

        The conversion rules are defined in :data:`_CONVERTERS` at module
        level.  If no rule matches, the raw string is returned.
        """
        try:
            value = self.config.get(section, key)
            value = value.split("#")[0].strip()  # strip inline comments

            converter = _find_converter(section, key)
            if converter is not None:
                return converter(value)
            return value

        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def set_value(self, section: str, key: str, value: str):
        """Set a configuration value at runtime (does NOT persist to disk)."""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, value)

    def save(self):
        """Persist current configuration to disk."""
        if self.config_path is None:
            self.config_path = Path.cwd() / "config.ini"
        with open(self.config_path, "w", encoding="utf-8") as fh:
            self.config.write(fh)


# Global singleton
config = Config()
