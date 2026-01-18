"""
File browser widget for selecting media files.
"""
import customtkinter as ctk
from typing import Optional, Callable
from pathlib import Path

from src.models.media_file import MediaFile, DirectoryNode
from src.gui.styles import FONTS, PADDING, COLORS, SPACING, DIMENSIONS, ICONS, get_file_icon


class FileTreeItem(ctk.CTkFrame):
    """Single item in the file tree (file or directory)."""

    def __init__(
        self,
        parent,
        item: MediaFile | DirectoryNode,
        indent_level: int = 0,
        on_select_change: Optional[Callable] = None,
        is_directory: bool = False,
    ):
        super().__init__(parent, fg_color="transparent")

        self.item = item
        self.indent_level = indent_level
        self.on_select_change = on_select_change
        self.is_directory = is_directory

        self._create_widgets()

    def _create_widgets(self):
        """Create item widgets."""
        # Indent spacer
        indent = self.indent_level * 20
        if indent > 0:
            spacer = ctk.CTkFrame(self, width=indent, height=1, fg_color="transparent")
            spacer.pack(side="left")

        # Checkbox
        self.checkbox_var = ctk.BooleanVar(value=self.item.selected)
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
        self.checkbox.pack(side="left")

        # Icon
        if self.is_directory:
            icon = ICONS["folder"]
        else:
            icon = get_file_icon(self.item.is_video)

        icon_label = ctk.CTkLabel(
            self,
            text=icon,
            font=FONTS["body"],
            width=24,
        )
        icon_label.pack(side="left")

        # Name
        name = self.item.name if self.is_directory else self.item.name
        name_label = ctk.CTkLabel(
            self,
            text=name,
            font=FONTS["body"],
            anchor="w",
        )
        name_label.pack(side="left", fill="x", expand=True, padx=(PADDING["small"], 0))

        # Size (for files only)
        if not self.is_directory:
            size_label = ctk.CTkLabel(
                self,
                text=self.item.size_formatted,
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
                width=80,
            )
            size_label.pack(side="right")

    def _on_checkbox_change(self):
        """Handle checkbox state change."""
        selected = self.checkbox_var.get()
        self.item.selected = selected

        # If this is a directory, propagate selection to all children
        if self.is_directory:
            self.item.select_children(selected)

        if self.on_select_change:
            self.on_select_change()

    def update_selection(self, selected: bool):
        """Update the selection state."""
        self.checkbox_var.set(selected)
        self.item.selected = selected


class FileBrowser(ctk.CTkFrame):
    """File browser widget for selecting media files."""

    def __init__(
        self,
        parent,
        on_selection_change: Optional[Callable[[list[MediaFile]], None]] = None,
    ):
        super().__init__(parent, fg_color=COLORS["surface"], corner_radius=DIMENSIONS["corner_radius_lg"], border_width=1, border_color=COLORS["border"])

        self.on_selection_change = on_selection_change
        self.root_node: Optional[DirectoryNode] = None
        self.file_items: list[FileTreeItem] = []

        self._create_widgets()

    def _create_widgets(self):
        """Create browser widgets."""
        # Configure grid with internal padding
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header frame
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=PADDING["medium"], pady=(PADDING["medium"], PADDING["small"]))
        header_frame.grid_columnconfigure(0, weight=1)

        header_label = ctk.CTkLabel(
            header_frame,
            text="Files to transcribe:",
            font=FONTS["heading"],
        )
        header_label.grid(row=0, column=0, sticky="w")

        # Select/Deselect buttons
        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")

        self.select_all_btn = ctk.CTkButton(
            btn_frame,
            text="Select All",
            width=90,
            height=DIMENSIONS["button_height_sm"],
            font=FONTS["small"],
            fg_color="transparent",
            hover_color=COLORS["surface_elevated"],
            text_color=COLORS["text_secondary"],
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._select_all,
        )
        self.select_all_btn.pack(side="left", padx=(0, SPACING["xs"]))

        self.deselect_all_btn = ctk.CTkButton(
            btn_frame,
            text="Clear All",
            width=80,
            height=DIMENSIONS["button_height_sm"],
            font=FONTS["small"],
            fg_color="transparent",
            hover_color=COLORS["surface_elevated"],
            text_color=COLORS["text_secondary"],
            corner_radius=DIMENSIONS["corner_radius"],
            command=self._deselect_all,
        )
        self.deselect_all_btn.pack(side="left")

        # Scrollable file list
        self.file_list_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=8,
        )
        self.file_list_frame.grid(row=1, column=0, sticky="nsew", padx=PADDING["medium"])
        self.file_list_frame.grid_columnconfigure(0, weight=1)

        # Empty state container - centered in the file list
        self.empty_container = ctk.CTkFrame(self.file_list_frame, fg_color="transparent")
        self.empty_container.pack(fill="x", pady=SPACING["2xl"])

        # Folder icon
        empty_icon = ctk.CTkLabel(
            self.empty_container,
            text="\U0001F4C2",  # Open folder emoji
            font=("Segoe UI Emoji", 48),
        )
        empty_icon.pack(pady=(SPACING["lg"], SPACING["sm"]))

        # Empty state label
        self.empty_label = ctk.CTkLabel(
            self.empty_container,
            text="Select a folder to begin",
            font=FONTS["heading"],
            text_color=COLORS["text_secondary"],
        )
        self.empty_label.pack(pady=(0, SPACING["xs"]))

        empty_sublabel = ctk.CTkLabel(
            self.empty_container,
            text="Audio and video files will appear here",
            font=FONTS["body"],
            text_color=COLORS["text_tertiary"],
        )
        empty_sublabel.pack(pady=(0, SPACING["lg"]))

        # Stats label
        self.stats_label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.stats_label.grid(row=2, column=0, sticky="w", padx=PADDING["medium"], pady=(PADDING["small"], PADDING["medium"]))

    def set_directory(self, node: DirectoryNode):
        """Set the directory to display."""
        self.root_node = node
        self._refresh_display()

    def clear(self):
        """Clear the file browser."""
        self.root_node = None
        self._clear_items()
        self.empty_container.pack(pady=SPACING["2xl"])
        self.stats_label.configure(text="")

    def _clear_items(self):
        """Clear all file items from display."""
        for item in self.file_items:
            item.destroy()
        self.file_items.clear()
        self.empty_container.pack_forget()

    def _refresh_display(self):
        """Refresh the file list display."""
        self._clear_items()

        if not self.root_node:
            self.empty_container.pack(pady=SPACING["2xl"])
            return

        if self.root_node.total_files == 0:
            self.empty_label.configure(text="No audio/video files found")
            self.empty_container.pack(pady=SPACING["2xl"])
            self._update_stats()
            return

        # Build tree view
        self._add_node_to_display(self.root_node, 0)
        self._update_stats()

    def _add_node_to_display(self, node: DirectoryNode, indent: int):
        """Recursively add directory node to display."""
        # Add directory item (except for root)
        if indent > 0:
            dir_item = FileTreeItem(
                self.file_list_frame,
                node,
                indent_level=indent - 1,
                on_select_change=self._on_item_select_change,
                is_directory=True,
            )
            dir_item.pack(fill="x", pady=1)
            self.file_items.append(dir_item)

        # Add files
        for media_file in node.files:
            file_item = FileTreeItem(
                self.file_list_frame,
                media_file,
                indent_level=indent,
                on_select_change=self._on_item_select_change,
                is_directory=False,
            )
            file_item.pack(fill="x", pady=1)
            self.file_items.append(file_item)

        # Add subdirectories
        for subdir in node.subdirs:
            self._add_node_to_display(subdir, indent + 1)

    def _on_item_select_change(self):
        """Handle item selection change."""
        self._update_stats()
        if self.on_selection_change and self.root_node:
            selected_files = self.root_node.get_selected_files()
            self.on_selection_change(selected_files)

    def _update_stats(self):
        """Update the stats label."""
        if not self.root_node:
            self.stats_label.configure(text="")
            return

        all_files = self.root_node.get_all_files()
        selected_files = self.root_node.get_selected_files()

        total_count = len(all_files)
        selected_count = len(selected_files)
        selected_size = sum(f.size_bytes for f in selected_files)

        # Format size
        size_str = self._format_size(selected_size)

        self.stats_label.configure(
            text=f"Selected: {selected_count} of {total_count} files ({size_str})"
        )

    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def _select_all(self):
        """Select all files."""
        if self.root_node:
            self.root_node.select_all(True)
            self._refresh_selection()

    def _deselect_all(self):
        """Deselect all files."""
        if self.root_node:
            self.root_node.select_all(False)
            self._refresh_selection()

    def _refresh_selection(self):
        """Refresh selection state of all items."""
        for item in self.file_items:
            item.update_selection(item.item.selected)
        self._on_item_select_change()

    def get_selected_files(self) -> list[MediaFile]:
        """Get list of selected files."""
        if not self.root_node:
            return []
        return self.root_node.get_selected_files()
