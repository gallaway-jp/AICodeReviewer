# src/aicodereviewer/backends/bedrock.py
"""
AWS Bedrock AI backend for code review and fix generation.

Provides a robust client for interacting with foundation models via
AWS Bedrock's ``converse`` API, with rate limiting, exponential back-off
retry, and connection validation.
"""
import time
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError, ProfileNotFound, TokenRetrievalError
from botocore.config import Config as BotoConfig

from .base import AIBackend
from aicodereviewer.config import config
from aicodereviewer.auth import create_aws_session

logger = logging.getLogger(__name__)


class BedrockBackend(AIBackend):
    """
    AWS Bedrock backend using the unified ``converse`` API.

    Works with any model provisioned through Bedrock (Claude, Qwen, Llama,
    Mistral, etc.) without model-specific prompt formatting.
    """

    def __init__(self, region: Optional[str] = None):
        config_region = config.get("aws", "region", "us-east-1")
        region = str(region or config_region)

        try:
            self.session, auth_desc = create_aws_session(region)
            logger.info("AWS authentication successful: %s", auth_desc)

            boto_cfg = BotoConfig(
                region_name=region,
                retries={"max_attempts": 3, "mode": "standard"},
                read_timeout=config.get("performance", "api_timeout_seconds"),
                connect_timeout=config.get("performance", "connect_timeout_seconds"),
            )
            self.client = self.session.client("bedrock-runtime", config=boto_cfg)
            self.model_id: str = config.get("model", "model_id")

            # Rate-limiting state
            self.last_request_time: float = 0.0
            self.min_request_interval: float = config.get(
                "performance", "min_request_interval_seconds"
            )
            self.request_count: int = 0
            self.window_start: float = time.time()
            self.max_requests_per_minute: int = config.get(
                "performance", "max_requests_per_minute"
            )
            self._validated: bool = False

        except ProfileNotFound as exc:
            raise RuntimeError(f"AWS profile not found: {exc}") from exc

    # ── AIBackend interface ────────────────────────────────────────────────

    def get_review(
        self,
        code_content: str,
        review_type: str = "best_practices",
        lang: str = "en",
        spec_content: Optional[str] = None,
    ) -> str:
        max_content = config.get("performance", "max_content_length")
        if len(code_content) > max_content:
            return (
                f"Error: Content too large for processing "
                f"({len(code_content)} > {max_content} characters)"
            )

        system_prompt = self._build_system_prompt(
            review_type, lang, self._project_context, self._detected_frameworks,
        )
        user_message = self._build_user_message(code_content, review_type, spec_content)
        return self._invoke(system_prompt, user_message)

    def get_fix(
        self,
        code_content: str,
        issue_feedback: str,
        review_type: str = "best_practices",
        lang: str = "en",
    ) -> Optional[str]:
        max_content = config.get("performance", "max_fix_content_length")
        if len(code_content) > max_content:
            logger.warning("File too large for AI fix (%d chars)", len(code_content))
            return None

        system_prompt = self._build_system_prompt("fix", lang)
        user_message = self._build_fix_message(code_content, issue_feedback, review_type)
        result = self._invoke(system_prompt, user_message)
        if result and not result.startswith("Error:"):
            return result.strip()
        return None

    def validate_connection(self) -> bool:
        try:
            self.client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": "Hello"}]}],
                inferenceConfig={"maxTokens": 1},
            )
            return True
        except TokenRetrievalError:
            logger.error("AWS login has expired. Run 'aws sso login' to refresh.")
            return False
        except ClientError as exc:
            msg = exc.response.get("Error", {}).get("Message", "")
            logger.error("Bedrock connection test failed: %s", msg)
            return False
        except Exception as exc:
            logger.error("Bedrock connection test failed: %s", exc)
            return False

    # ── private helpers ────────────────────────────────────────────────────

    def _enforce_rate_limit(self):
        """Enforce per-minute and per-request rate limits."""
        now = time.time()

        # Reset window
        if now - self.window_start >= 60:
            self.request_count = 0
            self.window_start = now

        # Per-minute cap
        if self.request_count >= self.max_requests_per_minute:
            sleep_time = 60 - (now - self.window_start)
            if sleep_time > 0:
                logger.info("Rate limit reached. Sleeping %.1fs …", sleep_time)
                time.sleep(sleep_time)
            self.request_count = 0
            self.window_start = time.time()

        # Minimum interval
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)

    def _invoke(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        _retry: int = 0,
    ) -> str:
        """Send a converse request with rate limiting and retry logic."""
        self._enforce_rate_limit()

        # Lazy validation on first real call
        if not self._validated:
            if not self.validate_connection():
                return "Error: Backend connection validation failed."
            self._validated = True

        messages = [{"role": "user", "content": [{"text": user_message}]}]
        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=messages,
                system=[{"text": system_prompt}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
            )
            self.last_request_time = time.time()
            self.request_count += 1
            return response["output"]["message"]["content"][0]["text"]

        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            msg = exc.response.get("Error", {}).get("Message", "")

            if code == "ThrottlingException" and _retry < 3:
                wait = min(30 * (2 ** _retry), 120)
                logger.warning("Throttled by AWS. Retrying in %ds …", wait)
                time.sleep(wait)
                return self._invoke(
                    system_prompt, user_message, max_tokens, temperature, _retry + 1
                )

            if code == "AccessDeniedException":
                return (
                    "Error: Access denied. Ensure your AWS profile has Bedrock permissions."
                )
            if "use case" in msg.lower() and "anthropic" in msg.lower():
                return (
                    "Error: Anthropic use-case form not completed. "
                    "Submit the form in the AWS Bedrock console."
                )
            if code == "ValidationException":
                return f"Error: Validation failed – {msg}"
            return f"Error: AWS API error – {code}: {msg}"

        except Exception as exc:
            return f"Error: {exc}"
