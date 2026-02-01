"""Tests for src/core/transcription.py"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
import httpx
from src.core.transcription import TranscriptionService, TranscriptionResult, UPLOAD_CHUNK_SIZE


FAKE_DEEPGRAM_RESPONSE = {
    "results": {
        "channels": [{
            "alternatives": [{
                "transcript": "This is a test transcript.",
                "words": [
                    {"word": "This", "start": 0.0, "end": 0.3, "confidence": 0.99},
                    {"word": "is", "start": 0.3, "end": 0.5, "confidence": 0.99},
                ],
                "paragraphs": {},
            }],
        }],
        "utterances": [{
            "start": 0.0, "end": 1.5,
            "transcript": "This is a test transcript.", "speaker": 0,
        }],
    },
    "metadata": {"duration": 1.5},
}


class TestTranscriptionResult:
    def test_success_result(self):
        r = TranscriptionResult(success=True, transcript="hello")
        assert r.success is True
        assert r.transcript == "hello"

    def test_failure_result(self):
        r = TranscriptionResult(success=False, error_message="bad")
        assert r.success is False
        assert r.error_message == "bad"

    def test_has_timestamps_with_words(self):
        r = TranscriptionResult(success=True, words=[{"word": "hi"}])
        assert r.has_timestamps is True

    def test_has_timestamps_without_words(self):
        r = TranscriptionResult(success=True, transcript="hi")
        assert r.has_timestamps is False


class TestFileStream:
    def test_file_stream_reads_in_chunks(self, sample_audio_file):
        svc = TranscriptionService(api_key="test-key")
        chunks = list(svc._file_stream(sample_audio_file))
        assert len(chunks) >= 1
        total = sum(len(c) for c in chunks)
        assert total == sample_audio_file.stat().st_size

    def test_file_stream_chunk_size_limit(self, tmp_path):
        big = tmp_path / "big.mp3"
        big.write_bytes(b"x" * (UPLOAD_CHUNK_SIZE * 3 + 100))
        svc = TranscriptionService(api_key="test-key")
        chunks = list(svc._file_stream(big))
        for c in chunks[:-1]:
            assert len(c) == UPLOAD_CHUNK_SIZE


class TestTranscribe:
    def test_transcribe_file_not_found(self, tmp_path):
        svc = TranscriptionService(api_key="test-key")
        r = svc.transcribe(tmp_path / "nonexistent.mp3")
        assert r.success is False
        assert "does not exist" in r.error_message.lower()

    def test_transcribe_success_with_mock(self, sample_audio_file):
        svc = TranscriptionService(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = FAKE_DEEPGRAM_RESPONSE
        mock_resp.content = b"data"
        with patch("httpx.Client") as mc:
            mc.return_value.__enter__ = Mock(return_value=MagicMock(
                post=Mock(return_value=mock_resp)))
            mc.return_value.__exit__ = Mock(return_value=False)
            r = svc.transcribe(sample_audio_file)
            assert r.success is True
            assert "test transcript" in r.transcript

    def test_transcribe_api_timeout(self, sample_audio_file):
        svc = TranscriptionService(api_key="test-key")
        with patch("httpx.Client") as mc:
            mc.return_value.__enter__ = Mock(return_value=MagicMock(
                post=Mock(side_effect=httpx.TimeoutException("timeout"))))
            mc.return_value.__exit__ = Mock(return_value=False)
            r = svc.transcribe(sample_audio_file)
            assert r.success is False
            assert "timeout" in r.error_message.lower()

    def test_transcribe_401_unauthorized(self, sample_audio_file):
        svc = TranscriptionService(api_key="bad")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("httpx.Client") as mc:
            mc.return_value.__enter__ = Mock(return_value=MagicMock(
                post=Mock(return_value=mock_resp)))
            mc.return_value.__exit__ = Mock(return_value=False)
            r = svc.transcribe(sample_audio_file)
            assert r.success is False

    def test_content_type_for_mp3(self):
        svc = TranscriptionService(api_key="test")
        assert svc._get_content_type(Path("test.mp3")) == "audio/mpeg"

    def test_content_type_for_mp4(self):
        svc = TranscriptionService(api_key="test")
        assert svc._get_content_type(Path("test.mp4")) == "video/mp4"


class TestFileStreamBugFix:
    """Bug #3: File handle leak in _file_stream generator."""

    def test_file_stream_closes_on_exception(self, sample_audio_file):
        """File handle should be closed even if consumer raises during iteration."""
        svc = TranscriptionService(api_key="test")
        gen = svc._file_stream(sample_audio_file)
        # Start iteration
        next(gen)
        # Simulate consumer aborting - close generator
        gen.close()
        # If we get here without ResourceWarning, the file handle was properly closed

    def test_file_stream_closes_on_normal_completion(self, sample_audio_file):
        """File handle should be closed after full iteration."""
        svc = TranscriptionService(api_key="test")
        chunks = list(svc._file_stream(sample_audio_file))
        assert len(chunks) > 0


# ---------------------------------------------------------------------------
# Tests for refactored helper methods (Stage 2)
# ---------------------------------------------------------------------------

class TestValidateInputs:
    def test_validate_inputs_file_not_found(self, tmp_path):
        svc = TranscriptionService(api_key="test")
        result = svc._validate_inputs(tmp_path / "nope.mp3", "en")
        assert result is not None
        assert result.success is False
        assert "does not exist" in result.error_message.lower()

    def test_validate_inputs_file_too_large(self, tmp_path):
        svc = TranscriptionService(api_key="test")
        big = tmp_path / "huge.mp3"
        big.write_bytes(b"x" * 100)
        # Patch the max file size to something tiny
        with patch("src.core.transcription.DEEPGRAM_MAX_FILE_SIZE", 50):
            result = svc._validate_inputs(big, "en")
        assert result is not None
        assert result.success is False
        assert "too large" in result.error_message.lower()

    def test_validate_inputs_ok(self, sample_audio_file):
        svc = TranscriptionService(api_key="test")
        result = svc._validate_inputs(sample_audio_file, "en")
        assert result is None  # No error


class TestBuildRequestParams:
    def test_auto_language(self):
        svc = TranscriptionService(api_key="test")
        params = svc._build_request_params("auto", False, True, True)
        assert "detect_language" in params
        assert "language" not in params

    def test_specific_language(self):
        svc = TranscriptionService(api_key="test")
        params = svc._build_request_params("pl", False, True, True)
        assert params["language"] == "pl"
        assert "detect_language" not in params

    def test_diarize_enabled(self):
        svc = TranscriptionService(api_key="test")
        params = svc._build_request_params("en", True, True, True)
        assert params["diarize"] == "true"

    def test_diarize_disabled(self):
        svc = TranscriptionService(api_key="test")
        params = svc._build_request_params("en", False, True, True)
        assert "diarize" not in params

    def test_smart_format_false(self):
        svc = TranscriptionService(api_key="test")
        params = svc._build_request_params("en", False, True, False)
        assert params["smart_format"] == "false"

    def test_model_included(self):
        svc = TranscriptionService(api_key="test", model="nova-3")
        params = svc._build_request_params("en", False, True, True)
        assert params["model"] == "nova-3"


class TestCheckResponseErrors:
    def test_401_returns_error(self):
        svc = TranscriptionService(api_key="test")
        resp = MagicMock()
        resp.status_code = 401
        result = svc._check_response_errors(resp)
        assert result is not None
        assert "Invalid API key" in result.error_message

    def test_403_returns_error(self):
        svc = TranscriptionService(api_key="test")
        resp = MagicMock()
        resp.status_code = 403
        result = svc._check_response_errors(resp)
        assert result is not None
        assert "Access denied" in result.error_message

    def test_429_returns_error(self):
        svc = TranscriptionService(api_key="test")
        resp = MagicMock()
        resp.status_code = 429
        result = svc._check_response_errors(resp)
        assert result is not None
        assert "rate limit" in result.error_message.lower()

    def test_500_returns_error(self):
        svc = TranscriptionService(api_key="test")
        resp = MagicMock()
        resp.status_code = 500
        resp.content = b'{"err_msg": "server error"}'
        resp.json.return_value = {"err_msg": "server error"}
        result = svc._check_response_errors(resp)
        assert result is not None
        assert "server error" in result.error_message

    def test_200_returns_none(self):
        svc = TranscriptionService(api_key="test")
        resp = MagicMock()
        resp.status_code = 200
        result = svc._check_response_errors(resp)
        assert result is None


class TestParseResponse:
    def test_parse_success(self):
        svc = TranscriptionService(api_key="test")
        result = svc._parse_response(FAKE_DEEPGRAM_RESPONSE)
        assert result.success is True
        assert "test transcript" in result.transcript
        assert result.duration_seconds == 1.5

    def test_parse_no_channels(self):
        svc = TranscriptionService(api_key="test")
        result = svc._parse_response({"results": {"channels": []}, "metadata": {}})
        assert result.success is False
        assert "No transcription results" in result.error_message

    def test_parse_no_alternatives(self):
        svc = TranscriptionService(api_key="test")
        data = {"results": {"channels": [{"alternatives": []}]}, "metadata": {}}
        result = svc._parse_response(data)
        assert result.success is False
        assert "No transcript alternatives" in result.error_message

    def test_parse_extracts_utterances(self):
        svc = TranscriptionService(api_key="test")
        result = svc._parse_response(FAKE_DEEPGRAM_RESPONSE)
        assert result.utterances is not None
        assert len(result.utterances) == 1
        assert result.utterances[0]["text"] == "This is a test transcript."

    def test_parse_extracts_words(self):
        svc = TranscriptionService(api_key="test")
        result = svc._parse_response(FAKE_DEEPGRAM_RESPONSE)
        assert result.words is not None
        assert len(result.words) == 2
        assert result.words[0]["word"] == "This"
