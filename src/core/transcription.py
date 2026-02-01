"""
Deepgram API integration for transcription using direct HTTP requests.

Security features:
- File streaming to reduce memory usage for large files
- Chunked upload support
"""
import logging
import httpx

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Optional, Callable, Iterator
from dataclasses import dataclass

from config import DEEPGRAM_DEFAULT_MODEL, DEEPGRAM_MAX_FILE_SIZE, API_TIMEOUT, UPLOAD_CHUNK_SIZE


DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen"


@dataclass
class TranscriptionResult:
    """Result of a transcription operation."""

    success: bool
    transcript: Optional[str] = None
    words: Optional[list] = None
    utterances: Optional[list] = None
    paragraphs: Optional[list] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None

    @property
    def has_timestamps(self) -> bool:
        """Check if result contains timestamp data."""
        return self.words is not None and len(self.words) > 0


class TranscriptionService:
    """Service for transcribing audio files using Deepgram API."""

    def __init__(self, api_key: str, model: str = None):
        """
        Initialize the transcription service.

        Args:
            api_key: Deepgram API key for authentication.
            model: Deepgram model name (e.g. "nova-2"). Defaults to config value.
        """
        self.api_key = api_key
        self.model = model or DEEPGRAM_DEFAULT_MODEL

    def _get_content_type(self, file_path: Path) -> str:
        """Get content type based on file extension."""
        ext = file_path.suffix.lower()
        content_types = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".wma": "audio/x-ms-wma",
            ".aac": "audio/aac",
            ".mp4": "video/mp4",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
            ".mov": "video/quicktime",
            ".wmv": "video/x-ms-wmv",
            ".webm": "video/webm",
            ".flv": "video/x-flv",
        }
        return content_types.get(ext, "audio/mpeg")

    def _file_stream(self, file_path: Path) -> Iterator[bytes]:
        """
        Stream file contents in chunks to reduce memory usage.

        Yields chunks of UPLOAD_CHUNK_SIZE bytes.
        """
        file_handle = None
        try:
            file_handle = open(file_path, "rb")
            while True:
                chunk = file_handle.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            if file_handle:
                file_handle.close()

    def _validate_inputs(self, file_path: Path, language: str) -> Optional[TranscriptionResult]:
        """
        Validate file existence and size before transcription.

        Args:
            file_path: Path to the audio file.
            language: Language code to validate.

        Returns:
            A failure TranscriptionResult if validation fails, None if OK.
        """
        if not file_path.exists():
            return TranscriptionResult(
                success=False,
                error_message=f"File does not exist: {file_path}"
            )

        file_size = file_path.stat().st_size
        if file_size > DEEPGRAM_MAX_FILE_SIZE:
            return TranscriptionResult(
                success=False,
                error_message=f"File too large (max 2GB): {file_size / (1024**3):.2f} GB"
            )

        return None

    def _build_request_params(
        self,
        language: str,
        diarize: bool,
        punctuate: bool,
        smart_format: bool,
    ) -> dict:
        """
        Build Deepgram API query parameters.

        Args:
            language: Language code or "auto" for detection.
            diarize: Enable speaker diarization.
            punctuate: Enable automatic punctuation.
            smart_format: Enable smart formatting.

        Returns:
            Dictionary of query parameters.
        """
        params = {
            "model": self.model,
            "punctuate": str(punctuate).lower(),
            "smart_format": str(smart_format).lower(),
            "utterances": "true",
            "paragraphs": "true",
        }

        if language == "auto":
            params["detect_language"] = "true"
        else:
            params["language"] = language

        if diarize:
            params["diarize"] = "true"

        return params

    def _make_request(self, file_path: Path, params: dict) -> 'httpx.Response':
        """
        Send the audio file to the Deepgram API.

        Args:
            file_path: Path to the audio file to upload.
            params: Query parameters for the API.

        Returns:
            The httpx Response object.

        Raises:
            httpx.TimeoutException: On request timeout.
            httpx.RequestError: On connection errors.
        """
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": self._get_content_type(file_path),
        }

        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.post(
                DEEPGRAM_API_URL,
                params=params,
                headers=headers,
                content=self._file_stream(file_path),
            )

        return response

    def _check_response_errors(self, response: 'httpx.Response') -> Optional[TranscriptionResult]:
        """
        Check the HTTP response for error status codes.

        Args:
            response: The httpx Response to check.

        Returns:
            A failure TranscriptionResult if an HTTP error occurred, None if OK.
        """
        if response.status_code == 401:
            return TranscriptionResult(success=False, error_message="Invalid API key")
        elif response.status_code == 403:
            return TranscriptionResult(success=False, error_message="Access denied for this API key")
        elif response.status_code == 429:
            return TranscriptionResult(success=False, error_message="API rate limit exceeded")
        elif response.status_code >= 400:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("err_msg", f"HTTP error {response.status_code}")
            return TranscriptionResult(success=False, error_message=error_msg)
        return None

    def _parse_response(self, data: dict) -> TranscriptionResult:
        """
        Parse the Deepgram API JSON response into a TranscriptionResult.

        Args:
            data: Parsed JSON response dictionary.

        Returns:
            TranscriptionResult with extracted transcript, words, utterances,
            paragraphs, and duration.
        """
        results = data.get("results", {})
        metadata = data.get("metadata", {})

        channels = results.get("channels", [])
        if not channels:
            return TranscriptionResult(success=False, error_message="No transcription results")

        channel = channels[0]
        alternatives = channel.get("alternatives", [])

        if not alternatives:
            return TranscriptionResult(success=False, error_message="No transcript alternatives")

        alternative = alternatives[0]
        duration = metadata.get("duration")

        # Extract utterances
        utterances = None
        utterances_data = results.get("utterances", [])
        if utterances_data:
            utterances = [
                {
                    "start": u.get("start", 0),
                    "end": u.get("end", 0),
                    "text": u.get("transcript", ""),
                    "speaker": u.get("speaker"),
                }
                for u in utterances_data
            ]

        # Extract words with timestamps
        words = None
        words_data = alternative.get("words", [])
        if words_data:
            words = [
                {
                    "word": w.get("word", ""),
                    "start": w.get("start", 0),
                    "end": w.get("end", 0),
                    "confidence": w.get("confidence", 0),
                    "speaker": w.get("speaker"),
                }
                for w in words_data
            ]

        # Extract paragraphs
        paragraphs = None
        paragraphs_data = alternative.get("paragraphs", {})
        if paragraphs_data:
            paragraphs_list = paragraphs_data.get("paragraphs", [])
            if paragraphs_list:
                paragraphs = []
                for p in paragraphs_list:
                    sentences = p.get("sentences", [])
                    text = " ".join(s.get("text", "") for s in sentences)
                    paragraphs.append({
                        "text": text,
                        "start": p.get("start"),
                        "end": p.get("end"),
                        "speaker": p.get("speaker"),
                    })

        return TranscriptionResult(
            success=True,
            transcript=alternative.get("transcript", ""),
            words=words,
            utterances=utterances,
            paragraphs=paragraphs,
            duration_seconds=duration,
        )

    def transcribe(
        self,
        file_path: Path,
        language: str = "pl",
        diarize: bool = False,
        punctuate: bool = True,
        smart_format: bool = True,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> TranscriptionResult:
        """
        Transcribe an audio file using the Deepgram API.

        Orchestrates validation, parameter building, HTTP request, and
        response parsing. Each step is delegated to a focused helper method.

        Args:
            file_path: Path to the audio file
            language: Language code (e.g., "pl", "en") or "auto"
            diarize: Enable speaker diarization
            punctuate: Enable automatic punctuation
            smart_format: Enable smart formatting
            progress_callback: Optional callback for progress updates

        Returns:
            TranscriptionResult with transcript and metadata
        """
        file_path = Path(file_path)

        # Step 1: Validate inputs
        validation_error = self._validate_inputs(file_path, language)
        if validation_error is not None:
            return validation_error

        if progress_callback:
            progress_callback("Preparing file...")

        try:
            # Step 2: Build request parameters
            params = self._build_request_params(language, diarize, punctuate, smart_format)

            if progress_callback:
                progress_callback("Sending to Deepgram API...")

            # Step 3: Make HTTP request
            response = self._make_request(file_path, params)

            # Step 4: Check for HTTP errors
            http_error = self._check_response_errors(response)
            if http_error is not None:
                return http_error

            if progress_callback:
                progress_callback("Processing response...")

            # Step 5: Parse response
            data = response.json()
            return self._parse_response(data)

        except httpx.TimeoutException:
            return TranscriptionResult(
                success=False,
                error_message="Timeout - operation took too long"
            )
        except httpx.RequestError as e:
            return TranscriptionResult(
                success=False,
                error_message=f"Connection error: {str(e)}"
            )
        except Exception as e:
            return TranscriptionResult(
                success=False,
                error_message=f"Transcription error: {str(e)}"
            )
