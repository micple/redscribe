"""
File system scanner for media files.
"""
from pathlib import Path
from typing import Optional

from config import ALL_MEDIA_EXTENSIONS
from src.models.media_file import MediaFile, DirectoryNode


class FileScanner:
    """Scans directories for audio and video files."""

    def __init__(self, extensions: set[str] | None = None):
        """
        Initialize scanner.

        Args:
            extensions: Set of file extensions to scan for.
                       Defaults to all supported media extensions.
        """
        self.extensions = extensions or ALL_MEDIA_EXTENSIONS

    def is_media_file(self, path: Path) -> bool:
        """Check if a file is a supported media file."""
        return path.suffix.lower() in self.extensions

    def scan_directory(
        self,
        directory: Path,
        recursive: bool = False,
    ) -> DirectoryNode:
        """
        Scan a directory for media files.

        Args:
            directory: Path to the directory to scan
            recursive: If True, also scan subdirectories

        Returns:
            DirectoryNode containing the directory structure
        """
        directory = Path(directory)

        if not directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")

        if not directory.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {directory}")

        return self._scan_node(directory, recursive)

    def _scan_node(self, directory: Path, recursive: bool) -> DirectoryNode:
        """Recursively scan a directory node."""
        node = DirectoryNode(
            path=directory,
            name=directory.name or str(directory),
            files=[],
            subdirs=[],
        )

        try:
            entries = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return node

        for entry in entries:
            if entry.is_file() and self.is_media_file(entry):
                node.files.append(MediaFile(path=entry))
            elif entry.is_dir() and recursive:
                # Skip hidden directories
                if not entry.name.startswith('.'):
                    subnode = self._scan_node(entry, recursive)
                    # Only add if it contains media files
                    if subnode.total_files > 0:
                        node.subdirs.append(subnode)

        return node

    def scan_files(
        self,
        directory: Path,
        recursive: bool = False,
    ) -> list[MediaFile]:
        """
        Scan directory and return flat list of media files.

        Args:
            directory: Path to the directory to scan
            recursive: If True, also scan subdirectories

        Returns:
            List of MediaFile objects
        """
        directory = Path(directory)

        if not directory.exists():
            return []

        files = []
        pattern = "**/*" if recursive else "*"

        for path in directory.glob(pattern):
            if path.is_file() and self.is_media_file(path):
                files.append(MediaFile(path=path))

        return sorted(files, key=lambda f: f.path)

    def get_directory_stats(self, node: DirectoryNode) -> dict:
        """
        Get statistics about scanned directory.

        Returns:
            Dictionary with file counts and sizes
        """
        all_files = node.get_all_files()
        selected_files = node.get_selected_files()

        audio_count = sum(1 for f in all_files if f.is_audio)
        video_count = sum(1 for f in all_files if f.is_video)

        return {
            "total_files": len(all_files),
            "selected_files": len(selected_files),
            "audio_files": audio_count,
            "video_files": video_count,
            "total_size_bytes": sum(f.size_bytes for f in all_files),
            "selected_size_bytes": sum(f.size_bytes for f in selected_files),
        }

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format size in bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
