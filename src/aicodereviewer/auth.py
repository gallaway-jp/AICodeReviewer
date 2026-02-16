# src/aicodereviewer/auth.py
"""
Authentication helpers and profile management.

Handles AWS profile storage via the system keyring, system language
detection, and AWS session creation with multiple auth strategies.

Performance Note:
    boto3 and botocore are imported lazily inside create_aws_session()
    to avoid loading heavy AWS SDK at module import time.
"""
import locale
import logging
import os
from typing import Optional, Tuple, TYPE_CHECKING

import keyring

# boto3 types for type checking only (not imported at runtime)
if TYPE_CHECKING:
    import boto3  # type: ignore

from .config import config
from .i18n import t

logger = logging.getLogger(__name__)
SERVICE_NAME = "AICodeReviewer"


# ── profile management ─────────────────────────────────────────────────────

def get_profile_name() -> str:
    """Retrieve stored AWS profile or prompt the user for initial setup."""
    profile = keyring.get_password(SERVICE_NAME, "aws_profile")
    if not profile:
        print(t("auth.setup_header"))
        print(t("auth.setup_prompt"))
        print(t("auth.setup_hint"))
        profile = input(t("auth.profile_prompt")).strip() or "default"
        keyring.set_password(SERVICE_NAME, "aws_profile", profile)
        print(t("auth.profile_saved", profile=profile) + "\n")
    return profile


def set_profile_name(new_profile: Optional[str] = None) -> str:
    """Set or change the stored AWS profile name."""
    if new_profile is None:
        print(t("auth.profile_header"))
        new_profile = input(t("auth.profile_prompt")).strip() or "default"
    keyring.set_password(SERVICE_NAME, "aws_profile", new_profile)
    print(t("auth.profile_saved", profile=new_profile))
    return new_profile


def clear_profile():
    """Remove the stored AWS profile from the system keyring."""
    try:
        keyring.delete_password(SERVICE_NAME, "aws_profile")
        print(t("auth.profile_removed"))
    except Exception as exc:
        print(t("auth.profile_remove_error", error=exc))


# ── language detection ─────────────────────────────────────────────────────

def get_system_language() -> str:
    """
    Detect the user's preferred language.

    Returns ``'ja'`` for Japanese locales, ``'en'`` otherwise.

    Detection order (Windows):
        1. Windows API via ctypes (GetUserDefaultUILanguage)
        2. Python locale module (fallback)
    Detection order (others):
        1. Environment variables (LC_ALL, LANG, LANGUAGE)
        2. Python locale module (fallback)

    On Windows the Win32 API is checked first because terminal
    emulators (Git Bash, MSYS2) often override LANG to ``en_US.UTF-8``
    even on a Japanese system.
    """
    try:
        # ── Windows-specific: Win32 API is the most reliable source ────
        if os.name == "nt":
            try:
                import ctypes
                lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
                primary = lang_id & 0x3FF
                if primary == 0x11:  # LANG_JAPANESE
                    return "ja"
                if primary == 0x09:  # LANG_ENGLISH
                    return "en"
            except Exception:
                pass

        # ── Non-Windows: environment variables ─────────────────────────
        for var in ("LC_ALL", "LANG", "LANGUAGE"):
            val = os.environ.get(var)
            if val:
                lower = val.lower()
                if lower.startswith("ja"):
                    return "ja"
                if lower.startswith("en"):
                    return "en"

        try:
            locale.setlocale(locale.LC_ALL, "")
        except Exception:
            pass
        loc = locale.getlocale()[0]
        if loc:
            ll = loc.lower()
            if ll.startswith("ja") or "japanese" in ll:
                return "ja"
    except Exception:
        pass
    return "en"


# ── AWS session creation ──────────────────────────────────────────────────

def create_aws_session(region: str = "us-east-1") -> Tuple["boto3.Session", str]:
    """
    Create an AWS session trying multiple auth strategies.

    Priority:
        1. SSO session (``[aws] sso_session``)
        2. Direct credentials (``[aws] access_key_id``)
        3. Profile-based (system keyring)

    Returns:
        ``(session, description)`` tuple.
    """
    # Lazy import of AWS SDK (avoids ~300ms startup penalty)
    import boto3  # type: ignore
    from botocore.exceptions import NoCredentialsError, PartialCredentialsError  # type: ignore

    config_region = config.get("aws", "region") or region

    # 1. SSO
    sso_session = (config.get("aws", "sso_session", "") or "").strip()
    if sso_session:
        try:
            sess = boto3.Session(sso_session=sso_session, region=config_region)  # type: ignore
            sess.client("sts").get_caller_identity()  # type: ignore
            return sess, f"SSO ({sso_session})"
        except Exception as exc:
            logger.warning("SSO auth failed (%s), trying next method …", exc)

    # 2. Direct credentials
    access_key = (config.get("aws", "access_key_id", "") or "").strip()
    if access_key:
        session_token = (config.get("aws", "session_token", "") or "").strip()
        secret = input(t("auth.secret_key_prompt")).strip()
        if secret:
            try:
                sess = boto3.Session(
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret,
                    aws_session_token=session_token or None,
                    region_name=config_region,
                )
                sess.client("sts").get_caller_identity()  # type: ignore
                return sess, f"Direct credentials ({access_key[:8]}…)"
            except (NoCredentialsError, PartialCredentialsError) as exc:
                logger.warning("Credential auth failed (%s), trying profile …", exc)

    # 3. Profile
    profile = get_profile_name()
    try:
        sess = boto3.Session(profile_name=profile, region_name=config_region)
        sess.client("sts").get_caller_identity()  # type: ignore
        return sess, f"Profile ({profile})"
    except Exception as exc:
        raise RuntimeError(f"All AWS auth methods failed. Last error: {exc}") from exc
