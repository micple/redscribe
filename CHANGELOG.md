# Changelog

All notable changes to Redscribe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-02-01

### Added
- `TranscriptionOrchestrator` class separating business logic from GUI with event-based progress updates
- `TempFileManager` class for centralized, thread-safe temporary file cleanup with path traversal prevention
- Comprehensive unit test suite with 70+ tests (pytest)
- Test coverage reporting for core and utils modules
- Type hints for core and utils modules
- Logging to file via Python logging module
- `ErrorClassifier` for categorizing transcription errors and retry decisions

### Fixed
- **CRITICAL:** Salt regeneration bug in `APIManager` -- salt was recreated on every call instead of being persisted, which could cause API key loss after restart (Bug #1)
- **HIGH:** Missing timeout for FFmpeg subprocess -- corrupted files could hang conversion indefinitely; added configurable timeout (Bug #2)
- **MEDIUM:** File handle leak in `TranscriptionService._file_stream()` generator -- file handle was not closed if the generator was not fully consumed (Bug #3)
- **MEDIUM:** Race condition in credits refresh allowing multiple concurrent API calls (Bug #4)
- **LOW:** Symlink loop detection in `FileScanner.scan_directory()` -- recursive scanning could loop infinitely on symlink cycles (Bug #5)

### Changed
- Refactored `TranscriptionService.transcribe()` from monolithic method into 5 focused helper methods
- Split `MainWindow._create_widgets()` from 358 lines into logical sections
- Split `SettingsDialog._create_widgets()` from 216 lines into sections
- Split `ProgressDialog._create_widgets()` from 163 lines into sections
- Extracted GUI business logic into `TranscriptionOrchestrator` (testable without GUI)
- Replaced duplicate cleanup methods across MediaConverter, YouTubeDownloader, MainWindow, and YouTubeTab with centralized `TempFileManager`
- Moved magic numbers to `config.py` (FFMPEG_CONVERSION_TIMEOUT, PBKDF2_ITERATIONS, etc.)
- Increased PBKDF2 iterations from 100,000 to 600,000 (OWASP 2023 recommendation)

### Security
- Updated Pillow to >= 11.0.0 (fixes CVE-2024-28219: buffer overflow in libwebp)
- Updated httpx to >= 0.28.0 (improved timeout handling and connection pooling)
- Updated cryptography to >= 43.0.0 (security patches)
- Increased PBKDF2 key derivation iterations to 600,000
- Added path traversal prevention in TempFileManager

### Developer Experience
- Added Google-style docstrings to all public methods in core and utils modules
- Replaced print statements with structured logging
- Added `mypy` and `pytest` to development dependencies

## [1.0.0] - Initial Release

### Added
- Desktop application for batch audio/video transcription using Deepgram AI
- Support for TXT, SRT, VTT output formats
- YouTube download and transcription via yt-dlp
- Speaker diarization
- Multi-language support (12+ languages)
- Encrypted API key storage with machine-bound encryption
- Automatic retry with error classification
- Session logging with statistics
- FFmpeg integration for video-to-audio conversion
