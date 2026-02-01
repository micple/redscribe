"""
YouTube video selection dialog.

Allows users to select which videos to transcribe from a playlist/channel.
"""
import customtkinter as ctk
from typing import Optional, Callable, List
from pathlib import Path

from src.gui.styles import FONTS, PADDING, COLORS, SPACING, DIMENSIONS
from src.core.youtube_downloader import VideoInfo, YouTubeDownloader


def _set_dialog_icon(dialog):
    """Set the dialog window icon."""
    icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.ico"
    if icon_path.exists():
        try:
            dialog.after(200, lambda: dialog.iconbitmap(str(icon_path)))
        except Exception:
            pass


class VideoListItem(ctk.CTkFrame):
    """Single video item in the selection list."""

    def __init__(
        self,
        parent,
        video: VideoInfo,
        row_index: int = 0,
        on_select_change: Optional[Callable] = None,
    ):
        # Alternating background colors
        bg_color = COLORS["surface"] if row_index % 2 == 0 else COLORS["background"]
        super().__init__(parent, fg_color=bg_color, corner_radius=0)

        self.video = video
        self.on_select_change = on_select_change
        self.selected = True  # Default to selected

        self._create_widgets()

    def _create_widgets(self):
        """Create item widgets."""
        self.grid_columnconfigure(1, weight=1)  # Title column expands

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
        self.checkbox.grid(row=0, column=0, padx=(PADDING["small"], 4), pady=4)

        # Video title - truncate if too long
        full_title = self.video.title
        max_title_len = 55
        display_title = full_title
        if len(full_title) > max_title_len:
            display_title = full_title[:max_title_len - 3] + "..."

        title_label = ctk.CTkLabel(
            self,
            text=display_title,
            font=FONTS["body"],
            anchor="w",
        )
        title_label.grid(row=0, column=1, sticky="w", padx=4, pady=4)

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
        duration_label.grid(row=0, column=2, padx=PADDING["small"], pady=4)

    def _on_checkbox_change(self):
        """Handle checkbox state change."""
        self.selected = self.checkbox_var.get()
        if self.on_select_change:
            self.on_select_change()

    def update_selection(self, selected: bool):
        """Update the selection state."""
        self.selected = selected
        self.checkbox_var.set(selected)


class YouTubeVideoDialog(ctk.CTkToplevel):
    """Dialog for selecting YouTube videos to transcribe."""

    def __init__(
        self,
        parent,
        videos: List[VideoInfo],
        on_confirm: Optional[Callable[[List[VideoInfo]], None]] = None,
    ):
        super().__init__(parent)

        self.videos = videos
        self.on_confirm = on_confirm
        self.video_items: List[VideoListItem] = []

        # Window configuration
        self.title("Select Videos to Transcribe")
        self.geometry("650x500")
        self.resizable(True, True)
        self.minsize(500, 350)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 650) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 500) // 2
        self.geometry(f"+{x}+{y}")

        self._create_widgets()
        _set_dialog_icon(self)

        # Populate video list
        self._populate_videos()
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

        # Header with select/deselect buttons
        header_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        header_frame.grid_columnconfigure(0, weight=1)

        # Calculate total duration
        total_duration = sum(v.duration_seconds for v in self.videos)
        duration_str = YouTubeDownloader.format_duration(total_duration)

        header_label = ctk.CTkLabel(
            header_frame,
            text=f"{len(self.videos)} videos (total: {duration_str})",
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

        deselect_all_btn = ctk.CTkButton(
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
            command=self._deselect_all,
        )
        deselect_all_btn.pack(side="left")

        # Scrollable video list
        self.video_list_frame = ctk.CTkScrollableFrame(
            content_frame,
            fg_color=COLORS["background"],
            corner_radius=8,
        )
        self.video_list_frame.grid(row=1, column=0, sticky="nsew")
        self.video_list_frame.grid_columnconfigure(0, weight=1)

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

    def _populate_videos(self):
        """Populate the video list."""
        for i, video in enumerate(self.videos):
            item = VideoListItem(
                self.video_list_frame,
                video=video,
                row_index=i,
                on_select_change=self._update_stats,
            )
            item.grid(row=i, column=0, sticky="ew")
            self.video_items.append(item)

    def _update_stats(self):
        """Update the stats label."""
        selected_count = sum(1 for item in self.video_items if item.selected)
        total_count = len(self.video_items)

        selected_duration = sum(
            item.video.duration_seconds
            for item in self.video_items
            if item.selected
        )
        duration_str = YouTubeDownloader.format_duration(selected_duration)

        self.stats_label.configure(
            text=f"Selected: {selected_count} of {total_count} videos ({duration_str})"
        )

    def _select_all(self):
        """Select all videos."""
        for item in self.video_items:
            item.update_selection(True)
        self._update_stats()

    def _deselect_all(self):
        """Deselect all videos."""
        for item in self.video_items:
            item.update_selection(False)
        self._update_stats()

    def _on_confirm(self):
        """Handle confirm button click."""
        selected_videos = [
            item.video for item in self.video_items if item.selected
        ]
        if self.on_confirm:
            self.on_confirm(selected_videos)
        self.destroy()

    def _on_cancel(self):
        """Handle cancel button click - returns empty list."""
        if self.on_confirm:
            self.on_confirm([])
        self.destroy()
