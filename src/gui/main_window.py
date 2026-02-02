"""
Main application window.
"""
import logging
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
import threading
import os
import time
import uuid
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from config import (
    APP_NAME,
    APP_VERSION,
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    SUPPORTED_LANGUAGES,
    OUTPUT_FORMATS,
    TEMP_DIR,
    YOUTUBE_TEMP_DIR,
    ICON_SIZES,
)
from src.utils.api_manager import APIManager
from src.utils.temp_file_manager import TempFileManager
from src.utils.batch_state_manager import BatchStateManager
from src.core.transcription_orchestrator import TranscriptionOrchestrator
from src.core.file_scanner import FileScanner
from src.core.media_converter import MediaConverter, FFmpegNotFoundError
from src.core.transcription import TranscriptionService
from src.core.output_writer import OutputWriter
from src.models.media_file import MediaFile, TranscriptionStatus, ErrorCategory
from src.core.error_classifier import ErrorClassifier
from contracts.batch_state import BatchState, BatchSettings, FileState, BatchStatistics
from src.gui.styles import configure_theme, FONTS, PADDING, COLORS, SPACING, BUTTON_STYLES, DIMENSIONS, Tooltip
from src.gui.settings_dialog import SettingsDialog
from src.gui.file_browser_dialog import FileBrowserDialog
from src.gui.progress_dialog import ProgressDialog
from src.gui.logs_tab import LogsTab
from src.gui.youtube_tab import YouTubeTab
from src.utils.session_logger import get_logger


class MainWindow(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Configure theme
        configure_theme()

        # Initialize components
        self.api_manager = APIManager()
        self.file_scanner = FileScanner()
        self.output_writer = OutputWriter()
        self.session_logger = get_logger()
        self.temp_manager = TempFileManager(TEMP_DIR)

        # Cleanup old temporary files from previous sessions
        self._cleanup_temp_files()

        # State
        self.selected_directory: Optional[Path] = None
        self.selected_files: list[MediaFile] = []
        self.root_node = None  # DirectoryNode from file scanner
        self.cancel_event = threading.Event()
        self.processing_thread: Optional[threading.Thread] = None
        self.last_output_dir: Optional[Path] = None
        self._credits_refreshing = False
        self.current_batch_id: Optional[str] = None

        # Window configuration
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(f"{WINDOW_MIN_WIDTH}x{WINDOW_MIN_HEIGHT}")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # Set window icon
        self._set_window_icon()

        # Create UI
        self._create_widgets()

        # Check for API key and load credits on startup
        self.after(100, self._on_startup)

        # Check for pending batch after startup
        self.after(500, self._check_pending_batch)

    def _set_window_icon(self):
        """Set the window icon with a red R."""
        if not HAS_PIL:
            return

        # Path to icon file
        icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.ico"

        # Create icon if it doesn't exist
        if not icon_path.exists():
            try:
                self._create_icon(icon_path)
            except Exception as e:
                logger.warning("Could not create icon: %s", e)
                return

        # Set the icon
        try:
            self.iconbitmap(str(icon_path))
        except Exception as e:
            logger.warning("Could not set icon: %s", e)

    def _create_icon(self, icon_path: Path):
        """Create a red R icon file."""
        # Create a simple red icon with white R
        sizes = ICON_SIZES
        images = []

        for size in sizes:
            img = Image.new('RGBA', size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Draw red rounded rectangle background
            margin = size[0] // 8
            draw.rounded_rectangle(
                [margin, margin, size[0] - margin, size[1] - margin],
                radius=size[0] // 4,
                fill='#B83A3F'  # Elegant red from our color scheme
            )

            # Draw white R letter
            try:
                font_size = int(size[0] * 0.6)
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                font = ImageFont.load_default()

            # Center the R
            bbox = draw.textbbox((0, 0), "R", font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (size[0] - text_width) // 2
            y = (size[1] - text_height) // 2 - bbox[1]

            draw.text((x, y), "R", fill='white', font=font)
            images.append(img)

        # Save as ICO
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        images[0].save(str(icon_path), format='ICO', sizes=[(s[0], s[1]) for s in sizes])

    def _on_startup(self):
        """Perform startup tasks."""
        self._refresh_credits()
        if not self.api_manager.has_api_key():
            messagebox.showinfo(
                "Configuration Required",
                "Please enter your Deepgram API key to use this application."
            )
            self._open_settings()

    def _check_pending_batch(self):
        """Check for interrupted batch and offer to resume."""
        try:
            if not BatchStateManager.has_pending_batch():
                return

            state = BatchStateManager.load_batch_state()
            if state is None:
                BatchStateManager.clear_batch_state()
                return

            incomplete = sum(1 for f in state.files if f.status.value in ("pending", "failed", "skipped"))
            completed = sum(1 for f in state.files if f.status.value == "completed")

            if incomplete == 0:
                BatchStateManager.clear_batch_state()
                return

            resume = messagebox.askyesno(
                "Resume Batch",
                f"Found incomplete batch:\n"
                f"  {completed} completed, {incomplete} remaining.\n\n"
                f"Resume transcription?"
            )

            if resume:
                self._resume_batch(state)
            else:
                BatchStateManager.clear_batch_state()
        except Exception as e:
            logger.error(f"Error checking pending batch: {e}")

    def _resume_batch(self, state: BatchState):
        """Resume an interrupted batch."""
        # Verify completed files still exist
        missing = BatchStateManager.verify_completed_files(state)
        if missing:
            BatchStateManager.mark_files_for_reprocessing(state, missing)
            messagebox.showwarning(
                "Missing Files",
                f"{len(missing)} output file(s) missing and will be reprocessed."
            )

        # Reconstruct selected_files from state
        self.selected_files = []
        for file_state in state.files:
            media_file = MediaFile(Path(file_state.source_path))
            # Map status
            status_map = {
                "pending": TranscriptionStatus.PENDING,
                "converting": TranscriptionStatus.CONVERTING,
                "transcribing": TranscriptionStatus.TRANSCRIBING,
                "completed": TranscriptionStatus.COMPLETED,
                "failed": TranscriptionStatus.FAILED,
                "skipped": TranscriptionStatus.SKIPPED,
            }
            media_file.status = status_map.get(file_state.status.value, TranscriptionStatus.PENDING)
            # Reset SKIPPED files to PENDING for resume
            if file_state.status.value == "skipped":
                media_file.status = TranscriptionStatus.PENDING
            if file_state.output_path:
                media_file.output_path = Path(file_state.output_path)
            media_file.error_message = file_state.error_message
            media_file.retry_count = file_state.retry_count
            self.selected_files.append(media_file)

        # Restore settings
        self.format_var.set(state.settings.output_format)

        # Update UI
        count = len(self.selected_files)
        if count > 0:
            total_size = sum(f.size_bytes for f in self.selected_files)
            size_str = self._format_size(total_size)
            self.files_summary_label.configure(
                text=f"{count} files selected ({size_str}) - Resumed",
                text_color=COLORS["primary"],
            )

        self.current_batch_id = state.batch_id
        self._update_start_button()

        logger.info(f"Resumed batch {state.batch_id} with {len(self.selected_files)} files")

        # Start transcription automatically after resume
        self.after(100, self._start_transcription)

    def _create_widgets(self):
        """Create main window widgets using grid layout.

        Orchestrates widget creation by delegating to focused helper methods,
        each responsible for one logical section of the UI.
        """
        self._setup_layout()
        self._create_top_bar()
        self._create_tab_frames()
        self._create_directory_section()
        self._create_files_section()
        self._create_options_section()
        self._create_output_section()
        self._create_action_buttons()
        self._create_youtube_tab()
        self._create_logs_tab()

    def _setup_layout(self):
        """Configure the root grid layout and main containers.

        Creates the top-level grid configuration and the tab_container
        and content_container frames that hold all other widgets.
        """
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.configure(fg_color=COLORS["background"])

        self._tab_container = ctk.CTkFrame(self, fg_color=COLORS["background"])
        self._tab_container.grid(row=0, column=0, sticky="nsew", padx=SPACING["lg"], pady=SPACING["lg"])
        self._tab_container.grid_columnconfigure(0, weight=1)
        self._tab_container.grid_rowconfigure(1, weight=1)

        self._content_container = ctk.CTkFrame(self._tab_container, fg_color=COLORS["background"])
        self._content_container.grid(row=1, column=0, sticky="nsew")
        self._content_container.grid_columnconfigure(0, weight=1)
        self._content_container.grid_rowconfigure(0, weight=1)

    def _create_top_bar(self):
        """Create the top bar with tab selector and credits display.

        Creates:
            - Tab selector segmented button (Main, YouTube, Logs)
            - Credits display frame with label and help icon
        """
        top_bar = ctk.CTkFrame(self._tab_container, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, PADDING["small"]))
        top_bar.grid_columnconfigure(1, weight=1)

        self.tab_selector = ctk.CTkSegmentedButton(
            top_bar,
            values=["Main", "YouTube", "Logs"],
            command=self._on_tab_change,
            fg_color=COLORS["surface"],
            selected_color=COLORS["primary"],
            selected_hover_color=COLORS["primary_hover"],
            unselected_color=COLORS["surface"],
            unselected_hover_color=COLORS["surface_elevated"],
            text_color=COLORS["text"],
            text_color_disabled=COLORS["text_secondary"],
        )
        self.tab_selector.set("Main")
        self.tab_selector.grid(row=0, column=0, sticky="w")

        self.credits_frame = ctk.CTkFrame(top_bar, fg_color=COLORS["surface_elevated"], corner_radius=6)
        self.credits_frame.grid(row=0, column=2, sticky="e")

        self.credits_label = ctk.CTkLabel(
            self.credits_frame,
            text="Credits: --",
            font=FONTS["small"],
            padx=PADDING["small"],
            pady=2,
        )
        self.credits_label.pack(side="left")

        self.credits_help_btn = ctk.CTkLabel(
            self.credits_frame,
            text="(?)",
            font=FONTS["small"],
            text_color=COLORS["warning"],
            cursor="question_arrow",
            padx=4,
            pady=2,
        )
        self.credits_tooltip = None

    def _create_tab_frames(self):
        """Create the main, YouTube, and logs tab frames.

        Sets up the three content frames that are shown/hidden
        when the user switches tabs via the segmented button.
        """
        self.main_tab_frame = ctk.CTkFrame(self._content_container, fg_color=COLORS["background"])
        self.main_tab_frame.grid(row=0, column=0, sticky="nsew")

        self.youtube_tab_frame = ctk.CTkFrame(self._content_container, fg_color=COLORS["background"])
        self.youtube_tab_frame.grid(row=0, column=0, sticky="nsew")
        self.youtube_tab_frame.grid_remove()

        self.logs_tab_frame = ctk.CTkFrame(self._content_container, fg_color=COLORS["background"])
        self.logs_tab_frame.grid(row=0, column=0, sticky="nsew")
        self.logs_tab_frame.grid_remove()

        self.main_tab_frame.grid_columnconfigure(0, weight=1)
        self.main_tab_frame.grid_rowconfigure(2, weight=1)

    def _create_directory_section(self):
        """Create the directory selection section.

        Creates:
            - Directory entry field (readonly)
            - Browse button for directory selection
            - Recursive subdirectory checkbox
        """
        dir_frame = ctk.CTkFrame(self.main_tab_frame, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])
        dir_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["base"]))
        dir_frame.grid_columnconfigure(1, weight=1)

        dir_label = ctk.CTkLabel(dir_frame, text="Directory:", font=FONTS["body"])
        dir_label.grid(row=0, column=0, padx=PADDING["medium"], pady=PADDING["medium"], sticky="w")

        self.dir_entry = ctk.CTkEntry(dir_frame, font=FONTS["body"], state="readonly")
        self.dir_entry.grid(row=0, column=1, padx=(0, PADDING["small"]), pady=PADDING["medium"], sticky="ew")

        self.browse_btn = ctk.CTkButton(
            dir_frame,
            text="Browse",
            width=100,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._browse_directory,
        )
        self.browse_btn.grid(row=0, column=2, padx=(0, PADDING["medium"]), pady=PADDING["medium"])

        self.recursive_var = ctk.BooleanVar(value=False)
        self.recursive_check = ctk.CTkCheckBox(
            dir_frame,
            text="Include subdirectories",
            variable=self.recursive_var,
            command=self._on_recursive_change,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        )
        self.recursive_check.grid(row=1, column=0, columnspan=3, padx=PADDING["medium"], pady=(0, PADDING["small"]), sticky="w")

    def _create_files_section(self):
        """Create the file selection section.

        Creates:
            - Files summary label showing selection count
            - Select Files button to open file browser dialog
        """
        files_frame = ctk.CTkFrame(self.main_tab_frame, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])
        files_frame.grid(row=1, column=0, sticky="ew", pady=(0, SPACING["base"]))
        files_frame.grid_columnconfigure(1, weight=1)

        files_label = ctk.CTkLabel(files_frame, text="Files to transcribe:", font=FONTS["body"])
        files_label.grid(row=0, column=0, padx=PADDING["medium"], pady=PADDING["medium"], sticky="w")

        self.files_summary_label = ctk.CTkLabel(
            files_frame,
            text="No files selected",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
        )
        self.files_summary_label.grid(row=0, column=1, padx=PADDING["small"], pady=PADDING["medium"], sticky="w")

        self.select_files_btn = ctk.CTkButton(
            files_frame,
            text="Select Files...",
            width=120,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            state="disabled",
            command=self._open_file_browser,
        )
        self.select_files_btn.grid(row=0, column=2, padx=(0, PADDING["medium"]), pady=PADDING["medium"])

    def _create_options_section(self):
        """Create the transcription options section.

        Creates:
            - Output format radio buttons (left column)
            - Speaker diarization checkbox (left column)
            - Language dropdown (right column)
            - Language info label (right column)
        """
        options_frame = ctk.CTkFrame(self.main_tab_frame, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])
        options_frame.grid(row=2, column=0, sticky="ew", pady=(0, SPACING["base"]))
        options_frame.grid_columnconfigure(0, weight=1)
        options_frame.grid_columnconfigure(1, weight=1)

        # Left column - Format selection
        left_col = ctk.CTkFrame(options_frame, fg_color="transparent")
        left_col.grid(row=0, column=0, padx=PADDING["medium"], pady=PADDING["medium"], sticky="nw")

        format_label = ctk.CTkLabel(left_col, text="Output format:", font=FONTS["body"])
        format_label.pack(anchor="w")

        format_frame = ctk.CTkFrame(left_col, fg_color="transparent")
        format_frame.pack(anchor="w", pady=(PADDING["small"], 0))

        self.format_var = ctk.StringVar(value="txt")
        for fmt in OUTPUT_FORMATS:
            rb = ctk.CTkRadioButton(
                format_frame,
                text=fmt.upper(),
                variable=self.format_var,
                value=fmt,
                fg_color=COLORS["primary"],
                hover_color=COLORS["primary_hover"],
                border_color=COLORS["border"],
            )
            rb.pack(side="left", padx=(0, PADDING["medium"]))

        self.diarize_var = ctk.BooleanVar(value=False)
        self.diarize_check = ctk.CTkCheckBox(
            left_col,
            text="Speaker diarization",
            variable=self.diarize_var,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        )
        self.diarize_check.pack(anchor="w", pady=(PADDING["small"], 0))

        # Right column - Language selection
        right_col = ctk.CTkFrame(options_frame, fg_color="transparent")
        right_col.grid(row=0, column=1, padx=PADDING["medium"], pady=PADDING["medium"], sticky="ne")

        lang_label = ctk.CTkLabel(right_col, text="Language:", font=FONTS["body"])
        lang_label.pack(anchor="w")

        lang_options = [f"{name} ({code})" for code, name in SUPPORTED_LANGUAGES.items()]
        self.lang_var = ctk.StringVar(value=lang_options[0])
        self.lang_dropdown = ctk.CTkOptionMenu(
            right_col,
            values=lang_options,
            variable=self.lang_var,
            width=180,
            fg_color=COLORS["surface_elevated"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["surface_elevated"],
            text_color=COLORS["text"],
            dropdown_text_color=COLORS["text"],
        )
        self.lang_dropdown.pack(anchor="w", pady=(PADDING["small"], 0))

        lang_info_label = ctk.CTkLabel(
            right_col,
            text="Manual selection provides best accuracy",
            font=FONTS["small"],
            text_color=COLORS["text_tertiary"],
        )
        lang_info_label.pack(anchor="w", pady=(SPACING["xs"], 0))

    def _create_output_section(self):
        """Create the output location section.

        Creates:
            - Output location label
            - Radio buttons for source-relative or custom output
            - Output directory entry field
            - Browse button for output directory
        """
        output_frame = ctk.CTkFrame(self.main_tab_frame, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])
        output_frame.grid(row=3, column=0, sticky="ew", pady=(0, SPACING["base"]))
        output_frame.grid_columnconfigure(2, weight=1)

        output_label = ctk.CTkLabel(output_frame, text="Output location:", font=FONTS["body"])
        output_label.grid(row=0, column=0, columnspan=4, padx=PADDING["medium"], pady=(PADDING["medium"], PADDING["small"]), sticky="w")

        self.output_location_var = ctk.StringVar(value="source")

        source_radio = ctk.CTkRadioButton(
            output_frame,
            text="Save next to source file",
            variable=self.output_location_var,
            value="source",
            command=self._on_output_location_change,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        )
        source_radio.grid(row=1, column=0, columnspan=4, padx=PADDING["medium"], pady=(0, PADDING["small"]), sticky="w")

        custom_radio = ctk.CTkRadioButton(
            output_frame,
            text="Save all to:",
            variable=self.output_location_var,
            value="custom",
            command=self._on_output_location_change,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        )
        custom_radio.grid(row=2, column=0, padx=PADDING["medium"], pady=(0, PADDING["medium"]), sticky="w")

        self.output_dir_entry = ctk.CTkEntry(
            output_frame,
            font=FONTS["body"],
            state="disabled",
        )
        self.output_dir_entry.grid(row=2, column=1, columnspan=2, padx=PADDING["small"], pady=(0, PADDING["medium"]), sticky="ew")

        self.output_browse_btn = ctk.CTkButton(
            output_frame,
            text="Browse",
            width=100,
            height=DIMENSIONS["button_height"],
            state="disabled",
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            text_color_disabled=COLORS["text_secondary"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._browse_output_directory,
        )
        self.output_browse_btn.grid(row=2, column=3, padx=(0, PADDING["medium"]), pady=(0, PADDING["medium"]))

    def _create_action_buttons(self):
        """Create the bottom action buttons row.

        Creates:
            - Settings button (left)
            - Start Transcription button (right)
            - About info button (far right)
        """
        action_frame = ctk.CTkFrame(self.main_tab_frame, fg_color="transparent")
        action_frame.grid(row=4, column=0, sticky="ew")
        action_frame.grid_columnconfigure(1, weight=1)

        self.settings_btn = ctk.CTkButton(
            action_frame,
            text="\u2699 Settings",
            width=100,
            height=DIMENSIONS["button_height"],
            fg_color="transparent",
            hover_color=COLORS["surface"],
            text_color=COLORS["text_secondary"],
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._open_settings,
        )
        self.settings_btn.grid(row=0, column=0, sticky="w")

        self.start_btn = ctk.CTkButton(
            action_frame,
            text="\u25B6 Start Transcription",
            width=180,
            height=DIMENSIONS["button_height"],
            state="disabled",
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._start_transcription,
        )
        self.start_btn.grid(row=0, column=2, sticky="e")

        self.about_btn = ctk.CTkButton(
            action_frame,
            text="\u2139",
            width=40,
            height=DIMENSIONS["button_height"],
            fg_color="transparent",
            hover_color=COLORS["surface"],
            text_color=COLORS["text_secondary"],
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._show_about_dialog,
        )
        self.about_btn.grid(row=0, column=3, sticky="e", padx=(SPACING["sm"], 0))

    def _create_youtube_tab(self):
        """Create the YouTube tab content.

        Initializes the YouTubeTab widget inside the youtube_tab_frame.
        """
        self.youtube_tab_frame.grid_columnconfigure(0, weight=1)
        self.youtube_tab_frame.grid_rowconfigure(0, weight=1)

        self.youtube_tab = YouTubeTab(
            self.youtube_tab_frame,
            api_manager=self.api_manager,
            session_logger=self.session_logger,
            open_settings_callback=self._open_settings,
        )
        self.youtube_tab.grid(row=0, column=0, sticky="nsew")

    def _create_logs_tab(self):
        """Create the Logs tab content.

        Initializes the LogsTab widget inside the logs_tab_frame.
        """
        self.logs_tab_frame.grid_columnconfigure(0, weight=1)
        self.logs_tab_frame.grid_rowconfigure(0, weight=1)

        self.logs_tab = LogsTab(self.logs_tab_frame)
        self.logs_tab.grid(row=0, column=0, sticky="nsew")

    def _show_about_dialog(self):
        """Show the About dialog with application info."""
        from src.gui.about_dialog import AboutDialog
        AboutDialog(self)

    def _on_tab_change(self, selected_tab: str):
        """Handle tab selection change."""
        # Hide all tabs
        self.main_tab_frame.grid_remove()
        self.youtube_tab_frame.grid_remove()
        self.logs_tab_frame.grid_remove()

        # Show selected tab
        if selected_tab == "Main":
            self.main_tab_frame.grid()
        elif selected_tab == "YouTube":
            self.youtube_tab_frame.grid()
        else:  # Logs
            self.logs_tab_frame.grid()

    def _refresh_credits(self):
        """Refresh the credits display."""
        if self._credits_refreshing:
            return

        self._credits_refreshing = True

        def fetch_credits():
            try:
                balance = self.api_manager.get_balance()
                try:
                    self.after(0, lambda: self._update_credits_display(balance))
                except RuntimeError:
                    pass  # Window may have been destroyed
            finally:
                try:
                    self.after(0, lambda: setattr(self, '_credits_refreshing', False))
                except RuntimeError:
                    self._credits_refreshing = False

        thread = threading.Thread(target=fetch_credits, daemon=True)
        thread.start()

    def _update_credits_display(self, balance: Optional[dict]):
        """Update the credits label with fetched balance."""
        # Hide help icon by default
        self.credits_help_btn.pack_forget()
        tooltip_text = None

        if balance is None:
            self.credits_label.configure(text="Credits: --")
            tooltip_text = "No API key configured.\nGo to Settings to add your Deepgram API key."
        elif "error" in balance:
            error_msg = balance.get("error", "Unknown error")
            logger.warning("Credits error: %s", error_msg)

            if "403" in str(error_msg):
                self.credits_label.configure(text="Credits: N/A")
                tooltip_text = (
                    "API key lacks permission to view balance.\n\n"
                    "To fix this:\n"
                    "1. Go to console.deepgram.com\n"
                    "2. Create a new API key with 'Admin' or 'Owner' role\n"
                    "3. Update the key in Settings\n\n"
                    "Note: Transcription will still work."
                )
            elif "401" in str(error_msg):
                self.credits_label.configure(text="Credits: Invalid key")
                tooltip_text = "API key is invalid or expired.\nPlease check your key in Settings."
            elif "Timeout" in str(error_msg):
                self.credits_label.configure(text="Credits: Timeout")
                tooltip_text = "Could not connect to Deepgram.\nCheck your internet connection."
            else:
                self.credits_label.configure(text="Credits: N/A")
                tooltip_text = f"Error: {error_msg}"
        else:
            amount = balance.get("amount", 0)
            units = balance.get("units", "")
            if units == "usd":
                self.credits_label.configure(text=f"Credits: ${amount:.2f}")
            elif units == "hour":
                self.credits_label.configure(text=f"Credits: {amount:.1f} hrs")
            else:
                self.credits_label.configure(text=f"Credits: {amount}")

        # Show help icon with tooltip if there's an issue
        if tooltip_text:
            self.credits_help_btn.pack(side="left")
            if self.credits_tooltip:
                self.credits_tooltip.update_text(tooltip_text)
            else:
                self.credits_tooltip = Tooltip(self.credits_help_btn, tooltip_text, delay=200)

    def _browse_directory(self):
        """Open directory browser dialog."""
        directory = filedialog.askdirectory(
            title="Select directory with audio/video files"
        )

        if directory:
            self.selected_directory = Path(directory)
            self.dir_entry.configure(state="normal")
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, str(self.selected_directory))
            self.dir_entry.configure(state="readonly")
            self._scan_directory()

    def _scan_directory(self):
        """Scan the selected directory for media files in background thread."""
        if not self.selected_directory:
            return

        # Show scanning indicator
        self.files_summary_label.configure(
            text="Scanning directory...",
            text_color=COLORS["text_secondary"],
        )
        self.select_files_btn.configure(state="disabled")
        self.update()

        def scan_thread():
            try:
                result = self.file_scanner.scan_directory(
                    self.selected_directory,
                    recursive=self.recursive_var.get(),
                )
                self.after(0, lambda: self._on_scan_complete(result, None))
            except Exception as e:
                self.after(0, lambda: self._on_scan_complete(None, str(e)))

        thread = threading.Thread(target=scan_thread, daemon=True)
        thread.start()

    def _on_scan_complete(self, root_node, error):
        """Handle scan completion on main thread."""
        if error:
            messagebox.showerror("Error", f"Cannot scan directory:\n{error}")
            self.files_summary_label.configure(
                text="Scan failed",
                text_color=COLORS["error"],
            )
            return

        self.root_node = root_node
        total_files = self.root_node.total_files if self.root_node else 0

        if total_files > 0:
            self.files_summary_label.configure(
                text=f"{total_files} files found - click to select",
                text_color=COLORS["text"],
            )
            self.select_files_btn.configure(state="normal")
        else:
            self.files_summary_label.configure(
                text="No audio/video files found",
                text_color=COLORS["text_secondary"],
            )
            self.select_files_btn.configure(state="disabled")

        # Clear previous selection
        self.selected_files = []
        self._update_start_button()

    def _on_recursive_change(self):
        """Handle recursive checkbox change."""
        self._scan_directory()

    def _open_file_browser(self):
        """Open the file browser dialog."""
        if not self.root_node:
            return

        def on_confirm(selected_files: list):
            self._on_selection_change(selected_files)

        FileBrowserDialog(self, self.root_node, on_confirm=on_confirm)

    def _on_selection_change(self, selected_files: list[MediaFile]):
        """Handle file selection change."""
        self.selected_files = selected_files
        # Update summary label
        count = len(selected_files)
        if count > 0:
            total_size = sum(f.size_bytes for f in selected_files)
            size_str = self._format_size(total_size)
            self.files_summary_label.configure(
                text=f"{count} files selected ({size_str})",
                text_color=COLORS["primary"],
            )
        else:
            total_files = self.root_node.total_files if self.root_node else 0
            self.files_summary_label.configure(
                text=f"{total_files} files found - click to select",
                text_color=COLORS["text"],
            )
        self._update_start_button()

    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def _update_start_button(self):
        """Update start button state."""
        has_files = len(self.selected_files) > 0
        # Active when files selected (API key checked on click)
        self.start_btn.configure(state="normal" if has_files else "disabled")

    def _on_output_location_change(self):
        """Handle output location radio button change."""
        if self.output_location_var.get() == "custom":
            self.output_dir_entry.configure(state="normal")
            self.output_browse_btn.configure(state="normal")
        else:
            self.output_dir_entry.configure(state="disabled")
            self.output_browse_btn.configure(state="disabled")

    def _browse_output_directory(self):
        """Open output directory browser dialog."""
        directory = filedialog.askdirectory(
            title="Select output directory"
        )

        if directory:
            self.output_dir_entry.configure(state="normal")
            self.output_dir_entry.delete(0, "end")
            self.output_dir_entry.insert(0, directory)

    def _open_settings(self):
        """Open settings dialog."""
        def on_save(api_key):
            self._update_start_button()
            self._refresh_credits()

        SettingsDialog(self, self.api_manager, on_save=on_save)

    def _get_language_code(self) -> str:
        """Extract language code from dropdown selection."""
        selection = self.lang_var.get()
        code = selection.split("(")[-1].rstrip(")")
        return code

    def _get_output_dir(self) -> Optional[Path]:
        """Get the output directory if custom location is selected."""
        if self.output_location_var.get() == "custom":
            path = self.output_dir_entry.get().strip()
            if path:
                return Path(path)
        return None

    def _start_transcription(self):
        """Start the transcription process."""
        if not self.selected_files:
            messagebox.showwarning("Warning", "No files selected")
            return

        api_key = self.api_manager.load_api_key()
        if not api_key:
            messagebox.showinfo(
                "API Key Required",
                "Please configure your Deepgram API key in Settings to start transcription."
            )
            self._open_settings()
            return

        # Check FFmpeg
        try:
            converter = MediaConverter()
        except FFmpegNotFoundError as e:
            messagebox.showerror("Error", str(e))
            return

        # Reset state
        self.cancel_event.clear()
        self.last_output_dir = self._get_output_dir() or (
            self.selected_files[0].parent_dir if self.selected_files else None
        )

        for file in self.selected_files:
            file.status = TranscriptionStatus.PENDING
            file.error_message = None
            file.retry_count = 0
            file.error_category = ErrorCategory.NONE

        # Start logging session
        model = self.api_manager.get_model_string(self._get_language_code())
        self.session_logger.set_model(model.split(":")[0] if ":" in model else model)
        self.session_logger.start_session()

        # Create batch state for persistence
        if not self.current_batch_id:
            self.current_batch_id = str(uuid.uuid4())

        output_dir = self._get_output_dir()
        batch_state = BatchState(
            batch_id=self.current_batch_id,
            created_at=datetime.now(),
            last_updated=datetime.now(),
            settings=BatchSettings(
                output_format=self.format_var.get(),
                output_dir=str(output_dir) if output_dir else None,
                language=self._get_language_code(),
                diarize=self.diarize_var.get(),
                smart_format=self.api_manager.get_preference("smart_formatting_enabled", True),
                max_concurrent_workers=self.api_manager.get_max_concurrent_workers(),
            ),
            files=[
                FileState(source_path=str(f.path), status="pending", retry_count=f.retry_count)
                for f in self.selected_files
            ],
            statistics=BatchStatistics(
                total_files=len(self.selected_files),
                pending=len(self.selected_files),
            ),
        )
        BatchStateManager.save_batch_state(batch_state)

        # Create progress dialog
        self.progress_dialog = ProgressDialog(
            self,
            self.selected_files,
            output_dir=self.last_output_dir,
            on_cancel=self._cancel_transcription,
            on_close=self._on_progress_close,
        )

        # Start processing thread
        self.processing_thread = threading.Thread(
            target=self._process_files,
            args=(api_key, converter),
            daemon=True,
        )
        self.processing_thread.start()

    def _cancel_transcription(self):
        """Cancel the transcription process."""
        self.cancel_event.set()

    def _on_progress_close(self):
        """Handle progress dialog close."""
        self._scan_directory()
        self._refresh_credits()

        # Clear batch state if dialog is closed
        # (Keep it if there are failed files for potential resume)
        if self.current_batch_id:
            has_failed = any(f.status == TranscriptionStatus.FAILED for f in self.selected_files)
            if not has_failed:
                BatchStateManager.clear_batch_state()
                self.current_batch_id = None

    def _process_files(self, api_key: str, converter: MediaConverter):
        """Process files in background thread with automatic retry using parallel workers."""
        output_format = self.format_var.get()
        language = self._get_language_code()
        diarize = self.diarize_var.get()
        model = self.api_manager.get_model_string(language)
        transcription_service = TranscriptionService(api_key, model=model)
        output_dir = self._get_output_dir()

        total = len(self.selected_files)
        success_count = 0
        max_workers = self.api_manager.get_max_concurrent_workers()

        # PHASE 1: Process all files concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for i, file in enumerate(self.selected_files):
                # Check for cancellation before submitting new futures
                if self.cancel_event.is_set():
                    break

                if file.status in (TranscriptionStatus.PENDING, TranscriptionStatus.FAILED):
                    future = executor.submit(
                        self._process_single_file,
                        file, i, transcription_service, converter,
                        output_format, output_dir, language, diarize
                    )
                    futures[future] = (i, file)

            # Initialize progress tracking
            completed_count = 0
            active_count = min(len(futures), max_workers)
            self.after(0, lambda a=active_count, t=max_workers:
                self.progress_dialog.update_workers_count(a, t))

            for future in as_completed(futures):
                if self.cancel_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    # Mark remaining files as skipped
                    for remaining_future, (idx, remaining_file) in futures.items():
                        if not remaining_future.done():
                            remaining_file.status = TranscriptionStatus.SKIPPED
                            self.after(0, lambda i=idx: self.progress_dialog.update_file_status(
                                i, TranscriptionStatus.SKIPPED
                            ))
                    break

                index, file = futures[future]

                try:
                    success = future.result()
                    if success:
                        success_count += 1
                    else:
                        # Classify error for retry decision
                        category, _ = ErrorClassifier.classify(file.error_message or "")
                        file.error_category = category
                except Exception as e:
                    logger.error(f"Error processing {file.name}: {e}")
                    file.status = TranscriptionStatus.FAILED
                    file.error_message = str(e)
                    category, _ = ErrorClassifier.classify(str(e))
                    file.error_category = category

                # Update progress after each file completes
                completed_count += 1
                active_count = max(0, active_count - 1)
                self.after(0, lambda c=completed_count, t=total, f=file:
                    self.progress_dialog.update_progress(c, t, f"Completed: {f.name}"))
                self.after(0, lambda a=active_count, t=max_workers:
                    self.progress_dialog.update_workers_count(a, t))

        # Reset workers count after parallel processing completes
        self.after(0, lambda: self.progress_dialog.update_workers_count(0, max_workers))

        # PHASE 2: Automatic retry for retryable errors
        if not self.cancel_event.is_set():
            retryable_files = [
                (i, f) for i, f in enumerate(self.selected_files)
                if f.status == TranscriptionStatus.FAILED
                and f.error_category in (
                    ErrorCategory.RETRYABLE_NETWORK,
                    ErrorCategory.RETRYABLE_RATE_LIMIT,
                    ErrorCategory.RETRYABLE_SERVER,
                )
                and f.retry_count < 1  # Only 1 automatic retry
            ]

            if retryable_files:
                # Notify user about retry phase
                self.after(0, lambda count=len(retryable_files):
                    self.progress_dialog.update_status(f"Retrying {count} failed file(s)..."))

                for i, file in retryable_files:
                    if self.cancel_event.is_set():
                        break

                    # Get delay based on error type
                    delay = ErrorClassifier.get_retry_delay(file.error_category, 1)
                    time.sleep(delay)

                    file.retry_count += 1
                    file.status = TranscriptionStatus.RETRYING
                    self.session_logger.log_retry(file.name, file.retry_count + 1)
                    self.after(0, lambda idx=i, attempt=file.retry_count:
                        self.progress_dialog.update_file_status(
                            idx, TranscriptionStatus.RETRYING, f"Retrying (attempt {attempt + 1})..."
                        ))

                    # Update workers count before retry
                    self.after(0, lambda t=max_workers:
                        self.progress_dialog.update_workers_count(1, t))

                    success = self._process_single_file(
                        file, i, transcription_service, converter,
                        output_format, output_dir, language, diarize
                    )

                    if success:
                        success_count += 1

                    # Update progress after retry completes
                    completed_count += 1
                    self.after(0, lambda c=completed_count, t=total, f=file:
                        self.progress_dialog.update_progress(c, t, f"Retry completed: {f.name}"))
                    self.after(0, lambda: self.progress_dialog.update_workers_count(0, max_workers))

        # Count final failures
        fail_count = sum(1 for f in self.selected_files if f.status == TranscriptionStatus.FAILED)
        failed_files = [f for f in self.selected_files if f.status == TranscriptionStatus.FAILED]

        # End logging session
        self.session_logger.end_session()

        # Clean up YouTube temporary files (always delete after transcription)
        for file in self.selected_files:
            if file.status == TranscriptionStatus.COMPLETED:
                self._cleanup_youtube_file(file)

        # Finalize
        if self.cancel_event.is_set():
            self.after(0, self.progress_dialog.set_cancelled)
        else:
            self.after(0, lambda: self.progress_dialog.set_completed_with_retry(
                success_count, fail_count, failed_files, self._retry_failed_files
            ))

        # Clear batch state after completion
        if self.current_batch_id and not self.cancel_event.is_set():
            BatchStateManager.clear_batch_state()
            self.current_batch_id = None

    def _process_single_file(
        self, file: MediaFile, index: int,
        transcription_service: TranscriptionService, converter: MediaConverter,
        output_format: str, output_dir: Optional[Path],
        language: str, diarize: bool
    ) -> bool:
        """
        Process a single file. Returns True on success, False on failure.

        Delegates to TranscriptionOrchestrator for the actual business logic.
        The GUI is updated via the _on_transcription_event callback.
        """
        orchestrator = TranscriptionOrchestrator(
            converter=converter,
            transcription_service=transcription_service,
            output_writer=self.output_writer,
            session_logger=self.session_logger,
            event_callback=lambda evt, f, extra: self._on_transcription_event(evt, f, extra, index),
            cancel_event=self.cancel_event,
        )
        return orchestrator.process_file(
            file=file,
            output_format=output_format,
            output_dir=output_dir,
            language=language,
            diarize=diarize,
            smart_format=True,
        )

    def _on_transcription_event(self, event_type: str, file: MediaFile, extra: dict, index: int) -> None:
        """
        Handle events from the TranscriptionOrchestrator.

        Updates the progress dialog on the GUI thread using self.after(0, ...).

        Args:
            event_type: One of 'converting', 'transcribing', 'saving', 'completed', 'failed'.
            file: The MediaFile being processed.
            extra: Additional data (e.g. output_path, error message).
            index: Index of the file in self.selected_files (for progress dialog).
        """
        if event_type == "converting":
            self.after(0, lambda idx=index: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.CONVERTING, "Converting to MP3..."
            ))
        elif event_type == "transcribing":
            self.after(0, lambda idx=index: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.TRANSCRIBING, "Sending to Deepgram..."
            ))
        elif event_type == "saving":
            self.after(0, lambda idx=index: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.TRANSCRIBING, "Saving result..."
            ))
        elif event_type == "completed":
            self.after(0, lambda idx=index: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.COMPLETED, "Done"
            ))
            # Update batch state
            if self.current_batch_id:
                try:
                    BatchStateManager.update_file_status(
                        batch_id=self.current_batch_id,
                        source_path=str(file.path),
                        status="completed",
                        output_path=str(extra.get("output_path", "")),
                        duration_seconds=extra.get("duration_seconds"),
                    )
                except Exception as e:
                    logger.error(f"Failed to update batch state: {e}")
        elif event_type == "failed":
            msg = str(extra.get("error", "Unknown error"))[:50]
            self.after(0, lambda idx=index, m=msg: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.FAILED, m
            ))
            # Update batch state
            if self.current_batch_id:
                try:
                    BatchStateManager.update_file_status(
                        batch_id=self.current_batch_id,
                        source_path=str(file.path),
                        status="failed",
                        error_message=str(extra.get("error", "")),
                    )
                except Exception as e:
                    logger.error(f"Failed to update batch state: {e}")

    def _retry_failed_files(self):
        """Retry all failed files (manual retry triggered by user)."""
        failed_files = [f for f in self.selected_files if f.status == TranscriptionStatus.FAILED]
        if not failed_files:
            return

        api_key = self.api_manager.load_api_key()
        if not api_key:
            return

        try:
            converter = MediaConverter()
        except FFmpegNotFoundError:
            return

        # Reset failed files for retry
        for file in failed_files:
            file.status = TranscriptionStatus.PENDING
            file.error_message = None
            file.error_category = ErrorCategory.NONE
            # Keep retry_count to track total attempts

        # Update UI
        self.after(0, lambda: self.progress_dialog.prepare_for_retry(failed_files))

        # Start retry in new thread
        self.processing_thread = threading.Thread(
            target=self._process_retry_files,
            args=(api_key, converter, failed_files),
            daemon=True,
        )
        self.processing_thread.start()

    def _process_retry_files(self, api_key: str, converter: MediaConverter, files_to_retry: list):
        """Process only the failed files in retry mode."""
        output_format = self.format_var.get()
        language = self._get_language_code()
        diarize = self.diarize_var.get()
        model = self.api_manager.get_model_string(language)
        transcription_service = TranscriptionService(api_key, model=model)
        output_dir = self._get_output_dir()

        success_count = 0

        for file in files_to_retry:
            if self.cancel_event.is_set():
                file.status = TranscriptionStatus.SKIPPED
                continue

            index = self.selected_files.index(file)
            file.retry_count += 1

            self.after(0, lambda f=file: self.progress_dialog.update_status(
                f"Retrying: {f.name}"
            ))

            success = self._process_single_file(
                file, index, transcription_service, converter,
                output_format, output_dir, language, diarize
            )

            if success:
                success_count += 1
            else:
                # Classify error again
                category, _ = ErrorClassifier.classify(file.error_message or "")
                file.error_category = category

        # Final count
        fail_count = sum(1 for f in files_to_retry if f.status == TranscriptionStatus.FAILED)
        failed_files = [f for f in files_to_retry if f.status == TranscriptionStatus.FAILED]

        # Update completion
        total_success = sum(1 for f in self.selected_files if f.status == TranscriptionStatus.COMPLETED)
        total_failed = sum(1 for f in self.selected_files if f.status == TranscriptionStatus.FAILED)

        self.after(0, lambda: self.progress_dialog.set_completed_with_retry(
            total_success, total_failed, failed_files, self._retry_failed_files
        ))

        # Clear batch state after retry completion if no failures
        if self.current_batch_id and total_failed == 0:
            BatchStateManager.clear_batch_state()
            self.current_batch_id = None

    def _cleanup_temp_files(self) -> None:
        """
        Clean up temporary files from previous sessions.

        Removes any leftover MP3 files in the temp directory that may have
        been left behind if the application crashed or was force-closed.
        """
        try:
            self.temp_manager.cleanup_pattern("*.mp3")
            # Also clean YouTube temp directory
            yt_manager = TempFileManager(YOUTUBE_TEMP_DIR)
            yt_manager.cleanup_pattern("*.mp3")
        except Exception:
            pass  # Don't fail startup if cleanup fails

    def _is_youtube_temp_file(self, file: MediaFile) -> bool:
        """Check if file is a YouTube temporary file that should be cleaned up."""
        try:
            return file.path.parent == YOUTUBE_TEMP_DIR
        except Exception:
            return False

    def _cleanup_youtube_file(self, file: MediaFile) -> None:
        """Clean up a YouTube temporary file after transcription."""
        if self._is_youtube_temp_file(file):
            yt_manager = TempFileManager(YOUTUBE_TEMP_DIR)
            yt_manager.cleanup_file(file.path)
