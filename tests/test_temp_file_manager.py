"""Tests for src/utils/temp_file_manager.py"""
import threading
import pytest
from pathlib import Path
from unittest.mock import patch

from src.utils.temp_file_manager import TempFileManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir(tmp_path):
    """Create a temp directory for the manager."""
    d = tmp_path / "temp"
    d.mkdir()
    return d


@pytest.fixture
def manager(temp_dir):
    """Create a TempFileManager instance."""
    return TempFileManager(temp_dir)


@pytest.fixture
def mp3_file(temp_dir):
    """Create a sample .mp3 file in temp_dir."""
    f = temp_dir / "sample.mp3"
    f.write_bytes(b"fake mp3 data")
    return f


# ---------------------------------------------------------------------------
# __init__ and _ensure_temp_dir
# ---------------------------------------------------------------------------

class TestInit:
    def test_creates_temp_dir_if_missing(self, tmp_path):
        new_dir = tmp_path / "nonexistent" / "deep"
        mgr = TempFileManager(new_dir)
        assert mgr.temp_dir.exists()

    def test_resolves_temp_dir_to_absolute(self, tmp_path):
        mgr = TempFileManager(tmp_path / "sub" / ".." / "sub")
        assert mgr.temp_dir.is_absolute()
        assert ".." not in str(mgr.temp_dir)

    def test_initial_tracked_files_empty(self, manager):
        assert len(manager.tracked_files) == 0


# ---------------------------------------------------------------------------
# track
# ---------------------------------------------------------------------------

class TestTrack:
    def test_track_file(self, manager, mp3_file):
        result = manager.track(mp3_file)
        assert result == mp3_file
        assert mp3_file in manager.tracked_files

    def test_track_returns_path_for_chaining(self, manager, temp_dir):
        p = temp_dir / "chained.mp3"
        assert manager.track(p) == p

    def test_track_same_file_twice(self, manager, mp3_file):
        manager.track(mp3_file)
        manager.track(mp3_file)
        assert len(manager.tracked_files) == 1

    def test_track_multiple_files(self, manager, temp_dir):
        files = [temp_dir / f"file{i}.mp3" for i in range(5)]
        for f in files:
            manager.track(f)
        assert len(manager.tracked_files) == 5

    def test_track_nonexistent_file(self, manager, temp_dir):
        """track() should accept paths even if the file does not exist yet."""
        p = temp_dir / "future.mp3"
        result = manager.track(p)
        assert result == p
        assert p in manager.tracked_files


# ---------------------------------------------------------------------------
# cleanup_file
# ---------------------------------------------------------------------------

class TestCleanupFile:
    def test_cleanup_file_success(self, manager, mp3_file):
        assert manager.cleanup_file(mp3_file) is True
        assert not mp3_file.exists()

    def test_cleanup_file_outside_temp_dir(self, manager, tmp_path):
        """Security: refuse to delete files outside temp_dir."""
        outside = tmp_path / "outside.txt"
        outside.write_text("important data")
        assert manager.cleanup_file(outside) is False
        assert outside.exists()

    def test_cleanup_file_nonexistent(self, manager, temp_dir):
        missing = temp_dir / "ghost.mp3"
        assert manager.cleanup_file(missing) is False

    def test_cleanup_file_removes_from_tracked(self, manager, mp3_file):
        manager.track(mp3_file)
        manager.cleanup_file(mp3_file)
        assert mp3_file not in manager.tracked_files

    def test_cleanup_file_path_traversal_attempt(self, manager, tmp_path):
        """Security: path traversal via '..' should be blocked."""
        parent_file = tmp_path / "secret.txt"
        parent_file.write_text("secret")
        traversal_path = manager.temp_dir / ".." / "secret.txt"
        assert manager.cleanup_file(traversal_path) is False
        assert parent_file.exists()

    def test_cleanup_temp_dir_itself(self, manager):
        """Security: should not delete the temp directory itself."""
        assert manager.cleanup_file(manager.temp_dir) is False

    def test_cleanup_file_permission_error(self, manager, mp3_file, monkeypatch):
        """Graceful handling when unlink raises OSError."""
        def raise_oserror(*a, **kw):
            raise OSError("Permission denied")
        monkeypatch.setattr(Path, "unlink", raise_oserror)
        assert manager.cleanup_file(mp3_file) is False


# ---------------------------------------------------------------------------
# cleanup_pattern
# ---------------------------------------------------------------------------

class TestCleanupPattern:
    def test_cleanup_pattern_mp3(self, manager, temp_dir):
        for i in range(3):
            (temp_dir / f"file{i}.mp3").write_bytes(b"data")
        (temp_dir / "keep.txt").write_text("keep")

        count = manager.cleanup_pattern("*.mp3")
        assert count == 3
        assert (temp_dir / "keep.txt").exists()

    def test_cleanup_pattern_no_matches(self, manager, temp_dir):
        (temp_dir / "file.txt").write_text("data")
        assert manager.cleanup_pattern("*.wav") == 0

    def test_cleanup_pattern_empty_dir(self, manager):
        assert manager.cleanup_pattern("*.mp3") == 0

    def test_cleanup_pattern_removes_from_tracked(self, manager, temp_dir):
        f = temp_dir / "tracked.mp3"
        f.write_bytes(b"data")
        manager.track(f)
        manager.cleanup_pattern("*.mp3")
        assert f not in manager.tracked_files

    def test_cleanup_pattern_star(self, manager, temp_dir):
        """Pattern '*' should match all files."""
        (temp_dir / "a.mp3").write_bytes(b"a")
        (temp_dir / "b.txt").write_text("b")
        count = manager.cleanup_pattern("*")
        assert count == 2


# ---------------------------------------------------------------------------
# cleanup_tracked
# ---------------------------------------------------------------------------

class TestCleanupTracked:
    def test_cleanup_tracked_all(self, manager, temp_dir):
        files = []
        for i in range(4):
            f = temp_dir / f"t{i}.mp3"
            f.write_bytes(b"data")
            manager.track(f)
            files.append(f)

        count = manager.cleanup_tracked()
        assert count == 4
        for f in files:
            assert not f.exists()
        assert len(manager.tracked_files) == 0

    def test_cleanup_tracked_some_missing(self, manager, temp_dir):
        existing = temp_dir / "exists.mp3"
        existing.write_bytes(b"data")
        manager.track(existing)
        manager.track(temp_dir / "ghost.mp3")  # does not exist

        count = manager.cleanup_tracked()
        assert count == 1
        assert not existing.exists()

    def test_cleanup_tracked_empty(self, manager):
        assert manager.cleanup_tracked() == 0


# ---------------------------------------------------------------------------
# cleanup_all
# ---------------------------------------------------------------------------

class TestCleanupAll:
    def test_cleanup_all_files(self, manager, temp_dir):
        for i in range(5):
            (temp_dir / f"f{i}.mp3").write_bytes(b"data")
        count = manager.cleanup_all()
        assert count == 5
        assert list(temp_dir.iterdir()) == []

    def test_cleanup_all_empty_dir(self, manager):
        assert manager.cleanup_all() == 0

    def test_cleanup_all_clears_tracked(self, manager, temp_dir):
        f = temp_dir / "x.mp3"
        f.write_bytes(b"data")
        manager.track(f)
        manager.cleanup_all()
        assert len(manager.tracked_files) == 0

    def test_cleanup_all_skips_subdirectories(self, manager, temp_dir):
        sub = temp_dir / "subdir"
        sub.mkdir()
        (sub / "nested.mp3").write_bytes(b"data")
        (temp_dir / "root.mp3").write_bytes(b"data")

        count = manager.cleanup_all()
        assert count == 1  # only root.mp3, not subdir
        assert sub.exists()


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_track(self, manager, temp_dir):
        """Multiple threads tracking files concurrently should not corrupt state."""
        errors = []

        def track_files(start):
            try:
                for i in range(50):
                    manager.track(temp_dir / f"thread_{start}_{i}.mp3")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=track_files, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(manager.tracked_files) == 200

    def test_concurrent_cleanup_tracked(self, manager, temp_dir):
        """Concurrent cleanup_tracked calls should not raise."""
        for i in range(20):
            f = temp_dir / f"cc{i}.mp3"
            f.write_bytes(b"data")
            manager.track(f)

        errors = []

        def do_cleanup():
            try:
                manager.cleanup_tracked()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_cleanup) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors


# ---------------------------------------------------------------------------
# _is_under_temp_dir edge cases
# ---------------------------------------------------------------------------

class TestIsUnderTempDir:
    def test_file_directly_in_temp_dir(self, manager, mp3_file):
        assert manager._is_under_temp_dir(mp3_file) is True

    def test_file_in_subdirectory(self, manager, temp_dir):
        sub = temp_dir / "sub"
        sub.mkdir()
        f = sub / "deep.mp3"
        f.write_bytes(b"data")
        assert manager._is_under_temp_dir(f) is True

    def test_temp_dir_itself(self, manager):
        assert manager._is_under_temp_dir(manager.temp_dir) is False

    def test_parent_of_temp_dir(self, manager):
        assert manager._is_under_temp_dir(manager.temp_dir.parent) is False
