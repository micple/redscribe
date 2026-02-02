"""
Batch Manager Tab - Master-Detail UI for batch history management.

This tab provides a complete interface for managing transcription batch history:
- Master panel: Scrollable list of batch cards with status badges
- Detail panel: Selected batch metadata, settings, file list, and actions
- Actions: Resume (all or selected), Export CSV, Delete batch

Features:
- Auto-refresh every 2 seconds when active batches exist
- Filter by batch status (All/Active/Paused/Completed)
- Batch cards show: date, status badge, format, file count, progress bar
- Detail panel shows: metadata, settings, progress, file list with checkboxes
"""
import logging
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Optional, Callable, List
from datetime import datetime
import csv

from src.gui.styles import FONTS, PADDING, COLORS, SPACING, DIMENSIONS
from src.utils.batch_history_manager import BatchHistoryManager
from contracts.batch_state import BatchState, BatchStatus, TranscriptionStatusEnum

logger = logging.getLogger(__name__)


class BatchManagerTab(ctk.CTkFrame):
    """Batch Manager Tab with master-detail layout."""

    def __init__(
        self,
        parent,
        api_manager,
        main_window,
    ):
        super().__init__(parent, fg_color=COLORS["background"])

        self.api_manager = api_manager
        self.main_window = main_window
        self.selected_batch_id: Optional[str] = None
        self.selected_batch: Optional[BatchState] = None
        self.auto_refresh_id: Optional[str] = None

        # State
        self.file_checkboxes: List[ctk.CTkCheckBox] = []

        self._create_widgets()
        self._load_batches()
        self._start_auto_refresh()

    def _create_widgets(self):
        """Create master-detail layout."""
        # Main container with grid
        self.grid_columnconfigure(0, weight=1, minsize=300)
        self.grid_columnconfigure(1, weight=2, minsize=400)
        self.grid_rowconfigure(0, weight=1)

        self._create_master_panel()
        self._create_detail_panel()

    def _create_master_panel(self):
        """Create left master panel with batch list."""
        master_frame = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])
        master_frame.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["sm"]))
        master_frame.grid_rowconfigure(2, weight=1)
        master_frame.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkLabel(
            master_frame,
            text="Batch History",
            font=FONTS["heading"],
            anchor="w",
        )
        header.grid(row=0, column=0, sticky="ew", padx=PADDING["medium"], pady=(PADDING["medium"], PADDING["small"]))

        # Filter + Refresh row
        control_frame = ctk.CTkFrame(master_frame, fg_color="transparent")
        control_frame.grid(row=1, column=0, sticky="ew", padx=PADDING["medium"], pady=(0, PADDING["small"]))
        control_frame.grid_columnconfigure(0, weight=1)

        self.filter_var = ctk.StringVar(value="All")
        self.filter_dropdown = ctk.CTkOptionMenu(
            control_frame,
            values=["All", "Active", "Paused", "Completed"],
            variable=self.filter_var,
            width=120,
            fg_color=COLORS["surface_elevated"],
            button_color=COLORS["primary"],
            button_hover_color=COLORS["primary_hover"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["surface_elevated"],
            text_color=COLORS["text"],
            dropdown_text_color=COLORS["text"],
            command=self._on_filter_change,
        )
        self.filter_dropdown.grid(row=0, column=0, sticky="w")

        self.refresh_btn = ctk.CTkButton(
            control_frame,
            text="⟳",
            width=40,
            height=DIMENSIONS["button_height_sm"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._load_batches,
        )
        self.refresh_btn.grid(row=0, column=1, sticky="e")

        # Scrollable batch list
        self.batch_list = ctk.CTkScrollableFrame(
            master_frame,
            fg_color=COLORS["background"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        self.batch_list.grid(row=2, column=0, sticky="nsew", padx=PADDING["small"], pady=(0, PADDING["small"]))
        self.batch_list.grid_columnconfigure(0, weight=1)

    def _create_detail_panel(self):
        """Create right detail panel (hidden by default)."""
        self.detail_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=DIMENSIONS["corner_radius_lg"],
            border_width=1,
            border_color=COLORS["border"],
        )
        # Hidden by default

        self.detail_frame.grid_columnconfigure(0, weight=1)
        self.detail_frame.grid_rowconfigure(3, weight=1)

        # Header with batch_id and status
        self.detail_header = ctk.CTkLabel(
            self.detail_frame,
            text="",
            font=FONTS["heading"],
            anchor="w",
        )
        self.detail_header.grid(row=0, column=0, sticky="ew", padx=PADDING["medium"], pady=(PADDING["medium"], PADDING["small"]))

        # Metadata section
        self.metadata_frame = ctk.CTkFrame(self.detail_frame, fg_color=COLORS["background"], corner_radius=DIMENSIONS["corner_radius"])
        self.metadata_frame.grid(row=1, column=0, sticky="ew", padx=PADDING["medium"], pady=(0, PADDING["small"]))
        self.metadata_frame.grid_columnconfigure(1, weight=1)

        # Settings preview
        self.settings_frame = ctk.CTkFrame(self.detail_frame, fg_color=COLORS["background"], corner_radius=DIMENSIONS["corner_radius"])
        self.settings_frame.grid(row=2, column=0, sticky="ew", padx=PADDING["medium"], pady=(0, PADDING["small"]))

        # File list with checkboxes
        file_list_label = ctk.CTkLabel(
            self.detail_frame,
            text="Files (pending/failed only):",
            font=FONTS["body"],
            anchor="w",
        )
        file_list_label.grid(row=3, column=0, sticky="ew", padx=PADDING["medium"], pady=(PADDING["small"], 2))

        self.file_list = ctk.CTkScrollableFrame(
            self.detail_frame,
            fg_color=COLORS["background"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        self.file_list.grid(row=4, column=0, sticky="nsew", padx=PADDING["medium"], pady=(0, PADDING["small"]))

        # Action buttons
        action_frame = ctk.CTkFrame(self.detail_frame, fg_color="transparent")
        action_frame.grid(row=5, column=0, sticky="ew", padx=PADDING["medium"], pady=(0, PADDING["medium"]))
        action_frame.grid_columnconfigure(0, weight=1)

        self.resume_all_btn = ctk.CTkButton(
            action_frame,
            text="▶ Resume All",
            width=120,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._on_resume_all,
        )
        self.resume_all_btn.grid(row=0, column=0, sticky="w", padx=(0, SPACING["sm"]))

        self.resume_selected_btn = ctk.CTkButton(
            action_frame,
            text="▶ Resume Selected",
            width=140,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["info"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._on_resume_selected,
        )
        self.resume_selected_btn.grid(row=0, column=1, sticky="w", padx=(0, SPACING["sm"]))

        self.export_btn = ctk.CTkButton(
            action_frame,
            text="📄 Export CSV",
            width=120,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._on_export_csv,
        )
        self.export_btn.grid(row=0, column=2, sticky="e")

        self.delete_btn = ctk.CTkButton(
            action_frame,
            text="🗑 Delete",
            width=100,
            height=DIMENSIONS["button_height"],
            fg_color=COLORS["error"],
            hover_color="#c0392b",
            text_color="#FFFFFF",
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._on_delete,
        )
        self.delete_btn.grid(row=0, column=3, sticky="e", padx=(SPACING["sm"], 0))

    def _load_batches(self):
        """Load and display batch list."""
        # Clear existing cards
        for widget in self.batch_list.winfo_children():
            widget.destroy()

        # Get filter
        filter_value = self.filter_var.get()
        status_filter = None
        if filter_value == "Active":
            status_filter = BatchStatus.ACTIVE
        elif filter_value == "Paused":
            status_filter = BatchStatus.PAUSED
        elif filter_value == "Completed":
            status_filter = BatchStatus.COMPLETED

        # Load batches from index (archived/completed)
        batches = BatchHistoryManager.list_batches(status_filter=status_filter)

        # Also include active batch (not in index yet)
        active_state = BatchHistoryManager.load_active_batch()
        if active_state:
            active_status = active_state.status.value if active_state.status else "active"
            # Check if filter matches
            if status_filter is None or active_status == status_filter.value:
                # Check it's not already in the index
                active_ids = {b.get("batch_id") for b in batches}
                if active_state.batch_id not in active_ids:
                    completed_count = sum(
                        1 for f in active_state.files if f.status.value == "completed"
                    )
                    active_entry = {
                        "batch_id": active_state.batch_id,
                        "status": active_status,
                        "created_at": active_state.created_at.isoformat(),
                        "completed_at": active_state.completed_at.isoformat() if active_state.completed_at else None,
                        "total_files": len(active_state.files),
                        "completed_files": completed_count,
                        "filename": None,
                    }
                    batches.insert(0, active_entry)

        if not batches:
            empty_label = ctk.CTkLabel(
                self.batch_list,
                text="No batches found",
                font=FONTS["body"],
                text_color=COLORS["text_secondary"],
            )
            empty_label.pack(pady=PADDING["large"])
            return

        # Create batch cards
        for batch_data in batches:
            self._create_batch_card(batch_data)

    def _create_batch_card(self, batch_data: dict):
        """Create a batch card widget.

        Args:
            batch_data: Dict with batch_id, status, created_at, total_files, completed_files, etc.
        """
        batch_id = batch_data.get("batch_id", "")
        status = batch_data.get("status", "")
        created_str = batch_data.get("created_at", "")
        total_files = batch_data.get("total_files", 0)
        completed_files = batch_data.get("completed_files", 0)

        # Parse created_at
        try:
            created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            date_str = created_dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            date_str = created_str

        # Card frame
        is_selected = (batch_id == self.selected_batch_id)
        card = ctk.CTkFrame(
            self.batch_list,
            fg_color=COLORS["primary_muted"] if is_selected else COLORS["surface"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=2 if is_selected else 1,
            border_color=COLORS["primary"] if is_selected else COLORS["border"],
            cursor="hand2",
        )
        card.pack(fill="x", pady=PADDING["small"])
        card.grid_columnconfigure(0, weight=1)

        # Click handler
        card.bind("<Button-1>", lambda e, bid=batch_id: self._on_batch_card_click(bid))

        # Top row: Date + Status badge
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.grid(row=0, column=0, sticky="ew", padx=PADDING["small"], pady=(PADDING["small"], 2))
        top_row.grid_columnconfigure(0, weight=1)

        date_label = ctk.CTkLabel(
            top_row,
            text=date_str,
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        date_label.pack(side="left")
        date_label.bind("<Button-1>", lambda e, bid=batch_id: self._on_batch_card_click(bid))

        # Status badge
        status_colors = {
            "active": ("● Active", COLORS["success"]),
            "paused": ("⏸ Paused", COLORS["warning"]),
            "completed": ("✓ Completed", COLORS["info"]),
        }
        badge_text, badge_color = status_colors.get(status, ("?", COLORS["text_secondary"]))
        status_badge = ctk.CTkLabel(
            top_row,
            text=badge_text,
            font=FONTS["small"],
            text_color=badge_color,
            anchor="e",
        )
        status_badge.pack(side="right")
        status_badge.bind("<Button-1>", lambda e, bid=batch_id: self._on_batch_card_click(bid))

        # Middle row: Batch ID (truncated)
        batch_id_short = batch_id[:16] + "..." if len(batch_id) > 16 else batch_id
        id_label = ctk.CTkLabel(
            card,
            text=f"ID: {batch_id_short}",
            font=FONTS["body"],
            anchor="w",
        )
        id_label.grid(row=1, column=0, sticky="ew", padx=PADDING["small"], pady=(0, 2))
        id_label.bind("<Button-1>", lambda e, bid=batch_id: self._on_batch_card_click(bid))

        # Bottom row: File count
        file_count_label = ctk.CTkLabel(
            card,
            text=f"{completed_files}/{total_files} files",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        file_count_label.grid(row=2, column=0, sticky="ew", padx=PADDING["small"], pady=(0, PADDING["small"]))
        file_count_label.bind("<Button-1>", lambda e, bid=batch_id: self._on_batch_card_click(bid))

        # Progress bar for incomplete batches
        if status in ("active", "paused") and total_files > 0:
            progress = completed_files / total_files
            progress_bar = ctk.CTkProgressBar(
                card,
                width=250,
                height=6,
                progress_color=COLORS["primary"],
            )
            progress_bar.grid(row=3, column=0, sticky="ew", padx=PADDING["small"], pady=(0, PADDING["small"]))
            progress_bar.set(progress)
            progress_bar.bind("<Button-1>", lambda e, bid=batch_id: self._on_batch_card_click(bid))

    def _on_batch_card_click(self, batch_id: str):
        """Handle batch card click - select and show detail."""
        self.selected_batch_id = batch_id
        self._load_batches()  # Refresh to update selection highlight
        self._show_batch_detail(batch_id)

    def _show_batch_detail(self, batch_id: str):
        """Load and display batch details in right panel."""
        # Load full batch state
        batch = BatchHistoryManager.load_batch_by_id(batch_id)
        if not batch:
            messagebox.showerror("Error", f"Could not load batch: {batch_id}")
            return

        self.selected_batch = batch

        # Show detail panel
        self.detail_frame.grid(row=0, column=1, sticky="nsew")

        # Update header
        status_text = batch.status.value.upper()
        self.detail_header.configure(text=f"Batch: {batch_id[:24]}... ({status_text})")

        # Update metadata
        for widget in self.metadata_frame.winfo_children():
            widget.destroy()

        created_str = batch.created_at.strftime("%Y-%m-%d %H:%M:%S")
        completed_str = batch.completed_at.strftime("%Y-%m-%d %H:%M:%S") if batch.completed_at else "N/A"

        metadata_rows = [
            ("Created:", created_str),
            ("Completed:", completed_str),
            ("Total Files:", str(batch.statistics.total_files)),
            ("Completed:", str(batch.statistics.completed)),
            ("Failed:", str(batch.statistics.failed)),
            ("Pending:", str(batch.statistics.pending)),
        ]

        for i, (label_text, value_text) in enumerate(metadata_rows):
            label = ctk.CTkLabel(
                self.metadata_frame,
                text=label_text,
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
                anchor="w",
            )
            label.grid(row=i, column=0, sticky="w", padx=PADDING["small"], pady=2)

            value = ctk.CTkLabel(
                self.metadata_frame,
                text=value_text,
                font=FONTS["small"],
                anchor="w",
            )
            value.grid(row=i, column=1, sticky="w", padx=PADDING["small"], pady=2)

        # Update settings
        for widget in self.settings_frame.winfo_children():
            widget.destroy()

        settings_label = ctk.CTkLabel(
            self.settings_frame,
            text="Settings:",
            font=FONTS["body"],
            anchor="w",
        )
        settings_label.pack(anchor="w", padx=PADDING["small"], pady=(PADDING["small"], 2))

        settings_text = (
            f"Format: {batch.settings.output_format.upper()}, "
            f"Language: {batch.settings.language}, "
            f"Diarize: {'Yes' if batch.settings.diarize else 'No'}, "
            f"Workers: {batch.settings.max_concurrent_workers}"
        )
        settings_value = ctk.CTkLabel(
            self.settings_frame,
            text=settings_text,
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
            wraplength=400,
        )
        settings_value.pack(anchor="w", padx=PADDING["small"], pady=(0, PADDING["small"]))

        # Update file list (only pending/failed files)
        for widget in self.file_list.winfo_children():
            widget.destroy()

        self.file_checkboxes = []
        resumable_files = [
            f for f in batch.files
            if f.status in (TranscriptionStatusEnum.PENDING, TranscriptionStatusEnum.FAILED, TranscriptionStatusEnum.SKIPPED)
        ]

        if not resumable_files:
            no_files_label = ctk.CTkLabel(
                self.file_list,
                text="No pending/failed files to resume",
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
            )
            no_files_label.pack(pady=PADDING["medium"])
        else:
            for file_state in resumable_files:
                file_frame = ctk.CTkFrame(self.file_list, fg_color="transparent")
                file_frame.pack(fill="x", pady=2)

                checkbox_var = ctk.BooleanVar(value=True)
                checkbox = ctk.CTkCheckBox(
                    file_frame,
                    text=Path(file_state.source_path).name,
                    variable=checkbox_var,
                    fg_color=COLORS["primary"],
                    hover_color=COLORS["primary_hover"],
                    border_color=COLORS["border"],
                    font=FONTS["small"],
                )
                checkbox.pack(side="left", anchor="w")
                checkbox.file_state = file_state
                checkbox.checkbox_var = checkbox_var
                self.file_checkboxes.append(checkbox)

                # Status label
                status_text = file_state.status.value.upper()
                status_color = COLORS["warning"] if file_state.status == TranscriptionStatusEnum.FAILED else COLORS["text_secondary"]
                status_label = ctk.CTkLabel(
                    file_frame,
                    text=status_text,
                    font=FONTS["small"],
                    text_color=status_color,
                )
                status_label.pack(side="right")

        # Enable/disable buttons
        has_resumable = len(resumable_files) > 0
        self.resume_all_btn.configure(state="normal" if has_resumable else "disabled")
        self.resume_selected_btn.configure(state="normal" if has_resumable else "disabled")

    def _on_filter_change(self, value: str):
        """Handle filter dropdown change."""
        self._load_batches()

    def _on_resume_all(self):
        """Resume all pending/failed files in batch."""
        if not self.selected_batch:
            return

        self.main_window._resume_batch(self.selected_batch, selected_files=None)

        # Switch to Main tab
        self.main_window.tab_selector.set("Main")
        self.main_window._on_tab_change("Main")

    def _on_resume_selected(self):
        """Resume only selected files from batch."""
        if not self.selected_batch:
            return

        # Get checked files
        selected_paths = [
            cb.file_state.source_path
            for cb in self.file_checkboxes
            if cb.checkbox_var.get()
        ]

        if not selected_paths:
            messagebox.showwarning("No Selection", "Please select at least one file to resume.")
            return

        # Filter batch files to only selected ones
        self.main_window._resume_batch(self.selected_batch, selected_files=selected_paths)

        # Switch to Main tab
        self.main_window.tab_selector.set("Main")
        self.main_window._on_tab_change("Main")

    def _on_export_csv(self):
        """Export batch file list to CSV."""
        if not self.selected_batch:
            return

        # Ask for save location
        filename = filedialog.asksaveasfilename(
            title="Export Batch as CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"batch_{self.selected_batch.batch_id[:8]}.csv",
        )

        if not filename:
            return

        try:
            with open(filename, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Source Path", "Status", "Output Path", "Duration (s)", "Error Message"])

                for file_state in self.selected_batch.files:
                    writer.writerow([
                        file_state.source_path,
                        file_state.status.value,
                        file_state.output_path or "",
                        file_state.duration_seconds or "",
                        file_state.error_message or "",
                    ])

            messagebox.showinfo("Export Complete", f"Batch exported to:\n{filename}")
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            messagebox.showerror("Export Failed", f"Could not export CSV:\n{e}")

    def _on_delete(self):
        """Delete selected batch."""
        if not self.selected_batch:
            return

        confirm = messagebox.askyesno(
            "Delete Batch",
            f"Are you sure you want to delete this batch?\n\n"
            f"Batch ID: {self.selected_batch.batch_id}\n"
            f"Files: {self.selected_batch.statistics.total_files}\n\n"
            f"This action cannot be undone.",
        )

        if not confirm:
            return

        try:
            BatchHistoryManager.delete_batch(self.selected_batch.batch_id)
            messagebox.showinfo("Deleted", "Batch deleted successfully.")

            # Hide detail panel
            self.detail_frame.grid_remove()
            self.selected_batch_id = None
            self.selected_batch = None

            # Reload list
            self._load_batches()
        except ValueError as e:
            messagebox.showerror("Cannot Delete", str(e))
        except Exception as e:
            logger.error(f"Failed to delete batch: {e}")
            messagebox.showerror("Delete Failed", f"Could not delete batch:\n{e}")

    def _start_auto_refresh(self):
        """Start auto-refresh timer (2 seconds)."""
        self._auto_refresh()

    def _auto_refresh(self):
        """Auto-refresh callback."""
        # Check if there are active batches
        if BatchHistoryManager.has_active_batch():
            # Reload batch list
            self._load_batches()

            # Reload detail panel if a batch is selected
            if self.selected_batch_id:
                self._show_batch_detail(self.selected_batch_id)

        # Schedule next refresh
        self.auto_refresh_id = self.after(2000, self._auto_refresh)

    def destroy(self):
        """Clean up auto-refresh timer."""
        if self.auto_refresh_id:
            self.after_cancel(self.auto_refresh_id)
        super().destroy()
