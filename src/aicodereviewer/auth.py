# src/aicodereviewer/auth.py
"""
AWS authentication and profile management for AICodeReviewer.

This module handles secure storage and retrieval of AWS profiles using
the system keyring, along with automatic language detection for UI.

Functions:
    get_profile_name: Retrieve or prompt for AWS profile name
    set_profile_name: Set or change AWS profile name
    clear_profile: Remove stored AWS profile
    get_system_language: Detect system language for UI localization
"""
import keyring
import locale
import os
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from .config import config
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from .config import config

SERVICE_NAME = "AICodeReviewer"


def get_profile_name():
    """
    Retrieve stored AWS profile name or prompt user for initial setup.

    Uses system keyring for secure storage of AWS profile credentials.
    If no profile is stored, guides user through initial configuration.

    Returns:
        str: AWS profile name for authentication
    """
    profile = keyring.get_password(SERVICE_NAME, "aws_profile")

    if not profile:
        print("--- AICodeReviewer 初期設定 ---")
        print("AWS IAM Identity Centerのプロファイル名を入力してください。")
        print("(例: 'default'。設定していない場合は 'aws configure sso' を先に実行してください)")

        profile = input("プロファイル名: ").strip()
        if not profile:
            profile = "default"

        keyring.set_password(SERVICE_NAME, "aws_profile", profile)
        print(f"プロファイル '{profile}' を保存しました。\n")

    return profile


def set_profile_name(new_profile=None):
    """
    Set or change the AWS profile name for authentication.

    Updates the stored profile in system keyring. If no profile provided,
    prompts user for input.

    Args:
        new_profile (str, optional): New profile name. If None, prompts user.

    Returns:
        str: The profile name that was set
    """
    if new_profile is None:
        print("--- AWSプロファイル設定 ---")
        print("現在のプロファイル名を入力してください。")
        print("(例: 'default'。設定していない場合は 'aws configure sso' を先に実行してください)")

        new_profile = input("プロファイル名: ").strip()
        if not new_profile:
            new_profile = "default"

    keyring.set_password(SERVICE_NAME, "aws_profile", new_profile)
    print(f"プロファイル '{new_profile}' を保存しました。")
    return new_profile


def clear_profile():
    """
    Remove the stored AWS profile from system keyring.

    Clears authentication credentials, requiring re-setup on next use.
    Useful for switching accounts or troubleshooting auth issues.
    """
    try:
        keyring.delete_password(SERVICE_NAME, "aws_profile")
        print("AWSプロファイルを削除しました。")
    except Exception as e:
        print(f"プロファイル削除エラー: {e}")


def get_system_language():
    """
    Detect system language for UI localization using recommended APIs.

    Prefers environment variables, then uses locale.setlocale/getlocale
    to read the user's configured locale without deprecated functions.

    Returns:
        str: 'ja' for Japanese systems, 'en' for others
    """
    try:
        # Check common environment variables first
        for var in ("LC_ALL", "LANG", "LANGUAGE"):
            val = os.environ.get(var)
            if val:
                v = val.lower()
                if v.startswith("ja"):
                    return "ja"
                if v.startswith("en"):
                    return "en"

        # Initialize locale from user settings and read it
        try:
            locale.setlocale(locale.LC_ALL, "")
        except Exception:
            # If setting locale fails, continue with current settings
            pass

        loc = locale.getlocale()[0]
        if loc:
            loc_lower = loc.lower()
            if loc_lower.startswith("ja") or "japanese" in loc_lower:
                return "ja"
    except Exception:
        # Fall through to default
        pass
    return "en"


def create_aws_session(region="us-east-1"):
    """
    Create AWS session using config-based credentials or AWS CLI profile.

    Priority order:
    1. SSO session (if sso_session configured) - opens browser automatically
    2. Config-based credentials (if access_key_id configured) - prompts for secret key
    3. Profile-based authentication (fallback)

    Args:
        region (str): AWS region for the session

    Returns:
        tuple: (boto3.Session, str) - session object and auth method description
    """
    # Check for SSO configuration first
    sso_session = config.get('aws', 'sso_session', '').strip()
    if sso_session:
        print("--- AWS設定 (SSO) ---")
        print(f"SSOセッション: {sso_session}")
        config_region = config.get('aws', 'region') or region
        try:
            session = boto3.Session(sso_session=sso_session, region=config_region)
            # Test credentials to trigger browser authentication if needed
            sts = session.client('sts')
            sts.get_caller_identity()
            return session, f"SSO認証 ({sso_session})"
        except Exception as e:
            print(f"SSO認証失敗: {e}")
            print("設定ファイル認証にフォールバックします...")

    # Check for config-based credentials
    access_key_id = config.get('aws', 'access_key_id', '').strip()
    if access_key_id:
        print("--- AWS設定 (設定ファイル) ---")
        print(f"アクセスキーID: {access_key_id}")
        config_region = config.get('aws', 'region') or region
        session_token = config.get('aws', 'session_token', '').strip()

        # Prompt for secret access key (not stored in config for security)
        secret_access_key = input("シークレットアクセスキー: ").strip()
        if not secret_access_key:
            raise ValueError("シークレットアクセスキーが必要です")

        # Create session with direct credentials
        try:
            session = boto3.Session(
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                aws_session_token=session_token if session_token else None,
                region_name=config_region
            )
            # Test the credentials
            sts = session.client('sts')
            sts.get_caller_identity()
            return session, f"設定ファイル認証 ({access_key_id[:8]}...)"

        except (NoCredentialsError, PartialCredentialsError) as e:
            print(f"設定ファイル認証失敗: {e}")
            print("プロファイル認証にフォールバックします...")

    # Fall back to AWS CLI profile authentication
    profile_name = get_profile_name()
    try:
        config_region = config.get('aws', 'region') or region
        session = boto3.Session(profile_name=profile_name, region_name=config_region)
        # Test the profile credentials
        sts = session.client('sts')
        sts.get_caller_identity()
        return session, f"プロファイル認証 ({profile_name})"

    except (NoCredentialsError, PartialCredentialsError) as e:
        raise Exception(f"AWSプロファイル認証エラー: {e}")
    except Exception as e:
        raise Exception(f"プロファイル '{profile_name}' の認証エラー: {e}")
