"""
Progress dialog for transcription process.
"""
import customtkinter as ctk
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Callable
from enum import Enum

from src.models.media_file import MediaFile, TranscriptionStatus
from src.gui.styles import FONTS, PADDING, COLORS, ICONS
from src.gui.settings_dialog import _set_dialog_icon


class ProcessState(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class ProgressDialog(ctk.CTkToplevel):
    """Dialog showing transcription progress."""

    def __init__(
        self,
        parent,
        files: list[MediaFile],
        output_dir: Optional[Path] = None,
        on_cancel: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
    ):
        super().__init__(parent)

        self.files = files
        self.output_dir = output_dir
        self.on_cancel = on_cancel
        self.on_close = on_close
        self.process_state = ProcessState.RUNNING
        self.current_index = 0

        # Window configuration
        self.title("Transcription in Progress")
        self.geometry("650x550")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 650) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 550) // 2
        self.geometry(f"+{x}+{y}")

        self._create_widgets()
        _set_dialog_icon(self)

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=PADDING["large"], pady=PADDING["large"])

        # Title
        self.title_label = ctk.CTkLabel(
            main_frame,
            text="Transcription in Progress...",
            font=FONTS["heading"],
        )
        self.title_label.pack(pady=(0, PADDING["medium"]))

        # Current file info frame
        info_frame = ctk.CTkFrame(main_frame, fg_color=COLORS["surface"], corner_radius=8)
        info_frame.pack(fill="x", pady=PADDING["small"])

        self.current_file_label = ctk.CTkLabel(
            info_frame,
            text="Preparing...",
            font=FONTS["body"],
        )
        self.current_file_label.pack(pady=(PADDING["small"], 2))

        self.file_size_label = ctk.CTkLabel(
            info_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.file_size_label.pack(pady=(0, PADDING["small"]))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            main_frame,
            width=550,
            height=20,
            progress_color=COLORS["primary"],
        )
        self.progress_bar.pack(pady=PADDING["medium"])
        self.progress_bar.set(0)

        # Progress text
        self.progress_text = ctk.CTkLabel(
            main_frame,
            text="0%",
            font=FONTS["body"],
        )
        self.progress_text.pack()

        # Status label with detailed info
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.status_label.pack(pady=PADDING["small"])

        # Warning label
        self.warning_label = ctk.CTkLabel(
            main_frame,
            text="Do not close the window - this will cancel the transcription process",
            font=FONTS["small"],
            text_color=COLORS["warning"],
        )
        self.warning_label.pack(pady=(0, PADDING["small"]))

        # File list frame (no expand to leave room for buttons)
        list_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        list_frame.pack(fill="x", pady=PADDING["medium"])

        list_label = ctk.CTkLabel(
            list_frame,
            text="File Progress:",
            font=FONTS["body"],
            anchor="w",
        )
        list_label.pack(fill="x")

        # Scrollable file status list
        self.file_list = ctk.CTkScrollableFrame(
            list_frame,
            fg_color=COLORS["surface"],
            corner_radius=8,
            height=120,
        )
        self.file_list.pack(fill="x", pady=(PADDING["small"], 0))

        # Create file status items
        self.file_status_labels = []
        for file in self.files:
            item_frame = ctk.CTkFrame(self.file_list, fg_color="transparent")
            item_frame.pack(fill="x", pady=2)

            status_icon = ctk.CTkLabel(
                item_frame,
                text="\u25CB",  # Empty circle
                font=FONTS["body"],
                width=24,
            )
            status_icon.pack(side="left")

            name_label = ctk.CTkLabel(
                item_frame,
                text=file.name,
                font=FONTS["small"],
                anchor="w",
            )
            name_label.pack(side="left", fill="x", expand=True)

            detail_label = ctk.CTkLabel(
                item_frame,
                text="Pending",
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
                width=150,
                anchor="e",
            )
            detail_label.pack(side="right")

            self.file_status_labels.append({
                "frame": item_frame,
                "icon": status_icon,
                "name": name_label,
                "status": detail_label,
            })

        # Buttons frame
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=(PADDING["medium"], 0))

        self.open_folder_btn = ctk.CTkButton(
            buttons_frame,
            text="\U0001F4C2 Open Folder",
            width=130,
            fg_color=COLORS["success"],
            text_color="#FFFFFF",
            command=self._open_output_folder,
        )
        # Hidden initially, shown after completion

        self.cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            width=100,
            fg_color=COLORS["error"],
            text_color="#FFFFFF",
            command=self._on_cancel_click,
        )
        self.cancel_btn.pack(side="right")

        self.close_btn = ctk.CTkButton(
            buttons_frame,
            text="Close",
            width=100,
            fg_color=COLORS["primary"],
            text_color="#FFFFFF",
            command=self._on_close_click,
        )
        # Hidden initially

    def update_progress(self, completed: int, total: int, status: str = "", file_size: str = ""):
        """Update the overall progress. 'completed' is number of files already done."""
        self.current_index = completed
        progress = completed / total if total > 0 else 0

        self.progress_bar.set(progress)
        self.progress_text.configure(text=f"{int(progress * 100)}% ({completed}/{total} completed)")
        self.current_file_label.configure(text=f"File {completed + 1} of {total}")

        if status:
            self.status_label.configure(text=status)

        if file_size:
            self.file_size_label.configure(text=f"Size: {file_size}")

    def update_file_status(self, index: int, status: TranscriptionStatus, message: str = ""):
        """Update the status of a specific file."""
        if index < 0 or index >= len(self.file_status_labels):
            return

        labels = self.file_status_labels[index]

        # Update icon and color based on status
        if status == TranscriptionStatus.PENDING:
            icon = "\u25CB"  # Empty circle
            color = COLORS["text_secondary"]
            text = "Pending"
        elif status == TranscriptionStatus.CONVERTING:
            icon = "\u21BB"  # Rotating arrow
            color = COLORS["info"]
            text = message or "Converting..."
        elif status == TranscriptionStatus.TRANSCRIBING:
            icon = "\u25B6"  # Play
            color = COLORS["primary"]
            text = message or "Transcribing..."
        elif status == TranscriptionStatus.COMPLETED:
            icon = ICONS["check"]
            color = COLORS["success"]
            text = message or "Completed"
        elif status == TranscriptionStatus.FAILED:
            icon = ICONS["cross"]
            color = COLORS["error"]
            text = message or "Failed"
        elif status == TranscriptionStatus.SKIPPED:
            icon = "\u2014"  # Em dash
            color = COLORS["warning"]
            text = "Skipped"
        else:
            icon = "\u25CB"
            color = COLORS["text_secondary"]
            text = str(status)

        labels["icon"].configure(text=icon, text_color=color)
        labels["status"].configure(text=text, text_color=color)

    def set_completed(self, success_count: int, fail_count: int):
        """Mark the process as completed."""
        self.process_state = ProcessState.COMPLETED
        self.progress_bar.set(1)
        self.progress_text.configure(text="100%")

        # Change warning to "safe to close" message
        self.warning_label.configure(
            text="You can now safely close this window",
            text_color=COLORS["success"],
        )

        if fail_count == 0:
            self.title_label.configure(
                text=f"Transcription Complete! ({success_count} files)"
            )
            self.status_label.configure(
                text="All files processed successfully",
                text_color=COLORS["success"],
            )
        else:
            self.title_label.configure(
                text=f"Transcription Complete ({success_count} success, {fail_count} failed)"
            )
            self.status_label.configure(
                text="Some files could not be processed",
                text_color=COLORS["warning"],
            )

        # Show close and open folder buttons, hide cancel button
        self.cancel_btn.pack_forget()
        self.open_folder_btn.pack(side="left")
        self.close_btn.pack(side="right")

    def set_cancelled(self):
        """Mark the process as cancelled."""
        self.process_state = ProcessState.CANCELLED
        self.warning_label.pack_forget()
        self.title_label.configure(text="Transcription Cancelled")
        self.status_label.configure(
            text="Process was interrupted by user",
            text_color=COLORS["warning"],
        )
        self.cancel_btn.pack_forget()
        self.close_btn.pack(side="right")

    def set_error(self, message: str):
        """Mark the process as failed with error."""
        self.process_state = ProcessState.ERROR
        self.warning_label.pack_forget()
        self.title_label.configure(text="Error Occurred")
        self.status_label.configure(text=message, text_color=COLORS["error"])
        self.cancel_btn.pack_forget()
        self.close_btn.pack(side="right")

    def _open_output_folder(self):
        """Open the output folder in file explorer."""
        folder_to_open = None

        # Determine which folder to open
        if self.output_dir and self.output_dir.exists():
            folder_to_open = self.output_dir
        elif self.files:
            # Find the first successfully completed file
            for file in self.files:
                if file.status == TranscriptionStatus.COMPLETED and file.output_path:
                    folder_to_open = file.output_path.parent
                    break
            # Fallback to first file's parent directory
            if not folder_to_open:
                folder_to_open = self.files[0].parent_dir

        if folder_to_open and folder_to_open.exists():
            try:
                if sys.platform == "win32":
                    os.startfile(folder_to_open)
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(folder_to_open)])
                else:
                    subprocess.run(["xdg-open", str(folder_to_open)])
            except Exception as e:
                print(f"Could not open folder: {e}")

    def _on_cancel_click(self):
        """Handle cancel button click."""
        if self.on_cancel:
            self.on_cancel()
        self.cancel_btn.configure(state="disabled", text="Cancelling...")

    def _on_close_click(self):
        """Handle close button click."""
        if self.on_close:
            self.on_close()
        self.destroy()

    def _on_window_close(self):
        """Handle window close button."""
        if self.process_state == ProcessState.RUNNING:
            self._on_cancel_click()
        else:
            self._on_close_click()
