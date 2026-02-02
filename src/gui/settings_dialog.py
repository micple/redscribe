"""
Settings dialog for API key management.
"""
import customtkinter as ctk
from typing import Optional, Callable
import threading
import webbrowser
from pathlib import Path

from src.utils.api_manager import APIManager
from src.gui.styles import FONTS, PADDING, COLORS, SPACING, DIMENSIONS
from config import (
    DEEPGRAM_MODELS,
    DEEPGRAM_SPECIALIZATIONS,
    MIN_CONCURRENT_WORKERS,
    MAX_CONCURRENT_WORKERS,
    MAX_CONCURRENT_WORKERS_LIMIT,
)


def _set_dialog_icon(dialog):
    """Set the dialog window icon."""
    icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.ico"
    if icon_path.exists():
        try:
            dialog.after(200, lambda: dialog.iconbitmap(str(icon_path)))
        except Exception:
            pass


class SettingsDialog(ctk.CTkToplevel):
    """Dialog for managing API key settings."""

    def __init__(
        self,
        parent,
        api_manager: APIManager,
        on_save: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent)

        self.api_manager = api_manager
        self.on_save = on_save
        self._show_key = False

        # Window configuration
        self.title("Settings")
        self.geometry("500x680")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center on parent, clamped to screen bounds
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 500) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 680) // 2
        x = max(0, x)
        y = max(0, y)
        self.geometry(f"+{x}+{y}")

        self._create_widgets()
        self._load_current_key()
        _set_dialog_icon(self)

    def _create_widgets(self):
        """Create dialog widgets.

        Orchestrates widget creation by delegating to focused helper methods,
        each responsible for one logical section of the settings dialog.
        """
        # Main frame with more padding
        main_frame = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=0)
        main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Content frame with internal padding (shared by all sections)
        self._content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self._content_frame.pack(fill="both", expand=True, padx=SPACING["xl"], pady=SPACING["lg"])

        self._create_api_key_section()
        self._create_model_section()
        self._create_performance_section()
        self._create_info_section()
        self._create_status_section()
        self._create_dialog_buttons()

    def _create_api_key_section(self):
        """Create the API key entry section.

        Creates:
            - Title label
            - API key entry field (password masked)
            - Show/Hide toggle button
            - Delete saved key button
            - Separator line
        """
        title_label = ctk.CTkLabel(
            self._content_frame,
            text="Deepgram API Key",
            font=FONTS["heading"],
        )
        title_label.pack(pady=(0, SPACING["lg"]))

        key_frame = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        key_frame.pack(fill="x", pady=PADDING["small"])

        self.key_entry = ctk.CTkEntry(
            key_frame,
            width=350,
            show="*",
            placeholder_text="Enter your Deepgram API key...",
            font=FONTS["mono"],
        )
        self.key_entry.pack(side="left", padx=(0, PADDING["small"]))

        self.show_key_btn = ctk.CTkButton(
            key_frame,
            text="Show",
            width=70,
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._toggle_show_key,
        )
        self.show_key_btn.pack(side="left")

        self.delete_btn = ctk.CTkButton(
            self._content_frame,
            text="Delete saved key",
            fg_color="transparent",
            hover_color=COLORS["surface_elevated"],
            text_color=COLORS["text_tertiary"],
            font=FONTS["small"],
            cursor="hand2",
            height=20,
            anchor="w",
            command=self._delete_key,
        )
        self.delete_btn.pack(anchor="w", pady=(SPACING["xs"], 0))

        separator = ctk.CTkFrame(self._content_frame, fg_color=COLORS["border"], height=1)
        separator.pack(fill="x", pady=SPACING["md"])

    def _create_model_section(self):
        """Create the transcription model selection section.

        Creates:
            - Model section title
            - Model dropdown (nova-2, whisper, etc.)
            - Specialization dropdown
            - Specialization info note
        """
        model_title = ctk.CTkLabel(
            self._content_frame,
            text="Transcription Model",
            font=FONTS["heading"],
        )
        model_title.pack(anchor="w", pady=(0, SPACING["sm"]))

        model_frame = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        model_frame.pack(fill="x", pady=PADDING["small"])

        model_label = ctk.CTkLabel(
            model_frame,
            text="Model:",
            font=FONTS["body"],
            width=100,
            anchor="w",
        )
        model_label.pack(side="left")

        self.model_var = ctk.StringVar(value=self.api_manager.get_model())
        self.model_dropdown = ctk.CTkOptionMenu(
            model_frame,
            values=list(DEEPGRAM_MODELS.keys()),
            variable=self.model_var,
            width=200,
            fg_color=COLORS["surface_elevated"],
            button_color=COLORS["border"],
            button_hover_color=COLORS["primary"],
            text_color=COLORS["text"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["primary_muted"],
            dropdown_text_color=COLORS["text"],
            command=self._on_model_change,
        )
        self.model_dropdown.pack(side="left")

        spec_frame = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        spec_frame.pack(fill="x", pady=PADDING["small"])

        spec_label = ctk.CTkLabel(
            spec_frame,
            text="Specialization:",
            font=FONTS["body"],
            width=100,
            anchor="w",
        )
        spec_label.pack(side="left")

        self.spec_var = ctk.StringVar(value=self.api_manager.get_specialization())
        self.spec_dropdown = ctk.CTkOptionMenu(
            spec_frame,
            values=list(DEEPGRAM_SPECIALIZATIONS[self.model_var.get()].keys()),
            variable=self.spec_var,
            width=200,
            fg_color=COLORS["surface_elevated"],
            button_color=COLORS["border"],
            button_hover_color=COLORS["primary"],
            text_color=COLORS["text"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["primary_muted"],
            dropdown_text_color=COLORS["text"],
        )
        self.spec_dropdown.pack(side="left")

        spec_info_label = ctk.CTkLabel(
            self._content_frame,
            text="Specializations other than 'General' work only with English",
            font=FONTS["small"],
            text_color=COLORS["text_tertiary"],
        )
        spec_info_label.pack(anchor="w", pady=(SPACING["xs"], 0))

        separator = ctk.CTkFrame(self._content_frame, fg_color=COLORS["border"], height=1)
        separator.pack(fill="x", pady=SPACING["md"])

    def _create_performance_section(self):
        """Create the performance settings section.

        Creates:
            - Performance section title
            - Concurrent transcriptions slider (1-10)
            - Value label showing current selection
            - Help text about rate limits
        """
        perf_title = ctk.CTkLabel(
            self._content_frame,
            text="Performance",
            font=FONTS["heading"],
        )
        perf_title.pack(anchor="w", pady=(0, SPACING["sm"]))

        workers_label = ctk.CTkLabel(
            self._content_frame,
            text="Concurrent transcriptions:",
            font=FONTS["body"],
        )
        workers_label.pack(anchor="w", pady=(0, SPACING["xs"]))

        slider_frame = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        slider_frame.pack(fill="x", pady=PADDING["small"])

        self.workers_slider = ctk.CTkSlider(
            slider_frame,
            from_=MIN_CONCURRENT_WORKERS,
            to=MAX_CONCURRENT_WORKERS_LIMIT,
            number_of_steps=MAX_CONCURRENT_WORKERS_LIMIT - MIN_CONCURRENT_WORKERS,
            fg_color=COLORS["surface_elevated"],
            progress_color=COLORS["primary"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"],
            command=self._on_workers_slider_change,
        )
        self.workers_slider.set(self.api_manager.get_max_concurrent_workers())
        self.workers_slider.pack(side="left", fill="x", expand=True, padx=(0, PADDING["small"]))

        self.workers_value_label = ctk.CTkLabel(
            slider_frame,
            text=f"{self.api_manager.get_max_concurrent_workers()} files",
            font=FONTS["body"],
            width=60,
        )
        self.workers_value_label.pack(side="right")

        help_label = ctk.CTkLabel(
            self._content_frame,
            text="⚠️ Higher values = faster batches but may hit API rate limits",
            font=FONTS["small"],
            text_color=COLORS["text_tertiary"],
        )
        help_label.pack(anchor="w", pady=(SPACING["xs"], 0))

    def _create_info_section(self):
        """Create the informational section with API key URL.

        Creates:
            - Info text directing user to Deepgram console
            - Clickable URL label
            - Encryption info note
        """
        info_frame = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        info_frame.pack(pady=SPACING["lg"])

        info_label1 = ctk.CTkLabel(
            info_frame,
            text="Get your API key at:",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        info_label1.pack()

        url_label = ctk.CTkLabel(
            info_frame,
            text="https://console.deepgram.com/",
            font=FONTS["small"],
            text_color=COLORS["primary"],
            cursor="hand2",
        )
        url_label.pack(pady=(SPACING["xs"], 0))
        url_label.bind("<Button-1>", lambda e: webbrowser.open("https://console.deepgram.com/"))

        info_label2 = ctk.CTkLabel(
            info_frame,
            text="The key is stored locally in encrypted form.",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        info_label2.pack(pady=(SPACING["sm"], 0))

    def _create_status_section(self):
        """Create the status message label.

        Creates:
            - Status label for displaying save/test/error messages
        """
        self.status_label = ctk.CTkLabel(
            self._content_frame,
            text="",
            font=FONTS["body"],
        )
        self.status_label.pack(pady=SPACING["sm"])

    def _create_dialog_buttons(self):
        """Create the dialog action buttons.

        Creates:
            - Test Connection button (left)
            - Save button (right)
            - Cancel button (far right)
        """
        buttons_frame = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=(SPACING["lg"], 0))

        self.test_btn = ctk.CTkButton(
            buttons_frame,
            text="Test Connection",
            width=120,
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._test_connection,
        )
        self.test_btn.pack(side="left")

        self.cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            width=90,
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            border_width=1,
            border_color=COLORS["border"],
            command=self.destroy,
        )
        self.cancel_btn.pack(side="right")

        self.save_btn = ctk.CTkButton(
            buttons_frame,
            text="Save",
            width=90,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._save_key,
        )
        self.save_btn.pack(side="right", padx=(0, PADDING["small"]))

    def _load_current_key(self):
        """Load the current API key if exists."""
        current_key = self.api_manager.load_api_key()
        if current_key:
            self.key_entry.insert(0, current_key)
            self._set_status("API key loaded", "success")

    def _on_model_change(self, selected_model: str):
        """Handle model dropdown change - update specializations."""
        specializations = list(DEEPGRAM_SPECIALIZATIONS.get(selected_model, {"general": "General"}).keys())
        self.spec_dropdown.configure(values=specializations)
        # Reset to general if current spec not available in new model
        if self.spec_var.get() not in specializations:
            self.spec_var.set("general")

    def _on_workers_slider_change(self, value: float):
        """Handle workers slider change - update value label."""
        workers = int(value)
        self.workers_value_label.configure(
            text=f"{workers} file{'s' if workers != 1 else ''}"
        )

    def _toggle_show_key(self):
        """Toggle visibility of the API key."""
        self._show_key = not self._show_key
        self.key_entry.configure(show="" if self._show_key else "*")
        self.show_key_btn.configure(text="Hide" if self._show_key else "Show")

    def _set_status(self, message: str, status_type: str = "info"):
        """Update status message with appropriate color."""
        color_map = {
            "success": COLORS["success"],
            "error": COLORS["error"],
            "info": COLORS["info"],
            "warning": COLORS["warning"],
        }
        self.status_label.configure(
            text=message,
            text_color=color_map.get(status_type, COLORS["text"]),
        )

    def _test_connection(self):
        """Test the API key connection."""
        api_key = self.key_entry.get().strip()

        if not api_key:
            self._set_status("Please enter an API key", "warning")
            return

        self._set_status("Testing connection...", "info")
        self.test_btn.configure(state="disabled")

        def test_thread():
            is_valid, message = self.api_manager.validate_api_key(api_key)
            self.after(0, lambda: self._on_test_complete(is_valid, message))

        thread = threading.Thread(target=test_thread, daemon=True)
        thread.start()

    def _on_test_complete(self, is_valid: bool, message: str):
        """Handle test completion."""
        self.test_btn.configure(state="normal")
        self._set_status(message, "success" if is_valid else "error")

    def _save_key(self):
        """Save the API key and model settings."""
        api_key = self.key_entry.get().strip()

        if not api_key:
            self._set_status("Please enter an API key", "warning")
            return

        try:
            self.api_manager.save_api_key(api_key)
            self.api_manager.set_model(self.model_var.get())
            self.api_manager.set_specialization(self.spec_var.get())
            self.api_manager.set_max_concurrent_workers(int(self.workers_slider.get()))
            self._set_status("Settings saved", "success")

            if self.on_save:
                self.on_save(api_key)

            self.after(500, self.destroy)

        except Exception as e:
            self._set_status(f"Save error: {str(e)}", "error")

    def _delete_key(self):
        """Delete the stored API key."""
        try:
            self.api_manager.delete_api_key()
            self.key_entry.delete(0, "end")
            self._set_status("API key deleted", "success")

            if self.on_save:
                self.on_save("")

        except Exception as e:
            self._set_status(f"Delete error: {str(e)}", "error")
