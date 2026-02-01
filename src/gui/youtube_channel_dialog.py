"""
YouTube channel selection dialog.

Allows users to select playlists and/or individual videos from a channel.
"""
import customtkinter as ctk
from typing import Optional, Callable, List
from pathlib import Path

from src.gui.styles import FONTS, PADDING, COLORS, SPACING, DIMENSIONS
from src.core.youtube_downloader import (
    ChannelContent,
    ChannelPlaylistInfo,
    VideoInfo,
    YouTubeDownloader,
)


def _set_dialog_icon(dialog):
    """Set the dialog window icon."""
    icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.ico"
    if icon_path.exists():
        try:
            dialog.after(200, lambda: dialog.iconbitmap(str(icon_path)))
        except Exception:
            pass


class PlaylistItem(ctk.CTkFrame):
    """Single playlist item with checkbox and expandable video list."""

    def __init__(
        self,
        parent,
        playlist: ChannelPlaylistInfo,
        row_index: int = 0,
        on_select_change: Optional[Callable] = None,
        on_load_videos: Optional[Callable] = None,
    ):
        bg_color = COLORS["surface"] if row_index % 2 == 0 else COLORS["background"]
        super().__init__(parent, fg_color=bg_color, corner_radius=0)

        self.playlist = playlist
        self.on_select_change = on_select_change
        self.on_load_videos = on_load_videos  # Callback to load videos from playlist
        self.selected = True  # Default to selected
        self.expanded = False
        self.videos_loaded = False
        self.video_items: List[VideoItem] = []
        self.videos_container = None

        self._create_widgets()

    def _create_widgets(self):
        """Create item widgets."""
        self.grid_columnconfigure(2, weight=1)

        # Expand button
        self.expand_btn = ctk.CTkLabel(
            self,
            text="▶",
            font=FONTS["body"],
            width=20,
            cursor="hand2",
        )
        self.expand_btn.grid(row=0, column=0, padx=(PADDING["small"], 0), pady=4)
        self.expand_btn.bind("<Button-1>", self._toggle_expand)

        # Checkbox
        self.checkbox_var = ctk.BooleanVar(value=self.selected)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self.checkbox_var,
            width=24,
            command=self._on_checkbox_change,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        )
        self.checkbox.grid(row=0, column=1, padx=(4, 4), pady=4)

        # Folder icon
        icon_label = ctk.CTkLabel(
            self,
            text="📁",
            font=FONTS["body"],
            width=20,
        )
        icon_label.grid(row=0, column=2, sticky="w", padx=(0, 4), pady=4)

        # Playlist title
        title = self.playlist.title
        if len(title) > 40:
            title = title[:37] + "..."

        title_label = ctk.CTkLabel(
            self,
            text=title,
            font=FONTS["body_medium"],
            anchor="w",
        )
        title_label.grid(row=0, column=3, sticky="w", padx=4, pady=4)

        # Video count
        count_text = f"{self.playlist.video_count} videos" if self.playlist.video_count else "? videos"
        self.count_label = ctk.CTkLabel(
            self,
            text=count_text,
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            width=80,
            anchor="e",
        )
        self.count_label.grid(row=0, column=4, padx=PADDING["small"], pady=4)

        # Videos container (hidden by default)
        self.videos_container = ctk.CTkFrame(self, fg_color="transparent")
        self.videos_container.grid(row=1, column=0, columnspan=5, sticky="ew", padx=(30, 0))
        self.videos_container.grid_columnconfigure(0, weight=1)
        self.videos_container.grid_remove()  # Hide initially

    def _on_checkbox_change(self):
        """Handle checkbox state change."""
        self.selected = self.checkbox_var.get()
        # If videos are loaded, update their selection too
        if self.videos_loaded:
            for video_item in self.video_items:
                video_item.update_selection(self.selected)
        if self.on_select_change:
            self.on_select_change()

    def _toggle_expand(self, event=None):
        """Toggle expand/collapse of video list."""
        if not self.videos_loaded:
            # Load videos first
            self._load_videos()
        else:
            # Toggle visibility
            self._set_expanded(not self.expanded)

    def _load_videos(self):
        """Load videos from playlist."""
        if self.on_load_videos:
            # Show loading indicator
            self.expand_btn.configure(text="⏳")
            self.update_idletasks()
            # Call the callback to load videos
            self.on_load_videos(self)

    def set_videos(self, videos: list):
        """Set the loaded videos and display them."""
        self.videos_loaded = True
        self.video_items.clear()

        # Clear container
        for widget in self.videos_container.winfo_children():
            widget.destroy()

        # Create video items
        for i, video in enumerate(videos):
            item = VideoItem(
                self.videos_container,
                video=video,
                row_index=i,
                on_select_change=self.on_select_change,
            )
            item.grid(row=i, column=0, sticky="ew")
            # Set initial selection to match playlist selection
            item.update_selection(self.selected)
            self.video_items.append(item)

        # Update count label with actual count
        self.count_label.configure(text=f"{len(videos)} videos")

        # Expand to show videos
        self._set_expanded(True)

    def _set_expanded(self, expanded: bool):
        """Set expanded state."""
        self.expanded = expanded
        if expanded:
            self.expand_btn.configure(text="▼")
            self.videos_container.grid()
        else:
            self.expand_btn.configure(text="▶")
            self.videos_container.grid_remove()

    def update_selection(self, selected: bool):
        """Update the selection state."""
        self.selected = selected
        self.checkbox_var.set(selected)
        # Update child videos too
        if self.videos_loaded:
            for video_item in self.video_items:
                video_item.update_selection(selected)

    def get_selected_videos(self) -> list:
        """Get list of selected videos from this playlist."""
        if not self.videos_loaded:
            return []  # Return empty - playlist not expanded
        return [item.video for item in self.video_items if item.selected]


class VideoItem(ctk.CTkFrame):
    """Single video item with checkbox."""

    def __init__(
        self,
        parent,
        video: VideoInfo,
        row_index: int = 0,
        on_select_change: Optional[Callable] = None,
    ):
        bg_color = COLORS["surface"] if row_index % 2 == 0 else COLORS["background"]
        super().__init__(parent, fg_color=bg_color, corner_radius=0)

        self.video = video
        self.on_select_change = on_select_change
        self.selected = False  # Default to not selected for loose videos

        self._create_widgets()

    def _create_widgets(self):
        """Create item widgets."""
        self.grid_columnconfigure(1, weight=1)

        # Checkbox
        self.checkbox_var = ctk.BooleanVar(value=self.selected)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self.checkbox_var,
            width=24,
            command=self._on_checkbox_change,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        )
        self.checkbox.grid(row=0, column=0, padx=(PADDING["medium"], 4), pady=3)

        # Video title
        title = self.video.title
        if len(title) > 50:
            title = title[:47] + "..."

        title_label = ctk.CTkLabel(
            self,
            text=title,
            font=FONTS["body"],
            anchor="w",
        )
        title_label.grid(row=0, column=1, sticky="w", padx=4, pady=3)

        # Duration
        duration_str = YouTubeDownloader.format_duration(self.video.duration_seconds)
        duration_label = ctk.CTkLabel(
            self,
            text=duration_str,
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            width=60,
            anchor="e",
        )
        duration_label.grid(row=0, column=2, padx=PADDING["small"], pady=3)

    def _on_checkbox_change(self):
        """Handle checkbox state change."""
        self.selected = self.checkbox_var.get()
        if self.on_select_change:
            self.on_select_change()

    def update_selection(self, selected: bool):
        """Update the selection state."""
        self.selected = selected
        self.checkbox_var.set(selected)


class YouTubeChannelDialog(ctk.CTkToplevel):
    """Dialog for selecting playlists and videos from a YouTube channel."""

    def __init__(
        self,
        parent,
        channel_content: ChannelContent,
        downloader: YouTubeDownloader,
        on_confirm: Optional[Callable[[List[ChannelPlaylistInfo], List[VideoInfo]], None]] = None,
    ):
        super().__init__(parent)

        self.channel_content = channel_content
        self.downloader = downloader
        self.on_confirm = on_confirm
        self.playlist_items: List[PlaylistItem] = []
        self.video_items: List[VideoItem] = []
        self.videos_expanded = False

        # Window configuration
        self.title(f"Select Content from {channel_content.channel_name}")
        self.geometry("700x600")
        self.resizable(True, True)
        self.minsize(550, 400)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 700) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 600) // 2
        self.geometry(f"+{x}+{y}")

        self._create_widgets()
        _set_dialog_icon(self)

        self._populate_content()
        self._update_stats()

    def _create_widgets(self):
        """Create dialog widgets."""
        # Main frame
        main_frame = ctk.CTkFrame(self, fg_color=COLORS["surface"])
        main_frame.pack(fill="both", expand=True)

        # Content with padding
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(1, weight=1)

        # Header
        header_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        header_frame.grid_columnconfigure(0, weight=1)

        header_label = ctk.CTkLabel(
            header_frame,
            text=f"Channel: {self.channel_content.channel_name}",
            font=FONTS["heading"],
        )
        header_label.grid(row=0, column=0, sticky="w")

        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")

        select_all_btn = ctk.CTkButton(
            btn_frame,
            text="Select All",
            width=85,
            height=DIMENSIONS["button_height_sm"],
            font=FONTS["small"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._select_all,
        )
        select_all_btn.pack(side="left", padx=(0, SPACING["xs"]))

        clear_all_btn = ctk.CTkButton(
            btn_frame,
            text="Clear All",
            width=80,
            height=DIMENSIONS["button_height_sm"],
            font=FONTS["small"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._clear_all,
        )
        clear_all_btn.pack(side="left")

        # Scrollable content area
        self.scroll_frame = ctk.CTkScrollableFrame(
            content_frame,
            fg_color=COLORS["background"],
            corner_radius=8,
        )
        self.scroll_frame.grid(row=1, column=0, sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        # Stats label
        self.stats_label = ctk.CTkLabel(
            content_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.stats_label.grid(row=2, column=0, sticky="w", pady=(SPACING["sm"], 0))

        # Buttons frame
        buttons_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        buttons_frame.grid(row=3, column=0, sticky="ew", pady=(SPACING["lg"], 0))

        cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            width=100,
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._on_cancel,
        )
        cancel_btn.pack(side="right")

        confirm_btn = ctk.CTkButton(
            buttons_frame,
            text="Confirm Selection",
            width=140,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_confirm,
        )
        confirm_btn.pack(side="right", padx=(0, SPACING["sm"]))

    def _populate_content(self):
        """Populate the content areas."""
        row = 0

        # === Playlists Section ===
        if self.channel_content.playlists:
            # Section header
            playlists_header = ctk.CTkFrame(self.scroll_frame, fg_color=COLORS["surface_elevated"])
            playlists_header.grid(row=row, column=0, sticky="ew", pady=(0, 2))
            playlists_header.grid_columnconfigure(0, weight=1)
            row += 1

            header_label = ctk.CTkLabel(
                playlists_header,
                text=f"📁 Playlists ({len(self.channel_content.playlists)})",
                font=FONTS["body_medium"],
                anchor="w",
            )
            header_label.grid(row=0, column=0, sticky="w", padx=PADDING["medium"], pady=PADDING["small"])

            # Playlist items
            for i, playlist in enumerate(self.channel_content.playlists):
                item = PlaylistItem(
                    self.scroll_frame,
                    playlist=playlist,
                    row_index=i,
                    on_select_change=self._update_stats,
                    on_load_videos=self._on_load_playlist_videos,
                )
                item.grid(row=row, column=0, sticky="ew")
                self.playlist_items.append(item)
                row += 1

        # === Loose Videos Section ===
        if self.channel_content.loose_videos:
            # Section header with expand/collapse
            videos_header = ctk.CTkFrame(self.scroll_frame, fg_color=COLORS["surface_elevated"])
            videos_header.grid(row=row, column=0, sticky="ew", pady=(SPACING["sm"], 2))
            videos_header.grid_columnconfigure(0, weight=1)
            row += 1

            self.videos_header_label = ctk.CTkLabel(
                videos_header,
                text=f"📄 Individual Videos ({len(self.channel_content.loose_videos)}) ▶",
                font=FONTS["body_medium"],
                anchor="w",
                cursor="hand2",
            )
            self.videos_header_label.grid(row=0, column=0, sticky="w", padx=PADDING["medium"], pady=PADDING["small"])
            self.videos_header_label.bind("<Button-1>", self._toggle_videos)

            # Videos container (initially hidden)
            self.videos_container = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            self.videos_container.grid(row=row, column=0, sticky="ew")
            self.videos_container.grid_columnconfigure(0, weight=1)
            self.videos_row = row
            row += 1

            # Create video items (hidden initially)
            for i, video in enumerate(self.channel_content.loose_videos):
                item = VideoItem(
                    self.videos_container,
                    video=video,
                    row_index=i,
                    on_select_change=self._update_stats,
                )
                item.grid(row=i, column=0, sticky="ew")
                self.video_items.append(item)

            # Hide videos initially
            self.videos_container.grid_remove()

    def _on_load_playlist_videos(self, playlist_item: PlaylistItem):
        """Load videos for a playlist item."""
        import threading

        def load_videos():
            try:
                # Fetch videos from playlist
                result = self.downloader.extract_info(playlist_item.playlist.url)
                videos = result.videos

                # Update UI on main thread
                self.after(0, lambda: playlist_item.set_videos(videos))
                self.after(0, self._update_stats)
            except Exception as e:
                # Show error and reset expand button
                self.after(0, lambda: playlist_item.expand_btn.configure(text="❌"))
                print(f"Error loading playlist: {e}")

        # Run in background thread
        thread = threading.Thread(target=load_videos, daemon=True)
        thread.start()

    def _toggle_videos(self, event=None):
        """Toggle visibility of loose videos."""
        self.videos_expanded = not self.videos_expanded

        if self.videos_expanded:
            self.videos_container.grid()
            self.videos_header_label.configure(
                text=f"📄 Individual Videos ({len(self.channel_content.loose_videos)}) ▼"
            )
        else:
            self.videos_container.grid_remove()
            self.videos_header_label.configure(
                text=f"📄 Individual Videos ({len(self.channel_content.loose_videos)}) ▶"
            )

    def _update_stats(self):
        """Update the stats label."""
        # Count playlists (unexpanded selected + expanded with any selection)
        selected_playlists = sum(
            1 for item in self.playlist_items
            if (item.selected and not item.videos_loaded) or
               (item.videos_loaded and any(v.selected for v in item.video_items))
        )

        # Count videos from expanded playlists
        playlist_videos = sum(
            sum(1 for v in item.video_items if v.selected)
            for item in self.playlist_items if item.videos_loaded
        )

        # Count loose videos
        loose_videos = sum(1 for item in self.video_items if item.selected)

        total_playlists = len(self.playlist_items)
        total_loose_videos = len(self.video_items)

        parts = []
        if total_playlists > 0:
            parts.append(f"{selected_playlists}/{total_playlists} playlists")
        if playlist_videos > 0:
            parts.append(f"{playlist_videos} from playlists")
        if total_loose_videos > 0:
            parts.append(f"{loose_videos}/{total_loose_videos} loose videos")

        self.stats_label.configure(text="Selected: " + ", ".join(parts))

    def _select_all(self):
        """Select all playlists and videos."""
        for item in self.playlist_items:
            item.update_selection(True)
        for item in self.video_items:
            item.update_selection(True)
        self._update_stats()

    def _clear_all(self):
        """Clear all selections."""
        for item in self.playlist_items:
            item.update_selection(False)
        for item in self.video_items:
            item.update_selection(False)
        self._update_stats()

    def _on_confirm(self):
        """Handle confirm button click."""
        # Playlists that are selected but NOT expanded (will be fetched later)
        selected_playlists = [
            item.playlist for item in self.playlist_items
            if item.selected and not item.videos_loaded
        ]

        # Collect all selected videos
        selected_videos = []

        # Videos from expanded playlists (user made specific selections)
        for item in self.playlist_items:
            if item.videos_loaded:
                selected_videos.extend(item.get_selected_videos())

        # Loose videos
        selected_videos.extend([
            item.video for item in self.video_items if item.selected
        ])

        if self.on_confirm:
            self.on_confirm(selected_playlists, selected_videos)
        self.destroy()

    def _on_cancel(self):
        """Handle cancel button click."""
        if self.on_confirm:
            self.on_confirm([], [])
        self.destroy()
