"""
Pydantic models for batch state persistence.

Models:
    - TranscriptionStatusEnum: File processing status enumeration
    - BatchStatus: Batch lifecycle status enumeration
    - BatchSettings: Configuration for a batch transcription session
    - FileState: State of a single file in the batch
    - BatchStatistics: Aggregated statistics for the batch
    - BatchState: Complete state of a transcription batch
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TranscriptionStatusEnum(str, Enum):
    """Status of a file in the transcription batch."""
    PENDING = "pending"
    CONVERTING = "converting"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BatchStatus(str, Enum):
    """Lifecycle status of a batch."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class BatchSettings(BaseModel):
    """Settings used for batch transcription."""
    output_format: str
    output_dir: Optional[str] = None
    language: str
    diarize: bool
    smart_format: bool
    max_concurrent_workers: int


class FileState(BaseModel):
    """State of a single file in the batch."""
    source_path: str
    status: TranscriptionStatusEnum
    output_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    retry_count: int = 0
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class BatchStatistics(BaseModel):
    """Aggregated statistics for the batch."""
    total_files: int
    completed: int = 0
    failed: int = 0
    pending: int
    total_duration_seconds: float = 0.0


class BatchState(BaseModel):
    """Complete state of a transcription batch for persistence."""
    batch_id: str
    created_at: datetime
    last_updated: datetime
    settings: BatchSettings
    files: List[FileState]
    statistics: BatchStatistics
    status: BatchStatus = BatchStatus.ACTIVE
    completed_at: Optional[datetime] = None
    archived: bool = False
