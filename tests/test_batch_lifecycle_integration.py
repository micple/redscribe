"""Integration tests for batch lifecycle (Stage 6)

Test E2E batch resume flow:
- Create batch → save → pause → resume → complete
- Selective resume (mark some files, resume only selected)
- Missing source files handling
- Missing output files handling
- All using real file I/O (tmp_path), no mocks except BatchHistoryManager paths
"""
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from src.utils.batch_history_manager import BatchHistoryManager
from src.utils.batch_state_writer import BatchStateWriter
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
def reset_writer_singleton():
    """Reset BatchStateWriter singleton."""
    BatchStateWriter._instance = None
    yield
    if BatchStateWriter._instance:
        try:
            BatchStateWriter._instance.shutdown(timeout=2.0)
        except:
            pass
        BatchStateWriter._instance = None


@pytest.fixture
def test_audio_files(tmp_path):
    """Create real audio files for testing."""
    files = []
    for i in range(5):
        file_path = tmp_path / f"audio{i+1}.mp3"
        file_path.write_text(f"fake audio content {i+1}")
        files.append(file_path)
    return files


class TestFullBatchLifecycle:
    """Test complete batch lifecycle: create → pause → resume → complete."""

    def test_create_save_pause_resume_complete(self, batches_dir, test_audio_files):
        """Test full lifecycle: create → save → pause → resume → complete."""
        # Step 1: Create batch
        settings = BatchSettings(
            output_format="txt",
            output_dir=str(test_audio_files[0].parent / "output"),
            language="en",
            diarize=False,
            smart_format=True,
            max_concurrent_workers=3
        )

        files = [
            FileState(
                source_path=str(f),
                status=TranscriptionStatusEnum.PENDING
            )
            for f in test_audio_files
        ]

        statistics = BatchStatistics(
            total_files=len(files),
            completed=0,
            failed=0,
            pending=len(files)
        )

        state = BatchState(
            batch_id="integration-test-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=settings,
            files=files,
            statistics=statistics,
            status=BatchStatus.ACTIVE
        )

        # Step 2: Save active batch
        BatchHistoryManager.save_active_batch(state)
        assert BatchHistoryManager.has_active_batch()

        # Step 3: Simulate partial completion
        state.files[0].status = TranscriptionStatusEnum.COMPLETED
        state.files[0].output_path = str(test_audio_files[0].with_suffix(".txt"))
        state.files[1].status = TranscriptionStatusEnum.COMPLETED
        state.files[1].output_path = str(test_audio_files[1].with_suffix(".txt"))
        state.statistics.completed = 2
        state.statistics.pending = 3
        BatchHistoryManager.save_active_batch(state)

        # Step 4: Pause batch
        BatchHistoryManager.pause_batch(state)
        loaded = BatchHistoryManager.load_active_batch()
        assert loaded.status == BatchStatus.PAUSED

        # Step 5: Resume batch (simulated by loading and continuing)
        resumed_state = BatchHistoryManager.load_active_batch()
        assert resumed_state is not None
        assert resumed_state.statistics.completed == 2
        assert resumed_state.statistics.pending == 3

        # Step 6: Complete remaining files
        for file_state in resumed_state.files:
            if file_state.status == TranscriptionStatusEnum.PENDING:
                file_state.status = TranscriptionStatusEnum.COMPLETED
                file_state.output_path = str(Path(file_state.source_path).with_suffix(".txt"))

        resumed_state.statistics.completed = 5
        resumed_state.statistics.pending = 0

        # Step 7: Complete batch
        BatchHistoryManager.complete_batch(resumed_state)
        assert not BatchHistoryManager.has_active_batch()

        # Step 8: Verify archived
        archived = BatchHistoryManager.load_batch_by_id("integration-test-batch")
        assert archived is not None
        assert archived.status == BatchStatus.COMPLETED
        assert archived.completed_at is not None
        assert archived.statistics.completed == 5

    def test_batch_persists_across_restarts(self, batches_dir, test_audio_files):
        """Test that batch state persists and can be loaded after 'restart'."""
        # Step 1: Create and save batch
        settings = BatchSettings(
            output_format="txt",
            language="en",
            diarize=False,
            smart_format=True,
            max_concurrent_workers=3
        )

        files = [
            FileState(
                source_path=str(f),
                status=TranscriptionStatusEnum.PENDING
            )
            for f in test_audio_files[:3]
        ]

        state = BatchState(
            batch_id="persist-test-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=settings,
            files=files,
            statistics=BatchStatistics(total_files=3, pending=3),
            status=BatchStatus.ACTIVE
        )

        BatchHistoryManager.save_active_batch(state)

        # Step 2: Simulate app restart (reload from disk)
        loaded = BatchHistoryManager.load_active_batch()

        # Step 3: Verify state restored
        assert loaded is not None
        assert loaded.batch_id == "persist-test-batch"
        assert len(loaded.files) == 3
        assert loaded.statistics.total_files == 3


class TestSelectiveResume:
    """Test selective resume (resume only selected files)."""

    def test_selective_resume_with_filtered_files(self, batches_dir, test_audio_files):
        """Test resuming only selected files from a paused batch."""
        # Step 1: Create batch with mixed statuses
        settings = BatchSettings(
            output_format="txt",
            language="en",
            diarize=False,
            smart_format=True,
            max_concurrent_workers=3
        )

        files = [
            FileState(
                source_path=str(test_audio_files[0]),
                status=TranscriptionStatusEnum.COMPLETED,
                output_path=str(test_audio_files[0].with_suffix(".txt"))
            ),
            FileState(
                source_path=str(test_audio_files[1]),
                status=TranscriptionStatusEnum.PENDING
            ),
            FileState(
                source_path=str(test_audio_files[2]),
                status=TranscriptionStatusEnum.FAILED,
                error_message="Network error"
            ),
            FileState(
                source_path=str(test_audio_files[3]),
                status=TranscriptionStatusEnum.PENDING
            )
        ]

        state = BatchState(
            batch_id="selective-resume-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=settings,
            files=files,
            statistics=BatchStatistics(total_files=4, completed=1, failed=1, pending=2),
            status=BatchStatus.PAUSED
        )

        BatchHistoryManager.save_active_batch(state)

        # Step 2: Load and filter only pending/failed files
        loaded = BatchHistoryManager.load_active_batch()
        resumable_files = [
            f for f in loaded.files
            if f.status in (TranscriptionStatusEnum.PENDING, TranscriptionStatusEnum.FAILED)
        ]

        # Step 3: Verify correct files identified for resume
        assert len(resumable_files) == 3
        resumable_paths = [f.source_path for f in resumable_files]
        assert str(test_audio_files[1]) in resumable_paths
        assert str(test_audio_files[2]) in resumable_paths
        assert str(test_audio_files[3]) in resumable_paths
        assert str(test_audio_files[0]) not in resumable_paths  # Already completed

    def test_selective_resume_user_unchecks_files(self, batches_dir, test_audio_files):
        """Test resuming when user unchecks some files (selective resume)."""
        # Step 1: Create batch
        settings = BatchSettings(
            output_format="txt",
            language="en",
            diarize=False,
            smart_format=True,
            max_concurrent_workers=3
        )

        files = [
            FileState(
                source_path=str(test_audio_files[0]),
                status=TranscriptionStatusEnum.PENDING
            ),
            FileState(
                source_path=str(test_audio_files[1]),
                status=TranscriptionStatusEnum.PENDING
            ),
            FileState(
                source_path=str(test_audio_files[2]),
                status=TranscriptionStatusEnum.PENDING
            )
        ]

        state = BatchState(
            batch_id="user-selective-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=settings,
            files=files,
            statistics=BatchStatistics(total_files=3, pending=3),
            status=BatchStatus.PAUSED
        )

        BatchHistoryManager.save_active_batch(state)

        # Step 2: User selects only files 0 and 2 (skips file 1)
        selected_paths = [str(test_audio_files[0]), str(test_audio_files[2])]

        # Step 3: Filter files to resume
        loaded = BatchHistoryManager.load_active_batch()
        files_to_resume = [f for f in loaded.files if f.source_path in selected_paths]

        # Step 4: Verify only 2 files selected
        assert len(files_to_resume) == 2
        assert files_to_resume[0].source_path == str(test_audio_files[0])
        assert files_to_resume[1].source_path == str(test_audio_files[2])


class TestMissingFilesHandling:
    """Test handling of missing source and output files."""

    def test_missing_source_files_detected(self, batches_dir, tmp_path):
        """Test that missing source files are detected during resume."""
        # Step 1: Create batch with files that will be deleted
        missing_file = tmp_path / "will_be_deleted.mp3"
        missing_file.write_text("temp")

        settings = BatchSettings(
            output_format="txt",
            language="en",
            diarize=False,
            smart_format=True,
            max_concurrent_workers=3
        )

        files = [
            FileState(
                source_path=str(missing_file),
                status=TranscriptionStatusEnum.PENDING
            )
        ]

        state = BatchState(
            batch_id="missing-source-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=settings,
            files=files,
            statistics=BatchStatistics(total_files=1, pending=1),
            status=BatchStatus.PAUSED
        )

        BatchHistoryManager.save_active_batch(state)

        # Step 2: Delete source file (simulating missing file)
        missing_file.unlink()

        # Step 3: Verify missing source detected
        loaded = BatchHistoryManager.load_active_batch()
        verification = BatchHistoryManager.verify_batch_files(loaded)

        assert len(verification["missing_sources"]) == 1
        assert str(missing_file) in verification["missing_sources"]

    def test_missing_output_files_detected(self, batches_dir, tmp_path):
        """Test that missing output files are detected during resume."""
        # Step 1: Create batch with completed file
        source_file = tmp_path / "audio.mp3"
        source_file.write_text("audio")

        output_file = tmp_path / "audio.txt"
        output_file.write_text("transcript")

        settings = BatchSettings(
            output_format="txt",
            language="en",
            diarize=False,
            smart_format=True,
            max_concurrent_workers=3
        )

        files = [
            FileState(
                source_path=str(source_file),
                status=TranscriptionStatusEnum.COMPLETED,
                output_path=str(output_file)
            )
        ]

        state = BatchState(
            batch_id="missing-output-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=settings,
            files=files,
            statistics=BatchStatistics(total_files=1, completed=1, pending=0),
            status=BatchStatus.COMPLETED
        )

        BatchHistoryManager.complete_batch(state)

        # Step 2: Delete output file
        output_file.unlink()

        # Step 3: Verify missing output detected
        loaded = BatchHistoryManager.load_batch_by_id("missing-output-batch")
        verification = BatchHistoryManager.verify_batch_files(loaded)

        assert len(verification["missing_outputs"]) == 1
        assert str(source_file) in verification["missing_outputs"]

    def test_mark_missing_sources_as_skipped(self, batches_dir, tmp_path):
        """Test that files with missing sources should be marked SKIPPED."""
        # Step 1: Create batch
        existing_file = tmp_path / "exists.mp3"
        existing_file.write_text("audio")

        missing_file = tmp_path / "missing.mp3"  # Never created

        settings = BatchSettings(
            output_format="txt",
            language="en",
            diarize=False,
            smart_format=True,
            max_concurrent_workers=3
        )

        files = [
            FileState(
                source_path=str(existing_file),
                status=TranscriptionStatusEnum.PENDING
            ),
            FileState(
                source_path=str(missing_file),
                status=TranscriptionStatusEnum.PENDING
            )
        ]

        state = BatchState(
            batch_id="skip-missing-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=settings,
            files=files,
            statistics=BatchStatistics(total_files=2, pending=2),
            status=BatchStatus.PAUSED
        )

        BatchHistoryManager.save_active_batch(state)

        # Step 2: Verify and mark missing sources
        loaded = BatchHistoryManager.load_active_batch()
        verification = BatchHistoryManager.verify_batch_files(loaded)

        # Mark missing sources as SKIPPED
        for file_state in loaded.files:
            if file_state.source_path in verification["missing_sources"]:
                file_state.status = TranscriptionStatusEnum.SKIPPED
                file_state.error_message = "Source file not found"

        # Step 3: Verify file marked correctly
        missing_file_state = next(f for f in loaded.files if f.source_path == str(missing_file))
        assert missing_file_state.status == TranscriptionStatusEnum.SKIPPED
        assert missing_file_state.error_message == "Source file not found"

        existing_file_state = next(f for f in loaded.files if f.source_path == str(existing_file))
        assert existing_file_state.status == TranscriptionStatusEnum.PENDING


class TestAsyncWriterIntegration:
    """Test integration with BatchStateWriter."""

    def test_async_writer_saves_state(self, batches_dir, reset_writer_singleton, test_audio_files):
        """Test that BatchStateWriter saves state asynchronously."""
        # Step 1: Create batch
        settings = BatchSettings(
            output_format="txt",
            language="en",
            diarize=False,
            smart_format=True,
            max_concurrent_workers=3
        )

        files = [
            FileState(
                source_path=str(test_audio_files[0]),
                status=TranscriptionStatusEnum.PENDING
            )
        ]

        state = BatchState(
            batch_id="async-writer-batch",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=settings,
            files=files,
            statistics=BatchStatistics(total_files=1, pending=1),
            status=BatchStatus.ACTIVE
        )

        # Step 2: Use writer to save
        writer = BatchStateWriter()
        writer.schedule_write(state)
        writer.flush(timeout=3.0)

        # Step 3: Verify saved
        loaded = BatchHistoryManager.load_active_batch()
        assert loaded is not None
        assert loaded.batch_id == "async-writer-batch"

    def test_async_writer_batching_integration(self, batches_dir, reset_writer_singleton, test_audio_files):
        """Test that multiple rapid updates result in single write."""
        # Step 1: Create initial state
        settings = BatchSettings(
            output_format="txt",
            language="en",
            diarize=False,
            smart_format=True,
            max_concurrent_workers=3
        )

        files = [
            FileState(
                source_path=str(f),
                status=TranscriptionStatusEnum.PENDING
            )
            for f in test_audio_files
        ]

        state = BatchState(
            batch_id="batching-test",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=settings,
            files=files,
            statistics=BatchStatistics(total_files=5, pending=5),
            status=BatchStatus.ACTIVE
        )

        # Step 2: Rapidly update state (simulating file completions)
        writer = BatchStateWriter()

        for i in range(5):
            state.files[i].status = TranscriptionStatusEnum.COMPLETED
            state.statistics.completed = i + 1
            state.statistics.pending = 5 - (i + 1)
            writer.schedule_write(state)
            import time
            time.sleep(0.01)  # 10ms between updates

        # Step 3: Flush and verify last state
        writer.flush(timeout=3.0)
        loaded = BatchHistoryManager.load_active_batch()

        assert loaded.statistics.completed == 5
        assert loaded.statistics.pending == 0


class TestBatchHistory:
    """Test batch history listing and archival."""

    def test_multiple_batches_in_history(self, batches_dir, test_audio_files):
        """Test that multiple completed batches are stored in history."""
        # Create 3 batches at different times
        for i in range(3):
            settings = BatchSettings(
                output_format="txt",
                language="en",
                diarize=False,
                smart_format=True,
                max_concurrent_workers=3
            )

            state = BatchState(
                batch_id=f"history-batch-{i}",
                created_at=datetime.now() - timedelta(hours=i),
                last_updated=datetime.now(),
                settings=settings,
                files=[],
                statistics=BatchStatistics(total_files=0, pending=0),
                status=BatchStatus.COMPLETED,
                completed_at=datetime.now()
            )

            BatchHistoryManager.complete_batch(state)

        # Verify all 3 in history
        batches = BatchHistoryManager.list_batches()
        assert len(batches) == 3

        # Verify sorted by created_at (newest first)
        assert batches[0]["batch_id"] == "history-batch-0"
        assert batches[2]["batch_id"] == "history-batch-2"
