"""
Logs tab UI component.

Displays:
- Event stream (left panel)
- Statistics dashboard (right panel)
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
from typing import Optional

from src.gui.styles import FONTS, PADDING, COLORS, ICONS
from src.utils.session_logger import get_logger, LogEntry, LogLevel


class LogsTab(ctk.CTkFrame):
    """Logs tab with event stream and statistics dashboard."""

    # Icon and color mapping for log levels
    LEVEL_STYLES = {
        "info": {"icon": "\u25B6", "color": COLORS["info"]},          # Play
        "success": {"icon": ICONS["check"], "color": COLORS["success"]},
        "warning": {"icon": "\u26A0", "color": COLORS["warning"]},    # Warning sign
        "error": {"icon": ICONS["cross"], "color": COLORS["error"]},
        "converting": {"icon": "\u21BB", "color": COLORS["info"]},    # Rotating arrow
        "transcribing": {"icon": "\u25B6", "color": COLORS["primary"]},
    }

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")

        self.logger = get_logger()

        # Register callbacks
        self.logger.on_event = self._on_new_event
        self.logger.on_stats_update = self._refresh_stats

        self._create_widgets()
        self._load_existing_events()
        self._refresh_stats()

    def _create_widgets(self):
        """Create the logs tab UI."""
        # Configure grid
        self.grid_columnconfigure(0, weight=3)  # Event log (wider)
        self.grid_columnconfigure(1, weight=2)  # Stats dashboard
        self.grid_rowconfigure(0, weight=1)

        # Left panel: Event log
        self._create_event_log_panel()

        # Right panel: Statistics dashboard
        self._create_stats_panel()

    def _create_event_log_panel(self):
        """Create the event log panel (left side)."""
        log_frame = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=12)
        log_frame.grid(row=0, column=0, sticky="nsew", padx=(0, PADDING["small"]), pady=0)
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkFrame(log_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PADDING["medium"], pady=PADDING["small"])

        ctk.CTkLabel(
            header,
            text="Event Log",
            font=FONTS["heading"],
        ).pack(side="left")

        # Clear button
        self.clear_btn = ctk.CTkButton(
            header,
            text="Clear",
            width=70,
            height=28,
            fg_color=COLORS["surface_elevated"],
            text_color=COLORS["text"],
            hover_color=COLORS["background_deep"],
            command=self._clear_logs,
        )
        self.clear_btn.pack(side="right")

        # Scrollable event list
        self.event_list = ctk.CTkScrollableFrame(
            log_frame,
            fg_color=COLORS["background"],
            corner_radius=8,
        )
        self.event_list.grid(row=1, column=0, sticky="nsew", padx=PADDING["small"], pady=(0, PADDING["small"]))

        # Placeholder for empty state
        self.empty_label = ctk.CTkLabel(
            self.event_list,
            text="No events yet.\nStart a transcription to see activity here.",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.empty_label.pack(pady=PADDING["large"])

    def _create_stats_panel(self):
        """Create the statistics dashboard panel (right side)."""
        stats_frame = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=12)
        stats_frame.grid(row=0, column=1, sticky="nsew", pady=0)
        stats_frame.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkFrame(stats_frame, fg_color="transparent")
        header.pack(fill="x", padx=PADDING["medium"], pady=PADDING["small"])

        ctk.CTkLabel(
            header,
            text="Statistics",
            font=FONTS["heading"],
        ).pack(side="left")

        # All-time stats card
        self._create_stats_card(
            stats_frame,
            "All Time",
            [
                ("total_files", "Total Files"),
                ("successful", "Successful"),
                ("failed", "Failed"),
            ]
        )

        # Duration & Cost card
        self._create_stats_card(
            stats_frame,
            "Usage",
            [
                ("duration", "Total Duration"),
                ("cost", "Total Cost"),
                ("cost_per_hour", "Cost/Hour"),
            ]
        )

        # Current session card
        self._create_stats_card(
            stats_frame,
            "Current Session",
            [
                ("session_files", "Files"),
                ("session_duration", "Duration"),
                ("session_cost", "Cost"),
            ]
        )

        # Buttons
        buttons_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=PADDING["medium"], pady=PADDING["medium"])

        self.export_btn = ctk.CTkButton(
            buttons_frame,
            text="Export CSV",
            width=90,
            height=28,
            fg_color=COLORS["surface_elevated"],
            text_color=COLORS["text"],
            hover_color=COLORS["background_deep"],
            command=self._export_stats,
        )
        self.export_btn.pack(side="left", padx=(0, PADDING["small"]))

        self.reset_btn = ctk.CTkButton(
            buttons_frame,
            text="Reset",
            width=70,
            height=28,
            fg_color=COLORS["error"],
            text_color="#FFFFFF",
            hover_color="#B91C1C",
            command=self._reset_stats,
        )
        self.reset_btn.pack(side="left")

    def _create_stats_card(self, parent, title: str, metrics: list):
        """Create a statistics card with labeled values."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["background"], corner_radius=8)
        card.pack(fill="x", padx=PADDING["medium"], pady=(0, PADDING["small"]))

        # Card title
        ctk.CTkLabel(
            card,
            text=title,
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=PADDING["small"], pady=(PADDING["small"], 2))

        # Metrics
        for metric_id, label in metrics:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=PADDING["small"], pady=2)

            ctk.CTkLabel(
                row,
                text=label,
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
                anchor="w",
            ).pack(side="left")

            value_label = ctk.CTkLabel(
                row,
                text="-",
                font=FONTS["body_medium"],
                anchor="e",
            )
            value_label.pack(side="right")

            # Store reference for updates
            setattr(self, f"stat_{metric_id}", value_label)

        # Bottom padding
        ctk.CTkFrame(card, fg_color="transparent", height=4).pack()

    def _load_existing_events(self):
        """Load and display existing events from logger."""
        if self.logger.events:
            self.empty_label.pack_forget()
            for entry in self.logger.events:
                self._add_event_to_list(entry)

    def _on_new_event(self, entry: LogEntry):
        """Handle new event from logger."""
        # Hide empty state
        self.empty_label.pack_forget()

        # Add to list
        self._add_event_to_list(entry)

        # Auto-scroll to bottom
        self.event_list._parent_canvas.yview_moveto(1.0)

    def _add_event_to_list(self, entry: LogEntry):
        """Add an event entry to the list."""
        style = self.LEVEL_STYLES.get(entry.level, self.LEVEL_STYLES["info"])

        row = ctk.CTkFrame(self.event_list, fg_color="transparent")
        row.pack(fill="x", pady=1)

        # Timestamp
        ctk.CTkLabel(
            row,
            text=entry.timestamp,
            font=FONTS["mono"],
            text_color=COLORS["text_tertiary"],
            width=60,
        ).pack(side="left", padx=(PADDING["small"], 4))

        # Icon
        ctk.CTkLabel(
            row,
            text=style["icon"],
            font=FONTS["body"],
            text_color=style["color"],
            width=20,
        ).pack(side="left")

        # File name (if present)
        if entry.file_name:
            ctk.CTkLabel(
                row,
                text=entry.file_name,
                font=FONTS["body_medium"],
                text_color=COLORS["text"],
                anchor="w",
            ).pack(side="left", padx=(4, 0))

            ctk.CTkLabel(
                row,
                text="-",
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
            ).pack(side="left", padx=4)

        # Message
        ctk.CTkLabel(
            row,
            text=entry.message,
            font=FONTS["small"],
            text_color=style["color"] if entry.level in ("error", "warning") else COLORS["text_secondary"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

    def _refresh_stats(self):
        """Refresh all statistics displays."""
        stats = self.logger.all_time

        # All time stats
        self.stat_total_files.configure(text=str(stats.total_files))

        success_rate = self.logger.get_success_rate()
        self.stat_successful.configure(
            text=f"{stats.successful_files} ({success_rate}%)",
            text_color=COLORS["success"] if success_rate >= 90 else COLORS["text"],
        )

        fail_rate = 100 - success_rate if stats.total_files > 0 else 0
        self.stat_failed.configure(
            text=f"{stats.failed_files} ({fail_rate:.1f}%)",
            text_color=COLORS["error"] if stats.failed_files > 0 else COLORS["text"],
        )

        # Usage stats
        self.stat_duration.configure(
            text=self.logger.format_duration_long(stats.total_duration_seconds)
        )
        self.stat_cost.configure(text=f"${stats.total_cost_usd:.2f}")
        self.stat_cost_per_hour.configure(text=f"${self.logger.get_cost_per_hour():.2f}")

        # App session stats - cumulative since app started
        app_session = self.logger.app_session
        self.stat_session_files.configure(
            text=f"{app_session.successful}/{app_session.files_count}" if app_session.files_count > 0 else "-"
        )
        self.stat_session_duration.configure(
            text=self.logger.format_duration_long(app_session.duration_seconds) if app_session.duration_seconds > 0 else "-"
        )
        self.stat_session_cost.configure(
            text=f"${app_session.cost_usd:.2f}" if app_session.files_count > 0 else "-"
        )

    def _clear_logs(self):
        """Clear the event log."""
        if not self.logger.events:
            return

        if messagebox.askyesno("Clear Logs", "Clear all logged events?\n\nStatistics will be preserved."):
            self.logger.clear_events()

            # Clear UI
            for widget in self.event_list.winfo_children():
                widget.destroy()

            # Show empty state
            self.empty_label = ctk.CTkLabel(
                self.event_list,
                text="No events yet.\nStart a transcription to see activity here.",
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
            )
            self.empty_label.pack(pady=PADDING["large"])

    def _reset_stats(self):
        """Reset all statistics."""
        if messagebox.askyesno(
            "Reset Statistics",
            "Reset ALL statistics?\n\nThis will clear:\n- Total files count\n- Duration tracking\n- Cost tracking\n\nThis cannot be undone."
        ):
            self.logger.reset_stats()
            self._refresh_stats()

    def _export_stats(self):
        """Export statistics to CSV."""
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="redscribe_stats.csv",
        )

        if path:
            from pathlib import Path
            if self.logger.export_stats_csv(Path(path)):
                messagebox.showinfo("Export Complete", f"Statistics exported to:\n{path}")
            else:
                messagebox.showerror("Export Failed", "Could not save the file.")
