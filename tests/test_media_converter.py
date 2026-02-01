"""Tests for src/core/media_converter.py"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess
from src.core.media_converter import MediaConverter, PathSecurityError, ConversionError


@pytest.fixture
def converter():
    with patch.object(MediaConverter, "_get_ffmpeg_path", return_value="ffmpeg"):
        with patch.object(MediaConverter, "_get_ffprobe_path", return_value="ffprobe"):
            yield MediaConverter()


class TestValidatePath:
    def test_validate_path_success(self, converter, sample_audio_file):
        result = converter._validate_path(sample_audio_file)
        assert result.is_absolute()

    def test_validate_path_traversal_detected(self, converter, tmp_path):
        suspicious = tmp_path / ".." / ".." / "etc" / "passwd"
        with pytest.raises(PathSecurityError, match="traversal"):
            converter._validate_path(suspicious)

    def test_validate_path_resolves_to_absolute(self, converter, sample_audio_file):
        result = converter._validate_path(sample_audio_file)
        assert result.is_absolute()


class TestToMp3:
    def test_to_mp3_file_not_found(self, converter, tmp_path):
        with pytest.raises(FileNotFoundError):
            converter.to_mp3(tmp_path / "missing.mp4")

    def test_to_mp3_conversion_error_on_nonzero_returncode(self, converter, sample_video_file):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some ffmpeg error"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(ConversionError):
                converter.to_mp3(sample_video_file)


class TestSanitizeErrorMessage:
    def test_sanitize_no_such_file(self, converter):
        r = converter._sanitize_error_message("No such file or directory: /secret/path")
        assert "not found" in r.lower()

    def test_sanitize_invalid_data(self, converter):
        r = converter._sanitize_error_message("Invalid data found when processing")
        assert "corrupted" in r.lower()

    def test_sanitize_unknown_error(self, converter):
        r = converter._sanitize_error_message("xyzzy weird error")
        assert "conversion failed" in r.lower()


class TestCleanup:
    def test_cleanup_nonexistent_file_no_error(self, converter, tmp_path):
        converter.cleanup(tmp_path / "nonexistent.mp3")


class TestGetDuration:
    def test_duration_success(self, converter, sample_audio_file):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12.5"
        with patch("subprocess.run", return_value=mock_result):
            d = converter.get_duration(sample_audio_file)
            assert d == 12.5

    def test_duration_nonexistent(self, converter, tmp_path):
        result = converter.get_duration(tmp_path / "missing.mp3")
        assert result is None

    def test_duration_error_returns_none(self, converter, sample_audio_file):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            assert converter.get_duration(sample_audio_file) is None

    def test_duration_subprocess_error(self, converter, sample_audio_file):
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("err")):
            assert converter.get_duration(sample_audio_file) is None


class TestIsAudioFile:
    def test_audio_only_file(self, converter, sample_audio_file):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            assert converter.is_audio_file(sample_audio_file) is True

    def test_video_file(self, converter, sample_video_file):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "video"
        with patch("subprocess.run", return_value=mock_result):
            assert converter.is_audio_file(sample_video_file) is False

    def test_nonexistent_file(self, converter, tmp_path):
        assert converter.is_audio_file(tmp_path / "missing.mp3") is False

    def test_subprocess_error(self, converter, sample_audio_file):
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("err")):
            assert converter.is_audio_file(sample_audio_file) is False


class TestToMp3Success:
    def test_successful_conversion(self, converter, sample_video_file):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            with patch("src.core.media_converter.TEMP_DIR", sample_video_file.parent):
                # Create fake output file
                import uuid
                with patch("uuid.uuid4") as mock_uuid:
                    mock_uuid.return_value.hex = "abc123"
                    out = sample_video_file.parent / "abc123.mp3"
                    out.write_bytes(b"fake mp3")
                    result = converter.to_mp3(sample_video_file)
                    assert result == out

    def test_subprocess_error_raises(self, converter, sample_video_file):
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("boom")):
            with patch("src.core.media_converter.TEMP_DIR", sample_video_file.parent):
                with pytest.raises(ConversionError):
                    converter.to_mp3(sample_video_file)


class TestFFmpegTimeout:
    def test_ffmpeg_timeout_raises_conversion_error(self, converter, sample_video_file):
        """Bug #2: FFmpeg subprocess should timeout and raise ConversionError."""
        with patch("src.core.media_converter.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=600)):
            with pytest.raises(ConversionError, match="timed out"):
                converter.to_mp3(sample_video_file)


class TestCleanupAll:
    def test_cleanup_all_removes_mp3s(self, converter, tmp_path):
        from src.utils.temp_file_manager import TempFileManager
        converter.temp_manager = TempFileManager(tmp_path)
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f3 = tmp_path / "c.txt"
        f1.write_bytes(b"x")
        f2.write_bytes(b"x")
        f3.write_bytes(b"x")
        converter.cleanup_all()
        assert not f1.exists()
        assert not f2.exists()
        assert f3.exists()

