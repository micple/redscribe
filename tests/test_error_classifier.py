"""Tests for src/core/error_classifier.py"""
import pytest
from src.core.error_classifier import ErrorClassifier
from src.models.media_file import ErrorCategory


class TestClassifyRateLimitErrors:
    def test_classify_rate_limit_message(self):
        category, retryable = ErrorClassifier.classify("rate limit exceeded")
        assert category == ErrorCategory.RETRYABLE_RATE_LIMIT
        assert retryable is True

    def test_classify_too_many_requests(self):
        category, retryable = ErrorClassifier.classify("too many requests")
        assert category == ErrorCategory.RETRYABLE_RATE_LIMIT
        assert retryable is True

    def test_classify_429_error(self):
        category, retryable = ErrorClassifier.classify("HTTP 429 error")
        assert category == ErrorCategory.RETRYABLE_RATE_LIMIT
        assert retryable is True


class TestClassifyNetworkErrors:
    def test_classify_timeout(self):
        category, retryable = ErrorClassifier.classify("Connection timeout")
        assert category == ErrorCategory.RETRYABLE_NETWORK
        assert retryable is True

    def test_classify_connection_error(self):
        category, retryable = ErrorClassifier.classify("connection error occurred")
        assert category == ErrorCategory.RETRYABLE_NETWORK
        assert retryable is True

    def test_classify_connection_refused(self):
        category, retryable = ErrorClassifier.classify("connection refused")
        assert category == ErrorCategory.RETRYABLE_NETWORK
        assert retryable is True

    def test_classify_connection_reset(self):
        category, retryable = ErrorClassifier.classify("connection reset by peer")
        assert category == ErrorCategory.RETRYABLE_NETWORK
        assert retryable is True

    def test_classify_operation_took_too_long(self):
        category, retryable = ErrorClassifier.classify("operation took too long")
        assert category == ErrorCategory.RETRYABLE_NETWORK
        assert retryable is True


class TestClassifyServerErrors:
    def test_classify_500_error(self):
        category, retryable = ErrorClassifier.classify("HTTP 500 internal error")
        assert category == ErrorCategory.RETRYABLE_SERVER
        assert retryable is True

    def test_classify_service_unavailable(self):
        category, retryable = ErrorClassifier.classify("service unavailable")
        assert category == ErrorCategory.RETRYABLE_SERVER
        assert retryable is True

    def test_classify_bad_gateway(self):
        category, retryable = ErrorClassifier.classify("bad gateway")
        assert category == ErrorCategory.RETRYABLE_SERVER
        assert retryable is True

    def test_classify_504_error(self):
        category, retryable = ErrorClassifier.classify("504 error occurred")
        assert category == ErrorCategory.RETRYABLE_SERVER
        assert retryable is True


class TestClassifyAuthErrors:
    def test_classify_invalid_api_key(self):
        category, retryable = ErrorClassifier.classify("Invalid API key provided")
        assert category == ErrorCategory.NON_RETRYABLE_AUTH
        assert retryable is False

    def test_classify_unauthorized(self):
        category, retryable = ErrorClassifier.classify("Unauthorized access")
        assert category == ErrorCategory.NON_RETRYABLE_AUTH
        assert retryable is False

    def test_classify_403_forbidden(self):
        category, retryable = ErrorClassifier.classify("403 Forbidden")
        assert category == ErrorCategory.NON_RETRYABLE_AUTH
        assert retryable is False


class TestClassifyFileErrors:
    def test_classify_file_not_found(self):
        category, retryable = ErrorClassifier.classify("File not found on disk")
        assert category == ErrorCategory.NON_RETRYABLE_FILE
        assert retryable is False

    def test_classify_file_too_large(self):
        category, retryable = ErrorClassifier.classify("File too large for upload")
        assert category == ErrorCategory.NON_RETRYABLE_FILE
        assert retryable is False


class TestClassifyConversionErrors:
    def test_classify_corrupted_file(self):
        category, retryable = ErrorClassifier.classify("File is corrupted")
        assert category == ErrorCategory.NON_RETRYABLE_CONVERSION
        assert retryable is False

    def test_classify_unsupported_format(self):
        category, retryable = ErrorClassifier.classify("Unsupported file format")
        assert category == ErrorCategory.NON_RETRYABLE_CONVERSION
        assert retryable is False


class TestClassifyConfigErrors:
    def test_classify_ffmpeg_not_found(self):
        category, retryable = ErrorClassifier.classify("FFmpeg not found on system")
        assert category == ErrorCategory.NON_RETRYABLE_CONFIG
        assert retryable is False

    def test_classify_permission_denied(self):
        category, retryable = ErrorClassifier.classify("Permission denied to file")
        assert category == ErrorCategory.NON_RETRYABLE_CONFIG
        assert retryable is False


class TestClassifyEdgeCases:
    def test_classify_empty_string_returns_none(self):
        category, retryable = ErrorClassifier.classify("")
        assert category == ErrorCategory.NONE
        assert retryable is False

    def test_classify_none_returns_none(self):
        category, retryable = ErrorClassifier.classify(None)
        assert category == ErrorCategory.NONE
        assert retryable is False

    def test_classify_unknown_error_defaults_to_retryable_network(self):
        category, retryable = ErrorClassifier.classify("some random unknown error xyz")
        assert category == ErrorCategory.RETRYABLE_NETWORK
        assert retryable is True

    def test_classify_mixed_case_matching(self):
        category, retryable = ErrorClassifier.classify("RATE LIMIT exceeded")
        assert category == ErrorCategory.RETRYABLE_RATE_LIMIT
        assert retryable is True

    def test_classify_message_with_special_characters(self):
        category, retryable = ErrorClassifier.classify("timeout!!!")
        assert category == ErrorCategory.RETRYABLE_NETWORK
        assert retryable is True


class TestIsRetryable:
    def test_is_retryable_true_for_network_error(self):
        assert ErrorClassifier.is_retryable("timeout") is True

    def test_is_retryable_false_for_auth_error(self):
        assert ErrorClassifier.is_retryable("unauthorized") is False

    def test_is_retryable_false_for_empty_message(self):
        assert ErrorClassifier.is_retryable("") is False


class TestGetRetryDelay:
    def test_rate_limit_base_delay_is_5_seconds(self):
        delay = ErrorClassifier.get_retry_delay(ErrorCategory.RETRYABLE_RATE_LIMIT, attempt=1)
        assert delay == 5.0

    def test_network_base_delay_is_2_seconds(self):
        delay = ErrorClassifier.get_retry_delay(ErrorCategory.RETRYABLE_NETWORK, attempt=1)
        assert delay == 2.0

    def test_server_base_delay_is_3_seconds(self):
        delay = ErrorClassifier.get_retry_delay(ErrorCategory.RETRYABLE_SERVER, attempt=1)
        assert delay == 3.0

    def test_exponential_backoff_attempt_2(self):
        delay = ErrorClassifier.get_retry_delay(ErrorCategory.RETRYABLE_NETWORK, attempt=2)
        assert delay == 4.0

    def test_exponential_backoff_attempt_3(self):
        delay = ErrorClassifier.get_retry_delay(ErrorCategory.RETRYABLE_NETWORK, attempt=3)
        assert delay == 8.0

    def test_non_retryable_category_uses_default_base(self):
        delay = ErrorClassifier.get_retry_delay(ErrorCategory.NON_RETRYABLE_AUTH, attempt=1)
        assert delay == 2.0
