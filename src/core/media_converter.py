"""
Media file converter using FFmpeg.

Security features:
- Path traversal validation
- Secure temporary file handling
"""
import subprocess
import shutil
import uuid
import os
import stat
import sys
from pathlib import Path
from typing import Optional, Callable

from config import (
    TEMP_DIR,
    FFMPEG_AUDIO_CODEC,
    FFMPEG_SAMPLE_RATE,
    FFMPEG_CHANNELS,
    FFMPEG_BITRATE,
    FFMPEG_CONVERSION_TIMEOUT,
)
from src.utils.temp_file_manager import TempFileManager


class FFmpegNotFoundError(Exception):
    """Raised when FFmpeg is not installed or not in PATH."""
    pass


class ConversionError(Exception):
    """Raised when media conversion fails."""
    pass


class PathSecurityError(Exception):
    """Raised when path validation fails."""
    pass


class MediaConverter:
    """Converts video files to MP3 for transcription."""

    def __init__(self):
        self._ffmpeg_path = self._get_ffmpeg_path()
        self._ffprobe_path = self._get_ffprobe_path()
        self.temp_manager = TempFileManager(TEMP_DIR)

    def _get_base_path(self) -> Path:
        """Get base path for bundled executables."""
        if getattr(sys, 'frozen', False):
            # Running as compiled exe (PyInstaller)
            return Path(sys.executable).parent
        else:
            # Running as script - go up from src/core to project root
            return Path(__file__).parent.parent.parent

    def _get_ffmpeg_path(self) -> str:
        """Get FFmpeg executable path - bundled first, then system PATH."""
        base_path = self._get_base_path()

        # Check bundled FFmpeg first
        bundled_ffmpeg = base_path / "ffmpeg" / "ffmpeg.exe"
        if bundled_ffmpeg.exists():
            return str(bundled_ffmpeg)

        # Fallback to system PATH
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg

        raise FFmpegNotFoundError(
            "FFmpeg not found. "
            "Please reinstall the application or install FFmpeg.\n"
            "Download from: https://ffmpeg.org/download.html"
        )

    def _get_ffprobe_path(self) -> str:
        """Get FFprobe executable path - bundled first, then system PATH."""
        base_path = self._get_base_path()

        # Check bundled FFprobe first
        bundled_ffprobe = base_path / "ffmpeg" / "ffprobe.exe"
        if bundled_ffprobe.exists():
            return str(bundled_ffprobe)

        # Fallback to system PATH
        system_ffprobe = shutil.which("ffprobe")
        if system_ffprobe:
            return system_ffprobe

        return "ffprobe"  # Last resort - let subprocess handle the error

    def _validate_path(self, input_path: Path) -> Path:
        """
        Validate input path for security issues.

        Checks for:
        - Path traversal attempts (../)
        - Symbolic link attacks
        - Absolute path resolution

        Returns:
            Resolved absolute path

        Raises:
            PathSecurityError: If path validation fails
        """
        try:
            # Convert to Path and resolve to absolute
            path = Path(input_path).resolve()

            # Check if original path contains suspicious patterns
            path_str = str(input_path)
            if '..' in path_str:
                raise PathSecurityError(
                    f"Path traversal detected in: {input_path}"
                )

            # On Unix, check if it's a symlink pointing outside expected areas
            if os.name != 'nt' and path.is_symlink():
                # Resolve symlink and verify it points to a real file
                real_path = path.resolve()
                if not real_path.exists():
                    raise PathSecurityError(
                        f"Symbolic link points to non-existent file: {input_path}"
                    )

            return path

        except (OSError, ValueError) as e:
            raise PathSecurityError(f"Invalid path: {input_path} - {e}")

    def _set_temp_file_permissions(self, file_path: Path) -> None:
        """Set restrictive permissions on temporary files."""
        try:
            if os.name != 'nt':  # Unix/Linux/macOS
                os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass  # Don't fail on permission errors

    def _sanitize_error_message(self, error_msg: str) -> str:
        """
        Sanitize FFmpeg error messages to prevent exposing system paths.

        Returns user-friendly error messages without sensitive details.
        """
        # Map common FFmpeg errors to user-friendly messages
        error_mappings = [
            ("No such file or directory", "Input file not found"),
            ("Invalid data found", "Invalid or corrupted file format"),
            ("does not contain any stream", "File does not contain audio"),
            ("Permission denied", "Cannot access file - permission denied"),
            ("Invalid argument", "Invalid file or unsupported format"),
            ("End of file", "File appears to be incomplete or corrupted"),
            ("could not find codec", "Unsupported audio codec"),
            ("Discarding buffer", "File encoding issue detected"),
        ]

        for pattern, friendly_msg in error_mappings:
            if pattern.lower() in error_msg.lower():
                return friendly_msg

        # Generic fallback - don't expose raw FFmpeg output
        return "Media conversion failed - file may be corrupted or unsupported"

    def to_mp3(
        self,
        input_path: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Path:
        """
        Convert a video/audio file to MP3 format optimized for transcription.

        Args:
            input_path: Path to the input media file
            progress_callback: Optional callback for progress updates

        Returns:
            Path to the temporary MP3 file

        Raises:
            FileNotFoundError: If input file doesn't exist
            PathSecurityError: If path validation fails
            ConversionError: If FFmpeg conversion fails
        """
        # Validate and resolve input path (security check)
        input_path = self._validate_path(input_path)

        if not input_path.exists():
            raise FileNotFoundError(f"File does not exist: {input_path}")

        # Create unique temp file name
        temp_filename = f"{uuid.uuid4().hex}.mp3"
        output_path = TEMP_DIR / temp_filename

        # Ensure temp directory exists
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(f"Converting: {input_path.name}")

        # Build FFmpeg command
        cmd = [
            self._ffmpeg_path,
            "-i", str(input_path),
            "-vn",  # No video
            "-acodec", FFMPEG_AUDIO_CODEC,
            "-ar", str(FFMPEG_SAMPLE_RATE),
            "-ac", str(FFMPEG_CHANNELS),
            "-b:a", FFMPEG_BITRATE,
            "-y",  # Overwrite output
            str(output_path),
        ]

        try:
            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=FFMPEG_CONVERSION_TIMEOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )

            if result.returncode != 0:
                error_msg = result.stderr or "Unknown FFmpeg error"
                # Sanitize error message - don't expose system paths
                error_msg = self._sanitize_error_message(error_msg)
                raise ConversionError(f"Conversion error: {error_msg}")

            if not output_path.exists():
                raise ConversionError("Output file was not created")

            # Set restrictive permissions on temp file
            self._set_temp_file_permissions(output_path)

            if progress_callback:
                progress_callback(f"Conversion complete: {input_path.name}")

            return self.temp_manager.track(output_path)

        except subprocess.TimeoutExpired:
            raise ConversionError(
                f"FFmpeg conversion timed out after {FFMPEG_CONVERSION_TIMEOUT} seconds: {input_path.name}"
            )
        except subprocess.SubprocessError as e:
            raise ConversionError(f"FFmpeg execution error: {str(e)}")

    def cleanup(self, temp_path: Path) -> None:
        """
        Remove a temporary file.

        Args:
            temp_path: Path to the temporary file to remove
        """
        self.temp_manager.cleanup_file(Path(temp_path))

    def cleanup_all(self) -> None:
        """Remove all temporary files created by this converter."""
        self.temp_manager.cleanup_pattern("*.mp3")

    def get_duration(self, input_path: Path) -> Optional[float]:
        """
        Get the duration of a media file in seconds.

        Args:
            input_path: Path to the media file

        Returns:
            Duration in seconds, or None if unable to determine
        """
        input_path = Path(input_path)

        if not input_path.exists():
            return None

        cmd = [
            self._ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )

            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())

        except (subprocess.SubprocessError, ValueError):
            pass

        return None

    def is_audio_file(self, input_path: Path) -> bool:
        """
        Check if file contains only audio (no video stream).

        Args:
            input_path: Path to the media file

        Returns:
            True if file is audio-only
        """
        input_path = Path(input_path)

        if not input_path.exists():
            return False

        cmd = [
            self._ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )

            # If no video stream found, it's audio-only
            return result.returncode == 0 and not result.stdout.strip()

        except subprocess.SubprocessError:
            pass

        return False
