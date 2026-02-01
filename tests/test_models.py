import pytest
from pathlib import Path
from src.models.media_file import MediaFile, MediaType, ErrorCategory, TranscriptionStatus, DirectoryNode

class TestMediaFileCreation:
    def test_create_from_path(self, tmp_path):
        mp3 = tmp_path / "test.mp3"; mp3.write_bytes(b"fake")
        mf = MediaFile(path=mp3)
        assert mf.name == "test.mp3"
        assert mf.stem == "test"

    def test_create_from_string(self, tmp_path):
        mp3 = tmp_path / "test.mp3"; mp3.write_bytes(b"fake")
        mf = MediaFile(path=str(mp3))
        assert isinstance(mf.path, Path)

    def test_default_status_pending(self):
        mf = MediaFile(path=Path("test.mp3"))
        assert mf.status == TranscriptionStatus.PENDING

    def test_default_selected_false(self):
        mf = MediaFile(path=Path("test.mp3"))
        assert mf.selected is False

class TestIsAudio:
    @pytest.mark.parametrize("ext,expected", [
        (".mp3", True), (".wav", True), (".flac", True), (".m4a", True),
        (".mp4", False), (".avi", False), (".mkv", False),
    ])
    def test_is_audio(self, ext, expected):
        assert MediaFile(path=Path(f"test{ext}")).is_audio == expected

class TestIsVideo:
    @pytest.mark.parametrize("ext,expected", [
        (".mp4", True), (".avi", True), (".mkv", True),
        (".mp3", False), (".wav", False),
    ])
    def test_is_video(self, ext, expected):
        assert MediaFile(path=Path(f"test{ext}")).is_video == expected

class TestMediaType:
    def test_audio_type(self):
        assert MediaFile(path=Path("t.mp3")).media_type == MediaType.AUDIO
    def test_video_type(self):
        assert MediaFile(path=Path("t.mp4")).media_type == MediaType.VIDEO

class TestSize:
    def test_size_bytes(self, tmp_path):
        f = tmp_path / "t.mp3"; f.write_bytes(b"x" * 2048)
        assert MediaFile(path=f).size_bytes == 2048
    def test_size_nonexistent(self):
        assert MediaFile(path=Path("/nonexistent/t.mp3")).size_bytes == 0
    def test_size_mb(self, tmp_path):
        f = tmp_path / "t.mp3"; f.write_bytes(b"x" * (1024*1024))
        assert MediaFile(path=f).size_mb == pytest.approx(1.0)

class TestEquality:
    def test_equal(self):
        p = Path("t.mp3")
        assert MediaFile(path=p) == MediaFile(path=p)
    def test_not_equal(self):
        assert MediaFile(path=Path("a.mp3")) != MediaFile(path=Path("b.mp3"))
    def test_hash(self):
        p = Path("t.mp3")
        assert hash(MediaFile(path=p)) == hash(MediaFile(path=p))

class TestDirectoryNode:
    def test_total_files(self, tmp_path):
        f1 = tmp_path / "a.mp3"; f1.write_bytes(b"x")
        f2 = tmp_path / "b.mp3"; f2.write_bytes(b"x")
        node = DirectoryNode(path=tmp_path, name="test", files=[MediaFile(path=f1), MediaFile(path=f2)])
        assert node.total_files == 2

    def test_select_all(self, tmp_path):
        f1 = tmp_path / "a.mp3"; f1.write_bytes(b"x")
        mf = MediaFile(path=f1)
        node = DirectoryNode(path=tmp_path, name="test", files=[mf])
        node.select_all(True)
        assert mf.selected is True

    def test_get_selected(self, tmp_path):
        f1 = tmp_path / "a.mp3"; f1.write_bytes(b"x")
        mf1 = MediaFile(path=f1, selected=True)
        mf2 = MediaFile(path=f1, selected=False)
        node = DirectoryNode(path=tmp_path, name="test", files=[mf1, mf2])
        assert len(node.get_selected_files()) == 1
