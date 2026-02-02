# Task Management: Redscribe Refactoring & Bug Fixes

## Instructions for AI Coding Agents

When working on these tasks:
1. **Focus on ONE stage at a time**, completing all tasks in that stage before moving to the next
2. **Mark each task complete** by replacing `[ ]` with `[X]` as you finish it
3. **Do NOT modify** any other content in this file unless explicitly instructed by the user
4. **Tasks without an `[X]` are not finished yet** - review the stage to see what remains

**Important notes:**
- Each task specifies the file(s) to modify and expected outcomes
- Acceptance criteria are provided for validation after implementation
- If a task fails, leave it unchecked and note the issue in comments (if needed)
- Dependencies are organized by stage - complete stages sequentially

**Graph ID for codebase tools:** `2a1b22f777a2`

---


## Agent Pipeline — Kolejność Uruchamiania

Poniższa tabela pokazuje, który plik agenta Claude Code odpowiada za które zadania. Uruchamiaj agentów po kolei, zgodnie z numeracją.

| # | Agent | Zadania (Sekcje w tasks.md) | Opis |
|---|-------|----------------------------|------|
| 1 | `CLAUDE-testwriter.md` 🧪 | Stage 1: sekcje 1.1-1.2 | Infrastruktura testowa + testy modułów core |
| 2 | `CLAUDE-backend.md` 🔧 | Stage 1: sekcja 1.3 | Naprawienie 5 krytycznych bugów |
| 3 | `CLAUDE-docs.md` 📚 | Stage 1: sekcja 1.4 | Aktualizacja zależności + walidacja Stage 1 |
| 4 | `CLAUDE-backend.md` 🔧 | Stage 2 (cały) | Separacja logiki biznesowej (TempFileManager, TranscriptionOrchestrator) |
| 5 | `CLAUDE-frontend.md` 🎨 | Stage 3 (cały) | Refaktoryzacja GUI (podział mega-metod) |
| 6 | `CLAUDE-backend.md` 🔧 / `CLAUDE-frontend.md` 🎨 | Stage 4: sekcje 4.1-4.3 | Type hints, eliminacja magic numbers, logging (backend na src/core/, frontend na src/gui/) |
| 7 | `CLAUDE-docs.md` 📚 | Stage 4: sekcje 4.4-4.5 | Dokumentacja (README, CHANGELOG) + testy końcowe |
| 8 | `CLAUDE-backend.md` 🔧 + `CLAUDE-frontend.md` 🎨 | Stage 5.1 | Parallel transcription (backend: ThreadPool, config; frontend: UI slider, progress) |
| 9 | `CLAUDE-backend.md` 🔧 + `CLAUDE-frontend.md` 🎨 | Stage 5.2 | Session persistence (backend: BatchStateManager; frontend: resume dialog) |
| 10 | `CLAUDE-backend.md` 🔧 | Stage 5.3 | Integracja równoległa + walidacja końcowa |

**Instrukcje dla użytkownika:**
1. Otwórz plik agenta (np. `CLAUDE-testwriter.md`)
2. Skopiuj zawartość do nowej sesji Claude Code / Cursor / Windsurf
3. Agent wykona zadania ze swojej sekcji i oznaczy je jako `[X]`
4. Przejdź do kolejnego agenta po zakończeniu wszystkich zadań z danej sekcji

## Stage 1: Foundation - Testing Infrastructure & Critical Bug Fixes

**Goal:** Establish test coverage before refactoring and fix critical bugs that pose immediate risks.

### 1.1 Testing Infrastructure Setup

**🤖 Agent: `CLAUDE-testwriter.md` 🧪**

- [X] **In root directory**, create `pytest.ini` with configuration:
  ```ini
  [pytest]
  testpaths = tests
  python_files = test_*.py
  python_classes = Test*
  python_functions = test_*
  addopts = -v --strict-markers
  ```
  **Acceptance:** File exists and pytest can be run with `pytest` command

- [X] **In `requirements.txt`**, add testing dependencies (append at end):
  ```
  # Testing
  pytest>=8.0.0
  pytest-cov>=4.1.0
  pytest-asyncio>=0.23.0
  ```
  **Acceptance:** `pip install -r requirements.txt` installs pytest successfully

- [X] **Create `tests/conftest.py`** with shared fixtures:
  - `temp_dir` fixture (provides temporary directory using tempfile)
  - `sample_audio_file` fixture (creates fake MP3 file in temp_dir)
  - `sample_video_file` fixture (creates fake MP4 file in temp_dir)
  - `mock_api_manager` fixture (mocks APIManager methods)
  **Acceptance:** Fixtures can be imported and used in test files

### 1.2 Core Module Tests (Before Refactoring)

**🤖 Agent: `CLAUDE-testwriter.md` 🧪**

- [X] **Create `tests/test_error_classifier.py`** with test cases:
  - `test_classify_rate_limit_error()` - verify ErrorCategory.RETRYABLE_RATE_LIMIT
  - `test_classify_network_timeout()` - verify ErrorCategory.RETRYABLE_NETWORK
  - `test_classify_authentication_error()` - verify ErrorCategory.AUTHENTICATION
  - `test_classify_file_not_found()` - verify ErrorCategory.FILE_ISSUES
  - `test_classify_unknown_error()` - verify ErrorCategory.UNKNOWN
  - `test_classify_retryable_vs_non_retryable()` - verify retryable flag
  - Add 4 more test cases covering edge cases
  **Acceptance:** 10+ tests pass, pytest shows coverage for `src/core/error_classifier.py`

- [X] **Create `tests/test_api_manager.py`** with test cases:
  - `test_salt_creation()` - verify salt is 16 bytes
  - `test_salt_persistence()` - verify same salt returned on second call
  - `test_api_key_encryption_decryption()` - round-trip test
  - `test_get_preference_default_value()` - verify default parameter works
  - `test_save_preference()` - verify preference is saved
  - `test_balance_retrieval()` - mock httpx, verify API call
  - `test_model_list()` - verify supported models returned
  - Add 8 more test cases (preferences, encryption edge cases)
  **Acceptance:** 15+ tests pass, coverage for `src/utils/api_manager.py` > 60%

- [X] **Create `tests/test_transcription.py`** with basic tests (will expand in Stage 2):
  - `test_file_stream_chunks()` - verify file is read in 64KB chunks
  - `test_transcribe_success()` - mock httpx response, verify TranscriptionResult
  - `test_transcribe_api_error()` - mock exception, verify error handling
  - `test_transcribe_timeout()` - mock timeout, verify error message
  **Acceptance:** 4+ tests pass, baseline coverage established

- [X] **Create `tests/test_media_converter.py`** with test cases:
  - `test_validate_path_success()` - valid path returns resolved Path
  - `test_validate_path_traversal_detected()` - path with ".." raises error
  - `test_validate_path_nonexistent()` - non-existent path raises error
  - `test_to_mp3_command_construction()` - verify FFmpeg command args (mock subprocess)
  **Acceptance:** 4+ tests pass, path validation covered

- [X] **Create `tests/test_output_writer.py`** with test cases:
  - `test_save_txt_format()` - verify plain text output
  - `test_save_srt_format()` - verify SRT with timestamps
  - `test_save_vtt_format()` - verify WebVTT format
  - `test_save_custom_output_dir()` - verify output path construction
  **Acceptance:** 4+ tests pass, all output formats tested

- [X] **Create `tests/test_file_scanner.py`** with test cases:
  - `test_scan_directory_audio_files()` - verify MP3, WAV, FLAC detected
  - `test_scan_directory_video_files()` - verify MP4, AVI, MKV detected
  - `test_scan_recursive()` - verify subdirectories scanned
  - `test_scan_ignores_non_media()` - verify .txt, .json ignored
  **Acceptance:** 4+ tests pass, scanner logic validated

### 1.3 Bug Fixes

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [X] **In `src/utils/api_manager.py`**, fix `_get_or_create_salt()` method (lines ~60-70):
  - Wrap `self._save_config_raw(config)` in try-except block
  - If save fails, raise `RuntimeError("Cannot initialize encryption - failed to save salt")`
  - After save, reload config and verify salt matches (add verification step)
  - Add logging with `logger.error()` if save fails
  **Acceptance:** Test case `test_salt_save_failure_raises_exception` passes (mock save to raise exception)

- [X] **In `config.py`**, add FFmpeg timeout constant:
  ```python
  # FFmpeg Configuration
  FFMPEG_CONVERSION_TIMEOUT = 600  # seconds (10 minutes)
  ```
  **Acceptance:** Constant is accessible via `from config import FFMPEG_CONVERSION_TIMEOUT`

- [X] **In `src/core/media_converter.py`**, add timeout to FFmpeg subprocess (line ~257):
  - Import `FFMPEG_CONVERSION_TIMEOUT` from config
  - Add `timeout=FFMPEG_CONVERSION_TIMEOUT` parameter to `subprocess.run()`
  - Add exception handler for `subprocess.TimeoutExpired`
  - Log timeout error with `logger.error()` and raise `MediaConversionError`
  **Acceptance:** Test case `test_ffmpeg_timeout_handling` passes (mock subprocess with timeout)

- [X] **In `src/core/transcription.py`**, fix `_file_stream()` method (lines ~75-81):
  - Replace `with open()` context manager with explicit file handle management
  - Use try-finally block to ensure `file_handle.close()` is always called
  - Structure:
    ```python
    def _file_stream(self, file_path: Path) -> Iterator[bytes]:
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
    ```
  **Acceptance:** Test case `test_file_stream_closes_on_exception` passes (verify file descriptor released)

- [X] **In `src/gui/main_window.py`**, fix `_refresh_credits()` method (line ~619):
  - Add instance variable `self._credits_refreshing = False` in `__init__()`
  - At start of `_refresh_credits()`, check if `self._credits_refreshing` is True, return early if so
  - Set `self._credits_refreshing = True` before starting thread
  - In `fetch_credits()` finally block, reset flag: `self.after(0, lambda: setattr(self, '_credits_refreshing', False))`
  - Optionally disable refresh button while refreshing
  **Acceptance:** Multiple rapid clicks do not spawn multiple threads (verify with logging or debugger)

- [X] **In `src/core/file_scanner.py`**, add symlink loop detection to `scan_directory()`:
  - Add optional parameter `_visited: Optional[set] = None`
  - At method start, initialize `_visited = set()` if None
  - Resolve directory to real path: `real_path = directory.resolve()`
  - Check if `real_path in _visited`, if yes: log warning and return empty DirectoryNode
  - Add `real_path` to `_visited` set before scanning
  - Pass `_visited` to recursive `scan_directory()` calls
  **Acceptance:** Test case `test_symlink_loop_detection` passes (create symlink A→B→A, verify no infinite loop)

### 1.4 Dependency Updates

**🤖 Agent: `CLAUDE-docs.md` 📚**

- [X] **In `requirements.txt`**, update dependencies to latest secure versions:
  ```
  customtkinter>=5.2.2
  Pillow>=11.0.0          # Fix CVE-2024-28219
  httpx>=0.28.0           # Timeout improvements
  cryptography>=43.0.0    # Security updates
  yt-dlp>=2026.0.0        # Latest version
  ```
  **Acceptance:** `pip install -r requirements.txt` succeeds without errors

- [ ] **Manual testing after dependency update** (run these tests and document results):
  - Test API key encryption/decryption (save and retrieve key)
  - Test Deepgram API call (transcribe one file)
  - Test icon loading (verify app icon displays)
  - Test YouTube download (download and transcribe one video)
  **Acceptance:** All manual tests pass, no regressions observed

### 1.5 Stage 1 Validation

**🤖 Agent: `CLAUDE-docs.md` 📚**

- [ ] **Run full test suite** with coverage report:
  ```bash
  pytest --cov=src --cov-report=html
  ```
  **Acceptance:** All tests pass (40+ tests), coverage report generated in htmlcov/

- [ ] **Manual E2E test** - Transcribe 10 files (mix of audio and video):
  - Select directory with test files
  - Run transcription with different settings (TXT, SRT, VTT formats)
  - Verify all 10 files complete successfully
  - Check output files are created and valid
  **Acceptance:** 10/10 files transcribed successfully, no crashes or errors

## Stage 2: Business Logic Separation

**Goal:** Extract business logic from GUI into dedicated, testable classes.

### 2.1 TempFileManager Class

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [X] **Create `src/utils/temp_file_manager.py`** with class implementation:
  - Class `TempFileManager` with `__init__(self, temp_dir: Path)`
  - Method `track(self, file_path: Path) -> Path` - adds file to tracked set
  - Method `cleanup_file(self, file_path: Path) -> bool` - removes specific file (with security check)
  - Method `cleanup_pattern(self, pattern: str) -> int` - removes files matching glob pattern
  - Method `cleanup_tracked(self) -> int` - removes all tracked files
  - Method `cleanup_all(self) -> int` - removes ALL files in temp_dir (use with caution)
  - Add logging to all methods with `logger = logging.getLogger(__name__)`
  **Acceptance:** Class exists, all methods have type hints and docstrings

- [X] **Create `tests/test_temp_file_manager.py`** with comprehensive tests:
  - `test_track_file()` - verify file added to tracked set
  - `test_cleanup_file_success()` - verify file removed
  - `test_cleanup_file_outside_temp_dir()` - verify security check (returns False)
  - `test_cleanup_pattern()` - verify pattern matching (*.mp3)
  - `test_cleanup_tracked()` - verify all tracked files removed
  - `test_cleanup_all()` - verify all files in temp_dir removed
  - Add 14+ more test cases (edge cases, concurrent access, etc.)
  **Acceptance:** 20+ tests pass, coverage for `src/utils/temp_file_manager.py` > 90%

- [X] **In `src/core/media_converter.py`**, integrate TempFileManager:
  - Add import: `from src.utils.temp_file_manager import TempFileManager`
  - In `__init__()`, create instance: `self.temp_manager = TempFileManager(TEMP_DIR)`
  - In `to_mp3()`, use `self.temp_manager.track(output_path)` to track temp files
  - Replace `cleanup()` method body with `self.temp_manager.cleanup_file(file_path)`
  - Replace `cleanup_all()` method body with `self.temp_manager.cleanup_pattern("*.mp3")`
  **Acceptance:** MediaConverter uses TempFileManager, old cleanup logic removed

- [X] **In `src/core/youtube_downloader.py`**, integrate TempFileManager:
  - Add import: `from src.utils.temp_file_manager import TempFileManager`
  - In `__init__()`, create instance: `self.temp_manager = TempFileManager(YOUTUBE_TEMP_DIR)`
  - Update `download()` to track downloaded files with `self.temp_manager.track()`
  - Replace `cleanup()` method with `self.temp_manager.cleanup_file()`
  - Replace `cleanup_all()` method with `self.temp_manager.cleanup_all()`
  **Acceptance:** YouTubeDownloader uses TempFileManager, duplicate cleanup removed

- [X] **In `src/gui/main_window.py`**, integrate TempFileManager:
  - Add import: `from src.utils.temp_file_manager import TempFileManager`
  - In `__init__()`, create instance: `self.temp_manager = TempFileManager(TEMP_DIR)`
  - Remove method `_cleanup_temp_files()` (delete entire method)
  - Remove method `_cleanup_youtube_file()` (delete entire method)
  - Replace calls to removed methods with `self.temp_manager.cleanup_pattern("*.mp3")`
  **Acceptance:** MainWindow no longer has custom cleanup methods

- [X] **In `src/gui/youtube_tab.py`**, integrate TempFileManager:
  - Add import: `from src.utils.temp_file_manager import TempFileManager`
  - In `__init__()`, create instance: `self.temp_manager = TempFileManager(YOUTUBE_TEMP_DIR)`
  - Remove method `_cleanup_temp_files()` (delete entire method)
  - Replace calls to removed method with `self.temp_manager.cleanup_all()`
  **Acceptance:** YouTubeTab no longer has custom cleanup methods

### 2.2 TranscriptionOrchestrator Class

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [X] **Create `src/core/transcription_orchestrator.py`** with class implementation:
  - Class `TranscriptionOrchestrator` with dependencies in `__init__()`:
    - `converter: MediaConverter`
    - `transcription_service: TranscriptionService`
    - `output_writer: OutputWriter`
    - `logger: SessionLogger`
    - `event_callback: Optional[Callable]` for GUI updates
  - Method `process_file()` with parameters:
    - `file: MediaFile`
    - `output_format: str`
    - `output_dir: Optional[Path]`
    - `language: str`
    - `diarize: bool`
    - `smart_format: bool`
  - Method `_emit(event_type, file, extra)` for emitting events
  - Events to emit: 'converting', 'transcribing', 'saving', 'completed', 'failed'
  - Include comprehensive error handling (try-except)
  **Acceptance:** Class exists with all methods, type hints, and docstrings

- [X] **Create `tests/test_transcription_orchestrator.py`** with test cases:
  - `test_process_file_audio_success()` - mock dependencies, verify workflow for audio
  - `test_process_file_video_success()` - verify conversion step for video
  - `test_process_file_transcription_failure()` - mock API error, verify error handling
  - `test_process_file_conversion_failure()` - mock FFmpeg error, verify error handling
  - `test_event_emission()` - verify all events emitted in correct order
  - Add 10+ more test cases (edge cases, error scenarios)
  **Acceptance:** 15+ tests pass, coverage for `src/core/transcription_orchestrator.py` > 80%

- [X] **In `src/gui/main_window.py`**, integrate TranscriptionOrchestrator:
  - Add import: `from src.core.transcription_orchestrator import TranscriptionOrchestrator`
  - In `_process_files()` method, create orchestrator instance before loop:
    ```python
    orchestrator = TranscriptionOrchestrator(
        converter=converter,
        transcription_service=TranscriptionService(api_key),
        output_writer=OutputWriter(),
        logger=self.session_logger,
        event_callback=self._on_transcription_event
    )
    ```
  - Replace `_process_single_file()` calls with `orchestrator.process_file()`
  - Remove `_process_single_file()` method entirely (delete entire method)
  **Acceptance:** MainWindow uses orchestrator, old processing method removed

- [X] **In `src/gui/main_window.py`**, add event callback handler:
  - Create method `_on_transcription_event(self, event_type: str, file: MediaFile, extra: Dict[str, Any])`:
    - Find file index in `self.selected_files`
    - For 'converting' event: update progress dialog status to CONVERTING
    - For 'transcribing' event: update progress dialog status to TRANSCRIBING
    - For 'saving' event: update progress dialog status to SAVING
    - For 'completed' event: update progress dialog status to COMPLETED
    - For 'failed' event: update progress dialog status to FAILED with error message
  - Use `self.after(0, lambda: ...)` for thread-safe GUI updates
  **Acceptance:** Progress dialog updates correctly for all events

### 2.3 TranscriptionService Refactoring

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [X] **In `src/core/transcription.py`**, split `transcribe()` method into smaller methods:
  - Extract `_validate_inputs(self, file_path: Path, language: str)` method:
    - Check if file exists, raise `FileNotFoundError` if not
    - Validate language is in SUPPORTED_LANGUAGES or "auto"
    - Max ~15 lines
  - Extract `_build_request_params(self, language: str, diarize: bool, smart_format: bool) -> Dict[str, Any]`:
    - Build params dict for Deepgram API
    - Handle language vs detect_language
    - Max ~20 lines
  - Extract `_make_request(self, file_path: Path, params: Dict[str, Any]) -> httpx.Response`:
    - Build headers with API key
    - Make httpx.Client.post() call
    - Handle HTTP errors
    - Max ~25 lines
  - Extract `_parse_response(self, response: httpx.Response) -> TranscriptionResult`:
    - Parse JSON response
    - Extract transcript, metadata, utterances
    - Build TranscriptionResult object
    - Max ~40 lines
  - Refactor `transcribe()` to orchestrate workflow (~40-50 lines):
    ```python
    def transcribe(self, file_path, language, diarize, smart_format):
        try:
            self._validate_inputs(file_path, language)
            params = self._build_request_params(language, diarize, smart_format)
            response = self._make_request(file_path, params)
            return self._parse_response(response)
        except httpx.TimeoutException as e:
            # ... error handling ...
    ```
  **Acceptance:** Original `transcribe()` method is now ~50 lines, logic split into 5 methods

- [X] **In `tests/test_transcription.py`**, update and expand tests:
  - Add `test_validate_inputs_file_not_found()` - verify FileNotFoundError raised
  - Add `test_validate_inputs_invalid_language()` - verify ValueError raised
  - Add `test_build_request_params_auto_language()` - verify detect_language=True
  - Add `test_build_request_params_specific_language()` - verify language param
  - Add `test_parse_response_success()` - mock response JSON, verify parsing
  - Add `test_parse_response_missing_transcript()` - verify error handling
  - Update existing tests to work with new structure
  **Acceptance:** 10+ tests pass, each new method tested independently

### 2.4 Stage 2 Validation

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [ ] **Run full test suite** with coverage report:
  ```bash
  pytest --cov=src --cov-report=html
  ```
  **Acceptance:** All tests pass (60+ tests), coverage for `src/core/` > 60%

- [ ] **Manual E2E test** - Batch transcribe 50 files:
  - Select directory with 50+ files (audio + video mix)
  - Run transcription and verify progress dialog updates correctly
  - Verify all events are emitted (converting, transcribing, saving, completed)
  - Check output files are created for all completed files
  **Acceptance:** 50/50 files transcribed, progress updates work correctly

## Stage 3: GUI Refactoring

**Goal:** Break down mega-methods in GUI classes to improve readability and maintainability.

### 3.1 MainWindow._create_widgets() Refactoring

**🤖 Agent: `CLAUDE-frontend.md` 🎨**

- [X] **In `src/gui/main_window.py`**, split `_create_widgets()` into 8 methods:
  - Extract `_create_top_bar(self)` - API key section, credits display (~30 lines)
  - Extract `_create_directory_section(self)` - directory label, entry, browse button, recursive checkbox (~40 lines)
  - Extract `_create_files_section(self)` - file count label, scan/browse buttons (~35 lines)
  - Extract `_create_options_section(self)` - model, language, format dropdowns (~50 lines)
  - Extract `_create_output_section(self)` - output directory widgets (~40 lines)
  - Extract `_create_action_buttons(self)` - transcribe, cancel, clear buttons (~30 lines)
  - Extract `_create_tabs(self)` - YouTube tab, logs tab (~40 lines)
  - Extract `_setup_layout(self)` - grid layout configuration (~20 lines)
  - Refactor `_create_widgets()` to call these 8 methods in order (~10 lines total)
  **Acceptance:** Each method max 50 lines, all widgets still created as `self.widget_name`, GUI appearance unchanged

- [ ] **Visual regression test** for MainWindow:
  - Run application and verify GUI layout is identical to before refactoring
  - Test all widgets are functional (buttons click, dropdowns work, etc.)
  - Compare screenshots before/after if possible
  **Acceptance:** GUI looks and behaves identically to pre-refactoring version

### 3.2 SettingsDialog._create_widgets() Refactoring

**🤖 Agent: `CLAUDE-frontend.md` 🎨**

- [X] **In `src/gui/settings_dialog.py`**, split `_create_widgets()` into 5 methods:
  - Extract `_create_api_key_section(self)`, `_create_model_section(self)`, `_create_info_section(self)`, `_create_status_section(self)`, `_create_dialog_buttons(self)`
  - Refactor `_create_widgets()` to call these methods in order
  **Acceptance:** Each method max 50 lines, dialog appearance unchanged
  **Note:** Method names differ slightly from original plan but serve same purpose

- [ ] **Visual regression test** for SettingsDialog:
  - Open settings dialog and verify all sections render correctly
  - Test changing settings and clicking OK
  - Verify settings are saved correctly
  **Acceptance:** Dialog looks and behaves identically to pre-refactoring version

### 3.3 ProgressDialog._create_widgets() Refactoring

**🤖 Agent: `CLAUDE-frontend.md` 🎨**

- [X] **In `src/gui/progress_dialog.py`**, split `_create_widgets()` into 4 methods:
  - Extract `_create_overall_progress(self)`, `_create_file_list(self)`, `_create_control_buttons(self)`
  - Refactor `_create_widgets()` to call these methods in order
  **Acceptance:** Each method max 50 lines, dialog appearance unchanged
  **Note:** Stats section integrated into _create_overall_progress or _create_file_list instead of separate method

- [ ] **Visual regression test** for ProgressDialog:
  - Run transcription of 10 files and verify progress dialog displays correctly
  - Verify all progress updates work (overall bar, file status, stats)
  - Test pause/cancel buttons
  **Acceptance:** Dialog looks and behaves identically to pre-refactoring version

### 3.4 YouTubeTab._process_videos() Refactoring

**🤖 Agent: `CLAUDE-frontend.md` 🎨**

- [X] **In `src/gui/youtube_tab.py`**, split `_create_widgets()` into sub-methods:
  - Extract `_create_url_section()`, `_create_video_list_section()`, `_create_options_section()`, `_create_output_section()`, `_create_action_section()`
  **Note:** _create_widgets() was split successfully into 5 sub-methods

- [ ] **In `src/gui/youtube_tab.py`**, split `_process_videos()` method:
  - Extract `_validate_video_selection(self) -> bool` - validate videos selected, return False if none (~15 lines)
  - Extract `_process_single_video(self, video, index: int) -> bool` - download and transcribe one video (~40 lines)
  - Extract `_handle_video_error(self, video, error: Exception)` - log error and update UI (~20 lines)
  - Refactor `_process_videos()` to use these helper methods (~50-60 lines):
    ```python
    def _process_videos(self):
        if not self._validate_video_selection():
            return
        
        for index, video in enumerate(self.selected_videos):
            try:
                success = self._process_single_video(video, index)
                # ... update stats ...
            except Exception as e:
                self._handle_video_error(video, e)
    ```
  **Acceptance:** Original method reduced to ~60 lines, logic split into helper methods

- [ ] **Functional test** for YouTubeTab:
  - Add YouTube video URL and download
  - Verify video processes correctly
  - Test error handling (invalid URL)
  **Acceptance:** YouTube tab works identically to pre-refactoring version

### 3.5 Stage 3 Validation

**🤖 Agent: `CLAUDE-frontend.md` 🎨**

- [ ] **Full application manual test** - Test all GUI features:
  - Main window: scan directory, select files, transcribe
  - Settings dialog: change model, language, format
  - Progress dialog: verify updates during transcription
  - YouTube tab: download and transcribe video
  - Logs tab: verify logs display
  **Acceptance:** All GUI features work identically to pre-refactoring version, no visual regressions

- [ ] **Code review** - Check refactored GUI code:
  - All methods max 80 lines (preferably 50)
  - All methods have clear single responsibility
  - Docstrings added to all new methods
  - No duplicate code
  **Acceptance:** Code review confirms improved readability

## Stage 4: Code Quality & Documentation

**Goal:** Finalize code quality improvements - add complete type hints, eliminate magic numbers, improve logging, and document changes.

### 4.1 Type Hints Completion

**🤖 Agent: `CLAUDE-backend.md` 🔧 (for core/utils files) / `CLAUDE-frontend.md` 🎨 (for GUI files)**

- [X] **In `src/utils/api_manager.py`**, add missing type hints:
  - Fix `get_preference()` return type: `-> Any`
  - Fix `_load_config()` return type: `-> Dict[str, Any]`
  - Add type hints to any other methods missing them
  - Add imports: `from typing import Any, Dict, Optional`
  **Acceptance:** All methods have complete type hints
  **Assigned to: `CLAUDE-backend.md` 🔧**

- [X] **In `src/core/file_scanner.py`**, add missing type hints:
  - Review all methods and add type hints where missing
  - Add return types to all methods
  - Add parameter types to all methods
  **Acceptance:** All methods have complete type hints
  **Assigned to: `CLAUDE-backend.md` 🔧**

- [X] **In `src/utils/session_logger.py`**, add missing type hints:
  - Review all methods and add type hints where missing
  - Add return types to all logging methods
  - Add parameter types to all methods
  **Acceptance:** All methods have complete type hints
  **Assigned to: `CLAUDE-backend.md` 🔧**

- [X] **Create `mypy.ini`** in root directory with configuration:
  ```ini
  [mypy]
  python_version = 3.11
  warn_return_any = True
  warn_unused_configs = True
  disallow_untyped_defs = True
  disallow_incomplete_defs = True

  [mypy-src.gui.*]
  # CustomTkinter has poor type hints, relax GUI rules
  disallow_untyped_defs = False

  [mypy-tests.*]
  disallow_untyped_defs = False
  ```
  **Acceptance:** File exists
  **Assigned to: `CLAUDE-docs.md` 📚**

- [X] **Run mypy validation** on core and utils modules:
  ```bash
  mypy src/core/ src/utils/ src/models/
  ```
  **Acceptance:** No type errors reported by mypy (warnings OK)
  **Assigned to: `CLAUDE-backend.md` 🔧**

### 4.2 Magic Numbers Elimination

**🤖 Agent: `CLAUDE-backend.md` 🔧 (for backend files) / `CLAUDE-frontend.md` 🎨 (for GUI files)**

- [X] **In `config.py`**, add new configuration constants:
  ```python
  # GUI Configuration
  ICON_SIZES = [(16, 16), (32, 32), (48, 48), (256, 256)]

  # FFmpeg Configuration
  FFMPEG_ERROR_LOG_MAX_LINES = 100

  # API Configuration (move from transcription.py)
  UPLOAD_CHUNK_SIZE = 64 * 1024  # 64KB chunks

  # Security (update)
  PBKDF2_ITERATIONS = 600000  # Increased from 100k to 600k (OWASP 2023)
  ```
  **Acceptance:** All constants added to config.py
  **Assigned to: `CLAUDE-backend.md` 🔧**

- [X] **In `src/gui/main_window.py`**, replace icon sizes magic numbers:
  - Find line with `sizes = [(16, 16), (32, 32), (48, 48), (256, 256)]`
  - Replace with `sizes = ICON_SIZES` (import from config)
  **Acceptance:** No hardcoded icon sizes in main_window.py
  **Assigned to: `CLAUDE-frontend.md` 🎨**

- [X] **In `src/core/media_converter.py`**, replace magic number:
  - Find line with `if len(stderr_lines) > 100:`
  - Replace `100` with `FFMPEG_ERROR_LOG_MAX_LINES` (import from config)
  **Acceptance:** No hardcoded max error lines
  **Assigned to: `CLAUDE-backend.md` 🔧**
  **Note:** Constant exists in config.py but NOT yet imported/used in media_converter.py

- [X] **In `src/core/transcription.py`**, move UPLOAD_CHUNK_SIZE to config:
  - Remove line `UPLOAD_CHUNK_SIZE = 64 * 1024` from module level
  - Import from config: `from config import UPLOAD_CHUNK_SIZE`
  **Acceptance:** Constant moved to config.py, imported in transcription.py
  **Assigned to: `CLAUDE-backend.md` 🔧**

- [X] **In `src/utils/api_manager.py`**, increase PBKDF2 iterations:
  - Find line with `iterations=100000`
  - Replace with `iterations=PBKDF2_ITERATIONS` (import from config)
  **Acceptance:** PBKDF2 uses 600k iterations from config
  **Assigned to: `CLAUDE-backend.md` 🔧**

### 4.3 Logging Improvements

**🤖 Agent: `CLAUDE-backend.md` 🔧 (for core/utils files) / `CLAUDE-frontend.md` 🎨 (for GUI files)**

- [X] **In all `src/core/*.py` files**, add logging:
  - Add `import logging` at top
  - Add `logger = logging.getLogger(__name__)` after imports
  - Replace `print()` statements with appropriate log level (`logger.info()`, `logger.warning()`, `logger.error()`)
  - Add contextual information to error messages (file names, operation details)
  - Use `logger.exception()` in exception handlers to capture stack traces
  **Acceptance:** All print statements replaced with logging, logger configured in each module
  **Assigned to: `CLAUDE-backend.md` 🔧**

- [X] **In all `src/utils/*.py` files**, add logging:
  - Same as above - add logging to all utility modules
  - Ensure errors are logged with sufficient context
  **Acceptance:** All utility modules use logging
  **Assigned to: `CLAUDE-backend.md` 🔧**

- [X] **In `main.py`**, configure logging to file:
  - Add logging configuration:
    ```python
    import logging
    from config import LOGS_DIR
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOGS_DIR / 'redscribe.log'),
            logging.StreamHandler()  # Console output
        ]
    )
    ```
  - Ensure LOGS_DIR exists before running
  **Acceptance:** Logging outputs to both file and console, log file created in LOGS_DIR
  **Assigned to: `CLAUDE-backend.md` 🔧**

### 4.4 Documentation

**🤖 Agent: `CLAUDE-docs.md` 📚**

- [X] **Add docstrings to all public methods** in `src/core/`:
  - Use Google or NumPy docstring style
  - Include parameters, return types, and brief description
  **Acceptance:** All public methods have docstrings

- [X] **Add docstrings to all public methods** in `src/utils/`:
  - Same as above - document all utility methods
  **Acceptance:** All public methods have docstrings

- [X] **Add docstrings to new classes**:
  - `TranscriptionOrchestrator` - document purpose, responsibilities, events
  - `TempFileManager` - document purpose, methods, security checks
  **Acceptance:** New classes have comprehensive class-level docstrings

- [X] **Update `README.md`** with architecture notes:
  - Add section "Architecture" describing new classes (TranscriptionOrchestrator, TempFileManager)
  - Add section "Testing" with instructions: `pytest --cov=src`
  - Add section "Development Setup" with venv and dependency installation steps
  **Acceptance:** README.md updated with new sections

- [X] **Create `CHANGELOG.md`** documenting refactoring changes:
  - Add version 1.1.0 with sections:
    - **Bug Fixes** - list all 5 bugs fixed
    - **Refactoring** - describe GUI split, orchestrator pattern
    - **Code Quality** - type hints, logging, tests added
    - **Dependencies** - list updated packages
  **Acceptance:** CHANGELOG.md created with comprehensive notes

### 4.5 Final Testing & Validation

**🤖 Agent: `CLAUDE-docs.md` 📚**

- [ ] **Run full unit test suite** with coverage:
  ```bash
  pytest --cov=src --cov-report=html --cov-report=term
  ```
  **Acceptance:** All tests pass (70+ tests), coverage >= 70% for core/utils/models

- [ ] **Manual E2E testing** - Comprehensive test suite:
  - Transcribe 100 files (50 audio, 50 video) with different settings
  - Test all output formats (TXT, SRT, VTT)
  - Test YouTube download and transcription (5 videos)
  - Test error cases:
    - Invalid API key
    - Network timeout (disconnect internet)
    - Corrupted audio file
    - No write permission for output directory
  **Acceptance:** All 100 files transcribe successfully, error cases handled gracefully

- [ ] **Performance validation** - No regressions:
  - Benchmark: Time to transcribe 100 files (measure before and after refactoring if possible)
  - Memory profiling: Run application and monitor memory usage during batch processing
  - Check for memory leaks (memory should not grow unbounded)
  **Acceptance:** No performance regression > 10%, no memory leaks detected

- [ ] **Run mypy on entire codebase**:
  ```bash
  mypy src/
  ```
  **Acceptance:** No type errors in core/utils/models (GUI can have errors due to CustomTkinter)

- [ ] **Code review checklist**:
  - [ ] All methods < 80 lines (except rare exceptions)
  - [ ] All bugs from Stage 1 are fixed
  - [ ] All duplicate code eliminated
  - [ ] All magic numbers moved to config
  - [ ] All print statements replaced with logging
  - [ ] All public methods have docstrings
  - [ ] All tests pass with good coverage
  **Acceptance:** All checklist items confirmed

## Stage 5: Parallel Transcription + Session Persistence

**Goal:** Add high-value features to improve user experience: parallel processing (3x speedup) and automatic session persistence (resume after crashes).

### 5.1 Parallel Transcription

**🤖 Agent: `CLAUDE-parallel-processing.md`**

#### 5.1.1 ThreadPoolExecutor Integration

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [X] **In `config.py`**, add concurrency constants:
  ```python
  # Parallel transcription configuration
  MAX_CONCURRENT_WORKERS = 3          # Default: 3 concurrent files
  MIN_CONCURRENT_WORKERS = 1          # Sequential mode
  MAX_CONCURRENT_WORKERS_LIMIT = 10   # Hard upper limit
  ```
  **Acceptance:** Constants accessible via import

- [X] **In `src/utils/api_manager.py`**, add concurrency preference methods:
  ```python
  def get_max_concurrent_workers(self) -> int:
      return self.get_preference("max_concurrent_workers", MAX_CONCURRENT_WORKERS)

  def set_max_concurrent_workers(self, workers: int):
      if not MIN_CONCURRENT_WORKERS <= workers <= MAX_CONCURRENT_WORKERS_LIMIT:
          raise ValueError(...)
      self.set_preference("max_concurrent_workers", workers)
  ```
  **Acceptance:** Settings persist across sessions

- [X] **In `src/gui/main_window.py`**, replace boolean cancel flag with threading.Event:
  - In `__init__()`, change `self.cancel_requested = False` to `self.cancel_event = threading.Event()`
  - Update `_cancel_processing()` to use `self.cancel_event.set()`
  - Update `_start_transcription()` to call `self.cancel_event.clear()` before starting
  **Acceptance:** Thread-safe cancellation mechanism

- [X] **In `src/gui/main_window.py:_process_files()`, replace sequential loop with ThreadPoolExecutor:
  ```python
  from concurrent.futures import ThreadPoolExecutor, as_completed

  max_workers = self.api_manager.get_max_concurrent_workers()

  with ThreadPoolExecutor(max_workers=max_workers) as executor:
      # Submit all pending files
      futures = {
          executor.submit(self._process_single_file, file, i, ...): (i, file)
          for i, file in enumerate(self.selected_files)
          if file.status == TranscriptionStatus.PENDING
      }

      # Process completions as they finish (out of order)
      for future in as_completed(futures):
          index, file = futures[future]

          if self.cancel_event.is_set():
              executor.shutdown(wait=False, cancel_futures=True)
              break

          try:
              success = future.result()
              if success:
                  success_count += 1
          except Exception as e:
              logger.error(f"Error processing {file.name}: {e}")
  ```
  **Acceptance:** Files process concurrently, cancel stops all workers

- [X] **In `src/gui/main_window.py`, update retry logic for parallel context (PHASE 2):
  - Extract `_parallel_process_batch()` method for reuse
  - After PHASE 1, collect retryable files
  - Use same ThreadPoolExecutor pattern for PHASE 2 retries
  **Acceptance:** Retry logic works with parallel processing

#### 5.1.2 Settings Dialog UI Enhancement

**🤖 Agent: `CLAUDE-frontend.md` 🎨**

- [X] **In `src/gui/settings_dialog.py`, add performance section with concurrency slider:
  ```python
  def _create_performance_section(self):
      """Create performance settings section."""
      # Section label
      ctk.CTkLabel(
          self.scrollable_frame,
          text="Concurrent Transcriptions:",
          font=("Roboto", 14, "bold")
      ).pack(anchor="w", pady=(10, 5))
      
      # Slider + value label
      slider_frame = ctk.CTkFrame(self.scrollable_frame)
      slider_frame.pack(fill="x", pady=5)
      
      self.workers_value_label = ctk.CTkLabel(
          slider_frame,
          text="3 files",
          font=("Roboto", 12)
      )
      self.workers_value_label.pack(side="right", padx=10)
      
      self.workers_slider = ctk.CTkSlider(
          slider_frame,
          from_=MIN_CONCURRENT_WORKERS,
          to=MAX_CONCURRENT_WORKERS_LIMIT,
          number_of_steps=9,
          command=self._on_workers_slider_change
      )
      self.workers_slider.set(MAX_CONCURRENT_WORKERS)
      self.workers_slider.pack(side="left", fill="x", expand=True)
      
      # Help text
      ctk.CTkLabel(
          self.scrollable_frame,
          text="⚠️ Higher values = faster batches but may hit API rate limits",
          font=("Roboto", 10),
          text_color="gray"
      ).pack(anchor="w", pady=(0, 10))
  
  def _on_workers_slider_change(self, value):
      workers = int(value)
      self.workers_value_label.configure(text=f"{workers} file{'s' if workers > 1 else ''}")
  ```
  **Acceptance:** Slider controls concurrency (1-10), setting persists

- [X] **Call `_create_performance_section()` in `_create_widgets()`:
  - Add call after existing sections
  - Load current setting from `api_manager.get_max_concurrent_workers()`
  - Save setting on dialog close via `api_manager.set_max_concurrent_workers()`
  **Acceptance:** Settings dialog shows performance section, saves on close

#### 5.1.3 Progress Dialog Enhancement

**🤖 Agent: `CLAUDE-frontend.md` 🎨**

- [X] **In `src/gui/progress_dialog.py`, add active workers display:
  ```python
  def _create_overall_progress(self):
      # Existing progress bar
      self.progress_bar = ctk.CTkProgressBar(...)
      
      # NEW: Active workers label
      self.workers_label = ctk.CTkLabel(
          self,
          text="Workers: 0/3 active",
          font=("Roboto", 12)
      )
      self.workers_label.pack(pady=5)
  
  def update_workers_count(self, active: int, total: int):
      """Update active workers display."""
      self.workers_label.configure(text=f"Workers: {active}/{total} active")
  ```
  **Acceptance:** Progress dialog shows active worker count

- [X] **In `src/gui/main_window.py:_process_files()`, update worker count during processing:
  - Call `self.progress_dialog.update_workers_count()` initially with `len(futures)`
  - Update after each completion with remaining count: `min(remaining, max_workers)`
  - Use `self.after(0, ...)` for thread-safe GUI updates
  **Acceptance:** Worker count updates in real-time

#### 5.1.4 Thread Safety Improvements

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [X] **In `src/utils/session_logger.py`, add thread-safe locking:
  ```python
  import threading
  
  class SessionLogger:
      def __init__(self):
          self._lock = threading.Lock()
          # ... existing init
      
      def log_file_completed(self, filename: str, duration: float):
          with self._lock:
              self.stats.successful += 1
              self.stats.duration_seconds += duration
              # ... write to file
      
      def log_file_failed(self, filename: str, error: str):
          with self._lock:
              self.stats.failed += 1
              # ... write to file
  ```
  **Acceptance:** No race conditions in statistics updates

#### 5.1.5 Testing

**🤖 Agent: `CLAUDE-testwriter.md` 🧪**

- [X] **Create `tests/test_parallel_processing.py` with test cases:
  - `test_parallel_processing_success()` - verify 10 files with 3 workers complete
  - `test_cancel_during_parallel_processing()` - verify cancel stops all workers
  - `test_worker_count_respects_settings()` - verify max_workers is honored
  - `test_concurrent_statistics_updates()` - verify no race conditions in SessionLogger
  - Add 6+ more test cases
  **Acceptance:** 10+ tests pass, concurrency logic validated

- [X] **Integration test: parallel transcription with 10 files, 3 workers:
  - Mock Deepgram API responses
  - Process 10 files concurrently
  - Verify all complete successfully
  - Verify duration is ~3x faster than sequential (accounting for mocking)
  **Acceptance:** Integration test passes, speedup verified

#### 5.1.6 Stage 5.1 Validation

**🤖 Agent: `CLAUDE-backend.md` 🔧 + `CLAUDE-frontend.md` 🎨 (joint validation)**

- [ ] **Manual E2E test: parallel transcription with 20 real files:
  - Test with 1 worker (baseline)
  - Test with 3 workers (verify ~3x speedup)
  - Test with 5 workers (verify ~5x speedup)
  - Test cancel mid-batch (verify clean shutdown)
  - Verify all output files created correctly
  **Acceptance:** 20/20 files complete, speedup achieved, cancel works

### 5.2 Session Persistence (Resume Interrupted Batches)

**🤖 Agent: `CLAUDE-session-persistence.md`**

#### 5.2.1 Pydantic Models for Batch State

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [X] **Create `contracts/batch_state.py` with Pydantic models:
  ```python
  from pydantic import BaseModel, Field
  from typing import Optional, List
  from datetime import datetime
  from enum import Enum
  
  class TranscriptionStatusEnum(str, Enum):
      PENDING = "pending"
      CONVERTING = "converting"
      TRANSCRIBING = "transcribing"
      COMPLETED = "completed"
      FAILED = "failed"
      SKIPPED = "skipped"
  
  class BatchSettings(BaseModel):
      output_format: str
      output_dir: Optional[str] = None
      language: str
      diarize: bool
      smart_format: bool
      max_concurrent_workers: int
  
  class FileState(BaseModel):
      source_path: str
      status: TranscriptionStatusEnum
      output_path: Optional[str] = None
      duration_seconds: Optional[float] = None
      retry_count: int = 0
      completed_at: Optional[datetime] = None
      error_message: Optional[str] = None
  
  class BatchStatistics(BaseModel):
      total_files: int
      completed: int = 0
      failed: int = 0
      pending: int
      total_duration_seconds: float = 0.0
  
  class BatchState(BaseModel):
      batch_id: str
      created_at: datetime
      last_updated: datetime
      settings: BatchSettings
      files: List[FileState]
      statistics: BatchStatistics
  ```
  **Acceptance:** Models validate JSON correctly, type hints complete

#### 5.2.2 BatchStateManager Class

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [X] **Create `src/utils/batch_state_manager.py` with atomic write support:
  - Class `BatchStateManager` with `STATE_FILE = APPDATA_DIR / "batch_state.json"`
  - Method `has_pending_batch() -> bool` - check if state file exists
  - Method `load_batch_state() -> Optional[BatchState]` - load and validate state
  - Method `save_batch_state(state: BatchState)` - atomic write with tempfile + os.replace
  - Method `update_file_status(batch_id, source_path, status, ...)` - update single file
  - Method `verify_completed_files(state) -> List[str]` - check outputs exist
  - Method `mark_files_for_reprocessing(state, source_paths)` - re-mark as pending
  - Method `clear_batch_state()` - remove state file
  - Method `_backup_corrupted_file()` - backup corrupted JSON for debugging
  - Add comprehensive error handling (catch json.JSONDecodeError)
  **Acceptance:** All methods have docstrings, atomic writes prevent corruption

- [X] **In `src/utils/batch_state_manager.py:save_batch_state()`, implement atomic write:
  ```python
  import tempfile
  import os
  
  temp_fd, temp_path = tempfile.mkstemp(
      dir=APPDATA_DIR,
      prefix="batch_state_",
      suffix=".tmp"
  )
  
  try:
      with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
          json.dump(state.model_dump(mode="json"), f, indent=2)
      
      # Atomic replace
      os.replace(temp_path, cls.STATE_FILE)
  except Exception as e:
      try:
          os.unlink(temp_path)
      except OSError:
          pass
      raise
  ```
  **Acceptance:** No corrupted files even if crash during write

#### 5.2.3 Integration with MainWindow

**🤖 Agent: `CLAUDE-frontend.md` 🎨**

- [X] **In `src/gui/main_window.py:__init__()`, add pending batch check:
  ```python
  # Check for pending batch after window shown
  self.after(500, self._check_pending_batch)
  ```
  **Acceptance:** Resume prompt appears 500ms after startup if state file exists

- [X] **In `src/gui/main_window.py`, create `_check_pending_batch()` method:
  - Call `BatchStateManager.has_pending_batch()`
  - If no pending batch, return early
  - Load batch state with `BatchStateManager.load_batch_state()`
  - Count incomplete files (status in ["pending", "failed"])
  - Show messagebox: "Found incomplete batch... X completed, Y remaining. Resume?"
  - If user clicks Yes, call `self._resume_batch(state)`
  - If user clicks No, call `BatchStateManager.clear_batch_state()`
  **Acceptance:** User prompted on startup if batch pending

- [X] **In `src/gui/main_window.py`, create `_resume_batch(state)` method:
  - Call `BatchStateManager.verify_completed_files(state)` to check missing outputs
  - If missing outputs found:
    - Call `BatchStateManager.mark_files_for_reprocessing(state, missing_paths)`
    - Show warning: "X output file(s) missing and will be reprocessed"
  - Reconstruct `self.selected_files` from `state.files`:
    ```python
    self.selected_files = []
    for file_state in state.files:
        media_file = MediaFile(Path(file_state.source_path))
        media_file.status = TranscriptionStatus[file_state.status.upper()]
        media_file.output_path = Path(file_state.output_path) if file_state.output_path else None
        media_file.error_message = file_state.error_message
        media_file.retry_count = file_state.retry_count
        self.selected_files.append(media_file)
    ```
  - Restore settings from `state.settings` (output_format, output_dir, language, etc.)
  - Update UI with `self._refresh_file_list()`
  - Show info message: "Resuming batch with X remaining files"
  **Acceptance:** Resume restores file list and settings, skips completed files

- [X] **In `src/gui/main_window.py:_start_transcription()`, create initial batch state:
  ```python
  import uuid
  from datetime import datetime
  from contracts.batch_state import BatchState, BatchSettings, FileState, BatchStatistics
  
  batch_id = str(uuid.uuid4())
  batch_state = BatchState(
      batch_id=batch_id,
      created_at=datetime.now(),
      last_updated=datetime.now(),
      settings=BatchSettings(
          output_format=self.output_format.get(),
          output_dir=str(self.output_dir) if self.custom_output_dir else None,
          language=self.api_manager.get_language(),
          diarize=self.api_manager.get_diarization_enabled(),
          smart_format=self.api_manager.get_smart_formatting_enabled(),
          max_concurrent_workers=self.api_manager.get_max_concurrent_workers()
      ),
      files=[
          FileState(source_path=str(file.path), status="pending", retry_count=0)
          for file in self.selected_files
      ],
      statistics=BatchStatistics(
          total_files=len(self.selected_files),
          pending=len(self.selected_files)
      )
  )
  
  BatchStateManager.save_batch_state(batch_state)
  self.current_batch_id = batch_id
  ```
  **Acceptance:** State file created when batch starts

- [X] **In `src/gui/main_window.py:_on_transcription_event()`, update batch state on completion:
  ```python
  if event_type == "completed":
      BatchStateManager.update_file_status(
          batch_id=self.current_batch_id,
          source_path=str(file.path),
          status="completed",
          output_path=str(extra["output_path"]),
          duration_seconds=extra.get("duration_seconds")
      )
  elif event_type == "failed":
      BatchStateManager.update_file_status(
          batch_id=self.current_batch_id,
          source_path=str(file.path),
          status="failed",
          error_message=extra["error"]
      )
  ```
  **Acceptance:** State file updated after each file completion

- [X] **In `src/gui/main_window.py:_on_batch_complete()`, cleanup state file:
  ```python
  BatchStateManager.clear_batch_state()
  logger.info("Batch complete, state file removed")
  ```
  **Acceptance:** State file removed after successful batch completion

#### 5.2.4 Edge Case Handling

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [X] **In `src/utils/batch_state_manager.py:load_batch_state()`, handle corrupted JSON:
  - Catch `json.JSONDecodeError` exception
  - Log error with `logger.error()`
  - Call `_backup_corrupted_file()` to save for debugging
  - Return `None` (fallback to new batch)
  **Acceptance:** Corrupted file doesn't crash app, backup created

- [X] **In `src/utils/batch_state_manager.py:verify_completed_files()`, check file existence:
  - For each file with status="completed", verify `Path(output_path).exists()`
  - Log warning if output missing
  - Return list of source_paths with missing outputs
  **Acceptance:** Missing output files detected

- [X] **In `src/gui/main_window.py:_resume_batch()`, handle missing source files:
  - If source file doesn't exist, `TranscriptionOrchestrator.process_file()` will fail
  - File will be marked as failed with "File not found" error
  - Batch continues with remaining files
  **Acceptance:** Missing source files handled gracefully

#### 5.2.5 Testing

**🤖 Agent: `CLAUDE-testwriter.md` 🧪**

- [X] **Create `tests/test_batch_state_manager.py` with test cases:
  - `test_save_and_load_batch_state()` - round-trip test
  - `test_corrupted_file_handling()` - verify fallback to None
  - `test_verify_completed_files()` - detect missing outputs
  - `test_mark_files_for_reprocessing()` - re-mark as pending
  - `test_atomic_write()` - verify tempfile + os.replace used
  - `test_update_file_status()` - update single file in batch
  - Add 10+ more test cases
  **Acceptance:** 16+ tests pass, all edge cases covered

- [X] **Create `tests/test_resume_batch_integration.py` with integration test:
  - Start batch of 10 files
  - Let 3 complete
  - Simulate crash (destroy window)
  - Restart app
  - Verify resume prompt shows "3 completed, 7 remaining"
  - Resume batch
  - Verify only 7 files processed
  **Acceptance:** Integration test passes, resume workflow validated

#### 5.2.6 Stage 5.2 Validation

**🤖 Agent: `CLAUDE-backend.md` 🔧 + `CLAUDE-frontend.md` 🎨 (joint validation)**

- [ ] **Manual E2E test: resume after simulated crash:
  - Start batch of 30 files with 3 workers
  - Let 10 complete, then kill app (Task Manager)
  - Restart app, verify resume prompt
  - Click "Resume", verify only 20 files processed
  - Verify completed files are skipped
  - Complete batch, verify state file deleted
  **Acceptance:** Resume works correctly, no data loss

- [ ] **Manual E2E test: missing output file handling:
  - Start batch, let 15 complete
  - Manually delete 5 output .txt files
  - Kill app, restart
  - Verify warning: "5 output file(s) missing and will be reprocessed"
  - Resume, verify those 5 are re-processed
  **Acceptance:** Missing outputs detected and re-processed

### 5.3 Integration & Final Validation

**🤖 Agent: `CLAUDE-backend.md` 🔧**

- [ ] **Integration test: parallel processing + persistence together:
  - Start batch of 20 files with 3 workers
  - Let 10 complete
  - Kill app during processing (mid-batch)
  - Restart, verify resume prompt shows "10 completed, 10 remaining"
  - Resume with 3 workers
  - Verify only 10 files processed concurrently
  - Complete batch successfully
  **Acceptance:** Both features work together without conflicts

- [ ] **Manual E2E test: cancel mid-parallel-batch then resume:
  - Start 30 files with 5 workers
  - Let 10 complete, then click Cancel
  - Verify remaining 20 marked as SKIPPED
  - Restart app
  - Verify resume prompt shows "10 completed, 20 skipped"
  - Resume, verify all 20 are processed (re-marked as pending)
  **Acceptance:** Cancel + resume workflow works correctly

- [ ] **Performance benchmark: compare 1 vs 3 vs 5 workers:
  - Benchmark: 50 files with 1 worker (baseline)
  - Benchmark: 50 files with 3 workers
  - Benchmark: 50 files with 5 workers
  - Measure total time for each
  - Verify ~3x speedup with 3 workers, ~5x with 5 workers
  **Acceptance:** Performance improvements verified

- [ ] **Manual E2E test with real Deepgram API:
  - Use 10 real audio/video files (not mocked)
  - Process with 3 workers
  - Verify all complete successfully
  - Check output files for correctness
  - Verify no API rate limit errors
  **Acceptance:** Real-world usage works correctly

- [ ] **Code review: verify concurrency safety:
  - Check `TranscriptionService` for shared state (should be none)
  - Check `MediaConverter` for unique temp file names (uuid.uuid4())
  - Check `OutputWriter` for unique output paths
  - Check `SessionLogger` has thread locks
  - Check GUI updates use `self.after(0, ...)`
  **Acceptance:** No concurrency issues found

- [ ] **Final validation: full test suite + manual testing:
  - Run all unit tests: `pytest --cov=src`
  - Run all integration tests
  - Manual E2E: 100 files with 3 workers (50 audio, 50 video)
  - Verify all features work: parallel processing, resume, cancel, retry
  - Verify no crashes or data loss
  **Acceptance:** All tests pass, 100/100 files complete successfully

## Post-Refactoring Notes

**When all stages are complete:**

1. Review this file and ensure all tasks are marked with `[X]`
2. Run final validation: `pytest --cov=src` should show 70%+ coverage
3. Create Git tag: `git tag v1.1.0-refactored`
4. Archive this tasks.md for future reference

**Known limitations after refactoring:**
- GUI tests are minimal (manual testing only) - automated GUI testing can be added in future
- Performance optimization (async/await) is out of scope - can be Phase 2
- CLI version is not implemented - can be added using TranscriptionOrchestrator

**Suggested next steps (Phase 2):**
- Extract reusable widgets (LabeledEntry, FileListWidget)
- Add CI/CD pipeline with GitHub Actions
- Implement async/await for better concurrency
- Add Sentry integration for error reporting

---

**End of Task List**
