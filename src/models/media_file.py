"""
Data model for media files.
"""
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from typing import Optional

from config import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS


class MediaType(Enum):
    AUDIO = "audio"
    VIDEO = "video"


class ErrorCategory(Enum):
    """Category of error for retry logic."""
    NONE = "none"
    RETRYABLE_NETWORK = "retryable_network"      # Timeout, connection errors
    RETRYABLE_RATE_LIMIT = "retryable_rate_limit"  # 429 - needs delay
    RETRYABLE_SERVER = "retryable_server"        # 5xx errors
    NON_RETRYABLE_AUTH = "non_retryable_auth"    # 401, 403
    NON_RETRYABLE_FILE = "non_retryable_file"    # File not found, too large
    NON_RETRYABLE_CONFIG = "non_retryable_config"  # FFmpeg missing
    NON_RETRYABLE_CONVERSION = "non_retryable_conversion"  # Corrupted file


class TranscriptionStatus(Enum):
    PENDING = "pending"
    CONVERTING = "converting"
    TRANSCRIBING = "transcribing"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class MediaFile:
    """Represents a media file for transcription."""

    path: Path
    selected: bool = False
    status: TranscriptionStatus = TranscriptionStatus.PENDING
    error_message: Optional[str] = None
    output_path: Optional[Path] = None
    retry_count: int = 0
    error_category: ErrorCategory = ErrorCategory.NONE

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            self.path = Path(self.path)

    @property
    def name(self) -> str:
        """File name without path."""
        return self.path.name

    @property
    def stem(self) -> str:
        """File name without extension."""
        return self.path.stem

    @property
    def extension(self) -> str:
        """File extension (lowercase with dot)."""
        return self.path.suffix.lower()

    @property
    def media_type(self) -> MediaType:
        """Determine if file is audio or video."""
        if self.extension in AUDIO_EXTENSIONS:
            return MediaType.AUDIO
        return MediaType.VIDEO

    @property
    def is_video(self) -> bool:
        """Check if file is a video."""
        return self.extension in VIDEO_EXTENSIONS

    @property
    def is_audio(self) -> bool:
        """Check if file is an audio file."""
        return self.extension in AUDIO_EXTENSIONS

    @property
    def size_bytes(self) -> int:
        """File size in bytes."""
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    @property
    def size_mb(self) -> float:
        """File size in megabytes."""
        return self.size_bytes / (1024 * 1024)

    @property
    def size_formatted(self) -> str:
        """Human-readable file size."""
        size: float = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def parent_dir(self) -> Path:
        """Parent directory of the file."""
        return self.path.parent

    @property
    def exists(self) -> bool:
        """Check if file exists."""
        return self.path.exists()

    def __str__(self) -> str:
        return f"{self.name} ({self.size_formatted})"

    def __hash__(self) -> int:
        return hash(self.path)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MediaFile):
            return self.path == other.path
        return False


@dataclass
class DirectoryNode:
    """Represents a directory in the file tree."""

    path: Path
    name: str
    files: list[MediaFile] = field(default_factory=list)
    subdirs: list["DirectoryNode"] = field(default_factory=list)
    expanded: bool = True
    selected: bool = False

    @property
    def total_files(self) -> int:
        """Total number of files in this directory and subdirectories."""
        count = len(self.files)
        for subdir in self.subdirs:
            count += subdir.total_files
        return count

    @property
    def selected_files(self) -> int:
        """Number of selected files in this directory and subdirectories."""
        count = sum(1 for f in self.files if f.selected)
        for subdir in self.subdirs:
            count += subdir.selected_files
        return count

    @property
    def total_size_bytes(self) -> int:
        """Total size of files in bytes."""
        size = sum(f.size_bytes for f in self.files)
        for subdir in self.subdirs:
            size += subdir.total_size_bytes
        return size

    def get_all_files(self) -> list[MediaFile]:
        """Get all files recursively."""
        all_files = list(self.files)
        for subdir in self.subdirs:
            all_files.extend(subdir.get_all_files())
        return all_files

    def get_selected_files(self) -> list[MediaFile]:
        """Get all selected files recursively."""
        selected = [f for f in self.files if f.selected]
        for subdir in self.subdirs:
            selected.extend(subdir.get_selected_files())
        return selected

    def select_all(self, selected: bool = True) -> None:
        """Select or deselect all files in this directory and subdirectories."""
        self.selected = selected
        for f in self.files:
            f.selected = selected
        for subdir in self.subdirs:
            subdir.select_all(selected)

    def select_children(self, selected: bool) -> None:
        """Select or deselect all children (files and subdirs) of this directory.

        Used when folder checkbox is toggled to propagate to all contents.
        """
        for f in self.files:
            f.selected = selected
        for subdir in self.subdirs:
            subdir.selected = selected
            subdir.select_children(selected)
