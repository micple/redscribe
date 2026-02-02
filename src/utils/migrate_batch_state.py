"""
Migration utility for old batch_state.json to new batches/ structure.

Migrates from:
    APPDATA_DIR/batch_state.json

To:
    APPDATA_DIR/batches/active.json

Creates backup of old file before migration.
Safe to run multiple times (idempotent).

Usage:
    from src.utils.migrate_batch_state import migrate_old_batch_state

    if migrate_old_batch_state():
        print("Migration completed successfully")
"""
import logging
import shutil
from pathlib import Path
from datetime import datetime

from config import APPDATA_DIR
from src.utils.batch_state_manager import BatchStateManager
from src.utils.batch_history_manager import BatchHistoryManager

logger = logging.getLogger(__name__)


def migrate_old_batch_state() -> bool:
    """Migrate old batch_state.json to new batches/active.json structure.

    Steps:
    1. Check if old batch_state.json exists
    2. Check if new active.json already exists (skip if yes)
    3. Backup old file
    4. Load old state
    5. Save to new active.json
    6. Remove old file (backup remains)

    Returns:
        True if migration was performed, False if not needed or failed.
    """
    old_file = BatchStateManager.STATE_FILE
    new_file = BatchHistoryManager.ACTIVE_FILE

    # Check if old file exists
    if not old_file.exists():
        logger.debug("No old batch_state.json to migrate")
        return False

    # Check if already migrated (new file exists)
    if new_file.exists():
        logger.info("Migration already completed (active.json exists)")
        # Clean up old file if it still exists
        try:
            if old_file.exists():
                _backup_old_file(old_file)
                old_file.unlink()
                logger.info("Removed old batch_state.json after migration")
        except OSError as e:
            logger.warning(f"Failed to remove old file: {e}")
        return False

    logger.info("Starting batch state migration...")

    try:
        # Backup old file
        backup_path = _backup_old_file(old_file)
        if not backup_path:
            logger.error("Failed to create backup, aborting migration")
            return False

        # Load old state
        old_state = BatchStateManager.load_batch_state()
        if not old_state:
            logger.error("Failed to load old batch state, aborting migration")
            return False

        # Save to new location
        BatchHistoryManager.save_active_batch(old_state)
        logger.info(f"Migrated batch {old_state.batch_id} to new structure")

        # Remove old file (backup exists)
        old_file.unlink()
        logger.info(f"Migration complete. Backup at: {backup_path}")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


def _backup_old_file(old_file: Path) -> Path:
    """Create timestamped backup of old batch_state.json.

    Args:
        old_file: Path to old batch_state.json.

    Returns:
        Path to backup file, or None if backup failed.
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = old_file.with_suffix(f".backup_{timestamp}.json")
        shutil.copy2(old_file, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return backup_path
    except OSError as e:
        logger.error(f"Failed to create backup: {e}")
        return None
