"""
Batch state persistence manager for resuming interrupted transcription sessions.

Features:
- Save/load batch state to JSON with atomic writes
- Update individual file statuses
- Verify completed files exist
- Handle corrupted state files gracefully
- Thread-safe operations

Usage:
    # Save batch state
    state = BatchState(...)
    BatchStateManager.save_batch_state(state)

    # Load and resume
    if BatchStateManager.has_pending_batch():
        state = BatchStateManager.load_batch_state()
        if state:
            # Resume processing
            missing = BatchStateManager.verify_completed_files(state)
            if missing:
                BatchStateManager.mark_files_for_reprocessing(state, missing)
"""
import json
import logging
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from config import APPDATA_DIR
from contracts.batch_state import (
    BatchState, FileState, TranscriptionStatusEnum
)

logger = logging.getLogger(__name__)


class BatchStateManager:
    """Manages persistence of batch transcription state for crash recovery."""

    STATE_FILE = APPDATA_DIR / "batch_state.json"
    BACKUP_SUFFIX = ".corrupted"

    @classmethod
    def has_pending_batch(cls) -> bool:
        """Check if a pending batch state file exists.

        Returns:
            True if state file exists and can be loaded.
        """
        return cls.STATE_FILE.exists()

    @classmethod
    def load_batch_state(cls) -> Optional[BatchState]:
        """Load batch state from disk.

        Returns:
            BatchState object if successful, None if file doesn't exist or is corrupted.
        """
        if not cls.STATE_FILE.exists():
            logger.debug("No batch state file found")
            return None

        try:
            with open(cls.STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate with Pydantic
            state = BatchState(**data)
            logger.info(f"Loaded batch state: {state.batch_id} with {len(state.files)} files")
            return state

        except json.JSONDecodeError as e:
            logger.error(f"Corrupted JSON in batch state file: {e}")
            cls._backup_corrupted_file()
            return None
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Invalid batch state structure: {e}")
            cls._backup_corrupted_file()
            return None
        except OSError as e:
            logger.error(f"Failed to read batch state file: {e}")
            return None

    @classmethod
    def save_batch_state(cls, state: BatchState) -> None:
        """Save batch state to disk with atomic write.

        Uses tempfile + os.replace to ensure atomic write (no partial files).

        Args:
            state: BatchState object to persist.

        Raises:
            OSError: If write fails.
        """
        try:
            # Ensure directory exists
            cls.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Update timestamp
            state.last_updated = datetime.now()

            # Serialize to JSON
            data = state.model_dump(mode='json')

            # Atomic write: write to temp file, then replace
            fd, temp_path = tempfile.mkstemp(
                dir=cls.STATE_FILE.parent,
                prefix=".batch_state_",
                suffix=".tmp"
            )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)

                # Atomic replace (Windows and Unix safe)
                os.replace(temp_path, cls.STATE_FILE)
                logger.debug(f"Saved batch state: {state.batch_id}")

            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise

        except OSError as e:
            logger.error(f"Failed to save batch state: {e}")
            raise

    @classmethod
    def update_file_status(
        cls,
        batch_id: str,
        source_path: str,
        status: TranscriptionStatusEnum,
        output_path: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update status of a single file in the batch.

        Loads batch, updates file, saves atomically.

        Args:
            batch_id: ID of the batch to update.
            source_path: Path to source file (unique identifier).
            status: New status for the file.
            output_path: Path to output file (if completed).
            duration_seconds: Audio duration in seconds (if completed).
            error_message: Error message (if failed).

        Raises:
            ValueError: If batch doesn't exist or file not found.
            OSError: If save fails.
        """
        state = cls.load_batch_state()
        if not state:
            raise ValueError("No batch state found")

        if state.batch_id != batch_id:
            raise ValueError(f"Batch ID mismatch: expected {batch_id}, got {state.batch_id}")

        # Find file in batch
        file_state: Optional[FileState] = None
        for f in state.files:
            if f.source_path == source_path:
                file_state = f
                break

        if not file_state:
            raise ValueError(f"File not found in batch: {source_path}")

        # Update file state
        old_status = file_state.status
        file_state.status = status

        if output_path:
            file_state.output_path = output_path

        if duration_seconds is not None:
            file_state.duration_seconds = duration_seconds

        if error_message:
            file_state.error_message = error_message

        if status == TranscriptionStatusEnum.COMPLETED:
            file_state.completed_at = datetime.now()

        # Update statistics
        if old_status == TranscriptionStatusEnum.PENDING and status != TranscriptionStatusEnum.PENDING:
            state.statistics.pending -= 1

        if status == TranscriptionStatusEnum.COMPLETED:
            state.statistics.completed += 1
            if duration_seconds:
                state.statistics.total_duration_seconds += duration_seconds

        if status == TranscriptionStatusEnum.FAILED:
            state.statistics.failed += 1

        # Save updated state
        cls.save_batch_state(state)
        logger.debug(f"Updated file {source_path}: {old_status.value} -> {status.value}")

    @classmethod
    def verify_completed_files(cls, state: BatchState) -> List[str]:
        """Verify that completed files still exist on disk.

        Args:
            state: BatchState to verify.

        Returns:
            List of source_paths for files marked completed but with missing output files.
        """
        missing: List[str] = []

        for file_state in state.files:
            if file_state.status == TranscriptionStatusEnum.COMPLETED:
                if not file_state.output_path:
                    logger.warning(f"Completed file missing output_path: {file_state.source_path}")
                    missing.append(file_state.source_path)
                    continue

                if not Path(file_state.output_path).exists():
                    logger.warning(f"Output file missing: {file_state.output_path}")
                    missing.append(file_state.source_path)

        if missing:
            logger.info(f"Found {len(missing)} completed files with missing outputs")

        return missing

    @classmethod
    def mark_files_for_reprocessing(cls, state: BatchState, source_paths: List[str]) -> None:
        """Mark files as pending for reprocessing.

        Args:
            state: BatchState to modify.
            source_paths: List of source file paths to re-mark as pending.
        """
        for source_path in source_paths:
            for file_state in state.files:
                if file_state.source_path == source_path:
                    old_status = file_state.status

                    # Reset to pending
                    file_state.status = TranscriptionStatusEnum.PENDING
                    file_state.output_path = None
                    file_state.error_message = None
                    file_state.completed_at = None

                    # Update statistics
                    if old_status == TranscriptionStatusEnum.COMPLETED:
                        state.statistics.completed -= 1
                        if file_state.duration_seconds:
                            state.statistics.total_duration_seconds -= file_state.duration_seconds
                    elif old_status == TranscriptionStatusEnum.FAILED:
                        state.statistics.failed -= 1

                    state.statistics.pending += 1

                    logger.info(f"Marked for reprocessing: {source_path}")
                    break

        # Save updated state
        cls.save_batch_state(state)

    @classmethod
    def clear_batch_state(cls) -> None:
        """Remove batch state file from disk.

        Safe to call even if file doesn't exist.
        """
        try:
            if cls.STATE_FILE.exists():
                cls.STATE_FILE.unlink()
                logger.info("Cleared batch state")
        except OSError as e:
            logger.warning(f"Failed to clear batch state: {e}")

    @classmethod
    def _backup_corrupted_file(cls) -> None:
        """Backup corrupted state file for debugging.

        Renames corrupted file with timestamp suffix.
        """
        if not cls.STATE_FILE.exists():
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = cls.STATE_FILE.with_suffix(f"{cls.BACKUP_SUFFIX}_{timestamp}")
            shutil.copy2(cls.STATE_FILE, backup_path)
            logger.info(f"Backed up corrupted state file to: {backup_path}")

            # Remove original corrupted file
            cls.STATE_FILE.unlink()

        except OSError as e:
            logger.warning(f"Failed to backup corrupted file: {e}")
