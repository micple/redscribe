import pytest
from pathlib import Path
from src.core.file_scanner import FileScanner
from src.models.media_file import MediaFile

@pytest.fixture
def scanner():
    return FileScanner()

@pytest.fixture
def media_dir(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"fake")
    (tmp_path / "audio.wav").write_bytes(b"fake")
    (tmp_path / "music.flac").write_bytes(b"fake")
    (tmp_path / "video.mp4").write_bytes(b"fake")
    (tmp_path / "movie.avi").write_bytes(b"fake")
    (tmp_path / "readme.txt").write_bytes(b"txt")
    (tmp_path / "data.json").write_bytes(b"{}")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.mp3").write_bytes(b"fake")
    (sub / "nested.txt").write_bytes(b"txt")
    return tmp_path

class TestIsMediaFile:
    def test_mp3_is_media(self, scanner):
        assert scanner.is_media_file(Path("test.mp3")) is True
    def test_wav_is_media(self, scanner):
        assert scanner.is_media_file(Path("test.wav")) is True
    def test_mp4_is_media(self, scanner):
        assert scanner.is_media_file(Path("test.mp4")) is True
    def test_txt_is_not_media(self, scanner):
        assert scanner.is_media_file(Path("test.txt")) is False

class TestScanDirectory:
    def test_scan_finds_audio_files(self, scanner, media_dir):
        node = scanner.scan_directory(media_dir, recursive=False)
        names = [f.name for f in node.files]
        assert "song.mp3" in names
        assert "audio.wav" in names

    def test_scan_finds_video_files(self, scanner, media_dir):
        node = scanner.scan_directory(media_dir, recursive=False)
        names = [f.name for f in node.files]
        assert "video.mp4" in names

    def test_scan_ignores_non_media(self, scanner, media_dir):
        node = scanner.scan_directory(media_dir, recursive=False)
        names = [f.name for f in node.files]
        assert "readme.txt" not in names

    def test_scan_non_recursive_skips_subdirs(self, scanner, media_dir):
        node = scanner.scan_directory(media_dir, recursive=False)
        assert len(node.subdirs) == 0

    def test_scan_recursive_includes_subdirs(self, scanner, media_dir):
        node = scanner.scan_directory(media_dir, recursive=True)
        all_files = node.get_all_files()
        names = [f.name for f in all_files]
        assert "nested.mp3" in names

    def test_scan_nonexistent_raises(self, scanner, tmp_path):
        with pytest.raises(FileNotFoundError):
            scanner.scan_directory(tmp_path / "nonexistent")

class TestScanFiles:
    def test_scan_files_flat_list(self, scanner, media_dir):
        files = scanner.scan_files(media_dir, recursive=False)
        assert isinstance(files, list)
        assert len(files) == 5

    def test_scan_files_recursive(self, scanner, media_dir):
        files = scanner.scan_files(media_dir, recursive=True)
        names = [f.name for f in files]
        assert "nested.mp3" in names

    def test_scan_files_empty_dir(self, scanner, tmp_path):
        assert scanner.scan_files(tmp_path) == []

class TestSymlinkLoopDetection:
    """Bug #5: Symlink loops should not cause infinite recursion."""

    def test_symlink_loop_does_not_recurse_infinitely(self, scanner, tmp_path):
        """Create A -> B -> A symlink loop and verify no infinite loop."""
        import os
        dir_a = tmp_path / "dir_a"
        dir_a.mkdir()
        (dir_a / "test.mp3").write_bytes(b"fake")

        # Create symlink loop: dir_a/link_b -> dir_a (self-referencing)
        link_path = dir_a / "link_back"
        try:
            os.symlink(str(dir_a), str(link_path))
        except OSError:
            pytest.skip("Cannot create symlinks (requires elevated privileges on Windows)")

        # Should not hang - symlink loop is detected
        result = scanner.scan_directory(dir_a, recursive=True)
        assert result is not None
        assert result.total_files >= 1


class TestFormatSize:
    def test_bytes(self):
        assert FileScanner.format_size(500) == "500.0 B"
    def test_kilobytes(self):
        assert FileScanner.format_size(1024) == "1.0 KB"
    def test_megabytes(self):
        assert FileScanner.format_size(1024*1024) == "1.0 MB"
