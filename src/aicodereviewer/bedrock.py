# src/aicodereviewer/bedrock.py
"""
AWS Bedrock AI client for code review and fix generation.

This module provides a robust client for interacting with Anthropic Claude
via AWS Bedrock, with comprehensive rate limiting, error handling, and
connection validation for reliable AI-powered code analysis.

Classes:
    BedrockClient: Main client for AI code review operations
"""
import boto3
import time
import logging
from botocore.exceptions import ClientError, ProfileNotFound, TokenRetrievalError
from botocore.config import Config
from typing import Optional

from .config import config
from .interfaces import AIClient
from .auth import create_aws_session


logger = logging.getLogger(__name__)


class BedrockClient:
    """
    AWS Bedrock client for AI-powered code review and fixes.

    Handles authentication, rate limiting, connection validation, and
    provides specialized prompts for different types of code analysis.

    Attributes:
        session: boto3 session with configured profile
        client: bedrock-runtime client instance
        model_id: Claude model identifier
        min_request_interval: Minimum seconds between requests
        max_requests_per_minute: Rate limit for requests per minute
    """

    def __init__(self, region="us-east-1"):
        """
        Initialize Bedrock client with AWS authentication and performance settings.

        Uses config-based credentials if available, otherwise falls back to
        AWS CLI profile authentication.

        Args:
            region (str): AWS region (default: us-east-1)

        Raises:
            Exception: If AWS authentication fails
        """
        try:
            # Create AWS session using config or profile authentication
            self.session, auth_description = create_aws_session(region)
            print(f"AWS認証成功: {auth_description}")
            
            config_settings = Config(
                region_name=region,
                retries={'max_attempts': 3, 'mode': 'standard'},
                read_timeout=config.get('performance', 'api_timeout_seconds'),
                connect_timeout=config.get('performance', 'connect_timeout_seconds')
            )
            self.client = self.session.client("bedrock-runtime", config=config_settings)
            self.model_id = config.get('model', 'model_id')

            # Rate limiting from config
            self.last_request_time = 0
            self.min_request_interval = config.get('performance', 'min_request_interval_seconds')
            self.request_count = 0
            self.window_start = time.time()
            self.max_requests_per_minute = config.get('performance', 'max_requests_per_minute')

        except ProfileNotFound:
            raise Exception(f"AWSプロファイル '{profile_name}' が見つかりません。")

    def _check_rate_limit(self):
        """
        Check and enforce rate limiting to prevent API throttling.

        Implements both per-minute request limits and minimum intervals
        between requests to ensure compliance with AWS Bedrock limits.
        """
        current_time = time.time()

        # Reset counter if window has passed
        if current_time - self.window_start >= 60:
            self.request_count = 0
            self.window_start = current_time

        # Check per-minute limit
        if self.request_count >= self.max_requests_per_minute:
            sleep_time = 60 - (current_time - self.window_start)
            if sleep_time > 0:
                logger.info(f"Rate limit reached. Sleeping for {sleep_time:.1f} seconds...")
                time.sleep(sleep_time)
                self.request_count = 0
                self.window_start = time.time()

        # Check minimum interval between requests
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            time.sleep(sleep_time)

    def _validate_connection(self):
        """
        Validate AWS connection and authentication with minimal test request.

        Raises:
            Exception: If authentication fails or connection is invalid
        """
        try:
            self.client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": "Hello"}]}],
                inferenceConfig={"maxTokens": 1}
            )
        except TokenRetrievalError as e:
            raise Exception("AWSログインの期限が切れています。'aws sso login --profile <プロファイル名>' を実行してください。")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', '')
            
            # Check for Anthropic use case form requirement
            if 'use case' in error_message.lower() and 'anthropic' in error_message.lower():
                raise Exception(
                    "Anthropicの利用規約フォームが完了していません。\n"
                    "AWS Bedrock コンソールで Anthropic Claude モデルの使用規約フォームを送信してください。\n"
                    "詳細: https://console.aws.amazon.com/bedrock"
                )
            
            # Check for model access denied
            if error_code == 'AccessDeniedException':
                raise Exception(
                    f"AWSアクセス権限がありません。\n"
                    f"プロファイル '{self.session.profile_name}' は Bedrock へのアクセス権限を持っていません。"
                )
            
            # Default to authentication error
            raise Exception("AWSログインの期限が切れています。'aws sso login --profile <プロファイル名>' を実行してください。")

    def get_review(self, code_content: str, review_type: str = "security", lang: str = "en", spec_content: Optional[str] = None) -> str:
        """
        Perform AI-powered code review with specialized prompts.

        Supports multiple review types with expert personas and language options.
        Includes comprehensive error handling and automatic retry on throttling.

        Args:
            code_content (str): Code to review
            review_type (str): Type of review ('security', 'performance', etc.)
            lang (str): Response language ('en' or 'ja')
            spec_content (Optional[str]): Specification document content for specification review

        Returns:
            str: AI review feedback or error message
        """
        # Rate limiting
        self._check_rate_limit()

        # Validate connection on first request
        if self.request_count == 0:
            self._validate_connection()

        # Skip processing if content is too large
        max_content = config.get('performance', 'max_content_length')
        if len(code_content) > max_content:
            return f"Error: Content too large for processing ({len(code_content)} > {max_content} characters)"

        prompts = {
            "security": "You are a Senior Security Auditor. Focus on critical vulnerabilities: injection attacks, XSS, authentication issues, insecure configurations. Provide specific recommendations with severity levels.",
            "performance": "You are a Performance Engineer. Optimize efficiency and resources.",
            "best_practices": "You are a Lead Developer. Review for clean code and SOLID principles.",
            "maintainability": "You are a Code Maintenance Expert. Analyze readability and maintainability.",
            "documentation": "You are a Technical Writer. Review documentation and comments.",
            "testing": "You are a QA Engineer. Analyze testability and suggest testing improvements.",
            "accessibility": "You are an Accessibility Specialist. Review accessibility compliance.",
            "scalability": "You are a System Architect. Analyze scalability and concurrency.",
            "compatibility": "You are a Platform Engineer. Review cross-platform compatibility.",
            "error_handling": "You are a Reliability Engineer. Analyze error handling and fault tolerance.",
            "complexity": "You are a Code Analyst. Evaluate code complexity and suggest simplifications.",
            "architecture": "You are a Software Architect. Review code structure and design patterns.",
            "license": "You are a License Compliance Specialist. Review third-party library usage and licenses.",
            "localization": "You are an Internationalization Specialist. Review code for localization readiness, hardcoded strings that need translation, regional formatting requirements, date/time/currency formatting, and cultural compliance issues.",
            "specification": "You are a Requirements Analyst. Compare the code against the provided specifications and identify any deviations, missing implementations, or incorrect interpretations.",
            "fix": "You are an expert code fixer. Fix the code issues identified. Return only the corrected code."
        }

        base_prompt = prompts.get(review_type, prompts["best_practices"])

        # Add language instruction
        if lang == "ja":
            lang_instruction = "IMPORTANT: Provide your entire response in Japanese (日本語で回答してください)."
        else:
            lang_instruction = "IMPORTANT: Provide your entire response in English."

        system_msg = f"{base_prompt} {lang_instruction}"

        # Construct user message with specification if provided
        if review_type == "specification" and spec_content:
            user_message = f"SPECIFICATION DOCUMENT:\n{spec_content}\n\n---\n\nCODE TO REVIEW:\n{code_content}\n\n---\n\nCompare the code against the specification and identify any deviations, missing implementations, or areas that don't meet the requirements."
        else:
            user_message = f"Review this code:\n\n{code_content}"

        messages = [{
            "role": "user",
            "content": [{"text": user_message}]
        }]

        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=messages,
                system=[{"text": system_msg}],
                inferenceConfig={"maxTokens": 2000, "temperature": 0.1}
            )

            self.last_request_time = time.time()
            self.request_count += 1

            return response["output"]["message"]["content"][0]["text"]

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error'].get('Message', '')
            
            # Check for Anthropic use case form requirement
            if 'use case' in error_message.lower() and 'anthropic' in error_message.lower():
                return (
                    "Error: Anthropicの利用規約フォームが完了していません。\n"
                    "AWS Bedrock コンソールで Anthropic Claude モデルの使用規約フォームを送信してください。\n"
                    "詳細: https://console.aws.amazon.com/bedrock"
                )
            
            if error_code == 'ThrottlingException':
                logger.warning("AWS API rate limit exceeded. Waiting before retry...")
                time.sleep(30)
                return self.get_review(code_content, review_type, lang, spec_content)  # Retry once
            elif error_code == 'ValidationException':
                return f"Error: Input validation failed - {str(e)}"
            elif error_code == 'AccessDeniedException':
                return (
                    f"Error: AWSアクセス権限がありません。\n"
                    f"プロファイル '{self.session.profile_name}' は Bedrock へのアクセス権限を持っていません。"
                )
            else:
                return f"Error: AWS API error - {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"
