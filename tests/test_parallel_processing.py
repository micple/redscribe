"""Tests for parallel processing functionality."""
import pytest
import threading
import time
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from src.utils.api_manager import APIManager
from src.utils.session_logger import SessionLogger
import src.utils.api_manager as api_mod
from config import (
    MAX_CONCURRENT_WORKERS,
    MIN_CONCURRENT_WORKERS,
    MAX_CONCURRENT_WORKERS_LIMIT
)


@pytest.fixture
def fresh_api_manager(tmp_path):
    """Create a fresh APIManager with isolated config."""
    config_file = tmp_path / "config.json"
    with patch.object(api_mod, "CONFIG_FILE", config_file):
        manager = APIManager()
        yield manager, config_file


class TestConcurrentWorkersConfig:
    """Test concurrent worker configuration constants."""

    def test_concurrent_workers_config_exists(self):
        """Test that worker configuration constants are defined."""
        # Assert
        assert MAX_CONCURRENT_WORKERS == 3
        assert MIN_CONCURRENT_WORKERS == 1
        assert MAX_CONCURRENT_WORKERS_LIMIT == 10

    def test_config_values_are_sane(self):
        """Test that configuration values are reasonable."""
        # Assert
        assert MIN_CONCURRENT_WORKERS >= 1
        assert MAX_CONCURRENT_WORKERS >= MIN_CONCURRENT_WORKERS
        assert MAX_CONCURRENT_WORKERS_LIMIT >= MAX_CONCURRENT_WORKERS
        assert MAX_CONCURRENT_WORKERS_LIMIT <= 100  # Sanity check


class TestAPIManagerWorkers:
    """Test APIManager worker configuration methods."""

    def test_api_manager_get_workers_default(self, fresh_api_manager):
        """Test that default value is MAX_CONCURRENT_WORKERS."""
        # Arrange
        manager, cf = fresh_api_manager

        # Act
        workers = manager.get_max_concurrent_workers()

        # Assert
        assert workers == MAX_CONCURRENT_WORKERS

    def test_api_manager_set_and_get_workers(self, fresh_api_manager):
        """Test setting and getting worker count."""
        # Arrange
        manager, cf = fresh_api_manager

        # Act
        manager.set_max_concurrent_workers(5)
        result = manager.get_max_concurrent_workers()

        # Assert
        assert result == 5

    def test_api_manager_workers_validation_too_low(self, fresh_api_manager):
        """Test that workers < MIN_CONCURRENT_WORKERS raises ValueError."""
        # Arrange
        manager, cf = fresh_api_manager

        # Act & Assert
        with pytest.raises(ValueError, match="Workers must be between"):
            manager.set_max_concurrent_workers(0)

    def test_api_manager_workers_validation_too_high(self, fresh_api_manager):
        """Test that workers > MAX_CONCURRENT_WORKERS_LIMIT raises ValueError."""
        # Arrange
        manager, cf = fresh_api_manager

        # Act & Assert
        with pytest.raises(ValueError, match="Workers must be between"):
            manager.set_max_concurrent_workers(11)

    def test_api_manager_workers_boundary_values(self, fresh_api_manager):
        """Test that boundary values are accepted."""
        # Arrange
        manager, cf = fresh_api_manager

        # Act & Assert - should not raise
        manager.set_max_concurrent_workers(MIN_CONCURRENT_WORKERS)
        assert manager.get_max_concurrent_workers() == MIN_CONCURRENT_WORKERS

        manager.set_max_concurrent_workers(MAX_CONCURRENT_WORKERS_LIMIT)
        assert manager.get_max_concurrent_workers() == MAX_CONCURRENT_WORKERS_LIMIT

    def test_api_manager_workers_persists_across_instances(self, fresh_api_manager):
        """Test that worker setting persists in config file."""
        # Arrange
        manager1, cf = fresh_api_manager
        manager1.set_max_concurrent_workers(7)

        # Act - create new manager instance
        with patch.object(api_mod, "CONFIG_FILE", cf):
            manager2 = APIManager()
            result = manager2.get_max_concurrent_workers()

        # Assert
        assert result == 7


class TestSessionLoggerThreadSafety:
    """Test that SessionLogger is thread-safe under concurrent access."""

    def test_session_logger_thread_safety(self, tmp_path, monkeypatch):
        """Verify SessionLogger doesn't lose data under concurrent access."""
        # Arrange - monkeypatch the stats/events file paths to use tmp_path
        stats_file = tmp_path / "statistics.json"
        events_file = tmp_path / "events.json"

        import src.utils.session_logger as logger_mod
        monkeypatch.setattr(logger_mod, "STATS_FILE", stats_file)
        monkeypatch.setattr(logger_mod, "EVENTS_FILE", events_file)

        logger = SessionLogger()
        logger.start_session()

        # Act - use ThreadPoolExecutor to call log_file_completed 100 times concurrently
        def log_completion():
            logger.log_file_completed("test_file.mp3", duration_seconds=10.0)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(log_completion) for _ in range(100)]
            # Wait for all to complete
            for future in futures:
                future.result()

        # Assert - verify stats.successful == 100
        assert logger.current_session.successful == 100
        assert logger.current_session.files_count == 100

    def test_session_logger_concurrent_updates_no_race(self, tmp_path, monkeypatch):
        """Test concurrent completed/failed updates don't corrupt statistics."""
        # Arrange
        stats_file = tmp_path / "statistics.json"
        events_file = tmp_path / "events.json"

        import src.utils.session_logger as logger_mod
        monkeypatch.setattr(logger_mod, "STATS_FILE", stats_file)
        monkeypatch.setattr(logger_mod, "EVENTS_FILE", events_file)

        logger = SessionLogger()
        logger.start_session()

        # Act - mix of success and failure
        def log_success():
            logger.log_file_completed("success.mp3", duration_seconds=10.0)

        def log_failure():
            logger.log_file_failed("failure.mp3", "Error")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(50):
                futures.append(executor.submit(log_success))
                futures.append(executor.submit(log_failure))

            for future in futures:
                future.result()

        # Assert
        assert logger.current_session.successful == 50
        assert logger.current_session.failed == 50
        assert logger.current_session.files_count == 100


class TestThreadingEventCancel:
    """Test threading.Event for cancellation."""

    def test_threading_event_cancel(self):
        """Verify threading.Event works for cancellation signal."""
        # Arrange
        cancel_event = threading.Event()
        results = []

        def worker():
            for i in range(10):
                if cancel_event.is_set():
                    results.append("cancelled")
                    return
                time.sleep(0.01)
                results.append(i)

        # Act
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.05)  # Let it do some work
        cancel_event.set()  # Cancel
        thread.join()

        # Assert
        assert "cancelled" in results
        assert len(results) < 11  # Should not complete all iterations

    def test_threading_event_initial_state(self):
        """Test that threading.Event starts unset."""
        # Act
        event = threading.Event()

        # Assert
        assert not event.is_set()

    def test_threading_event_set_and_clear(self):
        """Test setting and clearing event."""
        # Arrange
        event = threading.Event()

        # Act & Assert
        event.set()
        assert event.is_set()

        event.clear()
        assert not event.is_set()


class TestThreadPoolExecutorBasic:
    """Test ThreadPoolExecutor basic functionality."""

    def test_thread_pool_executor_basic(self):
        """Verify ThreadPoolExecutor processes items concurrently."""
        # Arrange
        results = []
        lock = threading.Lock()
        start_time = time.time()

        def worker(value):
            time.sleep(0.1)  # Simulate work
            with lock:
                results.append(value)

        # Act - process 5 items with 5 workers (should take ~0.1s, not 0.5s)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            for future in futures:
                future.result()

        elapsed = time.time() - start_time

        # Assert
        assert len(results) == 5
        assert set(results) == {0, 1, 2, 3, 4}
        # Should complete in ~0.1s (concurrent), not 0.5s (sequential)
        assert elapsed < 0.3  # Allow some overhead

    def test_thread_pool_executor_sequential_mode(self):
        """Test that max_workers=1 forces sequential processing."""
        # Arrange
        results = []
        lock = threading.Lock()

        def worker(value):
            time.sleep(0.05)
            with lock:
                results.append(value)

        # Act - process 3 items with 1 worker
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(worker, i) for i in range(3)]
            for future in futures:
                future.result()

        # Assert
        assert len(results) == 3
        # Results should be in order when sequential
        assert results == [0, 1, 2]

    def test_thread_pool_executor_respects_worker_count(self):
        """Test that ThreadPoolExecutor respects max_workers setting."""
        # Arrange
        active_threads = []
        lock = threading.Lock()
        max_concurrent = 0

        def worker(value):
            thread_id = threading.current_thread().ident
            with lock:
                active_threads.append(thread_id)
                nonlocal max_concurrent
                max_concurrent = max(max_concurrent, len(set(active_threads)))
            time.sleep(0.1)
            with lock:
                active_threads.remove(thread_id)

        # Act - 10 tasks with 3 workers
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            for future in futures:
                future.result()

        # Assert - at most 3 threads should have been active
        assert max_concurrent <= 3


class TestConcurrencyIntegration:
    """Test integration of concurrency components."""

    def test_cancel_event_propagates_to_executor(self):
        """Test that cancel event stops executor workers."""
        # Arrange
        cancel_event = threading.Event()
        completed = []
        cancelled = []

        def worker(value):
            if cancel_event.is_set():
                cancelled.append(value)
                return False
            time.sleep(0.05)
            completed.append(value)
            return True

        # Act
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]

            # Cancel after first few complete
            time.sleep(0.1)
            cancel_event.set()

            # Wait for all futures
            for future in futures:
                future.result()

        # Assert
        assert len(cancelled) > 0  # Some tasks were cancelled
        assert len(completed) < 10  # Not all tasks completed

    def test_worker_count_affects_throughput(self):
        """Test that more workers improve throughput."""
        # Arrange
        def worker():
            time.sleep(0.1)

        # Act - 9 tasks with 1 worker
        start1 = time.time()
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(worker) for _ in range(9)]
            for future in futures:
                future.result()
        time_sequential = time.time() - start1

        # Act - 9 tasks with 3 workers
        start2 = time.time()
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(worker) for _ in range(9)]
            for future in futures:
                future.result()
        time_parallel = time.time() - start2

        # Assert - parallel should be significantly faster
        # 9 tasks: 1 worker = 0.9s, 3 workers = 0.3s
        assert time_parallel < time_sequential * 0.6  # At least 40% faster
