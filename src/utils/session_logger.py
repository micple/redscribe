"""
Session logger for tracking transcription events and statistics.

Handles:
- Event logging (info, success, warning, error)
- Session statistics
- All-time statistics persistence
- Cost calculation
"""
import logging
import json

_module_logger = logging.getLogger(__name__)
import uuid
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, List
from enum import Enum

from config import LOGS_DIR


# File paths
STATS_FILE = LOGS_DIR / "statistics.json"
EVENTS_FILE = LOGS_DIR / "events.json"


class LogLevel(Enum):
    """Log entry severity level."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CONVERTING = "converting"
    TRANSCRIBING = "transcribing"


@dataclass
class LogEntry:
    """Single log entry."""
    timestamp: str
    level: str
    message: str
    file_name: Optional[str] = None
    details: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "LogEntry":
        return cls(**data)


@dataclass
class SessionStats:
    """Statistics for a single session."""
    id: str
    started: str
    ended: Optional[str] = None
    files_count: int = 0
    successful: int = 0
    failed: int = 0
    duration_seconds: float = 0.0
    cost_usd: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionStats":
        return cls(**data)


@dataclass
class AllTimeStats:
    """Cumulative statistics across all sessions."""
    total_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    total_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0
    first_session: Optional[str] = None
    last_session: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AllTimeStats":
        return cls(**data)


class SessionLogger:
    """
    Manages logging and statistics for transcription sessions.

    Usage:
        logger = SessionLogger()
        logger.start_session()
        logger.log_info("Started processing")
        logger.log_file_completed("audio.mp3", duration=60.5, cost=0.05)
        logger.end_session()
    """

    # Deepgram pricing per minute
    PRICING = {
        "nova-2": 0.0043,
        "nova-3": 0.0059,
    }

    def __init__(self):
        """Initialize the session logger and load persisted stats and events."""
        self.current_session: Optional[SessionStats] = None
        # App session - cumulative stats from app start to close (not persisted)
        self.app_session: SessionStats = SessionStats(
            id="app",
            started=datetime.now().isoformat(),
        )
        self.all_time: AllTimeStats = AllTimeStats()
        self.events: List[LogEntry] = []
        self.on_event: Optional[Callable[[LogEntry], None]] = None
        self.on_stats_update: Optional[Callable[[], None]] = None
        self.model: str = "nova-2"

        # Load persisted data
        self._load_stats()
        self._load_events()

    def _load_stats(self) -> None:
        """Load statistics from file."""
        try:
            if STATS_FILE.exists():
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "all_time" in data:
                        self.all_time = AllTimeStats.from_dict(data["all_time"])
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # Start fresh if file is corrupted

    def _save_stats(self) -> None:
        """Save statistics to file."""
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "all_time": self.all_time.to_dict(),
            }
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass  # Ignore save errors

    def _load_events(self) -> None:
        """Load events from file."""
        try:
            if EVENTS_FILE.exists():
                with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.events = [LogEntry.from_dict(e) for e in data]
        except (json.JSONDecodeError, KeyError, TypeError):
            self.events = []

    def _save_events(self) -> None:
        """Save events to file."""
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            data = [e.to_dict() for e in self.events]
            with open(EVENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def _add_event(self, level: LogLevel, message: str,
                   file_name: Optional[str] = None, details: Optional[str] = None) -> None:
        """Add a log entry."""
        entry = LogEntry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            level=level.value,
            message=message,
            file_name=file_name,
            details=details,
        )
        self.events.append(entry)
        self._save_events()

        # Notify UI
        if self.on_event:
            self.on_event(entry)

    def _notify_stats_update(self) -> None:
        """Notify UI of stats change."""
        if self.on_stats_update:
            self.on_stats_update()

    def set_model(self, model: str) -> None:
        """Set the transcription model for cost calculation."""
        self.model = model

    def calculate_cost(self, duration_seconds: float) -> float:
        """Calculate transcription cost based on audio duration and selected model.

        Args:
            duration_seconds: Audio duration in seconds.

        Returns:
            Estimated cost in USD.
        """
        rate = self.PRICING.get(self.model, self.PRICING["nova-2"])
        minutes = duration_seconds / 60
        return round(minutes * rate, 4)

    # === Session Management ===

    def start_session(self) -> None:
        """Start a new transcription session."""
        now = datetime.now().isoformat()
        self.current_session = SessionStats(
            id=str(uuid.uuid4())[:8],
            started=now,
        )

        # Update all-time
        if not self.all_time.first_session:
            self.all_time.first_session = now
        self.all_time.last_session = now

        self._add_event(LogLevel.INFO, "Started transcription session")
        self._notify_stats_update()

    def end_session(self) -> None:
        """End the current session and persist stats."""
        if not self.current_session:
            return

        self.current_session.ended = datetime.now().isoformat()

        # Update all-time stats
        self.all_time.total_files += self.current_session.files_count
        self.all_time.successful_files += self.current_session.successful
        self.all_time.failed_files += self.current_session.failed
        self.all_time.total_duration_seconds += self.current_session.duration_seconds
        self.all_time.total_cost_usd += self.current_session.cost_usd

        self._save_stats()

        # Log summary with duration
        duration_str = self._format_duration(self.current_session.duration_seconds)
        self._add_event(
            LogLevel.INFO,
            f"Session ended: {self.current_session.successful}/{self.current_session.files_count} files, "
            f"{duration_str}, ${self.current_session.cost_usd:.2f}"
        )

        # Accumulate to app session (visible until app closes)
        self.app_session.files_count += self.current_session.files_count
        self.app_session.successful += self.current_session.successful
        self.app_session.failed += self.current_session.failed
        self.app_session.duration_seconds += self.current_session.duration_seconds
        self.app_session.cost_usd += self.current_session.cost_usd

        self.current_session = None
        self._notify_stats_update()

    # === Logging Methods ===

    def log_info(self, message: str, file_name: Optional[str] = None) -> None:
        """Log an info message."""
        self._add_event(LogLevel.INFO, message, file_name)

    def log_success(self, message: str, file_name: Optional[str] = None) -> None:
        """Log a success message."""
        self._add_event(LogLevel.SUCCESS, message, file_name)

    def log_warning(self, message: str, file_name: Optional[str] = None) -> None:
        """Log a warning message."""
        self._add_event(LogLevel.WARNING, message, file_name)

    def log_error(self, message: str, file_name: Optional[str] = None, details: Optional[str] = None) -> None:
        """Log an error message."""
        self._add_event(LogLevel.ERROR, message, file_name, details)

    def log_converting(self, file_name: str) -> None:
        """Log file conversion start."""
        self._add_event(LogLevel.CONVERTING, f"Converting to MP3", file_name)

    def log_transcribing(self, file_name: str) -> None:
        """Log transcription start."""
        self._add_event(LogLevel.TRANSCRIBING, f"Transcribing", file_name)

    def log_file_completed(self, file_name: str, duration_seconds: float = 0) -> None:
        """Log successful file completion and update session statistics.

        Args:
            file_name: Name of the completed file.
            duration_seconds: Audio duration in seconds (for cost calculation).
        """
        cost = self.calculate_cost(duration_seconds)

        if self.current_session:
            self.current_session.files_count += 1
            self.current_session.successful += 1
            self.current_session.duration_seconds += duration_seconds
            self.current_session.cost_usd += cost

        duration_str = self._format_duration(duration_seconds) if duration_seconds else ""
        self._add_event(
            LogLevel.SUCCESS,
            f"Completed{f' ({duration_str})' if duration_str else ''}",
            file_name
        )
        self._notify_stats_update()

    def log_file_failed(self, file_name: str, error: str) -> None:
        """Log file failure and update session statistics.

        Args:
            file_name: Name of the failed file.
            error: Error message describing the failure.
        """
        if self.current_session:
            self.current_session.files_count += 1
            self.current_session.failed += 1

        self._add_event(LogLevel.ERROR, f"Failed: {error[:50]}", file_name)
        self._notify_stats_update()

    def log_retry(self, file_name: str, attempt: int) -> None:
        """Log retry attempt."""
        self._add_event(LogLevel.WARNING, f"Retrying (attempt {attempt})", file_name)

    # === Utility Methods ===

    def _format_duration(self, seconds: float) -> str:
        """Format duration for display."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}min"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

    def format_duration_long(self, seconds: float) -> str:
        """Format duration with hours:minutes."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}min"
        return f"{minutes}min"

    def clear_events(self) -> None:
        """Clear all logged events."""
        self.events = []
        self._save_events()
        self._notify_stats_update()

    def reset_stats(self) -> None:
        """Reset all statistics."""
        self.all_time = AllTimeStats()
        self.current_session = None
        self._save_stats()
        self._notify_stats_update()

    def get_success_rate(self) -> float:
        """Get overall success rate as percentage."""
        total = self.all_time.total_files
        if total == 0:
            return 100.0
        return round((self.all_time.successful_files / total) * 100, 1)

    def get_cost_per_hour(self) -> float:
        """Get average cost per hour of audio."""
        hours = self.all_time.total_duration_seconds / 3600
        if hours == 0:
            return 0.0
        return round(self.all_time.total_cost_usd / hours, 2)

    def export_stats_csv(self, path: Path) -> bool:
        """Export all-time statistics to a CSV file.

        Args:
            path: Destination file path for the CSV export.

        Returns:
            True if export succeeded, False on I/O error.
        """
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Metric,Value\n")
                f.write(f"Total Files,{self.all_time.total_files}\n")
                f.write(f"Successful,{self.all_time.successful_files}\n")
                f.write(f"Failed,{self.all_time.failed_files}\n")
                f.write(f"Success Rate,{self.get_success_rate()}%\n")
                f.write(f"Total Duration (hours),{self.all_time.total_duration_seconds / 3600:.2f}\n")
                f.write(f"Total Cost (USD),{self.all_time.total_cost_usd:.2f}\n")
                f.write(f"Cost per Hour,{self.get_cost_per_hour():.2f}\n")
                f.write(f"First Session,{self.all_time.first_session or 'N/A'}\n")
                f.write(f"Last Session,{self.all_time.last_session or 'N/A'}\n")
            return True
        except OSError:
            return False


# Global logger instance
_logger: Optional[SessionLogger] = None


def get_logger() -> SessionLogger:
    """Get the global logger instance."""
    global _logger
    if _logger is None:
        _logger = SessionLogger()
    return _logger
