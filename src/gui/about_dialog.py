"""
About dialog with application information and features.
"""
import customtkinter as ctk
import webbrowser

from config import APP_NAME, APP_VERSION
from src.gui.styles import FONTS, PADDING, COLORS, SPACING, DIMENSIONS
from src.gui.settings_dialog import _set_dialog_icon


class AboutDialog(ctk.CTkToplevel):
    """Dialog showing application information and features."""

    def __init__(self, parent):
        super().__init__(parent)

        # Window configuration
        self.title(f"About {APP_NAME}")
        self.geometry("480x380")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 480) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 380) // 2
        self.geometry(f"+{x}+{y}")

        self._create_widgets()
        _set_dialog_icon(self)

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=PADDING["large"], pady=PADDING["large"])

        # App title with logo - "[R]edscribe" style
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(pady=(0, SPACING["sm"]))

        logo_label = ctk.CTkLabel(
            title_frame,
            text="[R]",
            font=FONTS["display"],
            text_color=COLORS["primary"],
        )
        logo_label.pack(side="left")

        title_label = ctk.CTkLabel(
            title_frame,
            text="edscribe",
            font=FONTS["display"],
        )
        title_label.pack(side="left")

        version_label = ctk.CTkLabel(
            main_frame,
            text=f"Version {APP_VERSION}",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        version_label.pack(pady=(0, PADDING["medium"]))

        # Features frame (Version C - expanded box)
        features_frame = ctk.CTkFrame(main_frame, fg_color=COLORS["surface"], corner_radius=8)
        features_frame.pack(fill="x", pady=PADDING["medium"])

        features_title = ctk.CTkLabel(
            features_frame,
            text="Features",
            font=FONTS["heading"],
        )
        features_title.pack(anchor="w", padx=PADDING["medium"], pady=(PADDING["medium"], PADDING["small"]))

        features = [
            ("•", "Transcribe multiple audio/video files at once"),
            ("•", "Export to TXT, SRT, VTT (with timestamps)"),
            ("•", "Speaker diarization - automatically detects and labels different speakers"),
            ("•", "Multi-language support"),
        ]

        for bullet, text in features:
            feature_frame = ctk.CTkFrame(features_frame, fg_color="transparent")
            feature_frame.pack(fill="x", padx=PADDING["medium"], pady=2)

            bullet_label = ctk.CTkLabel(
                feature_frame,
                text=bullet,
                font=FONTS["body"],
                width=20,
            )
            bullet_label.pack(side="left")

            text_label = ctk.CTkLabel(
                feature_frame,
                text=text,
                font=FONTS["body"],
                anchor="w",
                wraplength=380,
                justify="left",
            )
            text_label.pack(side="left", fill="x", expand=True)

        # Powered by
        powered_label = ctk.CTkLabel(
            features_frame,
            text="Powered by Deepgram AI",
            font=FONTS["small"],
            text_color=COLORS["info"],
            cursor="hand2",
        )
        powered_label.pack(anchor="w", padx=PADDING["medium"], pady=(PADDING["small"], PADDING["small"]))
        powered_label.bind("<Button-1>", lambda e: webbrowser.open("https://deepgram.com"))

        # Author
        author_label = ctk.CTkLabel(
            features_frame,
            text="Created by @micple",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        author_label.pack(anchor="w", padx=PADDING["medium"], pady=(0, PADDING["small"]))

        # GitHub link
        github_label = ctk.CTkLabel(
            features_frame,
            text="github.com/micple/redscribe",
            font=FONTS["small"],
            text_color=COLORS["info"],
            cursor="hand2",
        )
        github_label.pack(anchor="w", padx=PADDING["medium"], pady=(0, PADDING["medium"]))
        github_label.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/micple/redscribe"))

