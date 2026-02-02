"""Tests for src/utils/batch_history_manager.py

Test coverage target: 90%+

Tests:
- Batch lifecycle: active → paused → completed
- has_active_batch(), load_active_batch(), save_active_batch()
- complete_batch() — verify archived file created, index updated
- pause_batch() — verify status changed
- dismiss_active_batch()
- load_batch_by_id() — existing and non-existing
- list_batches() with and without status_filter
- Index updates (add/update/remove entries)
- delete_batch() — verify batch file + index entry removed
- cleanup_old_batches() — batches >30 days deleted, recent kept
- Atomic writes (no corruption on error)
- verify_batch_files() — missing sources and missing outputs detected
"""
import pytest
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

from src.utils.batch_history_manager import BatchHistoryManager
from contracts.batch_state import (
    BatchState, BatchSettings, FileState, BatchStatistics,
    TranscriptionStatusEnum, BatchStatus
)


@pytest.fixture
def batches_dir(tmp_path, monkeypatch):
    """Override BatchHistoryManager paths to use tmp_path."""
    batches_dir = tmp_path / "batches"
    active_file = batches_dir / "active.json"
    index_file = batches_dir / "index.json"

    monkeypatch.setattr(BatchHistoryManager, "BATCHES_DIR", batches_dir)
    monkeypatch.setattr(BatchHistoryManager, "ACTIVE_FILE", active_file)
    monkeypatch.setattr(BatchHistoryManager, "INDEX_FILE", index_file)

    return batches_dir


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
        statistics=statistics,
        status=BatchStatus.ACTIVE
    )


@pytest.fixture
def temp_audio_files(tmp_path):
    """Create temporary audio files for verification tests."""
    files = []
    for i in range(3):
        file_path = tmp_path / f"audio{i+1}.mp3"
        file_path.write_text(f"fake audio {i+1}")
        files.append(file_path)
    return files


class TestBasicOperations:
    """Test basic batch operations."""

    def test_has_active_batch_false_when_no_file(self, batches_dir):
        """Test that has_active_batch returns False when no file exists."""
        # Act
        result = BatchHistoryManager.has_active_batch()

        # Assert
        assert result is False

    def test_has_active_batch_true_when_file_exists(self, batches_dir, sample_batch_state):
        """Test that has_active_batch returns True when file exists."""
        # Arrange
        BatchHistoryManager.save_active_batch(sample_batch_state)

        # Act
        result = BatchHistoryManager.has_active_batch()

        # Assert
        assert result is True

    def test_save_and_load_active_batch(self, batches_dir, sample_batch_state):
        """Test that saved active batch can be loaded correctly."""
        # Arrange & Act
        BatchHistoryManager.save_active_batch(sample_batch_state)
        loaded_state = BatchHistoryManager.load_active_batch()

        # Assert
        assert loaded_state is not None
        assert loaded_state.batch_id == sample_batch_state.batch_id
        assert len(loaded_state.files) == 3
        assert loaded_state.statistics.total_files == 3
        assert loaded_state.settings.output_format == "txt"

    def test_load_active_batch_returns_none_if_not_exists(self, batches_dir):
        """Test that load_active_batch returns None when file doesn't exist."""
        # Act
        result = BatchHistoryManager.load_active_batch()

        # Assert
        assert result is None

    def test_save_active_batch_creates_directory(self, batches_dir, sample_batch_state):
        """Test that save_active_batch creates batches directory if missing."""
        # Act
        BatchHistoryManager.save_active_batch(sample_batch_state)

        # Assert
        assert batches_dir.exists()
        assert BatchHistoryManager.ACTIVE_FILE.exists()

    def test_save_active_batch_updates_timestamp(self, batches_dir, sample_batch_state):
        """Test that save_active_batch updates last_updated timestamp."""
        # Arrange
        original_time = sample_batch_state.last_updated

        # Act (slight delay to ensure time difference)
        import time
        time.sleep(0.01)
        BatchHistoryManager.save_active_batch(sample_batch_state)
        loaded = BatchHistoryManager.load_active_batch()

        # Assert
        assert loaded.last_updated > original_time


class TestBatchLifecycle:
    """Test batch lifecycle transitions."""

    def test_pause_batch_sets_status_to_paused(self, batches_dir, sample_batch_state):
        """Test that pause_batch sets status to PAUSED."""
        # Arrange
        sample_batch_state.status = BatchStatus.ACTIVE

        # Act
        BatchHistoryManager.pause_batch(sample_batch_state)
        loaded = BatchHistoryManager.load_active_batch()

        # Assert
        assert loaded.status == BatchStatus.PAUSED

    def test_complete_batch_creates_archive(self, batches_dir, sample_batch_state):
        """Test that complete_batch creates archived file."""
        # Act
        BatchHistoryManager.complete_batch(sample_batch_state)

        # Assert
        # Check active.json removed
        assert not BatchHistoryManager.ACTIVE_FILE.exists()

        # Check archive file created
        archive_files = list(batches_dir.glob("*.json"))
        archive_files = [f for f in archive_files if f.name != "index.json"]
        assert len(archive_files) == 1

        # Verify archive filename format: YYYYMMDD_HHMMSS_{batch_id}.json
        archive_name = archive_files[0].name
        assert sample_batch_state.batch_id in archive_name

    def test_complete_batch_updates_status_and_timestamp(self, batches_dir, sample_batch_state):
        """Test that complete_batch sets status and completed_at."""
        # Act
        BatchHistoryManager.complete_batch(sample_batch_state)

        # Load from archive
        loaded = BatchHistoryManager.load_batch_by_id(sample_batch_state.batch_id)

        # Assert
        assert loaded.status == BatchStatus.COMPLETED
        assert loaded.completed_at is not None

    def test_complete_batch_updates_index(self, batches_dir, sample_batch_state):
        """Test that complete_batch adds entry to index."""
        # Act
        BatchHistoryManager.complete_batch(sample_batch_state)

        # Assert
        index = BatchHistoryManager._load_index()
        assert len(index) == 1
        assert index[0]["batch_id"] == sample_batch_state.batch_id
        assert index[0]["status"] == BatchStatus.COMPLETED.value
        assert index[0]["total_files"] == 3
        assert index[0]["completed_files"] == 1

    def test_dismiss_active_batch_removes_file(self, batches_dir, sample_batch_state):
        """Test that dismiss_active_batch removes active.json."""
        # Arrange
        BatchHistoryManager.save_active_batch(sample_batch_state)

        # Act
        BatchHistoryManager.dismiss_active_batch()

        # Assert
        assert not BatchHistoryManager.ACTIVE_FILE.exists()

    def test_dismiss_active_batch_safe_when_no_file(self, batches_dir):
        """Test that dismiss_active_batch is safe when file doesn't exist."""
        # Act & Assert (should not raise)
        BatchHistoryManager.dismiss_active_batch()


class TestLoadBatchById:
    """Test loading batches by ID."""

    def test_load_batch_by_id_finds_active_batch(self, batches_dir, sample_batch_state):
        """Test that load_batch_by_id finds active batch."""
        # Arrange
        BatchHistoryManager.save_active_batch(sample_batch_state)

        # Act
        loaded = BatchHistoryManager.load_batch_by_id(sample_batch_state.batch_id)

        # Assert
        assert loaded is not None
        assert loaded.batch_id == sample_batch_state.batch_id

    def test_load_batch_by_id_finds_archived_batch(self, batches_dir, sample_batch_state):
        """Test that load_batch_by_id finds archived batch."""
        # Arrange
        BatchHistoryManager.complete_batch(sample_batch_state)

        # Act
        loaded = BatchHistoryManager.load_batch_by_id(sample_batch_state.batch_id)

        # Assert
        assert loaded is not None
        assert loaded.batch_id == sample_batch_state.batch_id
        assert loaded.status == BatchStatus.COMPLETED

    def test_load_batch_by_id_returns_none_for_nonexistent(self, batches_dir):
        """Test that load_batch_by_id returns None for nonexistent ID."""
        # Act
        loaded = BatchHistoryManager.load_batch_by_id("nonexistent-id")

        # Assert
        assert loaded is None


class TestListBatches:
    """Test batch listing with filters."""

    def test_list_batches_empty_when_no_batches(self, batches_dir):
        """Test that list_batches returns empty list when no batches."""
        # Act
        batches = BatchHistoryManager.list_batches()

        # Assert
        assert batches == []

    def test_list_batches_returns_all_batches(self, batches_dir, sample_batch_state):
        """Test that list_batches returns all batches."""
        # Arrange - create 2 batches
        BatchHistoryManager.complete_batch(sample_batch_state)

        sample_batch_state.batch_id = "test-batch-456"
        sample_batch_state.status = BatchStatus.ACTIVE
        BatchHistoryManager.save_active_batch(sample_batch_state)
        BatchHistoryManager.pause_batch(sample_batch_state)
        BatchHistoryManager.complete_batch(sample_batch_state)

        # Act
        batches = BatchHistoryManager.list_batches()

        # Assert
        assert len(batches) == 2

    def test_list_batches_filter_by_status(self, batches_dir):
        """Test that list_batches filters by status."""
        # Arrange - create batches with different statuses
        state1 = BatchState(
            batch_id="batch-1",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt", language="en", diarize=False,
                smart_format=True, max_concurrent_workers=3
            ),
            files=[],
            statistics=BatchStatistics(total_files=0, pending=0),
            status=BatchStatus.COMPLETED
        )
        BatchHistoryManager.complete_batch(state1)

        state2 = BatchState(
            batch_id="batch-2",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt", language="en", diarize=False,
                smart_format=True, max_concurrent_workers=3
            ),
            files=[],
            statistics=BatchStatistics(total_files=0, pending=0),
            status=BatchStatus.PAUSED
        )
        BatchHistoryManager.save_active_batch(state2)
        BatchHistoryManager.pause_batch(state2)
        BatchHistoryManager.complete_batch(state2)

        # Act
        completed_batches = BatchHistoryManager.list_batches(status_filter=BatchStatus.COMPLETED)

        # Assert
        assert len(completed_batches) == 2  # Both completed

    def test_list_batches_sorted_by_created_at_descending(self, batches_dir):
        """Test that list_batches returns newest batches first."""
        # Arrange - create batches at different times
        old_state = BatchState(
            batch_id="old-batch",
            created_at=datetime.now() - timedelta(hours=2),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt", language="en", diarize=False,
                smart_format=True, max_concurrent_workers=3
            ),
            files=[],
            statistics=BatchStatistics(total_files=0, pending=0),
            status=BatchStatus.COMPLETED
        )
        BatchHistoryManager.complete_batch(old_state)

        new_state = BatchState(
            batch_id="new-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt", language="en", diarize=False,
                smart_format=True, max_concurrent_workers=3
            ),
            files=[],
            statistics=BatchStatistics(total_files=0, pending=0),
            status=BatchStatus.COMPLETED
        )
        BatchHistoryManager.complete_batch(new_state)

        # Act
        batches = BatchHistoryManager.list_batches()

        # Assert
        assert batches[0]["batch_id"] == "new-batch"
        assert batches[1]["batch_id"] == "old-batch"


class TestDeleteBatch:
    """Test batch deletion."""

    def test_delete_batch_removes_file_and_index_entry(self, batches_dir, sample_batch_state):
        """Test that delete_batch removes archive file and index entry."""
        # Arrange
        BatchHistoryManager.complete_batch(sample_batch_state)

        # Act
        BatchHistoryManager.delete_batch(sample_batch_state.batch_id)

        # Assert
        # Check archive file deleted
        archive_files = list(batches_dir.glob(f"*{sample_batch_state.batch_id}*.json"))
        assert len(archive_files) == 0

        # Check index entry removed
        index = BatchHistoryManager._load_index()
        assert len(index) == 0

    def test_delete_batch_raises_error_for_active_batch(self, batches_dir, sample_batch_state):
        """Test that delete_batch raises ValueError for active batch."""
        # Arrange
        BatchHistoryManager.save_active_batch(sample_batch_state)

        # Act & Assert
        with pytest.raises(ValueError, match="Cannot delete active batch"):
            BatchHistoryManager.delete_batch(sample_batch_state.batch_id)

    def test_delete_batch_safe_for_nonexistent(self, batches_dir):
        """Test that delete_batch is safe for nonexistent batch."""
        # Act & Assert (should not raise)
        BatchHistoryManager.delete_batch("nonexistent-id")


class TestCleanupOldBatches:
    """Test automatic cleanup of old batches."""

    def test_cleanup_old_batches_deletes_old_batches(self, batches_dir):
        """Test that cleanup_old_batches deletes batches older than threshold."""
        # Arrange - manually create old archived batch
        old_completed = datetime.now() - timedelta(days=35)
        old_state = BatchState(
            batch_id="old-batch",
            created_at=old_completed,
            last_updated=old_completed,
            settings=BatchSettings(
                output_format="txt", language="en", diarize=False,
                smart_format=True, max_concurrent_workers=3
            ),
            files=[],
            statistics=BatchStatistics(total_files=0, pending=0),
            status=BatchStatus.COMPLETED,
            completed_at=old_completed
        )

        # Manually save to archive and index (bypass complete_batch which sets completed_at to now)
        batches_dir.mkdir(parents=True, exist_ok=True)
        timestamp = old_completed.strftime("%Y%m%d_%H%M%S")
        archive_filename = f"{timestamp}_old-batch.json"
        archive_path = batches_dir / archive_filename

        data = old_state.model_dump(mode='json')
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        # Manually update index
        BatchHistoryManager._update_index(old_state, archive_filename)

        # Act
        deleted_count = BatchHistoryManager.cleanup_old_batches(days_threshold=30)

        # Assert
        assert deleted_count == 1

        # Verify batch removed
        batches = BatchHistoryManager.list_batches()
        assert len(batches) == 0

    def test_cleanup_old_batches_keeps_recent_batches(self, batches_dir):
        """Test that cleanup_old_batches keeps recent batches."""
        # Arrange - create recent batch
        recent_state = BatchState(
            batch_id="recent-batch",
            created_at=datetime.now() - timedelta(days=10),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt", language="en", diarize=False,
                smart_format=True, max_concurrent_workers=3
            ),
            files=[],
            statistics=BatchStatistics(total_files=0, pending=0),
            status=BatchStatus.COMPLETED,
            completed_at=datetime.now() - timedelta(days=10)
        )
        BatchHistoryManager.complete_batch(recent_state)

        # Act
        deleted_count = BatchHistoryManager.cleanup_old_batches(days_threshold=30)

        # Assert
        assert deleted_count == 0

        # Verify batch still exists
        batches = BatchHistoryManager.list_batches()
        assert len(batches) == 1

    def test_cleanup_old_batches_skips_batches_without_completed_at(self, batches_dir):
        """Test that cleanup_old_batches skips batches without completed_at."""
        # Arrange - create batch without completed_at (manually add to index)
        index = [{
            "batch_id": "incomplete-batch",
            "status": BatchStatus.PAUSED.value,
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "total_files": 0,
            "completed_files": 0,
            "filename": "test.json"
        }]
        BatchHistoryManager._save_index(index)

        # Act
        deleted_count = BatchHistoryManager.cleanup_old_batches(days_threshold=30)

        # Assert
        assert deleted_count == 0


class TestVerifyBatchFiles:
    """Test batch file verification."""

    def test_verify_batch_files_detects_missing_sources(self, batches_dir, tmp_path):
        """Test that verify_batch_files detects missing source files."""
        # Arrange
        state = BatchState(
            batch_id="test-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt", language="en", diarize=False,
                smart_format=True, max_concurrent_workers=3
            ),
            files=[
                FileState(
                    source_path=str(tmp_path / "missing.mp3"),
                    status=TranscriptionStatusEnum.PENDING
                )
            ],
            statistics=BatchStatistics(total_files=1, pending=1),
            status=BatchStatus.ACTIVE
        )

        # Act
        result = BatchHistoryManager.verify_batch_files(state)

        # Assert
        assert len(result["missing_sources"]) == 1
        assert str(tmp_path / "missing.mp3") in result["missing_sources"]

    def test_verify_batch_files_detects_missing_outputs(self, batches_dir, tmp_path):
        """Test that verify_batch_files detects missing output files."""
        # Arrange
        source_file = tmp_path / "audio.mp3"
        source_file.write_text("fake audio")

        state = BatchState(
            batch_id="test-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt", language="en", diarize=False,
                smart_format=True, max_concurrent_workers=3
            ),
            files=[
                FileState(
                    source_path=str(source_file),
                    status=TranscriptionStatusEnum.COMPLETED,
                    output_path=str(tmp_path / "missing_output.txt")
                )
            ],
            statistics=BatchStatistics(total_files=1, completed=1, pending=0),
            status=BatchStatus.COMPLETED
        )

        # Act
        result = BatchHistoryManager.verify_batch_files(state)

        # Assert
        assert len(result["missing_outputs"]) == 1
        assert str(source_file) in result["missing_outputs"]

    def test_verify_batch_files_all_files_exist(self, batches_dir, tmp_path):
        """Test that verify_batch_files returns empty lists when all files exist."""
        # Arrange
        source_file = tmp_path / "audio.mp3"
        source_file.write_text("fake audio")
        output_file = tmp_path / "audio.txt"
        output_file.write_text("transcript")

        state = BatchState(
            batch_id="test-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format="txt", language="en", diarize=False,
                smart_format=True, max_concurrent_workers=3
            ),
            files=[
                FileState(
                    source_path=str(source_file),
                    status=TranscriptionStatusEnum.COMPLETED,
                    output_path=str(output_file)
                )
            ],
            statistics=BatchStatistics(total_files=1, completed=1, pending=0),
            status=BatchStatus.COMPLETED
        )

        # Act
        result = BatchHistoryManager.verify_batch_files(state)

        # Assert
        assert len(result["missing_sources"]) == 0
        assert len(result["missing_outputs"]) == 0


class TestAtomicWrites:
    """Test atomic write operations."""

    def test_save_active_batch_atomic_write(self, batches_dir, sample_batch_state):
        """Test that save_active_batch uses atomic write (no partial files)."""
        # Act
        BatchHistoryManager.save_active_batch(sample_batch_state)

        # Assert
        assert BatchHistoryManager.ACTIVE_FILE.exists()

        # Verify no temp files left behind
        temp_files = list(batches_dir.glob(".active_*.tmp"))
        assert len(temp_files) == 0

    def test_save_index_atomic_write(self, batches_dir):
        """Test that _save_index uses atomic write."""
        # Arrange
        index = [{
            "batch_id": "test-123",
            "status": "completed",
            "created_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "total_files": 5,
            "completed_files": 5,
            "filename": "test.json"
        }]

        # Act
        BatchHistoryManager._save_index(index)

        # Assert
        assert BatchHistoryManager.INDEX_FILE.exists()

        # Verify no temp files left behind
        temp_files = list(batches_dir.glob(".index_*.tmp"))
        assert len(temp_files) == 0


class TestCorruptedFileHandling:
    """Test handling of corrupted files."""

    def test_load_active_batch_handles_corrupted_json(self, batches_dir):
        """Test that load_active_batch handles corrupted JSON gracefully."""
        # Arrange
        batches_dir.mkdir(parents=True, exist_ok=True)
        BatchHistoryManager.ACTIVE_FILE.write_text("{ invalid json }")

        # Act
        result = BatchHistoryManager.load_active_batch()

        # Assert
        assert result is None

        # Verify backup created
        backup_files = list(batches_dir.glob("*.corrupted_*"))
        assert len(backup_files) > 0

    def test_load_active_batch_handles_invalid_pydantic_structure(self, batches_dir):
        """Test that load_active_batch handles invalid Pydantic structure."""
        # Arrange
        batches_dir.mkdir(parents=True, exist_ok=True)
        BatchHistoryManager.ACTIVE_FILE.write_text('{"invalid": "structure"}')

        # Act
        result = BatchHistoryManager.load_active_batch()

        # Assert
        assert result is None


class TestIndexOperations:
    """Test index file operations."""

    def test_update_index_adds_new_entry(self, batches_dir, sample_batch_state):
        """Test that _update_index adds new entry to index."""
        # Act
        BatchHistoryManager._update_index(sample_batch_state, "test.json")

        # Assert
        index = BatchHistoryManager._load_index()
        assert len(index) == 1
        assert index[0]["batch_id"] == sample_batch_state.batch_id
        assert index[0]["filename"] == "test.json"

    def test_update_index_updates_existing_entry(self, batches_dir, sample_batch_state):
        """Test that _update_index updates existing entry."""
        # Arrange - add initial entry
        BatchHistoryManager._update_index(sample_batch_state, "test1.json")

        # Act - update same batch
        sample_batch_state.statistics.completed = 3
        BatchHistoryManager._update_index(sample_batch_state, "test2.json")

        # Assert
        index = BatchHistoryManager._load_index()
        assert len(index) == 1  # Still only 1 entry
        assert index[0]["completed_files"] == 3
        assert index[0]["filename"] == "test2.json"

    def test_load_index_returns_empty_list_when_not_exists(self, batches_dir):
        """Test that _load_index returns empty list when file doesn't exist."""
        # Act
        index = BatchHistoryManager._load_index()

        # Assert
        assert index == []

    def test_load_index_handles_corrupted_file(self, batches_dir):
        """Test that _load_index handles corrupted index gracefully."""
        # Arrange
        batches_dir.mkdir(parents=True, exist_ok=True)
        BatchHistoryManager.INDEX_FILE.write_text("{ invalid json }")

        # Act
        index = BatchHistoryManager._load_index()

        # Assert
        assert index == []
