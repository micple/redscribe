"""
GUI styles and theme configuration.
Light Elegant Design System
"""
import customtkinter as ctk

# Theme configuration
APPEARANCE_MODE = "light"
COLOR_THEME = "blue"

# =============================================================================
# LIGHT ELEGANT DESIGN SYSTEM
# =============================================================================

# Colors - Clean Light Theme with Elegant Red Accents
COLORS = {
    # Background hierarchy
    "background_deep": "#F0F0F0",
    "background": "#FAFAFA",
    "surface": "#FFFFFF",
    "surface_elevated": "#F5F5F5",

    # Borders
    "border_subtle": "#E5E5E5",
    "border": "#D0D0D0",

    # Brand - Elegant Red
    "primary": "#B83A3F",
    "primary_hover": "#9E3338",
    "primary_muted": "#F5E0E1",  # Light red tint (solid color)

    # Text hierarchy
    "text": "#1A1A1A",
    "text_secondary": "#666666",
    "text_tertiary": "#999999",

    # Semantic colors
    "success": "#059669",
    "warning": "#D97706",
    "error": "#DC2626",
    "info": "#4F46E5",
}

# Fonts - Inter for UI, JetBrains Mono for code
FONTS = {
    "display": ("Inter", 24, "bold"),
    "title": ("Inter", 18, "bold"),
    "heading": ("Inter", 14, "bold"),
    "body": ("Inter", 13),
    "body_medium": ("Inter", 13, "bold"),
    "small": ("Inter", 11),
    "caption": ("Inter", 10),
    "mono": ("JetBrains Mono", 11),
}

# Spacing - 8pt grid system
SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "base": 16,
    "lg": 24,
    "xl": 32,
    "2xl": 48,
}

# Legacy padding (for compatibility)
PADDING = {
    "small": SPACING["sm"],
    "medium": SPACING["md"],
    "large": SPACING["base"],
    "xlarge": SPACING["lg"],
}

# Component dimensions
DIMENSIONS = {
    "button_height": 40,
    "button_height_sm": 32,
    "input_height": 40,
    "corner_radius": 8,
    "corner_radius_lg": 12,
}

# Button styles
BUTTON_STYLES = {
    "primary": {
        "fg_color": COLORS["primary"],
        "hover_color": COLORS["primary_hover"],
        "text_color": "#FFFFFF",  # White text on red for contrast
        "corner_radius": DIMENSIONS["corner_radius"],
        "height": DIMENSIONS["button_height"],
    },
    "secondary": {
        "fg_color": "transparent",
        "hover_color": COLORS["surface_elevated"],
        "text_color": COLORS["text_secondary"],
        "border_width": 1,
        "border_color": COLORS["border"],
        "corner_radius": DIMENSIONS["corner_radius"],
        "height": DIMENSIONS["button_height"],
    },
    "ghost": {
        "fg_color": "transparent",
        "hover_color": COLORS["surface_elevated"],
        "text_color": COLORS["text_secondary"],
        "corner_radius": DIMENSIONS["corner_radius"],
        "height": DIMENSIONS["button_height"],
    },
    "text": {
        "fg_color": "transparent",
        "hover_color": "transparent",
        "text_color": COLORS["text_secondary"],
        "corner_radius": 0,
        "height": DIMENSIONS["button_height_sm"],
    },
}

# Icon characters (using ASCII/simple Unicode for better compatibility)
ICONS = {
    "folder": "▼",
    "folder_collapsed": "▶",
    "file_audio": "▪",
    "file_video": "▪",
    "check": "\u2713",
    "cross": "\u2717",
    "settings": "\u2699",
    "play": "\u25B6",
    "refresh": "\u21BB",
    "warning": "\u26A0",
    "info": "\u2139",
}


def configure_theme():
    """Apply the application theme."""
    ctk.set_appearance_mode(APPEARANCE_MODE)
    ctk.set_default_color_theme(COLOR_THEME)


def apply_button_style(button: ctk.CTkButton, style: str = "primary"):
    """Apply predefined button style."""
    if style in BUTTON_STYLES:
        config = BUTTON_STYLES[style]
        button.configure(**{k: v for k, v in config.items() if k != "height"})


def get_status_color(status: str) -> str:
    """Get color for a given status."""
    status_colors = {
        "pending": COLORS["text_secondary"],
        "converting": COLORS["info"],
        "transcribing": COLORS["primary"],
        "completed": COLORS["success"],
        "failed": COLORS["error"],
        "skipped": COLORS["warning"],
    }
    return status_colors.get(status, COLORS["text"])


def get_file_icon(is_video: bool) -> str:
    """Get icon for file type."""
    return ICONS["file_video"] if is_video else ICONS["file_audio"]


class Tooltip:
    """
    Simple tooltip that appears on hover.
    """

    def __init__(self, widget, text: str, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.scheduled_id = None

        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)

    def _on_enter(self, event=None):
        self.scheduled_id = self.widget.after(self.delay, self._show_tooltip)

    def _on_leave(self, event=None):
        if self.scheduled_id:
            self.widget.after_cancel(self.scheduled_id)
            self.scheduled_id = None
        self._hide_tooltip()

    def _show_tooltip(self):
        if self.tooltip_window:
            return

        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tooltip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)

        # Tooltip frame with text (dark background for visibility on light theme)
        frame = ctk.CTkFrame(tw, fg_color="#333333", corner_radius=6)
        frame.pack()

        label = ctk.CTkLabel(
            frame,
            text=self.text,
            font=FONTS["small"],
            text_color="#FFFFFF",
            padx=8,
            pady=4,
            wraplength=250,
            justify="left",
        )
        label.pack()

    def _hide_tooltip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    def update_text(self, text: str):
        """Update tooltip text."""
        self.text = text
