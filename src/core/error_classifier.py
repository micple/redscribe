"""
Error classification for retry logic.

Classifies transcription errors to determine if they should be retried.
"""
import logging
from typing import Tuple, cast

logger = logging.getLogger(__name__)

from src.models.media_file import ErrorCategory


class ErrorClassifier:
    """Classifies errors for retry decision."""

    # Patterns for retryable errors
    RETRYABLE_NETWORK_PATTERNS = [
        "timeout",
        "connection error",
        "connection refused",
        "network unreachable",
        "connection reset",
        "operation took too long",
    ]

    RETRYABLE_RATE_LIMIT_PATTERNS = [
        "rate limit",
        "too many requests",
        "429",
    ]

    RETRYABLE_SERVER_PATTERNS = [
        "500",
        "502",
        "503",
        "504",
        "internal server error",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
    ]

    # Non-retryable patterns
    NON_RETRYABLE_AUTH_PATTERNS = [
        "invalid api key",
        "access denied",
        "unauthorized",
        "401",
        "403",
        "forbidden",
    ]

    NON_RETRYABLE_FILE_PATTERNS = [
        "file does not exist",
        "file not found",
        "file too large",
        "max 2gb",
        "no such file",
    ]

    NON_RETRYABLE_CONVERSION_PATTERNS = [
        "corrupted",
        "unsupported",
        "invalid or corrupted",
        "does not contain audio",
        "does not contain any stream",
        "invalid data found",
    ]

    NON_RETRYABLE_CONFIG_PATTERNS = [
        "ffmpeg not found",
        "please reinstall",
        "permission denied",
        "cannot access file",
    ]

    @classmethod
    def classify(cls, error_message: str) -> Tuple[ErrorCategory, bool]:
        """
        Classify an error message.

        Args:
            error_message: The error message to classify.

        Returns:
            Tuple of (ErrorCategory, is_retryable)
        """
        if not error_message:
            return ErrorCategory.NONE, False

        msg_lower = error_message.lower()

        # Check retryable patterns first (order matters for rate limit)
        if any(p in msg_lower for p in cls.RETRYABLE_RATE_LIMIT_PATTERNS):
            return ErrorCategory.RETRYABLE_RATE_LIMIT, True

        if any(p in msg_lower for p in cls.RETRYABLE_NETWORK_PATTERNS):
            return ErrorCategory.RETRYABLE_NETWORK, True

        if any(p in msg_lower for p in cls.RETRYABLE_SERVER_PATTERNS):
            return ErrorCategory.RETRYABLE_SERVER, True

        # Check non-retryable patterns
        if any(p in msg_lower for p in cls.NON_RETRYABLE_AUTH_PATTERNS):
            return ErrorCategory.NON_RETRYABLE_AUTH, False

        if any(p in msg_lower for p in cls.NON_RETRYABLE_FILE_PATTERNS):
            return ErrorCategory.NON_RETRYABLE_FILE, False

        if any(p in msg_lower for p in cls.NON_RETRYABLE_CONVERSION_PATTERNS):
            return ErrorCategory.NON_RETRYABLE_CONVERSION, False

        if any(p in msg_lower for p in cls.NON_RETRYABLE_CONFIG_PATTERNS):
            return ErrorCategory.NON_RETRYABLE_CONFIG, False

        # Default: assume retryable network error (safer - gives user another chance)
        return ErrorCategory.RETRYABLE_NETWORK, True

    @classmethod
    def get_retry_delay(cls, category: ErrorCategory, attempt: int = 1) -> float:
        """
        Get delay before retry based on error category.

        Args:
            category: The error category.
            attempt: Current attempt number (1-based).

        Returns:
            Delay in seconds before retry.
        """
        base_delays: dict[ErrorCategory, float] = {
            ErrorCategory.RETRYABLE_RATE_LIMIT: 5.0,  # 429 needs longer delay
            ErrorCategory.RETRYABLE_NETWORK: 2.0,
            ErrorCategory.RETRYABLE_SERVER: 3.0,
        }

        base = cast(float, base_delays.get(category, 2.0))
        # Exponential backoff: delay * 2^(attempt-1)
        return float(base * (2 ** (attempt - 1)))

    @classmethod
    def is_retryable(cls, error_message: str) -> bool:
        """
        Quick check if an error is retryable.

        Args:
            error_message: The error message to check.

        Returns:
            True if the error should be retried.
        """
        _, retryable = cls.classify(error_message)
        return retryable
