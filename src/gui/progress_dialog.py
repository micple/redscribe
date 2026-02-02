"""
Progress dialog for transcription process.
"""
import logging
import customtkinter as ctk

logger = logging.getLogger(__name__)
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
        """Create dialog widgets.

        Orchestrates widget creation by delegating to focused helper methods,
        each responsible for one logical section of the progress dialog.
        """
        self._main_frame = ctk.CTkFrame(self)
        self._main_frame.pack(fill="both", expand=True, padx=PADDING["large"], pady=PADDING["large"])

        self._create_overall_progress()
        self._create_file_list()
        self._create_control_buttons()

    def _create_overall_progress(self):
        """Create the overall progress section.

        Creates:
            - Title label
            - Current file info frame with file name and size
            - Progress bar and percentage text
            - Status and warning labels
        """
        self.title_label = ctk.CTkLabel(
            self._main_frame,
            text="Transcription in Progress...",
            font=FONTS["heading"],
        )
        self.title_label.pack(pady=(0, PADDING["medium"]))

        info_frame = ctk.CTkFrame(self._main_frame, fg_color=COLORS["surface"], corner_radius=8)
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

        self.progress_bar = ctk.CTkProgressBar(
            self._main_frame,
            width=550,
            height=20,
            progress_color=COLORS["primary"],
        )
        self.progress_bar.pack(pady=PADDING["medium"])
        self.progress_bar.set(0)

        self.progress_text = ctk.CTkLabel(
            self._main_frame,
            text="0%",
            font=FONTS["body"],
        )
        self.progress_text.pack()

        self.status_label = ctk.CTkLabel(
            self._main_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.status_label.pack(pady=PADDING["small"])

        self.warning_label = ctk.CTkLabel(
            self._main_frame,
            text="Do not close the window - this will cancel the transcription process",
            font=FONTS["small"],
            text_color=COLORS["warning"],
        )
        self.warning_label.pack(pady=(0, PADDING["small"]))

        self.workers_label = ctk.CTkLabel(
            self._main_frame,
            text="Workers: 0/0 active",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.workers_label.pack(pady=(0, PADDING["small"]))

    def _create_file_list(self):
        """Create the scrollable file progress list.

        Creates:
            - File Progress label
            - Scrollable frame with per-file status rows
            - Each row has: status icon, file name, status detail label
        """
        list_frame = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        list_frame.pack(fill="x", pady=PADDING["medium"])

        list_label = ctk.CTkLabel(
            list_frame,
            text="File Progress:",
            font=FONTS["body"],
            anchor="w",
        )
        list_label.pack(fill="x")

        self.file_list = ctk.CTkScrollableFrame(
            list_frame,
            fg_color=COLORS["surface"],
            corner_radius=8,
            height=120,
        )
        self.file_list.pack(fill="x", pady=(PADDING["small"], 0))

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

    def _create_control_buttons(self):
        """Create the dialog control buttons.

        Creates:
            - Open Folder button (hidden initially, shown after completion)
            - Cancel button (visible during processing)
            - Close button (hidden initially, shown after completion)
            - Retry button placeholder (created dynamically when needed)
        """
        self.buttons_frame = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        self.buttons_frame.pack(fill="x", pady=(PADDING["medium"], 0))

        self.retry_btn = None

        self.open_folder_btn = ctk.CTkButton(
            self.buttons_frame,
            text="\U0001F4C2 Open Folder",
            width=130,
            fg_color=COLORS["success"],
            text_color="#FFFFFF",
            command=self._open_output_folder,
        )
        # Hidden initially, shown after completion

        self.cancel_btn = ctk.CTkButton(
            self.buttons_frame,
            text="Cancel",
            width=100,
            fg_color=COLORS["error"],
            text_color="#FFFFFF",
            command=self._on_cancel_click,
        )
        self.cancel_btn.pack(side="right")

        self.close_btn = ctk.CTkButton(
            self.buttons_frame,
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
        elif status == TranscriptionStatus.RETRYING:
            icon = "\u21BB"  # Rotating arrow
            color = COLORS["warning"]
            text = message or "Retrying..."
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

    def update_status(self, message: str):
        """Update the status label with a message."""
        self.status_label.configure(text=message)

    def update_workers_count(self, active: int, total: int):
        """Update the workers count display.

        Args:
            active: Number of currently active workers processing files.
            total: Maximum number of workers allowed.
        """
        self.workers_label.configure(text=f"Workers: {active}/{total} active")

    def set_completed_with_retry(
        self,
        success_count: int,
        fail_count: int,
        failed_files: list,
        on_retry: Callable = None
    ):
        """Mark process as completed with option to retry failed files."""
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

            # Build failure summary
            if len(failed_files) == 1:
                summary = f"Failed: {failed_files[0].name}"
            elif len(failed_files) <= 3:
                names = ", ".join(f.name for f in failed_files)
                summary = f"Failed: {names}"
            else:
                summary = f"{fail_count} files could not be processed"

            self.status_label.configure(
                text=summary,
                text_color=COLORS["warning"],
            )

        # Hide cancel button
        self.cancel_btn.pack_forget()

        # Remove old retry button if exists
        if self.retry_btn:
            self.retry_btn.pack_forget()
            self.retry_btn = None

        # Show retry button if there are failed files that can be retried
        if failed_files and on_retry:
            self.retry_btn = ctk.CTkButton(
                self.buttons_frame,
                text="\u21BB Retry Failed",
                width=120,
                fg_color=COLORS["warning"],
                text_color="#FFFFFF",
                command=on_retry,
            )
            self.retry_btn.pack(side="left", padx=(0, PADDING["small"]))

        # Ensure open folder and close buttons are visible
        self.open_folder_btn.pack_forget()
        self.close_btn.pack_forget()
        self.open_folder_btn.pack(side="left")
        self.close_btn.pack(side="right")

    def prepare_for_retry(self, files_to_retry: list):
        """Prepare dialog for retry operation."""
        self.process_state = ProcessState.RUNNING

        # Update title
        self.title_label.configure(text=f"Retrying {len(files_to_retry)} file(s)...")

        # Update warning
        self.warning_label.configure(
            text="Do not close the window - retry in progress",
            text_color=COLORS["warning"],
        )

        # Hide completion buttons, show cancel
        if self.retry_btn:
            self.retry_btn.pack_forget()
        self.open_folder_btn.pack_forget()
        self.close_btn.pack_forget()
        self.cancel_btn.configure(state="normal", text="Cancel")
        self.cancel_btn.pack(side="right")

        # Reset progress bar
        self.progress_bar.set(0)
        self.progress_text.configure(text="0%")

        # Update file statuses to pending for retry files
        for file in files_to_retry:
            index = self.files.index(file)
            self.update_file_status(index, TranscriptionStatus.PENDING, "Waiting for retry...")

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
                logger.warning("Could not open folder: %s", e)

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
