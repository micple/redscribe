"""
YouTube tab UI component - Self-contained transcription workflow.

Complete flow from URL to transcription without leaving the tab:
- Paste YouTube URL (video, playlist, channel)
- Fetch and preview videos
- Configure options (format, language, output)
- Start transcription with progress dialog
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import time
from typing import Optional, List
from pathlib import Path

from config import (
    SUPPORTED_LANGUAGES,
    OUTPUT_FORMATS,
    YOUTUBE_TEMP_DIR,
)
from src.gui.styles import FONTS, PADDING, COLORS, SPACING, DIMENSIONS
from src.core.youtube_downloader import (
    YouTubeDownloader,
    YtDlpNotFoundError,
    VideoInfo,
    DownloadResult,
    FetchResult,
    ChannelContent,
    ChannelPlaylistInfo,
)
from src.gui.youtube_video_dialog import YouTubeVideoDialog
from src.gui.youtube_channel_dialog import YouTubeChannelDialog
from src.models.media_file import MediaFile, TranscriptionStatus, ErrorCategory
from src.core.transcription import TranscriptionService
from src.core.output_writer import OutputWriter
from src.core.error_classifier import ErrorClassifier


class YouTubeTab(ctk.CTkFrame):
    """YouTube tab with complete transcription workflow."""

    def __init__(
        self,
        parent,
        api_manager,
        session_logger,
        open_settings_callback=None,
    ):
        """
        Initialize YouTube tab.

        Args:
            parent: Parent widget
            api_manager: API manager for Deepgram
            session_logger: Session logger for statistics
            open_settings_callback: Callback to open settings dialog
        """
        super().__init__(parent, fg_color="transparent")

        self.api_manager = api_manager
        self.session_logger = session_logger
        self.open_settings_callback = open_settings_callback
        self.output_writer = OutputWriter()

        self.downloader: Optional[YouTubeDownloader] = None
        self.video_list: List[VideoInfo] = []  # All fetched videos
        self.selected_videos: List[VideoInfo] = []  # User-selected videos
        self.downloaded_files: List[Path] = []
        self.is_processing = False
        self.cancel_requested = False
        self.progress_dialog = None
        self.current_channel_name: str = ""  # For folder organization
        self.current_playlist_name: str = ""  # Playlist name (if playlist)
        self.current_url_type: str = "video"  # video, playlist, channel

        # Try to initialize downloader
        try:
            self.downloader = YouTubeDownloader()
            self.ytdlp_available = True
        except YtDlpNotFoundError:
            self.ytdlp_available = False

        self._create_widgets()

    def _create_widgets(self):
        """Create the YouTube tab UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # Video list expands

        # URL Input Section
        self._create_url_section()

        # Video List Section
        self._create_video_list_section()

        # Options Section
        self._create_options_section()

        # Output Location Section
        self._create_output_section()

        # Action Buttons
        self._create_action_section()

        # Show warning if yt-dlp not available
        if not self.ytdlp_available:
            self._show_ytdlp_warning()

    def _create_url_section(self):
        """Create URL input section."""
        url_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=DIMENSIONS["corner_radius_lg"],
            border_width=1,
            border_color=COLORS["border"]
        )
        url_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["base"]))
        url_frame.grid_columnconfigure(1, weight=1)

        # Title
        title_label = ctk.CTkLabel(
            url_frame,
            text="YouTube URL",
            font=FONTS["heading"],
        )
        title_label.grid(row=0, column=0, columnspan=3, sticky="w",
                        padx=PADDING["medium"], pady=(PADDING["medium"], PADDING["small"]))

        # URL Entry
        self.url_entry = ctk.CTkEntry(
            url_frame,
            font=FONTS["body"],
            placeholder_text="Paste YouTube video, playlist, or channel URL...",
        )
        self.url_entry.grid(row=1, column=0, columnspan=2, sticky="ew",
                           padx=(PADDING["medium"], PADDING["small"]),
                           pady=(0, PADDING["medium"]))

        # Fetch button
        self.fetch_btn = ctk.CTkButton(
            url_frame,
            text="Fetch",
            width=100,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._on_fetch_click,
            state="normal" if self.ytdlp_available else "disabled",
        )
        self.fetch_btn.grid(row=1, column=2, padx=(0, PADDING["medium"]),
                           pady=(0, PADDING["medium"]))

        # Status label
        self.status_label = ctk.CTkLabel(
            url_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.status_label.grid(row=2, column=0, columnspan=3, sticky="w",
                              padx=PADDING["medium"], pady=(0, PADDING["small"]))

    def _create_video_list_section(self):
        """Create video selection section."""
        list_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=DIMENSIONS["corner_radius_lg"],
            border_width=1,
            border_color=COLORS["border"]
        )
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, SPACING["base"]))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(1, weight=1)

        # Header
        header_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew",
                         padx=PADDING["medium"], pady=PADDING["small"])
        header_frame.grid_columnconfigure(0, weight=1)

        self.videos_label = ctk.CTkLabel(
            header_frame,
            text="Videos",
            font=FONTS["body_medium"],
        )
        self.videos_label.grid(row=0, column=0, sticky="w")

        # Select videos button
        self.select_videos_btn = ctk.CTkButton(
            header_frame,
            text="Select Videos...",
            width=130,
            height=DIMENSIONS["button_height_sm"],
            font=FONTS["body"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._open_video_selection_dialog,
            state="disabled",
        )
        self.select_videos_btn.grid(row=0, column=1, sticky="e")

        # Selection summary area
        self.selection_frame = ctk.CTkFrame(
            list_frame,
            fg_color=COLORS["background"],
            corner_radius=8,
        )
        self.selection_frame.grid(row=1, column=0, sticky="nsew",
                                 padx=PADDING["small"], pady=(0, PADDING["small"]))
        self.selection_frame.grid_columnconfigure(0, weight=1)
        self.selection_frame.grid_rowconfigure(0, weight=1)

        # Empty state / selection summary
        self.selection_label = ctk.CTkLabel(
            self.selection_frame,
            text="Paste a YouTube URL above and click Fetch\nto see available videos.",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
            justify="center",
        )
        self.selection_label.grid(row=0, column=0, pady=PADDING["large"])

    def _create_options_section(self):
        """Create options section (format, language, diarization)."""
        options_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=DIMENSIONS["corner_radius_lg"],
            border_width=1,
            border_color=COLORS["border"]
        )
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

    def _get_default_output_dir(self) -> Path:
        """Get default output directory: Documents/Redscribe/YouTube"""
        documents = Path.home() / "Documents"
        return documents / "Redscribe" / "YouTube"

    def _create_output_section(self):
        """Create output location section."""
        output_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=DIMENSIONS["corner_radius_lg"],
            border_width=1,
            border_color=COLORS["border"]
        )
        output_frame.grid(row=3, column=0, sticky="ew", pady=(0, SPACING["base"]))
        output_frame.grid_columnconfigure(2, weight=1)

        output_label = ctk.CTkLabel(output_frame, text="Output location:", font=FONTS["body"])
        output_label.grid(row=0, column=0, columnspan=4, padx=PADDING["medium"],
                         pady=(PADDING["medium"], PADDING["small"]), sticky="w")

        # Radio buttons - default to Documents/Redscribe/YouTube
        self.output_location_var = ctk.StringVar(value="default")

        default_radio = ctk.CTkRadioButton(
            output_frame,
            text="Documents/Redscribe/YouTube/",
            variable=self.output_location_var,
            value="default",
            command=self._on_output_location_change,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        )
        default_radio.grid(row=1, column=0, columnspan=4, padx=PADDING["medium"],
                          pady=(0, PADDING["small"]), sticky="w")

        custom_radio = ctk.CTkRadioButton(
            output_frame,
            text="Custom:",
            variable=self.output_location_var,
            value="custom",
            command=self._on_output_location_change,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        )
        custom_radio.grid(row=2, column=0, padx=PADDING["medium"],
                         pady=(0, PADDING["medium"]), sticky="w")

        # Default to Documents/Redscribe/YouTube
        default_path = self._get_default_output_dir()
        self.output_dir_entry = ctk.CTkEntry(
            output_frame,
            font=FONTS["body"],
            state="disabled",
        )
        self.output_dir_entry.insert(0, str(default_path))
        self.output_dir_entry.grid(row=2, column=1, columnspan=2, padx=PADDING["small"],
                                  pady=(0, PADDING["medium"]), sticky="ew")

        self.output_browse_btn = ctk.CTkButton(
            output_frame,
            text="Browse",
            width=100,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._browse_output_directory,
            state="disabled",
        )
        self.output_browse_btn.grid(row=2, column=3, padx=(0, PADDING["medium"]),
                                   pady=(0, PADDING["medium"]))

    def _create_action_section(self):
        """Create action buttons section."""
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=4, column=0, sticky="ew")
        action_frame.grid_columnconfigure(1, weight=1)

        self.clear_btn = ctk.CTkButton(
            action_frame,
            text="Clear",
            width=100,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._on_clear,
            state="disabled",
        )
        self.clear_btn.grid(row=0, column=0, sticky="w")

        self.start_btn = ctk.CTkButton(
            action_frame,
            text="\u25B6 Start Transcription",
            width=180,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._start_transcription,
            state="disabled",
        )
        self.start_btn.grid(row=0, column=2, sticky="e")

    def _show_ytdlp_warning(self):
        """Show warning when yt-dlp is not available."""
        self.status_label.configure(
            text="yt-dlp not installed. Run: pip install yt-dlp",
            text_color=COLORS["error"]
        )

    def _on_output_location_change(self):
        """Handle output location radio button change."""
        if self.output_location_var.get() == "default":
            default_path = self._get_default_output_dir()
            self.output_dir_entry.configure(state="normal")
            self.output_dir_entry.delete(0, "end")
            self.output_dir_entry.insert(0, str(default_path))
            self.output_dir_entry.configure(state="disabled")
            self.output_browse_btn.configure(state="disabled")
        else:
            self.output_dir_entry.configure(state="normal")
            self.output_browse_btn.configure(state="normal")

    def _browse_output_directory(self):
        """Open output directory browser dialog."""
        directory = filedialog.askdirectory(title="Select output directory")
        if directory:
            self.output_dir_entry.delete(0, "end")
            self.output_dir_entry.insert(0, directory)

    def _get_output_dir(self) -> Path:
        """Get the output directory with channel and playlist subfolders.

        Structure:
        - Single video: Documents/Redscribe/YouTube/[Channel]/
        - Playlist: Documents/Redscribe/YouTube/[Channel]/[Playlist]/
        """
        if self.output_location_var.get() == "default":
            base_path = self._get_default_output_dir()

            if self.current_channel_name:
                # Add channel subfolder
                safe_channel = self._sanitize_filename(self.current_channel_name)
                channel_path = base_path / safe_channel

                # For playlist - add playlist subfolder
                if self.current_url_type == 'playlist' and self.current_playlist_name:
                    safe_playlist = self._sanitize_filename(self.current_playlist_name)
                    return channel_path / safe_playlist

                # For single video or channel - just channel folder
                return channel_path

            return base_path

        path = self.output_dir_entry.get().strip()
        if path:
            return Path(path)
        return self._get_default_output_dir()

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize string for use as filename/folder name."""
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '')
        # Limit length and strip whitespace
        return name.strip()[:100]

    def _get_language_code(self) -> str:
        """Extract language code from dropdown selection."""
        selection = self.lang_var.get()
        code = selection.split("(")[-1].rstrip(")")
        return code

    # ==================== Fetch Logic ====================

    def _on_fetch_click(self):
        """Handle Fetch button click."""
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.configure(
                text="Please enter a YouTube URL",
                text_color=COLORS["warning"]
            )
            return

        # Disable UI during fetch
        self.fetch_btn.configure(state="disabled", text="Fetching...")
        self.status_label.configure(text="Fetching video information...",
                                   text_color=COLORS["text_secondary"])
        self.update()

        # Fetch in background thread
        def fetch_thread():
            try:
                url_type = self.downloader.detect_url_type(url)

                if url_type == 'unknown':
                    self.after(0, lambda: self._on_fetch_error("Invalid YouTube URL"))
                    return

                # Handle channels differently - show playlists and loose videos
                if url_type == 'channel':
                    channel_content = self.downloader.extract_channel_content(
                        url,
                        on_progress=lambda msg: self.after(0, lambda m=msg:
                            self.status_label.configure(text=m))
                    )
                    self.after(0, lambda: self._on_channel_fetch_complete(channel_content))
                    return

                # For video/playlist - use existing logic
                fetch_result = self.downloader.extract_info(
                    url,
                    on_progress=lambda msg: self.after(0, lambda m=msg:
                        self.status_label.configure(text=m))
                )

                self.after(0, lambda: self._on_fetch_complete(fetch_result))

            except ValueError as e:
                self.after(0, lambda: self._on_fetch_error(str(e)))
            except Exception as e:
                self.after(0, lambda: self._on_fetch_error(f"Error: {str(e)[:50]}"))

        thread = threading.Thread(target=fetch_thread, daemon=True)
        thread.start()

    def _on_fetch_complete(self, fetch_result: FetchResult):
        """Handle successful fetch."""
        self.fetch_btn.configure(state="normal", text="Fetch")

        if not fetch_result.videos:
            self.status_label.configure(text="No videos found", text_color=COLORS["warning"])
            return

        self.video_list = fetch_result.videos
        self.current_url_type = fetch_result.url_type
        self.current_channel_name = fetch_result.channel_name
        self.current_playlist_name = fetch_result.playlist_title

        # Update status
        videos = fetch_result.videos
        total_duration = sum(v.duration_seconds for v in videos)
        duration_str = YouTubeDownloader.format_duration(total_duration)
        type_str = {"video": "video", "playlist": "playlist", "channel": "channel"}.get(self.current_url_type, "")

        status_text = f"Found {len(videos)} video(s) from {type_str} (total: {duration_str})"
        if self.current_channel_name:
            status_text += f" - {self.current_channel_name}"
        if self.current_playlist_name and self.current_url_type == 'playlist':
            status_text += f" [{self.current_playlist_name}]"

        self.status_label.configure(text=status_text, text_color=COLORS["success"])

        # Enable controls
        self.select_videos_btn.configure(state="normal")
        self.clear_btn.configure(state="normal")

        # Open selection dialog automatically
        self._open_video_selection_dialog()

    def _on_fetch_error(self, error: str):
        """Handle fetch error."""
        self.fetch_btn.configure(state="normal", text="Fetch")
        self.status_label.configure(text=error, text_color=COLORS["error"])

    def _open_video_selection_dialog(self):
        """Open the video selection dialog."""
        if not self.video_list:
            return

        dialog = YouTubeVideoDialog(
            self.winfo_toplevel(),
            videos=self.video_list,
            on_confirm=self._on_video_selection_confirmed,
        )

    # ==================== Channel Handling ====================

    def _on_channel_fetch_complete(self, channel_content: ChannelContent):
        """Handle successful channel content fetch."""
        self.fetch_btn.configure(state="normal", text="Fetch")

        if not channel_content.playlists and not channel_content.loose_videos:
            self.status_label.configure(
                text="No content found in channel",
                text_color=COLORS["warning"]
            )
            return

        # Store channel info
        self.current_channel_name = channel_content.channel_name
        self.current_url_type = "channel"
        self.current_playlist_name = ""
        self._channel_content = channel_content

        # Update status
        status_parts = []
        if channel_content.playlists:
            status_parts.append(f"{len(channel_content.playlists)} playlists")
        if channel_content.loose_videos:
            status_parts.append(f"{len(channel_content.loose_videos)} videos")

        status_text = f"Found {', '.join(status_parts)} in channel: {channel_content.channel_name}"
        self.status_label.configure(text=status_text, text_color=COLORS["success"])

        # Enable controls
        self.select_videos_btn.configure(state="normal")
        self.clear_btn.configure(state="normal")

        # Open channel selection dialog
        self._open_channel_selection_dialog()

    def _open_channel_selection_dialog(self):
        """Open the channel content selection dialog."""
        if not hasattr(self, '_channel_content') or not self._channel_content:
            return

        dialog = YouTubeChannelDialog(
            self.winfo_toplevel(),
            channel_content=self._channel_content,
            downloader=self.downloader,
            on_confirm=self._on_channel_selection_confirmed,
        )

    def _on_channel_selection_confirmed(
        self,
        selected_playlists: List[ChannelPlaylistInfo],
        selected_videos: List[VideoInfo]
    ):
        """Handle confirmed channel content selection."""
        if not selected_playlists and not selected_videos:
            self.selected_videos = []
            self._update_selection_display()
            return

        # Store selections for processing
        self._selected_playlists = selected_playlists
        self._selected_loose_videos = selected_videos

        # Build summary
        summary_parts = []
        if selected_playlists:
            summary_parts.append(f"{len(selected_playlists)} playlist(s)")
        if selected_videos:
            summary_parts.append(f"{len(selected_videos)} video(s)")

        # Update video list with just loose videos for now
        # Playlists will be expanded during transcription
        self.video_list = selected_videos.copy()
        self.selected_videos = selected_videos.copy()

        # Show summary in selection display
        self._update_channel_selection_display(selected_playlists, selected_videos)

    def _update_channel_selection_display(
        self,
        playlists: List[ChannelPlaylistInfo],
        videos: List[VideoInfo]
    ):
        """Update the selection summary for channel content."""
        summary_lines = []

        if playlists:
            summary_lines.append(f"Playlists ({len(playlists)}):")
            for p in playlists[:3]:
                title = p.title[:40] + ("..." if len(p.title) > 40 else "")
                summary_lines.append(f"  📁 {title}")
            if len(playlists) > 3:
                summary_lines.append(f"  ... and {len(playlists) - 3} more")

        if videos:
            summary_lines.append(f"Videos ({len(videos)}):")
            for v in videos[:3]:
                title = v.title[:40] + ("..." if len(v.title) > 40 else "")
                summary_lines.append(f"  📄 {title}")
            if len(videos) > 3:
                summary_lines.append(f"  ... and {len(videos) - 3} more")

        summary_text = "\n".join(summary_lines)

        self.selection_label.configure(
            text=summary_text,
            text_color=COLORS["text"],
            justify="left",
        )

        total_items = len(playlists) + len(videos)
        self.videos_label.configure(text=f"Content ({total_items} items selected)")
        self.start_btn.configure(state="normal" if total_items > 0 else "disabled")

    def _on_video_selection_confirmed(self, selected: List[VideoInfo]):
        """Handle confirmed video selection from dialog."""
        self.selected_videos = selected
        self._update_selection_display()

    def _update_selection_display(self):
        """Update the selection summary display."""
        if not self.selected_videos:
            self.selection_label.configure(
                text="No videos selected.\nClick 'Select Videos...' to choose videos.",
                text_color=COLORS["text_secondary"],
            )
            self.videos_label.configure(text="Videos (0 selected)")
            self.start_btn.configure(state="disabled")
            return

        total = len(self.video_list)
        selected = len(self.selected_videos)
        selected_duration = sum(v.duration_seconds for v in self.selected_videos)
        duration_str = YouTubeDownloader.format_duration(selected_duration)

        # Build selection summary
        summary_lines = []
        for i, video in enumerate(self.selected_videos[:5]):  # Show first 5
            title = video.title[:50] + ("..." if len(video.title) > 50 else "")
            summary_lines.append(f"• {title}")

        if len(self.selected_videos) > 5:
            summary_lines.append(f"  ... and {len(self.selected_videos) - 5} more")

        summary_text = "\n".join(summary_lines)

        self.selection_label.configure(
            text=summary_text,
            text_color=COLORS["text"],
            justify="left",
        )
        self.videos_label.configure(text=f"Videos ({selected}/{total} selected, {duration_str})")
        self.start_btn.configure(state="normal")

    def _on_clear(self):
        """Clear video list."""
        self.video_list.clear()
        self.selected_videos.clear()
        self.url_entry.delete(0, "end")
        self.current_channel_name = ""
        self.current_playlist_name = ""
        self.current_url_type = "video"

        # Clear channel-specific state
        if hasattr(self, '_channel_content'):
            self._channel_content = None
        if hasattr(self, '_selected_playlists'):
            self._selected_playlists = []
        if hasattr(self, '_selected_loose_videos'):
            self._selected_loose_videos = []

        # Reset selection display
        self.selection_label.configure(
            text="Paste a YouTube URL above and click Fetch\nto see available videos.",
            text_color=COLORS["text_secondary"],
            justify="center",
        )

        self.videos_label.configure(text="Videos")
        self.status_label.configure(text="", text_color=COLORS["text_secondary"])
        self.select_videos_btn.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        self.start_btn.configure(state="disabled")

    # ==================== Transcription Logic ====================

    def _start_transcription(self):
        """Start the transcription process."""
        # Check for channel content with playlists
        has_playlists = (
            hasattr(self, '_selected_playlists') and
            self._selected_playlists and
            len(self._selected_playlists) > 0
        )
        has_loose_videos = (
            hasattr(self, '_selected_loose_videos') and
            self._selected_loose_videos and
            len(self._selected_loose_videos) > 0
        )

        # For channels with playlists, use special processing
        if has_playlists:
            self._start_channel_transcription()
            return

        if not self.selected_videos:
            messagebox.showwarning("No Selection", "Please select at least one video.")
            return

        # Check API key
        api_key = self.api_manager.load_api_key()
        if not api_key:
            messagebox.showinfo(
                "API Key Required",
                "Please configure your Deepgram API key in Settings."
            )
            if self.open_settings_callback:
                self.open_settings_callback()
            return

        # Validate output directory
        output_dir = self._get_output_dir()
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Error", f"Cannot create output directory:\n{e}")
                return

        # Confirm if many videos
        if len(self.selected_videos) > 10:
            if not messagebox.askyesno(
                "Confirm",
                f"You're about to process {len(self.selected_videos)} videos.\nContinue?"
            ):
                return

        # Reset state
        self.cancel_requested = False
        self.is_processing = True
        self.downloaded_files.clear()

        # Create MediaFile placeholders for progress dialog
        media_files = []
        for video in self.selected_videos:
            # Create a placeholder MediaFile for progress tracking
            # We'll use a temp path that will be replaced during download
            temp_path = YOUTUBE_TEMP_DIR / f"{video.title[:50]}.mp3"
            media_file = MediaFile(path=temp_path, selected=True)
            media_files.append(media_file)

        # Start logging session
        language = self._get_language_code()
        model = self.api_manager.get_model_string(language)
        self.session_logger.set_model(model.split(":")[0] if ":" in model else model)
        self.session_logger.start_session()

        # Create progress dialog
        from src.gui.progress_dialog import ProgressDialog
        self.progress_dialog = ProgressDialog(
            self.winfo_toplevel(),
            media_files,
            output_dir=output_dir,
            on_cancel=self._cancel_transcription,
            on_close=self._on_progress_close,
        )

        # Start processing thread
        thread = threading.Thread(
            target=self._process_videos,
            args=(api_key, self.selected_videos, media_files, output_dir),
            daemon=True,
        )
        thread.start()

    def _cancel_transcription(self):
        """Cancel the transcription process."""
        self.cancel_requested = True

    def _on_progress_close(self):
        """Handle progress dialog close."""
        self.is_processing = False
        # Cleanup any remaining temp files
        self._cleanup_temp_files()

    def _process_videos(
        self,
        api_key: str,
        videos: List[VideoInfo],
        media_files: List[MediaFile],
        output_dir: Path,
    ):
        """Process videos: download and transcribe."""
        output_format = self.format_var.get()
        language = self._get_language_code()
        diarize = self.diarize_var.get()
        model = self.api_manager.get_model_string(language)
        transcription_service = TranscriptionService(api_key, model=model)

        total = len(videos)
        success_count = 0

        for i, (video, media_file) in enumerate(zip(videos, media_files)):
            if self.cancel_requested:
                for remaining in media_files[i:]:
                    remaining.status = TranscriptionStatus.SKIPPED
                    self.after(0, lambda idx=media_files.index(remaining):
                        self.progress_dialog.update_file_status(idx, TranscriptionStatus.SKIPPED))
                break

            # Update progress
            self.after(0, lambda idx=i, v=video: self.progress_dialog.update_progress(
                idx, total, f"Downloading: {v.title[:40]}...", ""
            ))

            # Step 1: Download audio
            media_file.status = TranscriptionStatus.CONVERTING
            self.after(0, lambda idx=i: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.CONVERTING, "Downloading from YouTube..."
            ))

            result = self.downloader.download_audio(
                video.url,
                on_progress=lambda pct, status, idx=i:
                    self.after(0, lambda p=pct, s=status, i=idx:
                        self.progress_dialog.update_file_status(
                            i, TranscriptionStatus.CONVERTING, f"Downloading... {p:.0f}%"
                        ))
            )

            if not result.success or not result.path:
                media_file.status = TranscriptionStatus.FAILED
                media_file.error_message = result.error or "Download failed"
                self.session_logger.log_file_failed(video.title, media_file.error_message)
                self.after(0, lambda idx=i, msg=media_file.error_message:
                    self.progress_dialog.update_file_status(idx, TranscriptionStatus.FAILED, msg[:50]))
                continue

            # Update media file with actual path
            media_file.path = result.path
            self.downloaded_files.append(result.path)

            # Step 2: Transcribe
            media_file.status = TranscriptionStatus.TRANSCRIBING
            self.session_logger.log_transcribing(video.title)
            self.after(0, lambda idx=i: self.progress_dialog.update_file_status(
                idx, TranscriptionStatus.TRANSCRIBING, "Transcribing..."
            ))

            try:
                transcription_result = transcription_service.transcribe(
                    file_path=result.path,
                    language=language,
                    diarize=diarize,
                )

                if not transcription_result.success:
                    raise Exception(transcription_result.error_message or "Transcription failed")

                # Step 3: Save output
                self.after(0, lambda idx=i: self.progress_dialog.update_file_status(
                    idx, TranscriptionStatus.TRANSCRIBING, "Saving..."
                ))

                # Use video title as output filename
                output_path = self.output_writer.save(
                    result=transcription_result,
                    source_path=result.path,
                    output_format=output_format,
                    output_dir=output_dir,
                )

                media_file.status = TranscriptionStatus.COMPLETED
                media_file.output_path = output_path

                # Log success
                duration = transcription_result.duration_seconds or result.duration_seconds or 0
                self.session_logger.log_file_completed(video.title, duration)

                self.after(0, lambda idx=i: self.progress_dialog.update_file_status(
                    idx, TranscriptionStatus.COMPLETED, "Done"
                ))

                success_count += 1

            except Exception as e:
                media_file.status = TranscriptionStatus.FAILED
                media_file.error_message = str(e)
                self.session_logger.log_file_failed(video.title, str(e))
                self.after(0, lambda idx=i, msg=str(e):
                    self.progress_dialog.update_file_status(idx, TranscriptionStatus.FAILED, msg[:50]))

            # Cleanup downloaded file immediately after processing
            if result.path and result.path.exists():
                try:
                    result.path.unlink()
                    if result.path in self.downloaded_files:
                        self.downloaded_files.remove(result.path)
                except OSError:
                    pass

        # End logging session
        self.session_logger.end_session()

        # Count failures
        fail_count = sum(1 for f in media_files if f.status == TranscriptionStatus.FAILED)
        failed_files = [f for f in media_files if f.status == TranscriptionStatus.FAILED]

        # Finalize
        if self.cancel_requested:
            self.after(0, self.progress_dialog.set_cancelled)
        else:
            self.after(0, lambda: self.progress_dialog.set_completed_with_retry(
                success_count, fail_count, failed_files, None  # No retry for YouTube
            ))

    def _start_channel_transcription(self):
        """Start transcription for channel content (playlists + loose videos)."""
        # Check API key
        api_key = self.api_manager.load_api_key()
        if not api_key:
            messagebox.showinfo(
                "API Key Required",
                "Please configure your Deepgram API key in Settings."
            )
            if self.open_settings_callback:
                self.open_settings_callback()
            return

        # Get base output directory
        base_output_dir = self._get_default_output_dir()
        if self.output_location_var.get() != "default":
            path = self.output_dir_entry.get().strip()
            if path:
                base_output_dir = Path(path)

        # Add channel subfolder
        if self.current_channel_name:
            safe_channel = self._sanitize_filename(self.current_channel_name)
            base_output_dir = base_output_dir / safe_channel

        # Create output directory
        try:
            base_output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Error", f"Cannot create output directory:\n{e}")
            return

        # Build processing list: (video, playlist_name or None)
        processing_list = []

        # Add videos from playlists
        selected_playlists = getattr(self, '_selected_playlists', [])
        for playlist in selected_playlists:
            processing_list.append(('playlist', playlist))

        # Add loose videos
        selected_loose = getattr(self, '_selected_loose_videos', [])
        for video in selected_loose:
            processing_list.append(('video', video))

        if not processing_list:
            messagebox.showwarning("No Selection", "Please select content to transcribe.")
            return

        # Count total expected videos (estimated)
        total_estimated = len(selected_loose)
        for p in selected_playlists:
            total_estimated += p.video_count if p.video_count else 10  # Estimate 10 if unknown

        # Confirm if many items
        if total_estimated > 10:
            if not messagebox.askyesno(
                "Confirm",
                f"You're about to process approximately {total_estimated} videos.\nContinue?"
            ):
                return

        # Reset state
        self.cancel_requested = False
        self.is_processing = True
        self.downloaded_files.clear()

        # Start logging session
        language = self._get_language_code()
        model = self.api_manager.get_model_string(language)
        self.session_logger.set_model(model.split(":")[0] if ":" in model else model)
        self.session_logger.start_session()

        # Create simple progress dialog placeholder
        from src.gui.progress_dialog import ProgressDialog
        placeholder_files = [MediaFile(path=Path("placeholder.mp3"), selected=True)]
        self.progress_dialog = ProgressDialog(
            self.winfo_toplevel(),
            placeholder_files,
            output_dir=base_output_dir,
            on_cancel=self._cancel_transcription,
            on_close=self._on_progress_close,
        )

        # Start processing thread
        thread = threading.Thread(
            target=self._process_channel_content,
            args=(api_key, processing_list, base_output_dir),
            daemon=True,
        )
        thread.start()

    def _process_channel_content(
        self,
        api_key: str,
        processing_list: list,
        base_output_dir: Path,
    ):
        """Process channel content: expand playlists and transcribe all videos."""
        output_format = self.format_var.get()
        language = self._get_language_code()
        diarize = self.diarize_var.get()
        model = self.api_manager.get_model_string(language)
        transcription_service = TranscriptionService(api_key, model=model)

        success_count = 0
        fail_count = 0
        video_index = 0

        for item_type, item in processing_list:
            if self.cancel_requested:
                break

            if item_type == 'playlist':
                playlist = item
                # Expand playlist to get videos
                self.after(0, lambda p=playlist: self.progress_dialog.update_progress(
                    0, 1, f"Fetching playlist: {p.title[:30]}...", ""
                ))

                try:
                    fetch_result = self.downloader.extract_info(playlist.url)
                    videos = fetch_result.videos

                    # Create output dir for this playlist
                    safe_playlist = self._sanitize_filename(playlist.title)
                    playlist_output_dir = base_output_dir / safe_playlist
                    playlist_output_dir.mkdir(parents=True, exist_ok=True)

                    # Process each video in playlist
                    for video in videos:
                        if self.cancel_requested:
                            break

                        result = self._transcribe_single_video(
                            video=video,
                            video_index=video_index,
                            output_dir=playlist_output_dir,
                            output_format=output_format,
                            language=language,
                            diarize=diarize,
                            transcription_service=transcription_service,
                        )

                        if result:
                            success_count += 1
                        else:
                            fail_count += 1

                        video_index += 1

                except Exception as e:
                    self.session_logger.log_error(f"Failed to expand playlist: {playlist.title}", details=str(e))
                    fail_count += 1

            else:
                # Process loose video
                video = item

                result = self._transcribe_single_video(
                    video=video,
                    video_index=video_index,
                    output_dir=base_output_dir,
                    output_format=output_format,
                    language=language,
                    diarize=diarize,
                    transcription_service=transcription_service,
                )

                if result:
                    success_count += 1
                else:
                    fail_count += 1

                video_index += 1

        # End logging session
        self.session_logger.end_session()

        # Finalize
        if self.cancel_requested:
            self.after(0, self.progress_dialog.set_cancelled)
        else:
            self.after(0, lambda: self.progress_dialog.set_completed_with_retry(
                success_count, fail_count, [], None
            ))

    def _transcribe_single_video(
        self,
        video: VideoInfo,
        video_index: int,
        output_dir: Path,
        output_format: str,
        language: str,
        diarize: bool,
        transcription_service,
    ) -> bool:
        """Transcribe a single video. Returns True on success."""
        # Update progress
        self.after(0, lambda v=video: self.progress_dialog.update_progress(
            0, 1, f"Downloading: {v.title[:40]}...", ""
        ))

        # Download
        self.session_logger.log_converting(video.title)
        result = self.downloader.download_audio(video.url)

        if not result.success or not result.path:
            self.session_logger.log_file_failed(video.title, result.error or "Download failed")
            return False

        self.downloaded_files.append(result.path)

        # Transcribe
        self.after(0, lambda v=video: self.progress_dialog.update_progress(
            0, 1, f"Transcribing: {v.title[:40]}...", ""
        ))

        self.session_logger.log_transcribing(video.title)

        try:
            transcription_result = transcription_service.transcribe(
                file_path=result.path,
                language=language,
                diarize=diarize,
            )

            if not transcription_result.success:
                raise Exception(transcription_result.error_message or "Transcription failed")

            # Save output
            output_path = self.output_writer.save(
                result=transcription_result,
                source_path=result.path,
                output_format=output_format,
                output_dir=output_dir,
            )

            # Log success
            duration = transcription_result.duration_seconds or result.duration_seconds or 0
            self.session_logger.log_file_completed(video.title, duration)

            success = True

        except Exception as e:
            self.session_logger.log_file_failed(video.title, str(e))
            success = False

        # Cleanup downloaded file
        if result.path and result.path.exists():
            try:
                result.path.unlink()
                if result.path in self.downloaded_files:
                    self.downloaded_files.remove(result.path)
            except OSError:
                pass

        return success

    def _cleanup_temp_files(self):
        """Clean up downloaded temporary files."""
        for path in self.downloaded_files:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        self.downloaded_files.clear()

        if self.downloader:
            self.downloader.cleanup_all()
