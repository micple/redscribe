"""
Main application window.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
import threading
import os
import time
from typing import Optional

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
)
from src.utils.api_manager import APIManager
from src.core.file_scanner import FileScanner
from src.core.media_converter import MediaConverter, FFmpegNotFoundError
from src.core.transcription import TranscriptionService
from src.core.output_writer import OutputWriter
from src.models.media_file import MediaFile, TranscriptionStatus, ErrorCategory
from src.core.error_classifier import ErrorClassifier
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

        # Cleanup old temporary files from previous sessions
        self._cleanup_temp_files()

        # State
        self.selected_directory: Optional[Path] = None
        self.selected_files: list[MediaFile] = []
        self.root_node = None  # DirectoryNode from file scanner
        self.cancel_requested = False
        self.processing_thread: Optional[threading.Thread] = None
        self.last_output_dir: Optional[Path] = None

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
                print(f"Could not create icon: {e}")
                return

        # Set the icon
        try:
            self.iconbitmap(str(icon_path))
        except Exception as e:
            print(f"Could not set icon: {e}")

    def _create_icon(self, icon_path: Path):
        """Create a red R icon file."""
        # Create a simple red icon with white R
        sizes = [(16, 16), (32, 32), (48, 48), (256, 256)]
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

    def _create_widgets(self):
        """Create main window widgets using grid layout."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Main container with premium dark background
        self.configure(fg_color=COLORS["background"])

        # Tab view container
        tab_container = ctk.CTkFrame(self, fg_color=COLORS["background"])
        tab_container.grid(row=0, column=0, sticky="nsew", padx=SPACING["lg"], pady=SPACING["lg"])
        tab_container.grid_columnconfigure(0, weight=1)
        tab_container.grid_rowconfigure(1, weight=1)

        # ===== Top Bar: Tabs on left + Credits on right =====
        top_bar = ctk.CTkFrame(tab_container, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, PADDING["small"]))
        top_bar.grid_columnconfigure(1, weight=1)

        # Tab selector (segmented button)
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

        # Credits display
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

        # Help icon for credits (hidden by default)
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

        # ===== Content Container =====
        content_container = ctk.CTkFrame(tab_container, fg_color=COLORS["background"])
        content_container.grid(row=1, column=0, sticky="nsew")
        content_container.grid_columnconfigure(0, weight=1)
        content_container.grid_rowconfigure(0, weight=1)

        # Main tab frame
        self.main_tab_frame = ctk.CTkFrame(content_container, fg_color=COLORS["background"])
        self.main_tab_frame.grid(row=0, column=0, sticky="nsew")

        # YouTube tab frame
        self.youtube_tab_frame = ctk.CTkFrame(content_container, fg_color=COLORS["background"])
        self.youtube_tab_frame.grid(row=0, column=0, sticky="nsew")
        self.youtube_tab_frame.grid_remove()  # Hidden by default

        # Logs tab frame
        self.logs_tab_frame = ctk.CTkFrame(content_container, fg_color=COLORS["background"])
        self.logs_tab_frame.grid(row=0, column=0, sticky="nsew")
        self.logs_tab_frame.grid_remove()  # Hidden by default

        # Aliases for the content setup
        main_tab = self.main_tab_frame
        logs_tab_frame = self.logs_tab_frame

        # Configure main tab
        main_tab.grid_columnconfigure(0, weight=1)
        main_tab.grid_rowconfigure(2, weight=1)

        # ===== Main Tab Content =====
        main_container = main_tab  # Use main_tab as the container

        # ===== Directory Selection Section =====
        dir_frame = ctk.CTkFrame(main_container, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])
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

        # Recursive checkbox
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

        # ===== Files Selection Section =====
        files_frame = ctk.CTkFrame(main_container, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])
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

        # ===== Options Section =====
        options_frame = ctk.CTkFrame(main_container, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])
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

        # Diarization checkbox
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

        # ===== Output Location Section =====
        output_frame = ctk.CTkFrame(main_container, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])
        output_frame.grid(row=3, column=0, sticky="ew", pady=(0, SPACING["base"]))
        output_frame.grid_columnconfigure(2, weight=1)

        output_label = ctk.CTkLabel(output_frame, text="Output location:", font=FONTS["body"])
        output_label.grid(row=0, column=0, columnspan=4, padx=PADDING["medium"], pady=(PADDING["medium"], PADDING["small"]), sticky="w")

        # Radio buttons for output location
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

        # ===== Action Buttons =====
        action_frame = ctk.CTkFrame(main_container, fg_color="transparent")
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

        # About button (info icon)
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

        # ===== YouTube Tab Content =====
        self.youtube_tab_frame.grid_columnconfigure(0, weight=1)
        self.youtube_tab_frame.grid_rowconfigure(0, weight=1)

        self.youtube_tab = YouTubeTab(
            self.youtube_tab_frame,
            api_manager=self.api_manager,
            session_logger=self.session_logger,
            open_settings_callback=self._open_settings,
        )
        self.youtube_tab.grid(row=0, column=0, sticky="nsew")

        # ===== Logs Tab Content =====
        logs_tab_frame.grid_columnconfigure(0, weight=1)
        logs_tab_frame.grid_rowconfigure(0, weight=1)

        self.logs_tab = LogsTab(logs_tab_frame)
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
        def fetch_credits():
            balance = self.api_manager.get_balance()
            self.after(0, lambda: self._update_credits_display(balance))

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
            print(f"Credits error: {error_msg}")

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
        self.cancel_requested = False
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
        self.cancel_requested = True

    def _on_progress_close(self):
        """Handle progress dialog close."""
        self._scan_directory()
        self._refresh_credits()

    def _process_files(self, api_key: str, converter: MediaConverter):
        """Process files in background thread with automatic retry."""
        output_format = self.format_var.get()
        language = self._get_language_code()
        diarize = self.diarize_var.get()
        model = self.api_manager.get_model_string(language)
        transcription_service = TranscriptionService(api_key, model=model)
        output_dir = self._get_output_dir()

        total = len(self.selected_files)
        success_count = 0

        # PHASE 1: Process all files
        for i, file in enumerate(self.selected_files):
            if self.cancel_requested:
                for remaining in self.selected_files[i:]:
                    remaining.status = TranscriptionStatus.SKIPPED
                    self.after(0, lambda idx=self.selected_files.index(remaining):
                        self.progress_dialog.update_file_status(idx, TranscriptionStatus.SKIPPED))
                break

            # Update progress with file info
            self.after(0, lambda idx=i, f=file: self.progress_dialog.update_progress(
                idx, total, f"Processing: {f.name}", f.size_formatted
            ))

            success = self._process_single_file(
                file, i, transcription_service, converter,
                output_format, output_dir, language, diarize
            )

            if success:
                success_count += 1
            else:
                # Classify error for retry decision
                category, _ = ErrorClassifier.classify(file.error_message or "")
                file.error_category = category

        # PHASE 2: Automatic retry for retryable errors
        if not self.cancel_requested:
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
                    if self.cancel_requested:
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

                    success = self._process_single_file(
                        file, i, transcription_service, converter,
                        output_format, output_dir, language, diarize
                    )

                    if success:
                        success_count += 1

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
        if self.cancel_requested:
            self.after(0, self.progress_dialog.set_cancelled)
        else:
            self.after(0, lambda: self.progress_dialog.set_completed_with_retry(
                success_count, fail_count, failed_files, self._retry_failed_files
            ))

    def _process_single_file(
        self, file: MediaFile, index: int,
        transcription_service: TranscriptionService, converter: MediaConverter,
        output_format: str, output_dir: Optional[Path],
        language: str, diarize: bool
    ) -> bool:
        """
        Process a single file. Returns True on success, False on failure.
        """
        temp_mp3_path = None

        try:
            # Step 1: Convert if video
            if file.is_video:
                file.status = TranscriptionStatus.CONVERTING
                self.session_logger.log_converting(file.name)
                self.after(0, lambda idx=index: self.progress_dialog.update_file_status(
                    idx, TranscriptionStatus.CONVERTING, "Converting to MP3..."
                ))

                temp_mp3_path = converter.to_mp3(file.path)
                audio_path = temp_mp3_path
            else:
                audio_path = file.path

            # Step 2: Transcribe
            file.status = TranscriptionStatus.TRANSCRIBING
            self.session_logger.log_transcribing(file.name)
            self.after(0, lambda idx=index: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.TRANSCRIBING, "Sending to Deepgram..."
            ))

            result = transcription_service.transcribe(
                file_path=audio_path,
                language=language,
                diarize=diarize,
            )

            if not result.success:
                raise Exception(result.error_message or "Transcription failed")

            # Step 3: Save output
            self.after(0, lambda idx=index: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.TRANSCRIBING, "Saving result..."
            ))

            output_path = self.output_writer.save(
                result=result,
                source_path=file.path,
                output_format=output_format,
                output_dir=output_dir,
            )

            file.status = TranscriptionStatus.COMPLETED
            file.output_path = output_path
            file.error_message = None
            file.error_category = ErrorCategory.NONE

            # Log success with duration
            duration = result.duration_seconds or 0
            self.session_logger.log_file_completed(file.name, duration)

            self.after(0, lambda idx=index: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.COMPLETED, "Done"
            ))

            return True

        except Exception as e:
            file.status = TranscriptionStatus.FAILED
            file.error_message = str(e)

            # Log failure
            self.session_logger.log_file_failed(file.name, str(e))

            self.after(0, lambda idx=index, msg=str(e): self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.FAILED, msg[:50]
            ))

            return False

        finally:
            if temp_mp3_path:
                converter.cleanup(temp_mp3_path)

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
            if self.cancel_requested:
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

    def _cleanup_temp_files(self) -> None:
        """
        Clean up temporary files from previous sessions.

        Removes any leftover MP3 files in the temp directory that may have
        been left behind if the application crashed or was force-closed.
        """
        try:
            if TEMP_DIR.exists():
                for file in TEMP_DIR.glob("*.mp3"):
                    try:
                        file.unlink()
                    except OSError:
                        pass  # Ignore files that can't be deleted (in use, etc.)

            # Also clean YouTube temp directory
            if YOUTUBE_TEMP_DIR.exists():
                for file in YOUTUBE_TEMP_DIR.glob("*.mp3"):
                    try:
                        file.unlink()
                    except OSError:
                        pass
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
            try:
                if file.path.exists():
                    file.path.unlink()
            except OSError:
                pass
