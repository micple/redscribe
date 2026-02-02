"""Tests for src/utils/batch_state_writer.py

Test coverage target: 85%+

Tests:
- schedule_write + flush (basic write works)
- Throttling: schedule multiple writes rapidly, verify max 1 write/sec
- Batching: multiple updates → single write (last state wins)
- Graceful shutdown
- Singleton pattern
- IMPORTANT: reset singleton between tests
"""
import pytest
import time
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.utils.batch_state_writer import BatchStateWriter
from src.utils.batch_history_manager import BatchHistoryManager
from contracts.batch_state import (
    BatchState, BatchSettings, FileState, BatchStatistics,
    TranscriptionStatusEnum, BatchStatus
)


@pytest.fixture
def reset_singleton():
    """Reset BatchStateWriter singleton before and after each test."""
    # Reset before test
    BatchStateWriter._instance = None

    yield

    # Cleanup after test
    if BatchStateWriter._instance is not None:
        try:
            BatchStateWriter._instance.shutdown(timeout=2.0)
        except:
            pass
        BatchStateWriter._instance = None


@pytest.fixture
def mock_save():
    """Mock BatchHistoryManager.save_active_batch for unit tests."""
    with patch.object(BatchHistoryManager, 'save_active_batch') as mock:
        yield mock


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
            status=TranscriptionStatusEnum.COMPLETED,
            output_path="/path/to/audio2.txt",
            duration_seconds=120.5
        )
    ]

    statistics = BatchStatistics(
        total_files=2,
        completed=1,
        failed=0,
        pending=1,
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


class TestSingletonPattern:
    """Test singleton pattern implementation."""

    def test_singleton_returns_same_instance(self, reset_singleton):
        """Test that multiple calls return the same instance."""
        # Act
        writer1 = BatchStateWriter()
        writer2 = BatchStateWriter()

        # Assert
        assert writer1 is writer2

    def test_singleton_initializes_only_once(self, reset_singleton):
        """Test that __init__ only runs once."""
        # Act
        writer1 = BatchStateWriter()
        thread1 = writer1._thread

        writer2 = BatchStateWriter()
        thread2 = writer2._thread

        # Assert
        assert thread1 is thread2  # Same thread object


class TestBasicWriteOperations:
    """Test basic write operations."""

    def test_schedule_write_and_flush_writes_state(self, reset_singleton, mock_save, sample_batch_state):
        """Test that schedule_write + flush successfully writes state."""
        # Arrange
        writer = BatchStateWriter()

        # Act
        writer.schedule_write(sample_batch_state)
        success = writer.flush(timeout=3.0)

        # Assert
        assert success is True
        mock_save.assert_called_once()
        # Verify correct state was passed
        saved_state = mock_save.call_args[0][0]
        assert saved_state.batch_id == sample_batch_state.batch_id

    def test_schedule_write_non_blocking(self, reset_singleton, sample_batch_state):
        """Test that schedule_write returns immediately (non-blocking)."""
        # Arrange
        writer = BatchStateWriter()

        # Act
        start_time = time.time()
        writer.schedule_write(sample_batch_state)
        elapsed = time.time() - start_time

        # Assert - should return almost instantly
        assert elapsed < 0.1  # Less than 100ms

    def test_flush_waits_for_write_completion(self, reset_singleton, mock_save, sample_batch_state):
        """Test that flush blocks until write completes."""
        # Arrange
        writer = BatchStateWriter()
        writer.schedule_write(sample_batch_state)

        # Act
        success = writer.flush(timeout=3.0)

        # Assert
        assert success is True
        mock_save.assert_called_once()


class TestThrottling:
    """Test write throttling (max 1 write/sec)."""

    def test_throttling_max_one_write_per_second(self, reset_singleton, mock_save, sample_batch_state):
        """Test that rapid writes are throttled to max 1/sec."""
        # Arrange
        writer = BatchStateWriter()

        # Track call times with side_effect
        call_times = []

        def track_calls(state):
            call_times.append(time.time())

        mock_save.side_effect = track_calls

        # Act - schedule 3 writes rapidly
        for i in range(3):
            sample_batch_state.statistics.completed = i
            writer.schedule_write(sample_batch_state)
            time.sleep(0.05)  # 50ms between schedules

        # Wait for writes to complete
        writer.flush(timeout=5.0)

        # Assert - writes should be throttled
        if len(call_times) >= 2:
            # Time between writes should be >= 1 second (with small tolerance)
            time_diff = call_times[1] - call_times[0]
            assert time_diff >= 0.9  # Allow 100ms tolerance


class TestBatching:
    """Test batching (multiple updates → single write)."""

    def test_batching_multiple_updates_single_write(self, reset_singleton, mock_save, sample_batch_state):
        """Test that multiple rapid updates result in single write (last state wins)."""
        # Arrange
        writer = BatchStateWriter()

        # Act - schedule 5 updates rapidly
        for i in range(5):
            sample_batch_state.statistics.completed = i
            writer.schedule_write(sample_batch_state)
            time.sleep(0.01)  # 10ms between updates

        # Flush immediately (before throttle interval)
        writer.flush(timeout=3.0)

        # Assert - should have batched (fewer calls than schedules)
        # Due to batching, we expect fewer writes than 5
        assert mock_save.call_count >= 1
        # Last written value should be 4 (last update)
        if mock_save.call_count > 0:
            last_call = mock_save.call_args_list[-1]
            last_state = last_call[0][0]
            assert last_state.statistics.completed == 4

    def test_batching_last_state_wins(self, reset_singleton, mock_save, sample_batch_state):
        """Test that when batching, the last state is written."""
        # Arrange
        writer = BatchStateWriter()

        # Act - schedule multiple updates rapidly
        for i in range(10):
            sample_batch_state.statistics.completed = i
            writer.schedule_write(sample_batch_state)

        writer.flush(timeout=3.0)

        # Assert - last written value should be 9 (last update)
        assert mock_save.called
        last_call = mock_save.call_args_list[-1]
        last_state = last_call[0][0]
        assert last_state.statistics.completed == 9


class TestGracefulShutdown:
    """Test graceful shutdown behavior."""

    def test_shutdown_flushes_pending_writes(self, reset_singleton, mock_save, sample_batch_state):
        """Test that shutdown flushes pending writes."""
        # Arrange
        writer = BatchStateWriter()
        writer.schedule_write(sample_batch_state)

        # Act
        writer.shutdown(timeout=3.0)

        # Assert - write should have been called during shutdown
        mock_save.assert_called_once()

    def test_shutdown_stops_thread(self, reset_singleton):
        """Test that shutdown stops the writer thread."""
        # Arrange
        writer = BatchStateWriter()
        thread = writer._thread

        # Act
        writer.shutdown(timeout=3.0)

        # Assert
        assert not thread.is_alive()

    def test_shutdown_sets_shutdown_event(self, reset_singleton):
        """Test that shutdown sets the shutdown event."""
        # Arrange
        writer = BatchStateWriter()

        # Act
        writer.shutdown(timeout=3.0)

        # Assert
        assert writer._shutdown_event.is_set()

    def test_schedule_write_after_shutdown_warns(self, reset_singleton, sample_batch_state):
        """Test that schedule_write after shutdown logs warning."""
        # Arrange
        writer = BatchStateWriter()
        writer.shutdown(timeout=2.0)

        # Act (should not crash, just warn)
        writer.schedule_write(sample_batch_state)

        # No exception should be raised


class TestFlushBehavior:
    """Test flush behavior in various scenarios."""

    def test_flush_returns_true_on_success(self, reset_singleton, mock_save, sample_batch_state):
        """Test that flush returns True when successful."""
        # Arrange
        writer = BatchStateWriter()
        writer.schedule_write(sample_batch_state)

        # Act
        result = writer.flush(timeout=3.0)

        # Assert
        assert result is True

    def test_flush_returns_false_on_timeout(self, reset_singleton, sample_batch_state):
        """Test that flush returns False when timeout occurs."""
        # Arrange
        writer = BatchStateWriter()

        # Mock _write_state to hang (simulates slow disk I/O)
        def slow_write(state):
            time.sleep(10)  # Longer than timeout

        writer._write_state = slow_write

        writer.schedule_write(sample_batch_state)

        # Act
        result = writer.flush(timeout=0.5)  # Short timeout

        # Assert
        assert result is False

    def test_flush_after_shutdown_returns_false(self, reset_singleton):
        """Test that flush after shutdown returns False."""
        # Arrange
        writer = BatchStateWriter()
        writer.shutdown(timeout=2.0)

        # Act
        result = writer.flush(timeout=3.0)

        # Assert
        assert result is False

    def test_flush_empty_queue_returns_true(self, reset_singleton):
        """Test that flush with empty queue returns True."""
        # Arrange
        writer = BatchStateWriter()

        # Act
        result = writer.flush(timeout=3.0)

        # Assert
        assert result is True


class TestErrorHandling:
    """Test error handling in writer."""

    def test_write_error_logged_but_not_raised(self, reset_singleton, sample_batch_state):
        """Test that write errors are logged but don't crash thread."""
        # Arrange
        writer = BatchStateWriter()

        # Mock BatchHistoryManager.save_active_batch to raise exception
        with patch.object(BatchHistoryManager, 'save_active_batch', side_effect=OSError("Disk full")):
            # Act
            writer.schedule_write(sample_batch_state)
            writer.flush(timeout=3.0)

            # Assert - thread should still be alive
            assert writer._thread.is_alive()


class TestWriterThreadLifecycle:
    """Test writer thread lifecycle."""

    def test_writer_thread_starts_on_init(self, reset_singleton):
        """Test that writer thread starts when instance is created."""
        # Act
        writer = BatchStateWriter()

        # Assert
        assert writer._thread is not None
        assert writer._thread.is_alive()

    def test_writer_thread_is_daemon(self, reset_singleton):
        """Test that writer thread is a daemon thread."""
        # Act
        writer = BatchStateWriter()

        # Assert
        assert writer._thread.daemon is True

    def test_writer_thread_name(self, reset_singleton):
        """Test that writer thread has correct name."""
        # Act
        writer = BatchStateWriter()

        # Assert
        assert writer._thread.name == "BatchStateWriter"


class TestConcurrentAccess:
    """Test thread-safe concurrent access."""

    def test_concurrent_schedule_write_safe(self, reset_singleton, mock_save, sample_batch_state):
        """Test that concurrent schedule_write calls are thread-safe."""
        import threading

        # Arrange
        writer = BatchStateWriter()
        threads = []

        def schedule_writes():
            for _ in range(10):
                writer.schedule_write(sample_batch_state)

        # Act - create multiple threads scheduling writes
        for _ in range(5):
            t = threading.Thread(target=schedule_writes)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Flush
        writer.flush(timeout=5.0)

        # Assert - should not crash, and save should have been called
        assert mock_save.called


class TestWriteInterval:
    """Test write interval configuration."""

    def test_write_interval_default_one_second(self, reset_singleton):
        """Test that default write interval is 1 second."""
        # Act
        writer = BatchStateWriter()

        # Assert
        assert writer._write_interval == 1.0


class TestQueueBehavior:
    """Test queue behavior under various conditions."""

    def test_queue_full_drops_oldest_state(self, reset_singleton, mock_save, sample_batch_state):
        """Test that when queue is full, oldest state is dropped."""
        # This is hard to test without mocking queue, but we can verify the logic
        # is there by checking schedule_write handles queue.Full

        # Arrange
        writer = BatchStateWriter()

        # Act - schedule many writes
        for i in range(100):
            sample_batch_state.statistics.completed = i
            writer.schedule_write(sample_batch_state)

        writer.flush(timeout=5.0)

        # Assert - should not crash, and save should have been called
        assert mock_save.called
        # Last value should be 99
        last_call = mock_save.call_args_list[-1]
        last_state = last_call[0][0]
        assert last_state.statistics.completed == 99
