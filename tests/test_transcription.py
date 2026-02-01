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
