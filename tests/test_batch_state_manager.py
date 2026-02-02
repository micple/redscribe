"""Tests for src/utils/batch_state_manager.py"""
import pytest
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

from src.utils.batch_state_manager import BatchStateManager
from contracts.batch_state import (
    BatchState, BatchSettings, FileState, BatchStatistics,
    TranscriptionStatusEnum
)


@pytest.fixture
def state_file_path(tmp_path, monkeypatch):
    """Override BatchStateManager.STATE_FILE to use tmp_path."""
    state_file = tmp_path / "batch_state.json"
    monkeypatch.setattr(BatchStateManager, "STATE_FILE", state_file)
    return state_file


@pytest.fixture
def sample_batch_state():
    """Create a sample BatchState for testing."""
    settings = BatchSettings(
        output_format="txt",
        output_dir=None,
        language="en",
        diarize=False,
        smart_format=True,
        max_concurrent_workers=3
    )

    files = [
        FileState(
            source_path="/path/to/audio1.mp3",
            status=TranscriptionStatusEnum.PENDING
        ),
        FileState(
            source_path="/path/to/audio2.mp3",
            status=TranscriptionStatusEnum.PENDING
        ),
        FileState(
            source_path="/path/to/audio3.mp3",
            status=TranscriptionStatusEnum.COMPLETED,
            output_path="/path/to/audio3.txt",
            duration_seconds=120.5,
            completed_at=datetime.now()
        )
    ]

    statistics = BatchStatistics(
        total_files=3,
        completed=1,
        failed=0,
        pending=2,
        total_duration_seconds=120.5
    )

    return BatchState(
        batch_id="test-batch-123",
        created_at=datetime.now(),
        last_updated=datetime.now(),
        settings=settings,
        files=files,
        statistics=statistics
    )


class TestSaveAndLoadBatchState:
    """Test save/load round-trip operations."""

    def test_save_and_load_batch_state(self, state_file_path, sample_batch_state):
        """Test that saved state can be loaded back correctly."""
        # Arrange & Act
        BatchStateManager.save_batch_state(sample_batch_state)
        loaded_state = BatchStateManager.load_batch_state()

        # Assert
        assert loaded_state is not None
        assert loaded_state.batch_id == sample_batch_state.batch_id
        assert len(loaded_state.files) == 3
        assert loaded_state.statistics.total_files == 3
        assert loaded_state.statistics.completed == 1
        assert loaded_state.statistics.pending == 2
        assert loaded_state.settings.output_format == "txt"

    def test_load_nonexistent_file(self, state_file_path):
        """Test that loading nonexistent file returns None."""
        # Act
        result = BatchStateManager.load_batch_state()

        # Assert
        assert result is None

    def test_atomic_write_creates_file(self, state_file_path, sample_batch_state):
        """Test that atomic write creates the state file."""
        # Act
        BatchStateManager.save_batch_state(sample_batch_state)

        # Assert
        assert state_file_path.exists()
        assert state_file_path.stat().st_size > 0


class TestPendingBatchDetection:
    """Test has_pending_batch method."""

    def test_has_pending_batch_true(self, state_file_path, sample_batch_state):
        """Test that state file existence is detected."""
        # Arrange
        BatchStateManager.save_batch_state(sample_batch_state)

        # Act
        result = BatchStateManager.has_pending_batch()

        # Assert
        assert result is True

    def test_has_pending_batch_false(self, state_file_path):
        """Test that no state file is correctly detected."""
        # Act
        result = BatchStateManager.has_pending_batch()

        # Assert
        assert result is False


class TestCorruptedFileHandling:
    """Test handling of corrupted JSON files."""

    def test_corrupted_file_handling(self, state_file_path):
        """Test that corrupted JSON returns None and creates backup."""
        # Arrange - write garbage JSON
        state_file_path.parent.mkdir(parents=True, exist_ok=True)
        state_file_path.write_text("{ invalid json garbage }")

        # Act
        result = BatchStateManager.load_batch_state()

        # Assert
        assert result is None

        # Check backup was created
        backup_files = list(state_file_path.parent.glob("*.corrupted_*"))
        assert len(backup_files) > 0

    def test_invalid_structure_creates_backup(self, state_file_path):
        """Test that invalid Pydantic structure returns None and creates backup."""
        # Arrange - valid JSON but invalid structure
        state_file_path.parent.mkdir(parents=True, exist_ok=True)
        state_file_path.write_text(json.dumps({"batch_id": "test", "invalid_field": "value"}))

        # Act
        result = BatchStateManager.load_batch_state()

        # Assert
        assert result is None

        # Check backup was created
        backup_files = list(state_file_path.parent.glob("*.corrupted_*"))
        assert len(backup_files) > 0


class TestFileStatusUpdates:
    """Test updating file status in batch."""

    def test_update_file_status_completed(self, state_file_path, sample_batch_state):
        """Test updating a file status to completed."""
        # Arrange
        BatchStateManager.save_batch_state(sample_batch_state)

        # Act
        BatchStateManager.update_file_status(
            batch_id="test-batch-123",
            source_path="/path/to/audio1.mp3",
            status=TranscriptionStatusEnum.COMPLETED,
            output_path="/path/to/audio1.txt",
            duration_seconds=90.0
        )

        # Assert
        loaded = BatchStateManager.load_batch_state()
        assert loaded is not None

        file_state = next(f for f in loaded.files if f.source_path == "/path/to/audio1.mp3")
        assert file_state.status == TranscriptionStatusEnum.COMPLETED
        assert file_state.output_path == "/path/to/audio1.txt"
        assert file_state.duration_seconds == 90.0
        assert file_state.completed_at is not None

        # Statistics should be updated
        assert loaded.statistics.completed == 2
        assert loaded.statistics.pending == 1
        assert loaded.statistics.total_duration_seconds == 210.5  # 120.5 + 90.0

    def test_update_file_status_failed(self, state_file_path, sample_batch_state):
        """Test updating a file status to failed with error message."""
        # Arrange
        BatchStateManager.save_batch_state(sample_batch_state)

        # Act
        BatchStateManager.update_file_status(
            batch_id="test-batch-123",
            source_path="/path/to/audio2.mp3",
            status=TranscriptionStatusEnum.FAILED,
            error_message="Network timeout"
        )

        # Assert
        loaded = BatchStateManager.load_batch_state()
        assert loaded is not None

        file_state = next(f for f in loaded.files if f.source_path == "/path/to/audio2.mp3")
        assert file_state.status == TranscriptionStatusEnum.FAILED
        assert file_state.error_message == "Network timeout"

        # Statistics should be updated
        assert loaded.statistics.failed == 1
        assert loaded.statistics.pending == 1

    def test_batch_id_mismatch(self, state_file_path, sample_batch_state):
        """Test that update with wrong batch_id raises ValueError."""
        # Arrange
        BatchStateManager.save_batch_state(sample_batch_state)

        # Act & Assert
        with pytest.raises(ValueError, match="Batch ID mismatch"):
            BatchStateManager.update_file_status(
                batch_id="wrong-batch-id",
                source_path="/path/to/audio1.mp3",
                status=TranscriptionStatusEnum.COMPLETED
            )

    def test_update_nonexistent_file_raises_error(self, state_file_path, sample_batch_state):
        """Test that updating nonexistent file raises ValueError."""
        # Arrange
        BatchStateManager.save_batch_state(sample_batch_state)

        # Act & Assert
        with pytest.raises(ValueError, match="File not found in batch"):
            BatchStateManager.update_file_status(
                batch_id="test-batch-123",
                source_path="/path/to/nonexistent.mp3",
                status=TranscriptionStatusEnum.COMPLETED
            )

    def test_statistics_update_on_file_completion(self, state_file_path, sample_batch_state):
        """Test that statistics are recalculated when file completes."""
        # Arrange
        BatchStateManager.save_batch_state(sample_batch_state)
        initial = BatchStateManager.load_batch_state()
        initial_completed = initial.statistics.completed
        initial_pending = initial.statistics.pending

        # Act
        BatchStateManager.update_file_status(
            batch_id="test-batch-123",
            source_path="/path/to/audio1.mp3",
            status=TranscriptionStatusEnum.COMPLETED,
            output_path="/path/to/audio1.txt",
            duration_seconds=60.0
        )

        # Assert
        updated = BatchStateManager.load_batch_state()
        assert updated.statistics.completed == initial_completed + 1
        assert updated.statistics.pending == initial_pending - 1


class TestVerifyCompletedFiles:
    """Test verification of completed file outputs."""

    def test_verify_completed_files_all_exist(self, state_file_path, tmp_path):
        """Test that all completed files are verified when outputs exist."""
        # Arrange - create output files
        output1 = tmp_path / "output1.txt"
        output1.write_text("transcript 1")

        state = BatchState(
            batch_id="test",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt",
                output_dir=None,
                language="en",
                diarize=False,
                smart_format=True,
                max_concurrent_workers=3
            ),
            files=[
                FileState(
                    source_path="/path/to/audio1.mp3",
                    status=TranscriptionStatusEnum.COMPLETED,
                    output_path=str(output1),
                    duration_seconds=60.0
                )
            ],
            statistics=BatchStatistics(
                total_files=1,
                completed=1,
                failed=0,
                pending=0
            )
        )

        # Act
        missing = BatchStateManager.verify_completed_files(state)

        # Assert
        assert len(missing) == 0

    def test_verify_completed_files_missing(self, state_file_path):
        """Test that missing output files are detected."""
        # Arrange - don't create output files
        state = BatchState(
            batch_id="test",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt",
                output_dir=None,
                language="en",
                diarize=False,
                smart_format=True,
                max_concurrent_workers=3
            ),
            files=[
                FileState(
                    source_path="/path/to/audio1.mp3",
                    status=TranscriptionStatusEnum.COMPLETED,
                    output_path="/nonexistent/output1.txt",
                    duration_seconds=60.0
                ),
                FileState(
                    source_path="/path/to/audio2.mp3",
                    status=TranscriptionStatusEnum.COMPLETED,
                    output_path="/nonexistent/output2.txt",
                    duration_seconds=90.0
                )
            ],
            statistics=BatchStatistics(
                total_files=2,
                completed=2,
                failed=0,
                pending=0
            )
        )

        # Act
        missing = BatchStateManager.verify_completed_files(state)

        # Assert
        assert len(missing) == 2
        assert "/path/to/audio1.mp3" in missing
        assert "/path/to/audio2.mp3" in missing

    def test_verify_completed_without_output_path(self, state_file_path):
        """Test that completed files without output_path are detected as missing."""
        # Arrange
        state = BatchState(
            batch_id="test",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt",
                output_dir=None,
                language="en",
                diarize=False,
                smart_format=True,
                max_concurrent_workers=3
            ),
            files=[
                FileState(
                    source_path="/path/to/audio1.mp3",
                    status=TranscriptionStatusEnum.COMPLETED,
                    output_path=None,  # Missing output path
                    duration_seconds=60.0
                )
            ],
            statistics=BatchStatistics(
                total_files=1,
                completed=1,
                failed=0,
                pending=0
            )
        )

        # Act
        missing = BatchStateManager.verify_completed_files(state)

        # Assert
        assert len(missing) == 1
        assert "/path/to/audio1.mp3" in missing


class TestMarkFilesForReprocessing:
    """Test marking files as pending for reprocessing."""

    def test_mark_files_for_reprocessing(self, state_file_path, tmp_path):
        """Test that files are marked as pending and statistics updated."""
        # Arrange
        state = BatchState(
            batch_id="test",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt",
                output_dir=None,
                language="en",
                diarize=False,
                smart_format=True,
                max_concurrent_workers=3
            ),
            files=[
                FileState(
                    source_path="/path/to/audio1.mp3",
                    status=TranscriptionStatusEnum.COMPLETED,
                    output_path="/path/to/audio1.txt",
                    duration_seconds=60.0,
                    completed_at=datetime.now()
                ),
                FileState(
                    source_path="/path/to/audio2.mp3",
                    status=TranscriptionStatusEnum.FAILED,
                    error_message="Timeout"
                )
            ],
            statistics=BatchStatistics(
                total_files=2,
                completed=1,
                failed=1,
                pending=0,
                total_duration_seconds=60.0
            )
        )

        # Act
        BatchStateManager.mark_files_for_reprocessing(
            state,
            ["/path/to/audio1.mp3", "/path/to/audio2.mp3"]
        )

        # Assert
        file1 = next(f for f in state.files if f.source_path == "/path/to/audio1.mp3")
        assert file1.status == TranscriptionStatusEnum.PENDING
        assert file1.output_path is None
        assert file1.completed_at is None

        file2 = next(f for f in state.files if f.source_path == "/path/to/audio2.mp3")
        assert file2.status == TranscriptionStatusEnum.PENDING
        assert file2.error_message is None

        # Statistics should be updated
        assert state.statistics.completed == 0
        assert state.statistics.failed == 0
        assert state.statistics.pending == 2
        assert state.statistics.total_duration_seconds == 0.0


class TestClearBatchState:
    """Test clearing batch state."""

    def test_clear_batch_state(self, state_file_path, sample_batch_state):
        """Test that clear removes the state file."""
        # Arrange
        BatchStateManager.save_batch_state(sample_batch_state)
        assert state_file_path.exists()

        # Act
        BatchStateManager.clear_batch_state()

        # Assert
        assert not state_file_path.exists()

    def test_clear_nonexistent(self, state_file_path):
        """Test that clear doesn't error when file doesn't exist."""
        # Act & Assert - should not raise
        BatchStateManager.clear_batch_state()
        assert not state_file_path.exists()


class TestMultipleSaveLoadCycles:
    """Test multiple save/load cycles."""

    def test_multiple_save_load_cycles(self, state_file_path, sample_batch_state):
        """Test that state can be saved, modified, and saved again."""
        # Arrange
        BatchStateManager.save_batch_state(sample_batch_state)

        # Act - Load, modify, save again
        loaded1 = BatchStateManager.load_batch_state()
        loaded1.statistics.completed = 2
        BatchStateManager.save_batch_state(loaded1)

        loaded2 = BatchStateManager.load_batch_state()
        loaded2.statistics.completed = 3
        BatchStateManager.save_batch_state(loaded2)

        # Assert
        final = BatchStateManager.load_batch_state()
        assert final.statistics.completed == 3


class TestLastUpdatedTimestamp:
    """Test that last_updated timestamp is updated on save."""

    def test_save_updates_last_updated(self, state_file_path, sample_batch_state):
        """Test that save_batch_state updates the last_updated timestamp."""
        # Arrange
        original_time = sample_batch_state.last_updated

        # Act
        import time
        time.sleep(0.01)  # Ensure time passes
        BatchStateManager.save_batch_state(sample_batch_state)

        # Assert
        assert sample_batch_state.last_updated > original_time
