"""
Transcription orchestrator -- extracts business logic from GUI.

Processes a single file through the transcription pipeline:
  1. Convert video to MP3 (if needed)
  2. Transcribe audio via Deepgram API
  3. Save output in requested format

Communicates progress via an event callback (observer pattern),
keeping this module completely free of GUI dependencies.
"""
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.core.media_converter import MediaConverter
from src.core.transcription import TranscriptionService, TranscriptionResult
from src.core.output_writer import OutputWriter
from src.models.media_file import MediaFile, TranscriptionStatus, ErrorCategory
from src.utils.session_logger import SessionLogger

logger = logging.getLogger(__name__)

# Type alias for the event callback signature
EventCallback = Callable[[str, MediaFile, Dict[str, Any]], None]


class CancelledException(Exception):
    """Raised when a cancel event is detected during processing."""
    pass


class TranscriptionOrchestrator:
    """
    Orchestrates the file transcription workflow without GUI dependencies.

    Emits events at each stage so that callers (GUI or CLI) can react:
        - 'converting'   -- before FFmpeg conversion (video files only)
        - 'transcribing' -- before Deepgram API call
        - 'saving'       -- before writing the output file
        - 'completed'    -- on successful completion
        - 'failed'       -- on any error

    Usage:
        orchestrator = TranscriptionOrchestrator(
            converter=converter,
            transcription_service=service,
            output_writer=writer,
            logger=session_logger,
            event_callback=my_callback,
        )
        success = orchestrator.process_file(file, "txt", output_dir, "en", False, True)
    """

    def __init__(
        self,
        converter: MediaConverter,
        transcription_service: TranscriptionService,
        output_writer: OutputWriter,
        session_logger: SessionLogger,
        event_callback: Optional[EventCallback] = None,
        cancel_event: Optional["threading.Event"] = None,
    ) -> None:
        """
        Initialize the orchestrator with its dependencies.

        Args:
            converter: MediaConverter instance for video-to-MP3 conversion.
            transcription_service: TranscriptionService for Deepgram API calls.
            output_writer: OutputWriter for saving transcription results.
            session_logger: SessionLogger for event/statistics logging.
            event_callback: Optional callback ``(event_type, file, extra_dict)``
                            invoked at each pipeline stage.
            cancel_event: Optional threading.Event checked before each pipeline step.
        """
        self.converter = converter
        self.transcription_service = transcription_service
        self.output_writer = output_writer
        self.session_logger = session_logger
        self.event_callback = event_callback
        self.cancel_event = cancel_event

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_file(
        self,
        file: MediaFile,
        output_format: str,
        output_dir: Optional[Path],
        language: str,
        diarize: bool,
        smart_format: bool,
    ) -> bool:
        """
        Process a single file through the full transcription pipeline.

        Args:
            file: The MediaFile to process.
            output_format: Desired output format ("txt", "srt", "vtt").
            output_dir: Directory for output files (None = next to source).
            language: Language code (e.g. "en", "pl", "auto").
            diarize: Whether to enable speaker diarization.
            smart_format: Whether to enable Deepgram smart formatting.

        Returns:
            True on success, False on failure.
        """
        temp_mp3_path: Optional[Path] = None

        try:
            self._check_cancelled()

            # Step 1: Convert video to MP3 if necessary
            if file.is_video:
                file.status = TranscriptionStatus.CONVERTING
                self.session_logger.log_converting(file.name)
                self._emit("converting", file, {})

                temp_mp3_path = self.converter.to_mp3(file.path)
                audio_path = temp_mp3_path
            else:
                audio_path = file.path

            self._check_cancelled()

            # Step 2: Transcribe via Deepgram
            file.status = TranscriptionStatus.TRANSCRIBING
            self.session_logger.log_transcribing(file.name)
            self._emit("transcribing", file, {})

            result: TranscriptionResult = self.transcription_service.transcribe(
                file_path=audio_path,
                language=language,
                diarize=diarize,
                smart_format=smart_format,
            )

            if not result.success:
                raise Exception(result.error_message or "Transcription failed")

            self._check_cancelled()

            # Step 3: Save output
            self._emit("saving", file, {})

            output_path = self.output_writer.save(
                result=result,
                source_path=file.path,
                output_format=output_format,
                output_dir=output_dir,
            )

            # Mark success
            file.status = TranscriptionStatus.COMPLETED
            file.output_path = output_path
            file.error_message = None
            file.error_category = ErrorCategory.NONE

            duration = result.duration_seconds or 0
            self.session_logger.log_file_completed(file.name, duration)

            self._emit("completed", file, {"output_path": output_path})
            return True

        except CancelledException:
            file.status = TranscriptionStatus.SKIPPED
            file.error_message = "Cancelled by user"
            self._emit("failed", file, {"error": "Cancelled by user"})
            return False

        except Exception as e:
            file.status = TranscriptionStatus.FAILED
            file.error_message = str(e)

            self.session_logger.log_file_failed(file.name, str(e))
            self._emit("failed", file, {"error": str(e)})

            return False

        finally:
            # Always clean up the temp MP3 produced by conversion
            if temp_mp3_path is not None:
                self.converter.cleanup(temp_mp3_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(self, event_type: str, file: MediaFile, extra: Dict[str, Any]) -> None:
        """
        Emit an event to the registered callback, if any.

        Args:
            event_type: One of 'converting', 'transcribing', 'saving',
                        'completed', 'failed'.
            file: The MediaFile being processed.
            extra: Additional event data as a dictionary.
        """
        if self.event_callback is not None:
            try:
                self.event_callback(event_type, file, extra)
            except Exception as exc:
                logger.debug("Event callback raised: %s", exc)

    def _check_cancelled(self) -> None:
        """Raise CancelledException if the cancel event is set."""
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise CancelledException("Processing cancelled")
