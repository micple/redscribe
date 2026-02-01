"""Tests for src/core/transcription_orchestrator.py"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

from src.core.transcription_orchestrator import TranscriptionOrchestrator
from src.core.transcription import TranscriptionResult
from src.models.media_file import MediaFile, TranscriptionStatus, ErrorCategory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_converter():
    converter = MagicMock()
    converter.to_mp3.return_value = Path("/tmp/converted.mp3")
    converter.cleanup = MagicMock()
    return converter


@pytest.fixture
def mock_transcription_service():
    svc = MagicMock()
    svc.transcribe.return_value = TranscriptionResult(
        success=True,
        transcript="Hello world",
        duration_seconds=10.0,
    )
    return svc


@pytest.fixture
def mock_output_writer():
    writer = MagicMock()
    writer.save.return_value = Path("/output/file.txt")
    return writer


@pytest.fixture
def mock_session_logger():
    logger = MagicMock()
    return logger


@pytest.fixture
def event_log():
    """Collects events emitted by the orchestrator."""
    events = []

    def callback(event_type, file, extra):
        events.append((event_type, file, extra))

    return events, callback


@pytest.fixture
def orchestrator(mock_converter, mock_transcription_service, mock_output_writer, mock_session_logger):
    return TranscriptionOrchestrator(
        converter=mock_converter,
        transcription_service=mock_transcription_service,
        output_writer=mock_output_writer,
        session_logger=mock_session_logger,
    )


@pytest.fixture
def audio_file(tmp_path):
    p = tmp_path / "song.mp3"
    p.write_bytes(b"fake audio")
    return MediaFile(path=p, selected=True)


@pytest.fixture
def video_file(tmp_path):
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"fake video")
    return MediaFile(path=p, selected=True)


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------

class TestProcessFileSuccess:
    def test_audio_success(self, orchestrator, audio_file, mock_converter, mock_transcription_service):
        result = orchestrator.process_file(audio_file, "txt", None, "en", False, True)
        assert result is True
        assert audio_file.status == TranscriptionStatus.COMPLETED
        assert audio_file.error_message is None
        mock_converter.to_mp3.assert_not_called()
        mock_transcription_service.transcribe.assert_called_once()

    def test_video_success(self, orchestrator, video_file, mock_converter, mock_transcription_service):
        result = orchestrator.process_file(video_file, "txt", None, "en", False, True)
        assert result is True
        assert video_file.status == TranscriptionStatus.COMPLETED
        mock_converter.to_mp3.assert_called_once_with(video_file.path)
        mock_converter.cleanup.assert_called_once()

    def test_output_path_set(self, orchestrator, audio_file, mock_output_writer):
        orchestrator.process_file(audio_file, "txt", None, "en", False, True)
        assert audio_file.output_path == Path("/output/file.txt")

    def test_error_category_cleared(self, orchestrator, audio_file):
        audio_file.error_category = ErrorCategory.RETRYABLE_NETWORK
        orchestrator.process_file(audio_file, "txt", None, "en", False, True)
        assert audio_file.error_category == ErrorCategory.NONE

    def test_custom_output_dir(self, orchestrator, audio_file, mock_output_writer, tmp_path):
        out = tmp_path / "custom"
        orchestrator.process_file(audio_file, "srt", out, "pl", True, False)
        mock_output_writer.save.assert_called_once()
        _, kwargs = mock_output_writer.save.call_args
        assert kwargs["output_dir"] == out
        assert kwargs["output_format"] == "srt"

    def test_logger_called_on_success(self, orchestrator, audio_file, mock_session_logger):
        orchestrator.process_file(audio_file, "txt", None, "en", False, True)
        mock_session_logger.log_transcribing.assert_called_once_with(audio_file.name)
        mock_session_logger.log_file_completed.assert_called_once()


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------

class TestProcessFileFailure:
    def test_transcription_failure(self, orchestrator, audio_file, mock_transcription_service):
        mock_transcription_service.transcribe.return_value = TranscriptionResult(
            success=False, error_message="API error"
        )
        result = orchestrator.process_file(audio_file, "txt", None, "en", False, True)
        assert result is False
        assert audio_file.status == TranscriptionStatus.FAILED
        assert "API error" in audio_file.error_message

    def test_conversion_failure(self, orchestrator, video_file, mock_converter):
        mock_converter.to_mp3.side_effect = Exception("FFmpeg crashed")
        result = orchestrator.process_file(video_file, "txt", None, "en", False, True)
        assert result is False
        assert video_file.status == TranscriptionStatus.FAILED
        assert "FFmpeg crashed" in video_file.error_message

    def test_output_writer_failure(self, orchestrator, audio_file, mock_output_writer):
        mock_output_writer.save.side_effect = OSError("Disk full")
        result = orchestrator.process_file(audio_file, "txt", None, "en", False, True)
        assert result is False
        assert audio_file.status == TranscriptionStatus.FAILED

    def test_logger_called_on_failure(self, orchestrator, audio_file, mock_transcription_service, mock_session_logger):
        mock_transcription_service.transcribe.return_value = TranscriptionResult(
            success=False, error_message="Timeout"
        )
        orchestrator.process_file(audio_file, "txt", None, "en", False, True)
        mock_session_logger.log_file_failed.assert_called_once()

    def test_cleanup_after_conversion_failure(self, orchestrator, video_file, mock_converter):
        """Temp MP3 should NOT be cleaned if conversion itself failed (no file created)."""
        mock_converter.to_mp3.side_effect = Exception("fail")
        orchestrator.process_file(video_file, "txt", None, "en", False, True)
        # cleanup is called in finally, but temp_mp3_path is None since to_mp3 raised
        mock_converter.cleanup.assert_not_called()

    def test_cleanup_after_transcription_failure(self, orchestrator, video_file, mock_converter, mock_transcription_service):
        """Temp MP3 should be cleaned up even if transcription fails."""
        mock_transcription_service.transcribe.return_value = TranscriptionResult(
            success=False, error_message="API down"
        )
        orchestrator.process_file(video_file, "txt", None, "en", False, True)
        mock_converter.cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

class TestEventEmission:
    def test_audio_events_order(self, mock_converter, mock_transcription_service, mock_output_writer, mock_session_logger, event_log, audio_file):
        events, callback = event_log
        orch = TranscriptionOrchestrator(
            converter=mock_converter,
            transcription_service=mock_transcription_service,
            output_writer=mock_output_writer,
            session_logger=mock_session_logger,
            event_callback=callback,
        )
        orch.process_file(audio_file, "txt", None, "en", False, True)
        event_types = [e[0] for e in events]
        assert event_types == ["transcribing", "saving", "completed"]

    def test_video_events_order(self, mock_converter, mock_transcription_service, mock_output_writer, mock_session_logger, event_log, video_file):
        events, callback = event_log
        orch = TranscriptionOrchestrator(
            converter=mock_converter,
            transcription_service=mock_transcription_service,
            output_writer=mock_output_writer,
            session_logger=mock_session_logger,
            event_callback=callback,
        )
        orch.process_file(video_file, "txt", None, "en", False, True)
        event_types = [e[0] for e in events]
        assert event_types == ["converting", "transcribing", "saving", "completed"]

    def test_failure_event(self, mock_converter, mock_transcription_service, mock_output_writer, mock_session_logger, event_log, audio_file):
        events, callback = event_log
        mock_transcription_service.transcribe.return_value = TranscriptionResult(
            success=False, error_message="Oops"
        )
        orch = TranscriptionOrchestrator(
            converter=mock_converter,
            transcription_service=mock_transcription_service,
            output_writer=mock_output_writer,
            session_logger=mock_session_logger,
            event_callback=callback,
        )
        orch.process_file(audio_file, "txt", None, "en", False, True)
        event_types = [e[0] for e in events]
        assert "failed" in event_types
        failed_event = [e for e in events if e[0] == "failed"][0]
        assert "Oops" in failed_event[2]["error"]

    def test_completed_event_has_output_path(self, mock_converter, mock_transcription_service, mock_output_writer, mock_session_logger, event_log, audio_file):
        events, callback = event_log
        orch = TranscriptionOrchestrator(
            converter=mock_converter,
            transcription_service=mock_transcription_service,
            output_writer=mock_output_writer,
            session_logger=mock_session_logger,
            event_callback=callback,
        )
        orch.process_file(audio_file, "txt", None, "en", False, True)
        completed = [e for e in events if e[0] == "completed"][0]
        assert "output_path" in completed[2]

    def test_no_callback_does_not_raise(self, orchestrator, audio_file):
        """process_file should work without event_callback."""
        orchestrator.event_callback = None
        result = orchestrator.process_file(audio_file, "txt", None, "en", False, True)
        assert result is True

    def test_callback_exception_does_not_break_pipeline(self, mock_converter, mock_transcription_service, mock_output_writer, mock_session_logger, audio_file):
        def bad_callback(event_type, file, extra):
            raise RuntimeError("callback bug")

        orch = TranscriptionOrchestrator(
            converter=mock_converter,
            transcription_service=mock_transcription_service,
            output_writer=mock_output_writer,
            session_logger=mock_session_logger,
            event_callback=bad_callback,
        )
        result = orch.process_file(audio_file, "txt", None, "en", False, True)
        assert result is True


# ---------------------------------------------------------------------------
# Parameter forwarding
# ---------------------------------------------------------------------------

class TestParameterForwarding:
    def test_language_forwarded(self, orchestrator, audio_file, mock_transcription_service):
        orchestrator.process_file(audio_file, "txt", None, "de", False, True)
        _, kwargs = mock_transcription_service.transcribe.call_args
        assert kwargs["language"] == "de"

    def test_diarize_forwarded(self, orchestrator, audio_file, mock_transcription_service):
        orchestrator.process_file(audio_file, "txt", None, "en", True, True)
        _, kwargs = mock_transcription_service.transcribe.call_args
        assert kwargs["diarize"] is True

    def test_smart_format_forwarded(self, orchestrator, audio_file, mock_transcription_service):
        orchestrator.process_file(audio_file, "txt", None, "en", False, False)
        _, kwargs = mock_transcription_service.transcribe.call_args
        assert kwargs["smart_format"] is False
