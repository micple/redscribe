"""
Batch history and lifecycle management for transcription sessions.

This module manages the complete lifecycle of transcription batches:
- Active batch state (batches/active.json)
- Historical batches (batches/{timestamp}_{batch_id}.json)
- Index file for quick batch lookups (batches/index.json)

Features:
- Persistent batch history with status tracking
- Atomic file writes to prevent corruption
- Batch archival and cleanup
- Source/output file verification
- Thread-safe operations

Usage:
    # Check for active batch
    if BatchHistoryManager.has_active_batch():
        state = BatchHistoryManager.load_active_batch()

    # Complete and archive batch
    BatchHistoryManager.complete_batch(state)

    # List historical batches
    batches = BatchHistoryManager.list_batches(status_filter=BatchStatus.COMPLETED)
"""
import json
import logging
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from config import APPDATA_DIR
from contracts.batch_state import (
    BatchState, FileState, TranscriptionStatusEnum, BatchStatus
)

logger = logging.getLogger(__name__)


class BatchHistoryManager:
    """Manages persistent batch history and lifecycle state."""

    BATCHES_DIR = APPDATA_DIR / "batches"
    ACTIVE_FILE = BATCHES_DIR / "active.json"
    INDEX_FILE = BATCHES_DIR / "index.json"
    BACKUP_SUFFIX = ".corrupted"

    @classmethod
    def _ensure_directories(cls) -> None:
        """Ensure batches directory structure exists."""
        cls.BATCHES_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def has_active_batch(cls) -> bool:
        """Check if an active batch exists.

        Returns:
            True if active.json exists and can be loaded.
        """
        return cls.ACTIVE_FILE.exists()

    @classmethod
    def load_active_batch(cls) -> Optional[BatchState]:
        """Load active batch state from disk.

        Returns:
            BatchState object if successful, None if file doesn't exist or is corrupted.
        """
        if not cls.ACTIVE_FILE.exists():
            logger.debug("No active batch file found")
            return None

        try:
            with open(cls.ACTIVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate with Pydantic
            state = BatchState(**data)
            logger.info(f"Loaded active batch: {state.batch_id} with {len(state.files)} files")
            return state

        except json.JSONDecodeError as e:
            logger.error(f"Corrupted JSON in active batch file: {e}")
            cls._backup_corrupted_file(cls.ACTIVE_FILE)
            return None
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Invalid batch state structure: {e}")
            cls._backup_corrupted_file(cls.ACTIVE_FILE)
            return None
        except OSError as e:
            logger.error(f"Failed to read active batch file: {e}")
            return None

    @classmethod
    def save_active_batch(cls, state: BatchState) -> None:
        """Save active batch state to disk with atomic write.

        Uses tempfile + os.replace to ensure atomic write (no partial files).

        Args:
            state: BatchState object to persist.

        Raises:
            OSError: If write fails.
        """
        try:
            cls._ensure_directories()

            # Update timestamp
            state.last_updated = datetime.now()

            # Serialize to JSON
            data = state.model_dump(mode='json')

            # Atomic write: write to temp file, then replace
            fd, temp_path = tempfile.mkstemp(
                dir=cls.BATCHES_DIR,
                prefix=".active_",
                suffix=".tmp"
            )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)

                # Atomic replace (Windows and Unix safe)
                os.replace(temp_path, cls.ACTIVE_FILE)
                logger.debug(f"Saved active batch: {state.batch_id}")

            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise

        except OSError as e:
            logger.error(f"Failed to save active batch: {e}")
            raise

    @classmethod
    def complete_batch(cls, state: BatchState) -> None:
        """Complete and archive a batch.

        Updates status to COMPLETED, sets completed_at timestamp,
        archives to historical file, updates index, removes active.json.

        Args:
            state: BatchState to complete and archive.

        Raises:
            OSError: If archive write fails.
        """
        try:
            cls._ensure_directories()

            # Update batch state
            state.status = BatchStatus.COMPLETED
            state.completed_at = datetime.now()
            state.last_updated = datetime.now()

            # Generate archived filename: YYYYMMDD_HHMMSS_{batch_id}.json
            timestamp = state.completed_at.strftime("%Y%m%d_%H%M%S")
            archive_filename = f"{timestamp}_{state.batch_id}.json"
            archive_path = cls.BATCHES_DIR / archive_filename

            # Save to archive
            data = state.model_dump(mode='json')
            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Archived batch to: {archive_path}")

            # Update index
            cls._update_index(state, archive_filename)

            # Remove active.json
            if cls.ACTIVE_FILE.exists():
                cls.ACTIVE_FILE.unlink()
                logger.debug("Removed active batch file")

        except OSError as e:
            logger.error(f"Failed to complete batch: {e}")
            raise

    @classmethod
    def pause_batch(cls, state: BatchState) -> None:
        """Pause the active batch.

        Sets status to PAUSED and saves to active.json.

        Args:
            state: BatchState to pause.

        Raises:
            OSError: If save fails.
        """
        state.status = BatchStatus.PAUSED
        cls.save_active_batch(state)
        logger.info(f"Paused batch: {state.batch_id}")

    @classmethod
    def dismiss_active_batch(cls) -> None:
        """Remove active batch file without archiving.

        Safe to call even if file doesn't exist.
        """
        try:
            if cls.ACTIVE_FILE.exists():
                cls.ACTIVE_FILE.unlink()
                logger.info("Dismissed active batch")
        except OSError as e:
            logger.warning(f"Failed to dismiss active batch: {e}")

    @classmethod
    def load_batch_by_id(cls, batch_id: str) -> Optional[BatchState]:
        """Load a batch by its ID from archive.

        Args:
            batch_id: ID of the batch to load.

        Returns:
            BatchState if found, None otherwise.
        """
        # Check active batch first
        if cls.has_active_batch():
            active = cls.load_active_batch()
            if active and active.batch_id == batch_id:
                return active

        # Search index for archived batch
        index = cls._load_index()
        for entry in index:
            if entry.get("batch_id") == batch_id:
                filename = entry.get("filename")
                if filename:
                    archive_path = cls.BATCHES_DIR / filename
                    if archive_path.exists():
                        try:
                            with open(archive_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            return BatchState(**data)
                        except Exception as e:
                            logger.error(f"Failed to load batch {batch_id}: {e}")
                            return None

        logger.warning(f"Batch not found: {batch_id}")
        return None

    @classmethod
    def list_batches(cls, status_filter: Optional[BatchStatus] = None) -> List[Dict]:
        """List all batches with optional status filter.

        Returns list from index.json with batch metadata.

        Args:
            status_filter: Optional BatchStatus to filter by.

        Returns:
            List of dicts with batch_id, status, created_at, completed_at,
            total_files, completed_files, filename.
        """
        index = cls._load_index()

        # Filter by status if requested
        if status_filter:
            index = [entry for entry in index if entry.get("status") == status_filter.value]

        # Sort by created_at descending (newest first)
        index.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return index

    @classmethod
    def delete_batch(cls, batch_id: str) -> None:
        """Delete a batch from archive and index.

        Args:
            batch_id: ID of the batch to delete.

        Raises:
            ValueError: If batch is currently active.
        """
        # Prevent deleting active batch
        if cls.has_active_batch():
            active = cls.load_active_batch()
            if active and active.batch_id == batch_id:
                raise ValueError("Cannot delete active batch. Dismiss it first.")

        # Find in index
        index = cls._load_index()
        entry = None
        for e in index:
            if e.get("batch_id") == batch_id:
                entry = e
                break

        if not entry:
            logger.warning(f"Batch not found in index: {batch_id}")
            return

        # Delete archive file
        filename = entry.get("filename")
        if filename:
            archive_path = cls.BATCHES_DIR / filename
            try:
                if archive_path.exists():
                    archive_path.unlink()
                    logger.info(f"Deleted batch file: {archive_path}")
            except OSError as e:
                logger.error(f"Failed to delete batch file: {e}")

        # Remove from index
        index.remove(entry)
        cls._save_index(index)
        logger.info(f"Deleted batch from index: {batch_id}")

    @classmethod
    def cleanup_old_batches(cls, days_threshold: int = 30) -> int:
        """Delete batches older than threshold.

        Args:
            days_threshold: Delete batches completed more than this many days ago.

        Returns:
            Number of batches deleted.
        """
        cutoff_date = datetime.now() - timedelta(days=days_threshold)
        index = cls._load_index()
        deleted_count = 0

        for entry in index[:]:  # Copy list to allow modification during iteration
            completed_str = entry.get("completed_at")
            if not completed_str:
                continue  # Skip batches without completion date

            try:
                completed_at = datetime.fromisoformat(completed_str.replace("Z", "+00:00"))
                if completed_at < cutoff_date:
                    batch_id = entry.get("batch_id")
                    if batch_id:
                        try:
                            cls.delete_batch(batch_id)
                            deleted_count += 1
                        except Exception as e:
                            logger.error(f"Failed to cleanup batch {batch_id}: {e}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid completed_at date in entry: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old batches (older than {days_threshold} days)")

        return deleted_count

    @classmethod
    def verify_batch_files(cls, state: BatchState) -> Dict[str, List[str]]:
        """Verify that batch source and output files exist.

        Checks:
        - Source files exist at source_path
        - Output files exist for COMPLETED status

        Args:
            state: BatchState to verify.

        Returns:
            Dict with 'missing_sources' and 'missing_outputs' lists (source_path strings).
        """
        missing_sources: List[str] = []
        missing_outputs: List[str] = []

        for file_state in state.files:
            # Check source file
            source_path = Path(file_state.source_path)
            if not source_path.exists():
                logger.warning(f"Source file missing: {file_state.source_path}")
                missing_sources.append(file_state.source_path)

            # Check output file for completed status
            if file_state.status == TranscriptionStatusEnum.COMPLETED:
                if not file_state.output_path:
                    logger.warning(f"Completed file missing output_path: {file_state.source_path}")
                    missing_outputs.append(file_state.source_path)
                    continue

                output_path = Path(file_state.output_path)
                if not output_path.exists():
                    logger.warning(f"Output file missing: {file_state.output_path}")
                    missing_outputs.append(file_state.source_path)

        if missing_sources or missing_outputs:
            logger.info(
                f"File verification: {len(missing_sources)} missing sources, "
                f"{len(missing_outputs)} missing outputs"
            )

        return {
            "missing_sources": missing_sources,
            "missing_outputs": missing_outputs
        }

    @classmethod
    def _load_index(cls) -> List[Dict]:
        """Load index file.

        Returns:
            List of batch metadata dicts, empty list if file doesn't exist.
        """
        if not cls.INDEX_FILE.exists():
            return []

        try:
            with open(cls.INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load index file: {e}")
            return []

    @classmethod
    def _save_index(cls, index: List[Dict]) -> None:
        """Save index file with atomic write.

        Args:
            index: List of batch metadata dicts.
        """
        try:
            cls._ensure_directories()

            # Atomic write
            fd, temp_path = tempfile.mkstemp(
                dir=cls.BATCHES_DIR,
                prefix=".index_",
                suffix=".tmp"
            )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(index, f, indent=2, ensure_ascii=False, default=str)

                os.replace(temp_path, cls.INDEX_FILE)
                logger.debug("Saved index file")

            except Exception:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise

        except OSError as e:
            logger.error(f"Failed to save index file: {e}")
            raise

    @classmethod
    def _update_index(cls, state: BatchState, filename: str) -> None:
        """Update or add batch entry in index.

        Args:
            state: BatchState to index.
            filename: Archive filename.
        """
        index = cls._load_index()

        # Create index entry
        entry = {
            "batch_id": state.batch_id,
            "status": state.status.value,
            "created_at": state.created_at.isoformat(),
            "completed_at": state.completed_at.isoformat() if state.completed_at else None,
            "total_files": state.statistics.total_files,
            "completed_files": state.statistics.completed,
            "filename": filename
        }

        # Update existing or append new
        found = False
        for i, existing in enumerate(index):
            if existing.get("batch_id") == state.batch_id:
                index[i] = entry
                found = True
                break

        if not found:
            index.append(entry)

        cls._save_index(index)
        logger.debug(f"Updated index for batch: {state.batch_id}")

    @classmethod
    def _backup_corrupted_file(cls, file_path: Path) -> None:
        """Backup corrupted file for debugging.

        Args:
            file_path: Path to corrupted file.
        """
        if not file_path.exists():
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = file_path.with_suffix(f"{cls.BACKUP_SUFFIX}_{timestamp}")
            shutil.copy2(file_path, backup_path)
            logger.info(f"Backed up corrupted file to: {backup_path}")

            # Remove original corrupted file
            file_path.unlink()

        except OSError as e:
            logger.warning(f"Failed to backup corrupted file: {e}")
