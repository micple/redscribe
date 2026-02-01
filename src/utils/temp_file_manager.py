"""
Centralized temporary file management.

Replaces duplicate cleanup methods across MediaConverter, YouTubeDownloader,
MainWindow, and YouTubeTab with a single, tested, thread-safe class.

Security features:
- Path traversal prevention (cleanup_file refuses paths outside temp_dir)
- Thread-safe tracked file set (protected by threading.Lock)
"""
import logging
import threading
from pathlib import Path
from typing import Set

logger = logging.getLogger(__name__)


class TempFileManager:
    """
    Manages temporary files within a designated directory.

    Provides tracking, pattern-based cleanup, and security checks to ensure
    files outside the temp directory are never deleted.

    Usage:
        manager = TempFileManager(Path("/tmp/myapp"))
        path = manager.track(some_file_path)
        manager.cleanup_file(path)
        manager.cleanup_pattern("*.mp3")
        manager.cleanup_tracked()
        manager.cleanup_all()
    """

    def __init__(self, temp_dir: Path) -> None:
        """
        Initialize the temp file manager.

        Args:
            temp_dir: Root directory for temporary files. All cleanup operations
                      are restricted to this directory for security.
        """
        self.temp_dir = Path(temp_dir).resolve()
        self.tracked_files: Set[Path] = set()
        self._lock = threading.Lock()
        self._ensure_temp_dir()

    def _ensure_temp_dir(self) -> None:
        """Create the temp directory if it does not exist."""
        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Could not create temp directory %s: %s", self.temp_dir, e)

    def _is_under_temp_dir(self, file_path: Path) -> bool:
        """
        Check whether a file path resides under the managed temp directory.

        Uses resolved (absolute) paths to prevent path traversal attacks.

        Args:
            file_path: The path to validate.

        Returns:
            True if the file is under temp_dir, False otherwise.
        """
        try:
            resolved = Path(file_path).resolve()
            return resolved != self.temp_dir and (
                self.temp_dir == resolved.parent or self.temp_dir in resolved.parents
            )
        except (OSError, ValueError):
            return False

    def track(self, file_path: Path) -> Path:
        """
        Add a file to the tracked set.

        Args:
            file_path: Path to the file to track.

        Returns:
            The same path, for convenient chaining.
        """
        file_path = Path(file_path)
        with self._lock:
            self.tracked_files.add(file_path)
        logger.debug("Tracking temp file: %s", file_path)
        return file_path

    def cleanup_file(self, file_path: Path) -> bool:
        """
        Remove a specific file if it is under the managed temp directory.

        Security: refuses to delete files outside temp_dir to prevent
        accidental or malicious deletion of arbitrary files.

        Args:
            file_path: Path to the file to remove.

        Returns:
            True if the file was successfully removed, False otherwise.
        """
        file_path = Path(file_path)

        if not self._is_under_temp_dir(file_path):
            logger.warning("Refusing to cleanup file outside temp dir: %s", file_path)
            return False

        try:
            if file_path.exists():
                file_path.unlink()
                with self._lock:
                    self.tracked_files.discard(file_path)
                logger.debug("Cleaned up file: %s", file_path)
                return True
            else:
                with self._lock:
                    self.tracked_files.discard(file_path)
                logger.debug("File already gone: %s", file_path)
                return False
        except OSError as e:
            logger.debug("Could not cleanup file %s: %s", file_path, e)
            return False

    def cleanup_pattern(self, pattern: str = "*.mp3") -> int:
        """
        Remove all files in temp_dir matching a glob pattern.

        Args:
            pattern: Glob pattern to match (e.g. "*.mp3", "*.wav").

        Returns:
            Number of files successfully removed.
        """
        count = 0
        try:
            if not self.temp_dir.exists():
                return 0
            for file_path in self.temp_dir.glob(pattern):
                try:
                    if file_path.is_file():
                        file_path.unlink()
                        with self._lock:
                            self.tracked_files.discard(file_path)
                        count += 1
                except OSError:
                    pass
        except OSError:
            pass
        logger.debug("Cleaned up %d files matching pattern '%s' in %s", count, pattern, self.temp_dir)
        return count

    def cleanup_tracked(self) -> int:
        """
        Remove all tracked files.

        Returns:
            Number of files successfully removed.
        """
        count = 0
        with self._lock:
            files_to_clean = set(self.tracked_files)

        for file_path in files_to_clean:
            try:
                if file_path.exists():
                    file_path.unlink()
                    count += 1
            except OSError:
                pass

        with self._lock:
            self.tracked_files -= files_to_clean
        logger.debug("Cleaned up %d tracked files", count)
        return count

    def cleanup_all(self) -> int:
        """
        Remove ALL files in the temp directory.

        Use with caution -- this is the nuclear option that deletes every
        file directly inside temp_dir (non-recursive).

        Returns:
            Number of files successfully removed.
        """
        count = 0
        try:
            if not self.temp_dir.exists():
                return 0
            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    try:
                        file_path.unlink()
                        count += 1
                    except OSError:
                        pass
        except OSError:
            pass

        with self._lock:
            self.tracked_files.clear()
        logger.debug("Cleaned up all %d files in %s", count, self.temp_dir)
        return count
