"""
Singleton background writer thread for batch state persistence.

Provides throttled, batched writes to prevent UI lag during high-frequency
state updates (e.g., processing 1000 files concurrently).

Features:
- Singleton pattern (one writer per application)
- Background daemon thread
- Throttling: max 1 write per second
- Batching: multiple queued updates → single write (last state wins)
- Graceful shutdown with flush
- Thread-safe operations

Usage:
    # Initialize at app startup
    writer = BatchStateWriter()

    # Schedule writes (non-blocking)
    writer.schedule_write(batch_state)

    # Flush before critical operations (blocking)
    writer.flush(timeout=5.0)

    # Cleanup at app shutdown
    writer.shutdown()
"""
import logging
import queue
import threading
import time
from typing import Optional

from contracts.batch_state import BatchState
from src.utils.batch_history_manager import BatchHistoryManager

logger = logging.getLogger(__name__)


class BatchStateWriter:
    """Singleton background writer for throttled batch state persistence."""

    _instance: Optional['BatchStateWriter'] = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern - ensure only one instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # Double-check locking
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize writer thread (only once due to singleton)."""
        if self._initialized:
            return

        self._queue: queue.Queue[Optional[BatchState]] = queue.Queue()
        self._shutdown_event = threading.Event()
        self._flush_event = threading.Event()
        self._last_write_time = 0.0
        self._write_interval = 1.0  # Max 1 write per second
        self._thread: Optional[threading.Thread] = None

        # Start background thread
        self._start_thread()
        self._initialized = True

        logger.info("BatchStateWriter initialized")

    def _start_thread(self) -> None:
        """Start background writer thread."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._writer_loop,
                name="BatchStateWriter",
                daemon=True
            )
            self._thread.start()
            logger.debug("Writer thread started")

    def schedule_write(self, state: BatchState) -> None:
        """Schedule a batch state write (non-blocking).

        Adds state to queue. If multiple writes are queued, only the last
        state is written (older states are discarded).

        Args:
            state: BatchState to persist.
        """
        if self._shutdown_event.is_set():
            logger.warning("Writer is shutting down, cannot schedule write")
            return

        try:
            # Non-blocking put with timeout
            self._queue.put(state, timeout=0.1)
            logger.debug(f"Scheduled write for batch {state.batch_id}")
        except queue.Full:
            logger.warning("Write queue full, dropping oldest state")
            # Discard old state, add new one
            try:
                self._queue.get_nowait()  # Remove oldest
                self._queue.put(state, timeout=0.1)  # Add newest
            except (queue.Empty, queue.Full):
                pass

    def flush(self, timeout: float = 5.0) -> bool:
        """Flush pending writes immediately (blocking).

        Waits for all queued writes to complete.

        Args:
            timeout: Maximum seconds to wait for flush.

        Returns:
            True if flushed successfully, False if timeout.
        """
        if self._shutdown_event.is_set():
            logger.warning("Writer is shutting down, cannot flush")
            return False

        logger.debug("Flushing pending writes...")
        self._flush_event.clear()

        # Signal flush request by queueing None
        try:
            self._queue.put(None, timeout=timeout)
        except queue.Full:
            logger.error("Failed to queue flush request (queue full)")
            return False

        # Wait for flush completion
        flushed = self._flush_event.wait(timeout=timeout)

        if flushed:
            logger.debug("Flush completed")
        else:
            logger.warning(f"Flush timed out after {timeout}s")

        return flushed

    def shutdown(self, timeout: float = 5.0) -> None:
        """Shutdown writer thread gracefully.

        Flushes pending writes, then stops thread.

        Args:
            timeout: Maximum seconds to wait for shutdown.
        """
        logger.info("Shutting down BatchStateWriter...")

        # Flush pending writes
        self.flush(timeout=timeout / 2)

        # Signal shutdown
        self._shutdown_event.set()

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout / 2)

            if self._thread.is_alive():
                logger.warning("Writer thread did not stop gracefully")
            else:
                logger.info("Writer thread stopped")

    def _writer_loop(self) -> None:
        """Background writer thread loop.

        Processes queued writes with throttling and batching.
        """
        logger.debug("Writer loop started")

        while not self._shutdown_event.is_set():
            try:
                # Wait for next state (blocking with timeout)
                state = self._queue.get(timeout=0.5)

                # Check for flush signal
                if state is None:
                    self._process_pending_writes()
                    self._flush_event.set()
                    continue

                # Batch multiple updates: drain queue and keep only last state
                latest_state = state
                flush_after_write = False
                while True:
                    try:
                        next_state = self._queue.get_nowait()
                        if next_state is None:
                            # Flush signal during batching — write first, then signal
                            flush_after_write = True
                            break
                        latest_state = next_state  # Keep newest state
                    except queue.Empty:
                        break  # No more queued states

                # Throttle writes (max 1 per second) — skip throttle on flush
                if not flush_after_write:
                    elapsed = time.time() - self._last_write_time
                    if elapsed < self._write_interval:
                        sleep_time = self._write_interval - elapsed
                        logger.debug(f"Throttling write, sleeping {sleep_time:.2f}s")
                        time.sleep(sleep_time)

                # Perform write
                self._write_state(latest_state)

                # Signal flush completion after write is done
                if flush_after_write:
                    self._flush_event.set()

            except queue.Empty:
                continue  # Timeout, check shutdown flag
            except Exception as e:
                logger.error(f"Error in writer loop: {e}", exc_info=True)

        logger.debug("Writer loop exited")

    def _process_pending_writes(self) -> None:
        """Process all pending writes immediately (for flush)."""
        latest_state = None

        # Drain queue
        while True:
            try:
                state = self._queue.get_nowait()
                if state is not None:  # Ignore flush signals
                    latest_state = state
            except queue.Empty:
                break

        # Write latest state if any
        if latest_state:
            self._write_state(latest_state)

    def _write_state(self, state: BatchState) -> None:
        """Write batch state to disk.

        Args:
            state: BatchState to persist.
        """
        try:
            BatchHistoryManager.save_active_batch(state)
            self._last_write_time = time.time()
            logger.debug(f"Wrote batch state: {state.batch_id}")
        except Exception as e:
            logger.error(f"Failed to write batch state: {e}", exc_info=True)
